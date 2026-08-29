from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from culsma.frontend.resolver import resolve_program
from culsma.pipeline.analysis import build_compile_analysis
from culsma.pipeline.compile import compile_ast as _compile_ast
from culsma.driver.human import HumanDriver
from culsma.driver.robot import RobotDriver
from culsma.driver.stub import StubDriver
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.runtime.executor import run
from culsma.runtime.material.accounting import InputLot, MaterialAccounting, MaterialQuantity
from culsma.runtime.replay import replay_events
from culsma.runtime.state import init_state
from culsma.runtime.user_result import build_user_result
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate as _validate
from culsma.parser.parser import parse, parse_file


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures_parser"
LEGACY_FIXTURES = ROOT / "tests" / "fixtures_parser_legacy"


def compile_to_ir(ast):
    return _compile_ast(resolve_program(ast).prepared_program).ir


def validate(ir, **kwargs):
    kwargs.setdefault("analysis", build_compile_analysis(ir))
    return _validate(ir, **kwargs)


def _build_plan_from_source(source: str):
    compile_result = _compile_ast(resolve_program(parse(source)).prepared_program)
    ir = compile_result.ir
    sem = _validate(ir, analysis=compile_result.analysis)
    assert sem.ok, [d.to_dict() for d in sem.diagnostics]
    typ = typecheck(sem.ir, analysis=compile_result.analysis)
    assert typ.ok, [d.to_dict() for d in typ.diagnostics]
    return lower_ir_to_plan(typ.ir, analysis=compile_result.analysis)


def _runtime_state_with_source(plan, *, source: str = "A", volume_uL: float = 10.0):
    state = init_state(plan)
    state.artifacts["material_state"] = {
        "containers": {
            source: {"volume_uL": volume_uL, "mass_mg": volume_uL, "components": {}, "metadata": {}},
        }
    }
    return state


def test_content_attrs_record_literal_reaches_material_registry():
    plan = _build_plan_from_source(
        '''
protocol T {
  let source = tube(
    label = "Source",
    capacity = 100uL,
    load = [content(kind = formulation, type = buffer, code = "PBS1", attrs = { role: wash }):10uL]
  );
}
'''
    )
    result = run(plan=plan, driver=StubDriver())
    registry = result.state.artifacts["material_state"]["content_registry"]

    assert result.ok
    assert registry["PBS1"]["content_attrs"] == {"role": "wash"}


def test_runtime_happy_path_completes_all_steps():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube1 = tube(label = "Tube1", capacity = 100uL);
  tube1 << [A:5uL];
  with env(thermal = 37C, duration = 10min) { hold(sample = tube1); }
}
"""
    )
    result = run(plan=plan, driver=StubDriver(), state=_runtime_state_with_source(plan))

    assert result.ok
    statuses = set(result.state.step_status.values())
    assert statuses == {"completed"}

    kinds = [e.kind for e in result.events]
    assert kinds.count("STEP_STARTED") == 3
    assert kinds.count("STEP_COMPLETED") == 3


def test_runtime_script_entry_avoids_multi_root_material_state_reuse():
    source = """
include Wrapper;
protocol Wrapper {
  let mix = tube(
    label = "Mix",
    capacity = 100uL,
    load = [content(kind = formulation, type = master_mix, code = "MIX"):70uL]
  );
}
protocol Section {
  let mix = tube(
    label = "Mix",
    capacity = 100uL,
    load = [content(kind = formulation, type = master_mix, code = "MIX"):70uL]
  );
}
"""
    compiled = _compile_ast(resolve_program(parse(source)).prepared_program)
    sem = _validate(compiled.ir, analysis=compiled.analysis)
    assert sem.ok, [d.to_dict() for d in sem.diagnostics]
    typ = typecheck(sem.ir, analysis=compiled.analysis)
    assert typ.ok, [d.to_dict() for d in typ.diagnostics]

    entry_plan = lower_ir_to_plan(typ.ir, analysis=compiled.analysis)
    entry_result = run(plan=entry_plan, driver=StubDriver())

    assert [protocol.protocol_name for protocol in entry_plan.plans] == ["entry"]
    assert entry_result.ok, [d.to_dict() for d in entry_result.diagnostics]


@pytest.mark.parametrize(
    ("ctor", "binding", "overflow_volume"),
    [
        ('tube(label = "Tube1")', "tube1", 1501.0),
        ('well(label = "A1")', "well1", 201.0),
        ('container(label = "Generic1")', "container1", 1001.0),
    ],
)
def test_runtime_omitted_capacity_uses_family_default_overflow_guard(ctor: str, binding: str, overflow_volume: float):
    plan = _build_plan_from_source(
        f"""
protocol T {{
  let {binding} = {ctor};
  {binding} << [A:{overflow_volume}uL];
}}
"""
    )

    result = run(
        plan=plan,
        driver=StubDriver(),
        state=_runtime_state_with_source(plan, volume_uL=overflow_volume),
    )

    assert not result.ok
    assert "MAT_CONTAINER_OVERFLOW" in [d.code for d in result.diagnostics]


def test_runtime_legacy_dna_extraction_fixture_is_rejected_by_current_source_gate():
    ast = parse_file(LEGACY_FIXTURES / "dna_extraction.culs")
    with pytest.raises(ValueError, match="staining_method"):
        compile_to_ir(ast)


def test_runtime_marks_failed_and_skipped_on_driver_failure():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube1 = tube(label = "Tube1", capacity = 100uL);
  tube1 << [A:5uL];
  with env(thermal = 37C, duration = 10min) { hold(sample = tube1); }
}
"""
    )
    result = run(plan=plan, driver=StubDriver(fail_ops={"Mutation"}), state=_runtime_state_with_source(plan))

    status_by_op = {step.op: result.state.step_status[step.step_id] for p in plan.plans for step in p.steps}
    assert status_by_op["Mutation"] == "failed"
    assert status_by_op["env_hold"] == "skipped"

    codes = [d.code for d in result.diagnostics]
    assert "RT_DRIVER_ERROR" in codes
    assert "RT_ABORTED_AFTER_FAILURE" in codes


def test_runtime_non_fatal_driver_failure_does_not_abort_all_ready_steps():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube1 = tube(label = "Tube1", capacity = 100uL);
  tube1 << [A:5uL];
  with env(thermal = 37C, duration = 10min) { hold(sample = tube1); }
}
"""
    )
    result = run(plan=plan, driver=StubDriver(non_fatal_fail_ops={"Mutation"}), state=_runtime_state_with_source(plan))

    status_by_op = {step.op: result.state.step_status[step.step_id] for p in plan.plans for step in p.steps}
    assert status_by_op["Mutation"] == "failed"
    assert status_by_op["env_hold"] == "skipped"
    assert "RT_ABORTED_AFTER_FAILURE" not in [d.code for d in result.diagnostics]


def test_runtime_driver_requirement_check_allows_supported_constraint_step():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube1 = tube(label = "Tube1", capacity = 100uL);
  with constraint(gentle) {
    tube1 << [feed:5uL];
  }
}
"""
    )
    result = run(
        plan=plan,
        driver=StubDriver(supported_requirements={"gentle"}),
        state=_runtime_state_with_source(plan, source="feed"),
    )

    assert result.ok
    steps = [step for protocol in plan.plans for step in protocol.steps]
    mutation_step = next(step for step in steps if step.op == "Mutation")
    assert result.state.step_status[mutation_step.step_id] == "completed"
    codes = [d.code for d in result.diagnostics]
    assert "RT_DRIVER_REQUIREMENT_UNSUPPORTED" not in codes


def test_runtime_driver_requirement_check_fails_unsupported_constraint_step():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube1 = tube(label = "Tube1", capacity = 100uL);
  with constraint(gentle) {
    tube1 << [feed:5uL];
  }
}
"""
    )
    result = run(
        plan=plan,
        driver=StubDriver(supported_requirements={"aseptic"}),
        state=_runtime_state_with_source(plan, source="feed"),
    )

    assert not result.ok
    steps = [step for protocol in plan.plans for step in protocol.steps]
    alloc_step = next(step for step in steps if step.op == "AllocContainer")
    mutation_step = next(step for step in steps if step.op == "Mutation")
    assert result.state.step_status[alloc_step.step_id] == "completed"
    assert result.state.step_status[mutation_step.step_id] == "failed"
    codes = [d.code for d in result.diagnostics]
    assert "RT_DRIVER_REQUIREMENT_UNSUPPORTED" in codes
    assert "RT_ABORTED_AFTER_FAILURE" in codes

    material_state = result.state.artifacts["material_state"]
    tube1_id = material_state["bindings"]["tube1"]
    tube1 = material_state["containers"][tube1_id]
    assert tube1["volume_uL"] == 0.0


def test_runtime_driver_requirement_check_passes_customized_constraint_with_schema_option():
    plan = _build_plan_from_source(
        """
protocol T {
  let req_schema = data_schema(label = "Req", fields = [mode]);
  let tube1 = tube(label = "Tube1", capacity = 100uL);
  with constraint(customized, schema_ref = req_schema) {
    tube1 << [feed:5uL];
  }
}
"""
    )
    result = run(
        plan=plan,
        driver=StubDriver(
            supported_requirements={"customized"},
            supported_constraint_option_keys={"schema_ref"},
        ),
        state=_runtime_state_with_source(plan, source="feed"),
    )

    assert result.ok


def test_runtime_driver_requirement_check_fails_customized_constraint_when_option_unsupported():
    plan = _build_plan_from_source(
        """
protocol T {
  let req_schema = data_schema(label = "Req", fields = [mode]);
  let tube1 = tube(label = "Tube1", capacity = 100uL);
  with constraint(customized, schema_ref = req_schema) {
    tube1 << [feed:5uL];
  }
}
"""
    )
    result = run(
        plan=plan,
        driver=StubDriver(
            supported_requirements={"customized"},
            supported_constraint_option_keys=set(),
        ),
        state=_runtime_state_with_source(plan, source="feed"),
    )

    assert not result.ok
    assert "RT_DRIVER_REQUIREMENT_UNSUPPORTED" in [d.code for d in result.diagnostics]
    assert any(
        entry.get("unsupported_constraint_options") == ["schema_ref"]
        for entry in result.state.history
        if entry.get("status") == "failed"
    )


def test_runtime_driver_requirement_check_still_checks_options_when_requirements_are_unrestricted():
    plan = _build_plan_from_source(
        """
protocol T {
  let req_schema = data_schema(label = "Req", fields = [mode]);
  let tube1 = tube(label = "Tube1", capacity = 100uL);
  with constraint(customized, schema_ref = req_schema) {
    tube1 << [feed:5uL];
  }
}
"""
    )
    result = run(
        plan=plan,
        driver=StubDriver(
            supported_requirements=None,
            supported_constraint_option_keys=set(),
        ),
        state=_runtime_state_with_source(plan, source="feed"),
    )

    assert not result.ok
    assert "RT_DRIVER_REQUIREMENT_UNSUPPORTED" in [d.code for d in result.diagnostics]
    assert any(
        entry.get("unsupported_constraint_options") == ["schema_ref"]
        for entry in result.state.history
        if entry.get("status") == "failed"
    )


def test_human_and_robot_drivers_share_requirement_surface():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube1 = tube(label = "Tube1", capacity = 100uL);
  with constraint(gentle) {
    tube1 << [feed:5uL];
  }
}
"""
    )
    human_result = run(
        plan=plan,
        driver=HumanDriver(supported_requirements={"gentle"}),
        state=_runtime_state_with_source(plan, source="feed"),
    )
    robot_result = run(
        plan=plan,
        driver=RobotDriver(supported_requirements={"gentle"}),
        state=_runtime_state_with_source(plan, source="feed"),
    )

    assert human_result.ok
    assert robot_result.ok
    human_completed = [
        e
        for e in human_result.events
        if e.kind == "STEP_COMPLETED"
        and e.payload.get("driver_code") == "DRV_HUMAN_OK"
        and e.payload.get("driver_payload", {}).get("op") == "Mutation"
    ]
    robot_completed = [
        e
        for e in robot_result.events
        if e.kind == "STEP_COMPLETED"
        and e.payload.get("driver_code") == "DRV_ROBOT_OK"
        and e.payload.get("driver_payload", {}).get("op") == "Mutation"
    ]
    assert len(human_completed) == 1
    assert len(robot_completed) == 1
    assert human_completed[0].payload["driver_payload"]["driver_kind"] == "human"
    assert robot_completed[0].payload["driver_payload"]["driver_kind"] == "robot"


def test_runtime_continue_mode_keeps_non_failfast_behavior():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube1 = tube(label = "Tube1", capacity = 100uL);
  tube1 << [A:5uL];
  with env(thermal = 37C, duration = 10min) { hold(sample = tube1); }
}
"""
    )
    result = run(
        plan=plan,
        driver=StubDriver(fail_ops={"Mutation"}),
        on_error="continue",
        state=_runtime_state_with_source(plan),
    )

    status_by_op = {step.op: result.state.step_status[step.step_id] for p in plan.plans for step in p.steps}
    assert status_by_op["Mutation"] == "failed"
    assert status_by_op["env_hold"] == "skipped"

    codes = [d.code for d in result.diagnostics]
    assert "RT_DRIVER_ERROR" in codes
    assert "RT_UNSATISFIED_DEPENDENCY" in codes


def test_runtime_executes_explicit_hold_env_without_material_delta():
    plan = _build_plan_from_source(
        'protocol T { with env(thermal = 37C, duration = 10min) { hold(sample = Tube1); } }'
    )
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    steps = [step for protocol in plan.plans for step in protocol.steps]
    assert [step.op for step in steps] == ["env_hold"]
    completed = [e for e in result.events if e.kind == "STEP_COMPLETED"]
    assert len(completed) == 1
    assert completed[0].payload["gate"]["env"]["thermal"]["value"] == 37.0
    assert "material_delta" not in completed[0].payload


def test_runtime_keeps_empty_with_env_compatibility_path():
    plan = _build_plan_from_source(
        'protocol T { with env(thermal = 37C, duration = 10min) { hold(sample = Tube1); } }'
    )
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    steps = [step for protocol in plan.plans for step in protocol.steps]
    assert [step.op for step in steps] == ["env_hold"]
    completed = [e for e in result.events if e.kind == "STEP_COMPLETED"]
    assert len(completed) == 1
    assert completed[0].payload["gate"]["env"]["thermal"]["value"] == 37.0
    assert "material_delta" not in completed[0].payload


def test_runtime_statement_pcr_executes_expanded_env_hold_path():
    plan = _build_plan_from_source(
        'protocol T { PCR(sample = Tube1, primers = "Panel", cycles = 2, annealing_temp = 60C); }'
    )
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    steps = [step for protocol in plan.plans for step in protocol.steps]
    assert [step.op for step in steps] == ["env_hold", "env_hold", "env_hold", "env_hold", "env_hold", "env_hold"]


def test_runtime_statement_lyse_executes_expanded_primitive_path():
    plan = _build_plan_from_source(
        'protocol T { let lysed = Lyse(sample = sample_tube, buffer = lysis_input, duration = 10min, temp = 4C); let sep_group = sep(sample = lysed, program = centrifuge_program(drive = 12000g)); }'
    )
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    ops = [step.op for protocol in plan.plans for step in protocol.steps]
    assert "Lyse" not in ops
    assert ops[:3] == ["Mutation", "sep", "Mutation"]
    assert ops[-1] == "sep"


def test_runtime_local_assignment_updates_conditions_and_quantified_mutation_args():
    plan = _build_plan_from_source(
        """
protocol T {
  let reactor = tube(label = "Reactor", capacity = 1000uL);
  let feed = tube(label = "Feed", capacity = 1000uL, load = [buffer(code = "MED", type = "media"):400uL]);
  let total_added = 0uL;
  let count = 0;

  repeat tick in schedule(start = 1, end = 3, step = 1) {
    count = count + 1;
    total_added = total_added + 50uL;
    reactor << [feed:total_added];
    if count >= 2 {
      break;
    }
  }
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    local_bindings = result.state.artifacts.get("local_bindings", {})
    assert local_bindings["count"] == 2
    assert local_bindings["total_added"]["kind"] == "IRQuantity"
    assert local_bindings["total_added"]["value"] == 100.0
    assert local_bindings["total_added"]["unit"] == "uL"

    material_state = result.state.artifacts["material_state"]
    reactor_id = material_state["bindings"]["reactor"]
    reactor = material_state["containers"][reactor_id]
    assert reactor["volume_uL"] == 150.0
    assert result.user_result is not None
    assert result.user_result["execution"]["completed_steps"] == sum(
        1 for status in result.state.step_status.values() if status == "completed"
    )
    assert result.user_result["materials"]["has_material_state"] is True
    assert result.user_result["process_summary"]["mutation_steps"] == 2


def test_runtime_mutable_local_preserves_initial_value_when_runtime_branch_is_skipped():
    plan = _build_plan_from_source(
        """
protocol T {
  let readout = data_ref(kind = qc);
  readout.result.ok = true;
  let controls_pass = true;
  let decision = data_ref(kind = qc_decision);

  if readout.result.ok == false {
    controls_pass = false;
  }
  if controls_pass == true {
    decision.result.accepted = true;
  }
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    local_bindings = result.state.artifacts["local_bindings"]
    assert local_bindings["controls_pass"] is True
    assert local_bindings["decision"]["result"]["accepted"] is True


def test_runtime_mutable_local_branch_assignment_overrides_initial_value():
    plan = _build_plan_from_source(
        """
protocol T {
  let readout = data_ref(kind = qc);
  readout.result.ok = false;
  let controls_pass = true;
  let decision = data_ref(kind = qc_decision);

  if readout.result.ok == false {
    controls_pass = false;
  }
  if controls_pass == true {
    decision.result.accepted = true;
  }
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    local_bindings = result.state.artifacts["local_bindings"]
    assert local_bindings["controls_pass"] is False
    assert "accepted" not in local_bindings["decision"]["result"]


def test_runtime_issue_61_readout_driven_boolean_accumulator_controls_final_condition():
    plan = _build_plan_from_source(
        """
protocol T {
  let wt_readout = data_ref(kind = qc);
  wt_readout.result.control_qc_pass = true;
  let nt_readout = data_ref(kind = qc);
  nt_readout.result.control_qc_pass = true;
  let candidate_readout = data_ref(kind = qc);
  candidate_readout.result.qc_pass = true;
  let candidate = data_ref(kind = candidate);
  let validated_output = data_group_ref(kind = validated_output);
  let controls_pass = true;

  if wt_readout.result.control_qc_pass == false {
    controls_pass = false;
  }

  if nt_readout.result.control_qc_pass == false {
    controls_pass = false;
  }

  if controls_pass == true and candidate_readout.result.qc_pass == true {
    validated_output.items.append(candidate);
  }
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    local_bindings = result.state.artifacts["local_bindings"]
    assert local_bindings["controls_pass"] is True
    assert [item["data_kind"] for item in local_bindings["validated_output"]["items"]] == ["candidate"]


def test_runtime_nested_runtime_branches_materialize_multiple_assigned_locals():
    plan = _build_plan_from_source(
        """
protocol T {
  let first_readout = data_ref(kind = qc);
  first_readout.result.ok = true;
  let second_readout = data_ref(kind = qc);
  second_readout.result.ok = true;
  let decision = data_ref(kind = qc_decision);
  let controls_pass = true;
  let manual_review = false;
  let score = 0;

  if first_readout.result.ok == true {
    if second_readout.result.ok == true {
      controls_pass = false;
      manual_review = true;
      score = score + 2;
    }
  }

  if controls_pass == false and manual_review == true and score == 2 {
    decision.result.needs_review = true;
  }
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    local_bindings = result.state.artifacts["local_bindings"]
    assert local_bindings["controls_pass"] is False
    assert local_bindings["manual_review"] is True
    assert local_bindings["score"] == 2
    assert local_bindings["decision"]["result"]["needs_review"] is True


def test_runtime_dynamic_repeat_accumulator_uses_previous_iteration_value():
    plan = _build_plan_from_source(
        """
protocol T {
  let cells = tube(label = "Cells", capacity = 500uL);
  let events = stream(sample = cells, unit = single_cell);
  let count = 0;

  repeat cell in events {
    count = count + 1;
  }

  let summary = data_ref(kind = count_summary);
  if count == 2 {
    summary.result.complete = true;
  }
}
"""
    )
    state = init_state(plan)
    state.artifacts["stream_units"] = {"events": ["cell_0", "cell_1"]}

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert result.ok
    local_bindings = result.state.artifacts["local_bindings"]
    assert local_bindings["count"] == 2
    assert local_bindings["summary"]["result"]["complete"] is True


def test_runtime_dynamic_repeat_inner_condition_reads_mutable_local_at_runtime():
    plan = _build_plan_from_source(
        """
protocol T {
  let cells = tube(label = "Cells", capacity = 500uL);
  let events = stream(sample = cells, unit = single_cell);
  let count = 0;
  let reads = data_group_ref(kind = sequence_read);

  repeat cell in events {
    count = count + 1;
    if count == 2 {
      let read = data_ref(kind = sequence_read, subject_ref = cell);
      reads.items.append(read);
    }
  }
}
"""
    )
    state = init_state(plan)
    state.artifacts["stream_units"] = {"events": ["cell_0", "cell_1"]}

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert result.ok
    local_bindings = result.state.artifacts["local_bindings"]
    assert local_bindings["count"] == 2
    assert [item["subject_ref"]["id"] for item in local_bindings["reads"]["items"]] == ["cell_1"]


def test_runtime_repeat_nested_condition_preserves_multiple_mutable_locals():
    plan = _build_plan_from_source(
        """
protocol T {
  let cells = tube(label = "Cells", capacity = 500uL);
  let events = stream(sample = cells, unit = single_cell);
  let count = 0;
  let total = 0;
  let flagged = false;
  let summary = data_ref(kind = repeat_summary);

  repeat cell in events {
    count = count + 1;
    total = total + 1;
    if count == 2 {
      total = total + 10;
      flagged = true;
    }
  }

  if flagged == true and count == 2 and total == 12 {
    summary.result.complete = true;
  }
}
"""
    )
    state = init_state(plan)
    state.artifacts["stream_units"] = {"events": ["cell_0", "cell_1"]}

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    local_bindings = result.state.artifacts["local_bindings"]
    assert local_bindings["count"] == 2
    assert local_bindings["total"] == 12
    assert local_bindings["flagged"] is True
    assert local_bindings["summary"]["result"]["complete"] is True


def test_runtime_user_result_includes_container_and_instrument_usage_summary():
    plan = _build_plan_from_source(
        """
protocol T {
  let reactor = tube(label = "Reactor", capacity = 1000uL);
  let feed = tube(label = "Feed", capacity = 1000uL, load = [buffer(code = "MED", type = "media"):400uL]);
  reactor << [feed:50uL];
  img(sample = reactor, quantity = fluorescence);
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    assert result.user_result is not None

    containers = result.user_result["resource_summary"]["containers"]
    assert containers["allocated_count"] == 2
    assert containers["touched_count"] == 2
    assert {"kind": "tube", "count": 2} in containers["container_kinds"]
    assert containers["touched_names"] == ["Feed", "Reactor"]

    instruments = result.user_result["resource_summary"]["instruments"]
    assert instruments["tools"] == []
    assert instruments["devices"] == []


def test_runtime_user_result_tracks_internal_constructor_stock_consumption():
    plan = _build_plan_from_source(
        """
protocol T {
  let reactor = tube(label = "Reactor", capacity = 1000uL);
  let feed = tube(label = "Feed", capacity = 1000uL, load = [buffer(code = "MED", type = "media"):400uL]);
  reactor << [feed:50uL];
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    assert result.user_result is not None
    reagent_consumption = result.user_result["materials"]["reagent_consumption"]
    assert reagent_consumption == [
        {
            "name": "Feed",
            "roles": ["source"],
            "consumed_uL": 50.0,
            "consumed_mL": 0.05,
            "consumed_mg": None,
        }
    ]


def test_runtime_user_result_omits_unused_internal_constructor_stock_from_consumption():
    plan = _build_plan_from_source(
        """
protocol T {
  let reactor = tube(label = "Reactor", capacity = 1000uL);
  let feed = tube(label = "Feed", capacity = 1000uL, load = [buffer(code = "MED", type = "media"):400uL]);
  let spare = tube(label = "Spare", capacity = 1000uL, load = [buffer(code = "BUF", type = "wash_buffer"):200uL]);
  reactor << [feed:50uL];
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    assert result.user_result is not None
    reagent_consumption = result.user_result["materials"]["reagent_consumption"]
    names = [row["name"] for row in reagent_consumption]
    assert "Feed" in names
    assert "Spare" not in names


def test_runtime_user_result_combines_initial_and_runtime_loaded_inputs():
    plan = _build_plan_from_source(
        """
protocol T {
  let reactor = tube(label = "Reactor", capacity = 1000uL);
  let feed = tube(label = "Feed", capacity = 1000uL, load = [buffer(code = "MED", type = "media"):100uL]);
  reactor << [feed:25uL];
}
"""
    )
    state = init_state(plan)
    state.artifacts["material_state"] = {
        "containers": {
            "external": {
                "volume_uL": 40.0,
                "mass_mg": 0.0,
                "components": {},
                "metadata": {"label": "External"},
            }
        }
    }

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    assert result.user_result is not None
    materials = result.user_result["materials"]
    assert {row["name"] for row in materials["input_inventory"]} == {"External", "Feed"}
    assert materials["reagent_consumption"] == [
        {
            "name": "Feed",
            "roles": ["source"],
            "consumed_uL": 25.0,
            "consumed_mL": 0.025,
            "consumed_mg": None,
        }
    ]


def test_runtime_report_exposes_complete_end_to_end_contract():
    plan = _build_plan_from_source(
        """
protocol T {
  let reactor = tube(label = "Reactor", capacity = 1000uL);
  let feed = tube(
    label = "Feed",
    capacity = 1000uL,
    load = [buffer(code = "MED", type = "media"):100uL]
  );
  reactor << [feed:25uL];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    assert result.user_result == {
        "schema": "lab_report_v1",
        "execution": {
            "ok": True,
            "diagnostic_count": 0,
            "total_steps": 5,
            "completed_steps": 5,
            "failed_steps": 0,
            "skipped_steps": 0,
        },
        "headline": "Experiment completed successfully with no runtime errors.",
        "materials": {
            "has_material_state": True,
            "input_inventory": [
                {
                    "name": "Feed",
                    "initial_uL": 100.0,
                    "initial_mL": 0.1,
                    "initial_mg": 0.0,
                }
            ],
            "final_products": [
                {
                    "name": "Reactor",
                    "volume_uL": 25.0,
                    "volume_mL": 0.025,
                    "mass_mg": 25.0,
                    "primary_component": "MED",
                }
            ],
            "intermediate_materials": [],
            "reagent_consumption": [
                {
                    "name": "Feed",
                    "roles": ["source"],
                    "consumed_uL": 25.0,
                    "consumed_mL": 0.025,
                    "consumed_mg": None,
                }
            ],
        },
        "qc_results": [],
        "resource_summary": {
            "containers": {
                "allocated_count": 2,
                "touched_count": 2,
                "container_kinds": [{"kind": "tube", "count": 2}],
                "touched_names": ["Feed", "Reactor"],
            },
            "instruments": {"tools": [], "devices": []},
        },
        "process_summary": {
            "mutation_steps": 1,
            "separation_steps": 0,
            "environment_steps": 0,
            "readout_steps": 0,
        },
        "alerts": [],
        "external_inventory": {
            "schema": "culsma_inventory_reconciliation_v1",
            "checked": False,
            "sufficient": None,
            "reason": "inventory_not_supplied",
            "items": [],
            "shortages": [],
        },
    }


def test_runtime_user_result_reagent_consumption_is_not_display_capped():
    feeds = "\n".join(
        f'  let feed_{idx} = tube(\n'
        f'    label = "Feed {idx:02d}",\n'
        f"    capacity = 100uL,\n"
        f'    load = [buffer(code = "B{idx:02d}", type = "buffer"):10uL]\n'
        f"  );"
        for idx in range(25)
    )
    source_refs = ", ".join(f"feed_{idx}:1uL" for idx in range(25))
    plan = _build_plan_from_source(
        f"""
protocol T {{
  let reactor = tube(label = "Reactor", capacity = 1000uL);
{feeds}
  reactor << [{source_refs}];
}}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    assert result.user_result is not None
    materials = result.user_result["materials"]
    assert len(materials["reagent_consumption"]) == 25
    assert {row["name"] for row in materials["reagent_consumption"]} == {
        f"Feed {idx:02d}" for idx in range(25)
    }


def test_runtime_user_result_attributes_fraction_usage_to_original_input():
    plan = _build_plan_from_source(
        """
protocol T {
  let sample = tube(label = "Sample", capacity = 1000uL, load = [content(kind = "biosample", code = "S", type = "dna_stock"):100uL]);
  let out = tube(label = "Out", capacity = 1000uL);
  let parts = sep(sample = sample, program = centrifuge_program(drive = 1000g));
  out << [parts[0]];
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    assert result.user_result is not None
    materials = result.user_result["materials"]
    assert materials["reagent_consumption"] == [
        {
            "name": "Sample",
            "roles": ["sample"],
            "consumed_uL": 100.0,
            "consumed_mL": 0.1,
            "consumed_mg": None,
        }
    ]


def test_runtime_user_result_models_mass_only_accounting_and_wire_contract():
    state = SimpleNamespace(
        step_status={},
        artifacts={
            "material_state": {
                "containers": {
                    "stock": {
                        "volume_uL": 0.0,
                        "mass_mg": 3.0,
                        "components": {"Powder": 3.0},
                        "metadata": {"label": "Powder"},
                    }
                },
                "bindings": {},
                "content_registry": {},
                "measurements": [],
            }
        },
    )
    accounting = MaterialAccounting()
    accounting.register_input_lot(
        InputLot(
            lot_id="load:stock",
            container_id="stock",
            name="Powder",
            origin="load_content",
            initial=MaterialQuantity(mass_mg=5.0),
        )
    )
    accounting.record_movement(
        step_id="move",
        source="stock",
        destination="reactor",
        quantity=MaterialQuantity(mass_mg=2.0),
    )

    report = build_user_result(
        ok=True,
        diagnostics=[],
        state=state,
        events=[],
        plan=SimpleNamespace(plans=[]),
        initial_material_state={"containers": {}},
        material_accounting=accounting,
    )

    assert set(report) == {
        "schema",
        "execution",
        "headline",
        "materials",
        "qc_results",
        "resource_summary",
        "process_summary",
        "alerts",
        "external_inventory",
    }
    assert set(report["materials"]) == {
        "has_material_state",
        "input_inventory",
        "final_products",
        "intermediate_materials",
        "reagent_consumption",
    }
    assert report["materials"]["reagent_consumption"] == [
        {
            "name": "Powder",
            "roles": [],
            "consumed_uL": None,
            "consumed_mL": None,
            "consumed_mg": 2.0,
        }
    ]


def test_runtime_user_result_keeps_complete_report_lists():
    names = [f"Product {idx:02d}" for idx in range(12)]
    steps = [
        PlanStep(
            step_id=f"s{idx}",
            op="Mutation",
            args={"target": {"kind": "IRIdentifier", "name": name}, "sources": []},
        )
        for idx, name in enumerate(names)
    ]
    plan = PlanProgram(
        plans=[ProtocolPlan(protocol_id="p", protocol_name="P", steps=steps)]
    )
    state = SimpleNamespace(
        step_status={step.step_id: "completed" for step in steps},
        artifacts={
            "material_state": {
                "containers": {
                    name: {
                        "volume_uL": float(idx + 1),
                        "mass_mg": 0.0,
                        "components": {},
                        "metadata": {"label": name},
                    }
                    for idx, name in enumerate(names)
                },
                "bindings": {},
                "content_registry": {},
                "measurements": [],
            }
        },
    )
    diagnostics = [
        SimpleNamespace(code=f"WARN_{idx}", message=f"warning {idx}")
        for idx in range(7)
    ]

    report = build_user_result(
        ok=True,
        diagnostics=diagnostics,
        state=state,
        events=[],
        plan=plan,
        initial_material_state={"containers": {}},
        material_accounting=MaterialAccounting(),
    )

    assert len(report["materials"]["final_products"]) == 12
    assert len(report["resource_summary"]["containers"]["touched_names"]) == 12
    assert len(report["alerts"]) == 7


def test_runtime_user_result_keeps_same_consumable_summary_for_data_and_container_returns():
    data_ref_plan = _build_plan_from_source(
        """
protocol T() returns (qc) {
  let reactor = tube(label = "Reactor", capacity = 1000uL);
  let feed = tube(label = "Feed", capacity = 1000uL, load = [buffer(code = "MED", type = "media"):400uL]);
  reactor << [feed:50uL];
  let qc = img(sample = reactor, quantity = fluorescence);
  return qc;
}
"""
    )
    container_ref_plan = _build_plan_from_source(
        """
protocol T() returns (reactor) {
  let reactor = tube(label = "Reactor", capacity = 1000uL);
  let feed = tube(label = "Feed", capacity = 1000uL, load = [buffer(code = "MED", type = "media"):400uL]);
  reactor << [feed:50uL];
  return reactor;
}
"""
    )

    data_result = run(plan=data_ref_plan, driver=StubDriver())
    container_result = run(plan=container_ref_plan, driver=StubDriver())

    assert data_result.ok
    assert container_result.ok
    assert data_result.user_result is not None
    assert container_result.user_result is not None
    assert (
        data_result.user_result["materials"]["reagent_consumption"]
        == container_result.user_result["materials"]["reagent_consumption"]
    )


def test_runtime_user_result_includes_derived_state_for_final_product_container():
    plan = _build_plan_from_source(
        """
protocol T {
  let stock = tube(label = "Stock", capacity = 500uL, load = [content(kind = "biosample", code = "DNA001", type = "dna_stock"):200uL]);
  let water = tube(label = "Water", capacity = 1000uL, load = [buffer(code = "H2O", type = "diluent"):500uL]);
  let working = tube(label = "Working", capacity = 500uL);
  working << [stock:20uL];
  working << [water:80uL];
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    assert result.user_result is not None
    final_products = result.user_result["materials"]["final_products"]
    diluted = next(item for item in final_products if item["name"] == "Working")
    assert diluted == {
        "name": "Working",
        "volume_uL": 100.0,
        "volume_mL": 0.1,
        "mass_mg": 100.0,
        "primary_component": "DNA001",
    }


def test_runtime_user_result_normalizes_working_container_roles_from_source_bindings():
    plan = _build_plan_from_source(
        """
protocol T {
  let stock = tube(label = "Stock", capacity = 500uL, load = [content(kind = "biosample", code = "DNA001", type = "dna_stock"):200uL]);
  let water = tube(label = "Water", capacity = 1000uL, load = [buffer(code = "H2O", type = "diluent"):500uL]);
  let working = tube(label = "Working", capacity = 500uL);
  working << [stock:20uL];
  working << [water:80uL];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    assert result.user_result is not None
    final_products = result.user_result["materials"]["final_products"]
    diluted = next(item for item in final_products if item["name"] == "Working")
    assert diluted == {
        "name": "Working",
        "volume_uL": 100.0,
        "volume_mL": 0.1,
        "mass_mg": 100.0,
        "primary_component": "DNA001",
    }


def test_runtime_continuous_schedule_flag_break_skips_remainder_of_outer_window():
    plan = _build_plan_from_source(
        """
protocol T {
  let reactor = tube(label = "Reactor", capacity = 1000uL);
  let inside = tube(label = "Inside", capacity = 1000uL);
  let outside = tube(label = "Outside", capacity = 1000uL);
  let stop_perf = false;

  repeat perf in schedule(start = 0h, duration = 3h, mode = continuous) {
    repeat t in schedule(start = 1h, step = 1h) {
      let obs = phy(sample = reactor, quantity = temperature);
      if obs.result.temperature >= 37 {
        stop_perf = true;
        break;
      }
    }

    if stop_perf {
      break;
    }

    img(sample = inside, quantity = fluorescence);
  }

  img(sample = outside, quantity = fluorescence);
}
"""
    )
    result = run(
        plan=plan,
        driver=StubDriver(
            op_payloads={
                "phy": {"result": {"temperature": 40}},
            }
        ),
    )

    assert result.ok
    steps = [step for protocol in plan.plans for step in protocol.steps]
    inside_steps = [step for step in steps if step.op == "img" and step.args.get("sample", {}).get("name") == "inside"]
    outside_steps = [step for step in steps if step.op == "img" and step.args.get("sample", {}).get("name") == "outside"]
    assert len(inside_steps) == 1
    assert len(outside_steps) == 1
    assert result.state.step_status[inside_steps[0].step_id] == "skipped"
    assert result.state.step_status[outside_steps[0].step_id] == "completed"
    assert result.state.artifacts["local_bindings"]["stop_perf"] is True


def test_runtime_group_series_mutation_applies_ordered_amounts():
    plan = _build_plan_from_source(
        """
protocol T {
  let t1 = tube(label = "T1", capacity = 500uL);
  let t2 = tube(label = "T2", capacity = 500uL);
  let t3 = tube(label = "T3", capacity = 500uL);
  let drug = tube(label = "Drug", capacity = 500uL, load = [buffer(code = "D", type = "drug_stock"):200uL]);
  let aliquots = group([t1, t2, t3]);
  aliquots << [series(drug, [5uL, 10uL, 20uL])];
}
"""
    )
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    containers = result.state.artifacts["material_state"]["containers"]
    assert containers["Drug"]["volume_uL"] == 165.0
    assert containers["T1"]["volume_uL"] == 5.0
    assert containers["T2"]["volume_uL"] == 10.0
    assert containers["T3"]["volume_uL"] == 20.0


def test_runtime_statement_extract_dna_precipitation_executes_expanded_primitive_path():
    plan = _build_plan_from_source(
        """
protocol T {
  let lysate = tube(label = "Lysate", capacity = 2000uL, load = [content(kind = "biosample", code = "DNA_EXT", type = "dna_lysate"):800uL]);
  let precip_in = tube(label = "Precip", capacity = 1000uL, load = [reagent(code = "IPA", type = "precipitation_reagent"):800uL]);
  let wash1 = tube(label = "Wash1", capacity = 1000uL, load = [buffer(code = "W1", type = "ethanol_wash_buffer"):500uL]);
  let wash2 = tube(label = "Wash2", capacity = 1000uL, load = [buffer(code = "W2", type = "ethanol_wash_buffer"):500uL]);
  let dissolve_in = tube(label = "Dissolve", capacity = 500uL, load = [buffer(code = "TE", type = "resuspension_buffer"):120uL]);
  let dna_out = tube(label = "DNAOut", capacity = 1000uL);
  ExtractDNAPrecipitation(sample = lysate, precip_buffer = precip_in, wash_inputs = [wash1, wash2], dissolve_buffer = dissolve_in, output = dna_out, cleanup_temp = 25C, cleanup_duration = 3min);
}
"""
    )
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    ops = [step.op for protocol in plan.plans for step in protocol.steps]
    assert "ExtractDNA" not in ops
    assert "sep" in ops


def test_runtime_statement_extract_dna_column_executes_expanded_primitive_path():
    plan = _build_plan_from_source(
        """
protocol T {
  let lysate = tube(label = "Lysate", capacity = 2000uL, load = [content(kind = "biosample", code = "DNA_COL", type = "dna_lysate", attrs = { filter_retains: true }):600uL]);
  let bind_in = tube(label = "Bind", capacity = 1000uL, load = [buffer(code = "BIND", type = "binding_buffer"):600uL]);
  let wash1 = tube(label = "Wash1", capacity = 1000uL, load = [buffer(code = "W1", type = "column_wash_buffer"):500uL]);
  let wash2 = tube(label = "Wash2", capacity = 1000uL, load = [buffer(code = "W2", type = "column_wash_buffer"):500uL]);
  let elute_in = tube(label = "Elute", capacity = 500uL, load = [buffer(code = "EB", type = "elution_buffer"):80uL]);
  let spin_col = tube(label = "Column", capacity = 2000uL);
  let waste_tube = tube(label = "Waste", capacity = 5000uL);
  let dna_out = tube(label = "DNAOut", capacity = 1000uL);
  ExtractDNAColumn(sample = lysate, bind_buffer = bind_in, wash_inputs = [wash1, wash2], elution_buffer = elute_in, column = spin_col, waste = waste_tube, output = dna_out, cleanup_temp = 25C, cleanup_duration = 2min);
}
"""
    )
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    ops = [step.op for protocol in plan.plans for step in protocol.steps]
    assert "ExtractDNA" not in ops


def test_runtime_sep_partition_keeps_dna_cleanup_product_from_wash_reagents():
    plan = _build_plan_from_source(
        """
protocol T() returns (plasmid_dna) {
  let aqueous = tube(label = "Aqueous", capacity = 2500uL, load = [
    content(kind = "biosample", code = "DNA_EXT", type = "dna_lysate"):100uL,
    buffer(code = "AQ", type = "buffer"):400uL
  ]);
  let phenol_chloroform = tube(label = "Phenol Chloroform", capacity = 1000uL, load = [
    reagent(code = "PCI", type = "cleanup_reagent"):450uL
  ]);
  let ethanol_abs = tube(label = "Absolute Ethanol", capacity = 1000uL, load = [
    reagent(code = "ETOH_ABS", type = "precipitation_reagent"):900uL
  ]);
  let ethanol_70 = tube(label = "70 Percent Ethanol", capacity = 1500uL, load = [
    buffer(code = "ETOH70", type = "ethanol_wash_buffer"):1000uL
  ]);
  let te = tube(label = "TE", capacity = 200uL, load = [
    buffer(code = "TE", type = "te_buffer"):50uL
  ]);
  let aqueous_phase = tube(label = "Aqueous Phase", capacity = 2500uL);
  let dna_pellet = tube(label = "DNA Pellet", capacity = 2500uL);
  let washed_pellet = tube(label = "Washed DNA Pellet", capacity = 2500uL);
  let plasmid_dna = tube(label = "Plasmid DNA", capacity = 200uL);

  aqueous << [phenol_chloroform:450uL];
  let extraction_group = sep(
    sample = aqueous,
    program = phase_partition_program(solvent = "phenol_chloroform"),
    component_fates = {
      DNA_EXT: { target_phase: 100%, other_phase: 0% },
      AQ: { target_phase: 100%, other_phase: 0% },
      PCI: { target_phase: 0%, other_phase: 100% }
    }
  );
  aqueous_phase << [extraction_group[0]];

  aqueous_phase << [ethanol_abs:900uL];
  let precip_group = sep(
    sample = aqueous_phase,
    program = precipitation_program(reagent = "ethanol"),
    component_fates = {
      DNA_EXT: { precipitate: 100%, supernatant: 0% }
    }
  );
  dna_pellet << [precip_group[0]];

  dna_pellet << [ethanol_70:1000uL];
  let wash_group = sep(
    sample = dna_pellet,
    program = centrifuge_program(drive = 12000g)
  );
  washed_pellet << [wash_group[1]];

  washed_pellet << [te:50uL];
  plasmid_dna << [washed_pellet:50uL];
  return plasmid_dna;
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    returned = result.state.artifacts["protocol_outputs"]["T"]["value"]
    assert returned == {
        "kind": "container_ref",
        "id": "Plasmid DNA",
        "volume_uL": 50,
        "mass_mg": 50,
        "container_kind": "tube",
        "label": "Plasmid DNA",
    }
    components = result.state.artifacts["material_state"]["containers"]["Plasmid DNA"]["components"]
    assert {key: round(float(value), 6) for key, value in sorted(components.items())} == {
        "AQ": 0.0,
        "DNA_EXT": 33.333333,
        "ETOH70": 0.0,
        "ETOH_ABS": 0.0,
        "PCI": 0.0,
        "TE": 16.666667,
    }
    final_products = result.user_result["materials"]["final_products"]
    plasmid = next(item for item in final_products if item["name"] == "Plasmid DNA")
    assert plasmid == {
        "name": "Plasmid DNA",
        "volume_uL": 50.0,
        "volume_mL": 0.05,
        "mass_mg": 50.0,
        "primary_component": "DNA_EXT",
    }


def test_runtime_phase_partition_without_facts_is_unresolved():
    plan = _build_plan_from_source(
        """
protocol T {
  let sample = tube(label = "Sample", capacity = 1000uL, load = [
    content(kind = "chemical", code = "CUSTOM", type = "custom_local_mix"):100uL
  ]);
  let parts = sep(
    sample = sample,
    program = phase_partition_program(solvent = "unknown")
  );
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert "MAT_SCIENTIFIC_MODEL_UNRESOLVED" in [
        diagnostic.code for diagnostic in result.diagnostics
    ]


def test_runtime_source_partition_magnetic_removes_flowthrough_without_sep_group():
    plan = _build_plan_from_source(
        """
protocol T {
  let bead_tube = tube(label = "BeadTube", capacity = 500uL, load = [
    content(kind = "particulate", code = "BEADS", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "WASH", type = "buffer"):180uL
  ]);
  let waste = tube(label = "Waste", capacity = 500uL);
  let mag_sep = magnetic_program(duration = 5min);

  with env(field = magnetic_rack) {
    waste << [bead_tube.partition(mag_sep)[1]];
  }
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    material_state = result.state.artifacts["material_state"]
    assert "indexed_bindings" not in material_state or "mag_sep" not in material_state["indexed_bindings"]
    bead_components = material_state["containers"]["BeadTube"]["components"]
    waste_components = material_state["containers"]["Waste"]["components"]
    assert round(float(bead_components["BEADS"]), 6) == 20.0
    assert round(float(bead_components["WASH"]), 6) == 0.0
    assert round(float(waste_components["BEADS"]), 6) == 0.0
    assert round(float(waste_components["WASH"]), 6) == 180.0


def test_runtime_standalone_sep_contents_index_transfers_flowthrough():
    plan = _build_plan_from_source(
        """
protocol T {
  let bead_tube = tube(label = "BeadTube", capacity = 500uL, load = [
    content(kind = "particulate", code = "BEADS", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "WASH", type = "buffer"):180uL
  ]);
  let waste = tube(label = "Waste", capacity = 500uL);

  with env(field = magnetic_rack) {
    sep(sample = bead_tube, program = magnetic_program(duration = 5min));
    waste << [bead_tube.contents[1]];
  }
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    material_state = result.state.artifacts["material_state"]
    contents_state = material_state["contents_states"]["BeadTube"]
    assert contents_state["kind"] == "partitioned"
    assert contents_state["slot_contract"] == {"0": "bound", "1": "flowthrough"}
    bead_components = material_state["containers"]["BeadTube"]["components"]
    waste_components = material_state["containers"]["Waste"]["components"]
    assert round(float(bead_components["BEADS"]), 6) == 20.0
    assert round(float(bead_components["WASH"]), 6) == 0.0
    assert round(float(waste_components["BEADS"]), 6) == 0.0
    assert round(float(waste_components["WASH"]), 6) == 180.0


def test_runtime_magnetic_contents_index_requires_preservation_context():
    plan = _build_plan_from_source(
        """
protocol T {
  let bead_tube = tube(label = "BeadTube", capacity = 500uL, load = [
    content(kind = "particulate", code = "BEADS", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "WASH", type = "buffer"):180uL
  ]);
  let waste = tube(label = "Waste", capacity = 500uL);

  with env(field = magnetic_rack) {
    sep(sample = bead_tube, program = magnetic_program(duration = 5min));
  }
  waste << [bead_tube.contents[1]];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert any(d.code == "MAT_CONTENTS_STATE_PRESERVATION_NOT_SATISFIED" for d in result.diagnostics)


def test_runtime_standalone_frac_contents_index_transfers_fraction():
    plan = _build_plan_from_source(
        """
protocol T {
  let sample_tube = tube(label = "SampleTube", capacity = 200uL, load = [
    content(kind = "biosample", code = "S1", type = "dna_sample"):120uL
  ]);
  let fraction_tube = tube(label = "FractionTube", capacity = 100uL);

  frac(sample = sample_tube, program = density_gradient_program(axis = density, order = top_to_bottom, bins = 3));
  fraction_tube << [sample_tube.contents[1]];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    material_state = result.state.artifacts["material_state"]
    contents_state = material_state["contents_states"]["SampleTube"]
    assert contents_state["kind"] == "fractionated"
    assert contents_state["slot_contract"] == {"0": "fraction_0", "1": "fraction_1", "2": "fraction_2"}
    sample_components = material_state["containers"]["SampleTube"]["components"]
    fraction_components = material_state["containers"]["FractionTube"]["components"]
    assert round(float(sample_components["S1"]), 6) == 80.0
    assert round(float(fraction_components["S1"]), 6) == 40.0


def test_runtime_contents_index_requires_prior_contents_state():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube_a = tube(label = "TubeA", capacity = 100uL, load = [
    buffer(code = "BUF", type = "buffer"):50uL
  ]);
  let waste = tube(label = "Waste", capacity = 100uL);
  waste << [tube_a.contents[0]:10uL];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert any(d.code == "MAT_CONTENTS_STATE_NOT_INDEXED" for d in result.diagnostics)


def test_runtime_contents_index_rejects_stale_state_after_material_mutation():
    plan = _build_plan_from_source(
        """
protocol T {
  let sample_tube = tube(label = "SampleTube", capacity = 300uL, load = [
    content(kind = "particulate", code = "BEADS", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "WASH", type = "buffer"):100uL
  ]);
  let donor_tube = tube(label = "DonorTube", capacity = 100uL, load = [
    buffer(code = "BUF", type = "buffer"):10uL
  ]);
  let waste = tube(label = "Waste", capacity = 300uL);

  sep(sample = sample_tube, program = magnetic_program(duration = 5min));
  sample_tube << [donor_tube];
  waste << [sample_tube.contents[1]];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert any(d.code == "MAT_CONTENTS_STATE_NOT_INDEXED" for d in result.diagnostics)


def test_runtime_magnetic_env_preserves_contents_state_after_compatible_addition():
    plan = _build_plan_from_source(
        """
protocol T {
  let bead_tube = tube(label = "BeadTube", capacity = 700uL, load = [
    content(kind = "particulate", code = "BEADS", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "BIND", type = "buffer"):180uL
  ]);
  let ethanol = tube(label = "Ethanol", capacity = 300uL, load = [
    buffer(code = "ETOH", type = "buffer"):200uL
  ]);
  let waste = tube(label = "Waste", capacity = 700uL);

  with env(field = magnetic_rack) {
    sep(sample = bead_tube, program = magnetic_program(duration = 5min));
    bead_tube << [ethanol:200uL];
    waste << [bead_tube.contents[1]];
  }
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    material_state = result.state.artifacts["material_state"]
    contents_state = material_state["contents_states"]["BeadTube"]
    assert contents_state["valid"] is True
    assert contents_state["preservation_contract"] == {
        "kind": "field_retention",
        "field": "magnetic_rack",
        "retained_slot": "0",
        "default_incoming_slot": "1",
    }
    bead_components = material_state["containers"]["BeadTube"]["components"]
    waste_components = material_state["containers"]["Waste"]["components"]
    assert round(float(bead_components["BEADS"]), 6) == 20.0
    assert round(float(bead_components["BIND"]), 6) == 0.0
    assert round(float(waste_components["BEADS"]), 6) == 0.0
    assert round(float(waste_components["BIND"]), 6) == 180.0
    assert round(float(waste_components["ETOH"]), 6) == 200.0


def test_runtime_source_partition_target_addition_uses_contents_state_classifier():
    plan = _build_plan_from_source(
        """
protocol T {
  let bead_tube = tube(label = "BeadTube", capacity = 700uL, load = [
    content(kind = "particulate", code = "BEADS", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "BIND", type = "buffer"):180uL
  ]);
  let donor = tube(label = "Donor", capacity = 200uL, load = [
    buffer(code = "DON", type = "buffer"):100uL
  ]);
  let waste = tube(label = "Waste", capacity = 700uL);
  let mag_sep = magnetic_program(duration = 5min);

  with env(field = magnetic_rack) {
    sep(sample = bead_tube, program = magnetic_program(duration = 5min));
    bead_tube << [donor.partition(mag_sep)[1]:50uL];
    waste << [bead_tube.contents[1]];
  }
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    material_state = result.state.artifacts["material_state"]
    contents_state = material_state["contents_states"]["BeadTube"]
    assert contents_state["valid"] is True
    waste_components = material_state["containers"]["Waste"]["components"]
    assert round(float(waste_components["BEADS"]), 6) == 0.0
    assert round(float(waste_components["BIND"]), 6) == 180.0
    assert round(float(waste_components["DON"]), 6) == 50.0


def test_runtime_magnetic_env_hold_target_does_not_narrow_block_context():
    plan = _build_plan_from_source(
        """
protocol T {
  let bead_tube = tube(label = "BeadTube", capacity = 700uL, load = [
    content(kind = "particulate", code = "BEADS", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "BIND", type = "buffer"):180uL
  ]);
  let shielded = tube(label = "Shielded", capacity = 100uL);
  let ethanol = tube(label = "Ethanol", capacity = 300uL, load = [
    buffer(code = "ETOH", type = "buffer"):200uL
  ]);
  let waste = tube(label = "Waste", capacity = 700uL);

  sep(sample = bead_tube, program = magnetic_program(duration = 5min));
  with env(field = magnetic_rack) {
    hold(sample = shielded);
    bead_tube << [ethanol:200uL];
    waste << [bead_tube.contents[1]];
  }
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    material_state = result.state.artifacts["material_state"]
    contents_state = material_state["contents_states"]["BeadTube"]
    assert contents_state["valid"] is True
    waste_components = material_state["containers"]["Waste"]["components"]
    assert round(float(waste_components["BEADS"]), 6) == 0.0
    assert round(float(waste_components["BIND"]), 6) == 180.0
    assert round(float(waste_components["ETOH"]), 6) == 200.0


def test_runtime_whole_container_removal_stales_contents_state_even_in_magnetic_env():
    plan = _build_plan_from_source(
        """
protocol T {
  let bead_tube = tube(label = "BeadTube", capacity = 700uL, load = [
    content(kind = "particulate", code = "BEADS", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "BIND", type = "buffer"):180uL
  ]);
  let waste = tube(label = "Waste", capacity = 700uL);
  let waste2 = tube(label = "Waste2", capacity = 700uL);

  with env(field = magnetic_rack) {
    sep(sample = bead_tube, program = magnetic_program(duration = 5min));
    waste << [bead_tube:100uL];
    waste2 << [bead_tube.contents[1]];
  }
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert any(d.code == "MAT_CONTENTS_STATE_NOT_INDEXED" for d in result.diagnostics)
    contents_state = result.state.artifacts["material_state"]["contents_states"]["BeadTube"]
    assert contents_state["valid"] is False
    assert contents_state["invalid_reason"] == "whole_container_transfer"


def test_runtime_agit_marks_contents_state_mixed_and_stale():
    plan = _build_plan_from_source(
        """
protocol T {
  let bead_tube = tube(label = "BeadTube", capacity = 500uL, load = [
    content(kind = "particulate", code = "BEADS", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "BIND", type = "buffer"):180uL
  ]);
  let waste = tube(label = "Waste", capacity = 500uL);

  sep(sample = bead_tube, program = magnetic_program(duration = 5min));
  agit(sample = bead_tube, mode = shake, duration = 30s, rate = 800rpm);
  waste << [bead_tube.contents[1]];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert any(d.code == "MAT_CONTENTS_STATE_NOT_INDEXED" for d in result.diagnostics)
    contents_state = result.state.artifacts["material_state"]["contents_states"]["BeadTube"]
    assert contents_state["valid"] is False
    assert contents_state["kind"] == "mixed"
    assert contents_state["invalid_reason"] == "explicit_mixing"


def test_runtime_agit_applies_to_each_explicit_group_sample():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube1 = tube(label = "Tube1", capacity = 500uL, load = [
    content(kind = "particulate", code = "BEADS1", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "BIND1", type = "buffer"):180uL
  ]);
  let tube2 = tube(label = "Tube2", capacity = 500uL, load = [
    content(kind = "particulate", code = "BEADS2", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "BIND2", type = "buffer"):180uL
  ]);

  sep(sample = tube1, program = magnetic_program(duration = 5min));
  sep(sample = tube2, program = magnetic_program(duration = 5min));
  agit(sample = group([tube1, tube2]), mode = shake, duration = 30s, rate = 800rpm);
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    contents_states = result.state.artifacts["material_state"]["contents_states"]
    assert contents_states["Tube1"]["valid"] is False
    assert contents_states["Tube1"]["kind"] == "mixed"
    assert contents_states["Tube1"]["invalid_reason"] == "explicit_mixing"
    assert contents_states["Tube2"]["valid"] is False
    assert contents_states["Tube2"]["kind"] == "mixed"
    assert contents_states["Tube2"]["invalid_reason"] == "explicit_mixing"


def test_runtime_agit_applies_to_each_let_bound_group_sample():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube1 = tube(label = "Tube1", capacity = 500uL, load = [
    content(kind = "particulate", code = "BEADS1", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "BIND1", type = "buffer"):180uL
  ]);
  let tube2 = tube(label = "Tube2", capacity = 500uL, load = [
    content(kind = "particulate", code = "BEADS2", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "BIND2", type = "buffer"):180uL
  ]);
  let bead_tubes = group([tube1, tube2]);

  sep(sample = tube1, program = magnetic_program(duration = 5min));
  sep(sample = tube2, program = magnetic_program(duration = 5min));
  agit(sample = bead_tubes, mode = shake, duration = 30s, rate = 800rpm);
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    contents_states = result.state.artifacts["material_state"]["contents_states"]
    assert contents_states["Tube1"]["valid"] is False
    assert contents_states["Tube1"]["kind"] == "mixed"
    assert contents_states["Tube2"]["valid"] is False
    assert contents_states["Tube2"]["kind"] == "mixed"


def test_runtime_contents_self_transfer_invalidates_contents_state_without_material_move():
    plan = _build_plan_from_source(
        """
protocol T {
  let bead_tube = tube(label = "BeadTube", capacity = 500uL, load = [
    content(kind = "particulate", code = "BEADS", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "WASH", type = "buffer"):180uL
  ]);

  with env(field = magnetic_rack) {
    sep(sample = bead_tube, program = magnetic_program(duration = 5min));
    bead_tube << [bead_tube.contents[1]];
  }
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    material_state = result.state.artifacts["material_state"]
    bead_tube = material_state["containers"]["BeadTube"]
    assert round(float(bead_tube["volume_uL"]), 6) == 200.0
    assert {k: round(float(v), 6) for k, v in bead_tube["components"].items()} == {"BEADS": 20.0, "WASH": 180.0}
    contents_state = material_state["contents_states"]["BeadTube"]
    assert contents_state["valid"] is False
    assert contents_state["invalid_reason"] == "contents_self_transfer"


def test_runtime_contents_self_transfer_makes_later_contents_read_stale():
    plan = _build_plan_from_source(
        """
protocol T {
  let bead_tube = tube(label = "BeadTube", capacity = 500uL, load = [
    content(kind = "particulate", code = "BEADS", type = "beads", attrs = { bead_property: magnetic }):20uL,
    buffer(code = "WASH", type = "buffer"):180uL
  ]);
  let waste = tube(label = "Waste", capacity = 500uL);

  with env(field = magnetic_rack) {
    sep(sample = bead_tube, program = magnetic_program(duration = 5min));
    bead_tube << [bead_tube.contents[1]];
  }
  waste << [bead_tube.contents[1]];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert any(d.code == "MAT_CONTENTS_STATE_NOT_INDEXED" for d in result.diagnostics)


def test_runtime_source_partition_magnetic_does_not_guess_custom_fate():
    plan = _build_plan_from_source(
        """
protocol T {
  let src = tube(label = "Src", capacity = 500uL, load = [
    content(kind = "chemical", code = "CUSTOM", type = "custom_local_mix"):100uL
  ]);
  let dst = tube(label = "Dst", capacity = 500uL);
  let mag_sep = magnetic_program(duration = 5min);

  dst << [src.partition(mag_sep)[1]:50uL];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert "MAT_SCIENTIFIC_MODEL_UNRESOLVED" in [
        diagnostic.code for diagnostic in result.diagnostics
    ]


def test_runtime_electrophoresis_requires_field_fate_provider_coverage():
    plan = _build_plan_from_source(
        """
protocol T {
  let gel_lane = tube(label = "GelLane", capacity = 100uL, load = [content(kind = "biosample", code = "DNA1", type = "amplicon"):10uL]);
  let stain_input = tube(label = "Stain", capacity = 500uL, load = [reagent(code = "SYBR", type = "dna_stain"):100uL]);
  let gel_obs_schema = data_schema(label = "GelObs", fields = [bands]);
  let gel_obs = Electrophoresis(
    sample = gel_lane,
    gel_type = "Agarose_1.5pct",
    stain = stain_input,
    field = 100V,
    duration = 30min,
    readout_schema = gel_obs_schema
  );
}
"""
    )
    result = run(plan=plan, driver=StubDriver())
    assert not result.ok
    assert "MAT_SCIENTIFIC_MODEL_UNRESOLVED" in [
        diagnostic.code for diagnostic in result.diagnostics
    ]
    ops = [step.op for protocol in plan.plans for step in protocol.steps]
    assert "Electrophoresis" not in ops


def test_replay_reconstructs_state_from_events():
    plan = _build_plan_from_source(
        'protocol T { let tube1 = tube(label = "Tube1", capacity = 100uL); tube1 << [A:5uL]; }'
    )
    state = init_state(plan)
    state.artifacts["material_state"] = {
        "containers": {
            "A": {"volume_uL": 10.0, "mass_mg": 10.0, "components": {"DNA": 1.0}, "metadata": {}},
            "Tube1": {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
        }
    }
    result = run(plan=plan, driver=StubDriver(), state=state)
    replayed = replay_events([e.to_dict() for e in result.events])
    assert replayed.step_status == result.state.step_status
    assert replayed.artifacts.get("material_state") == result.state.artifacts.get("material_state")


def test_runtime_scheduler_guard_limit_stops_and_reports():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube1 = tube(label = "Tube1", capacity = 100uL);
  tube1 << [A:5uL];
  with env(thermal = 37C, duration = 10min) { hold(sample = tube1); }
}
"""
    )
    result = run(plan=plan, driver=StubDriver(), max_scheduler_rounds=0, state=_runtime_state_with_source(plan))

    codes = [d.code for d in result.diagnostics]
    assert "RT_SCHEDULER_GUARD_LIMIT" in codes
    assert "RT_STUCK_STEP" in codes


def test_runtime_ref_auto_reuse_avoids_duplicate_execution_for_same_call_path():
    plan = PlanProgram(
        plans=[
            ProtocolPlan(
                protocol_id="p0",
                protocol_name="Demo",
                steps=[
                    PlanStep(
                        step_id="u1::s0",
                        op="Mutation",
                        args={
                            "target": {"kind": "IRIdentifier", "name": "B", "span": None},
                            "sources": [
                                {
                                    "kind": "IRPair",
                                    "left": {"kind": "IRIdentifier", "name": "A", "span": None},
                                    "right": {"kind": "IRQuantity", "value": 5, "unit": "uL", "span": None},
                                    "span": None,
                                }
                            ],
                        },
                        deps=[],
                        gate={
                            "protocol_name": "Demo",
                            "ref_meta": {"ref_protocol": "Base", "ref_call_id": "u1", "call_path": "u1"},
                        },
                    ),
                    PlanStep(
                        step_id="u1::s1",
                        op="env_hold",
                        args={},
                        deps=["u1::s0"],
                        gate={
                            "protocol_name": "Demo",
                            "env": {
                                "thermal": {"kind": "IRQuantity", "value": 37.0, "unit": "C", "span": None},
                                "duration": {"kind": "IRQuantity", "value": 10.0, "unit": "min", "span": None},
                            },
                            "env_targets": [{"kind": "IRIdentifier", "name": "B", "span": None}],
                            "ref_meta": {"ref_protocol": "Base", "ref_call_id": "u1", "call_path": "u1"},
                        },
                    ),
                    # Intentional duplicated expanded subtree with same call_path.
                    PlanStep(
                        step_id="u1_copy::s0",
                        op="Mutation",
                        args={
                            "target": {"kind": "IRIdentifier", "name": "B", "span": None},
                            "sources": [
                                {
                                    "kind": "IRPair",
                                    "left": {"kind": "IRIdentifier", "name": "A", "span": None},
                                    "right": {"kind": "IRQuantity", "value": 5, "unit": "uL", "span": None},
                                    "span": None,
                                }
                            ],
                        },
                        deps=["u1::s1"],
                        gate={
                            "protocol_name": "Demo",
                            "ref_meta": {"ref_protocol": "Base", "ref_call_id": "u1_copy", "call_path": "u1"},
                        },
                    ),
                    PlanStep(
                        step_id="u1_copy::s1",
                        op="env_hold",
                        args={},
                        deps=["u1_copy::s0"],
                        gate={
                            "protocol_name": "Demo",
                            "env": {
                                "thermal": {"kind": "IRQuantity", "value": 37.0, "unit": "C", "span": None},
                                "duration": {"kind": "IRQuantity", "value": 10.0, "unit": "min", "span": None},
                            },
                            "env_targets": [{"kind": "IRIdentifier", "name": "B", "span": None}],
                            "ref_meta": {"ref_protocol": "Base", "ref_call_id": "u1_copy", "call_path": "u1"},
                        },
                    ),
                ],
            )
        ]
    )

    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    assert all(status == "completed" for status in result.state.step_status.values())

    ref_decisions = [e for e in result.events if e.kind == "REF_DECISION"]
    assert len(ref_decisions) == 2
    assert ref_decisions[0].payload["ref_decision"] == "rerun"
    assert ref_decisions[1].payload["ref_decision"] == "reuse"


def test_runtime_emits_binding_overwritten_event_for_fraction_rebind():
    plan = PlanProgram(
        plans=[
            ProtocolPlan(
                protocol_id="p0",
                protocol_name="T",
                steps=[
                    PlanStep(
                        step_id="p0.s0",
                        op="sep",
                        args={
                            "sample": {"kind": "IRIdentifier", "name": "Lysate", "span": None},
                            "program": {
                                "kind": "IRCall",
                                "name": "centrifuge_program",
                                "args": [],
                                "span": None,
                            },
                            "bind": "sep_group",
                        },
                        deps=[],
                        gate=None,
                    ),
                    PlanStep(
                        step_id="p0.s1",
                        op="sep",
                        args={
                            "sample": {"kind": "IRIdentifier", "name": "Lysate", "span": None},
                            "program": {
                                "kind": "IRCall",
                                "name": "centrifuge_program",
                                "args": [],
                                "span": None,
                            },
                            "bind": "sep_group",
                        },
                        deps=["p0.s0"],
                        gate=None,
                    ),
                ],
            )
        ]
    )
    state = init_state(plan)
    state.artifacts["material_state"] = {
        "containers": {
            "Lysate": {"volume_uL": 1000.0, "mass_mg": 1000.0, "components": {"RNA": 100.0}, "metadata": {}}
        },
        "content_registry": {
            "RNA": {"content_kind": "bio_molecule_or_virus", "content_type": "rna"}
        },
    }

    result = run(plan=plan, driver=StubDriver(), state=state)
    assert result.ok
    overwritten = [e for e in result.events if e.kind == "BINDING_OVERWRITTEN"]
    assert len(overwritten) >= 1
    assert overwritten[0].payload["name"] in {"sep_group[0]", "sep_group[1]"}


def test_runtime_executes_mutation_step_and_updates_material_state():
    plan = PlanProgram(
        plans=[
            ProtocolPlan(
                protocol_id="p0",
                protocol_name="T",
                steps=[
                    PlanStep(
                        step_id="p0.s0",
                        op="Mutation",
                        args={
                            "target": {"kind": "IRIdentifier", "name": "B", "span": None},
                            "sources": [{"kind": "IRIdentifier", "name": "A", "span": None}],
                        },
                        deps=[],
                        gate=None,
                        span=None,
                    )
                ],
            )
        ]
    )
    state = init_state(plan)
    state.artifacts["material_state"] = {
        "containers": {
            "A": {"volume_uL": 10.0, "mass_mg": 10.0, "components": {"DNA": 1.0}, "metadata": {}},
            "B": {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
        }
    }

    result = run(plan=plan, driver=StubDriver(), state=state)
    assert result.ok
    assert result.state.artifacts["material_state"]["containers"]["A"]["volume_uL"] == 0.0
    assert result.state.artifacts["material_state"]["containers"]["B"]["volume_uL"] == 10.0


def test_runtime_step_events_preserve_gate_for_env_backed_steps():
    plan = PlanProgram(
        plans=[
            ProtocolPlan(
                protocol_id="p0",
                protocol_name="T",
                steps=[
                    PlanStep(
                        step_id="p0.s0",
                        op="Mutation",
                        args={
                            "target": {"kind": "IRIdentifier", "name": "tube", "span": None},
                            "sources": [
                                {
                                    "kind": "IRPair",
                                    "left": {"kind": "IRIdentifier", "name": "feed", "span": None},
                                    "right": {"kind": "IRQuantity", "value": 1.0, "unit": "uL", "span": None},
                                    "span": None,
                                }
                            ],
                        },
                        deps=[],
                        gate={
                            "protocol_name": "T",
                            "env": {
                                "thermal": {"kind": "IRQuantity", "value": 37.0, "unit": "C", "span": None},
                                "duration": {"kind": "IRQuantity", "value": 10.0, "unit": "min", "span": None},
                            },
                            "env_targets": [{"kind": "IRIdentifier", "name": "tube", "span": None}],
                        },
                        span=None,
                    )
                ],
            )
        ]
    )
    state = init_state(plan)
    state.artifacts["material_state"] = {
        "containers": {
            "feed": {"volume_uL": 10.0, "mass_mg": 10.0, "components": {"DNA": 1.0}, "metadata": {}},
            "tube": {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
        }
    }

    result = run(plan=plan, driver=StubDriver(), state=state)
    assert result.ok
    started = [e for e in result.events if e.kind == "STEP_STARTED"][0]
    completed = [e for e in result.events if e.kind == "STEP_COMPLETED"][0]
    assert started.payload["gate"]["env"]["thermal"]["value"] == 37.0
    assert completed.payload["gate"]["env_targets"][0]["name"] == "tube"


def test_runtime_records_img_observation_binding_and_raw_metadata():
    plan = PlanProgram(
        plans=[
            ProtocolPlan(
                protocol_id="p0",
                protocol_name="T",
                steps=[
                    PlanStep(
                        step_id="p0.s0",
                        op="img",
                        args={
                            "sample": {"kind": "IRIdentifier", "name": "tube", "span": None},
                            "quantity": {"kind": "IRIdentifier", "name": "fluorescence", "span": None},
                            "save_raw": {"kind": "IRBoolean", "value": True, "span": None},
                            "bind": "img_obs",
                        },
                        deps=[],
                        gate=None,
                        span=None,
                    )
                ],
            )
        ]
    )
    state = init_state(plan)
    state.artifacts["material_state"] = {
        "containers": {
            "tube": {"volume_uL": 10.0, "mass_mg": 10.0, "components": {"DNA": 1.0}, "metadata": {}},
        }
    }

    result = run(plan=plan, driver=StubDriver(), state=state)
    assert result.ok
    data_id = result.state.artifacts["data_bindings"]["img_obs"]
    record = result.state.artifacts["data_objects"][data_id]
    assert record["op"] == "img"
    assert record["resolved_sample"] == "tube"
    assert record["save_raw"] is True
    assert record["raw_artifact"]["artifact_id"] == f"{data_id}::raw"
    completed = [e for e in result.events if e.kind == "STEP_COMPLETED"][0]
    assert completed.payload["observation_delta"]["binding"] == "img_obs"


def test_runtime_records_img_data_binding_as_canonical_readout_handle():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):10uL]);
  let img_obs = img(sample = tube, quantity = fluorescence);
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    data_id = result.state.artifacts["data_bindings"]["img_obs"]
    record = result.state.artifacts["data_objects"][data_id]
    assert record["kind"] == "data_ref"
    assert record["data_kind"] == "observation"
    assert record["family"] == "img"
    assert record["contract_kind"] == "fluorescence"
    assert record["result"] == {"signal": None, "channel": None}


def test_runtime_records_ecp_data_binding_as_canonical_readout_handle():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL, load = [buffer(code = "BUF", type = "test_buffer"):10uL]);
  let ecp_obs = ecp(sample = tube, quantity = ph);
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    data_id = result.state.artifacts["data_bindings"]["ecp_obs"]
    record = result.state.artifacts["data_objects"][data_id]
    assert record["kind"] == "data_ref"
    assert record["data_kind"] == "observation"
    assert record["family"] == "ecp"
    assert record["contract_kind"] == "ph"
    assert record["result"] == {"ph": None}


def test_runtime_resolves_group_index_for_observation_sample():
    plan = PlanProgram(
        plans=[
            ProtocolPlan(
                protocol_id="p0",
                protocol_name="T",
                steps=[
                    PlanStep(
                        step_id="p0.s0",
                        op="sep",
                        args={
                            "sample": {"kind": "IRIdentifier", "name": "lysate", "span": None},
                            "program": {
                                "kind": "IRCall",
                                "name": "centrifuge_program",
                                "args": [
                                    {
                                        "kind": "IRArg",
                                        "name": "drive",
                                        "value": {"kind": "IRQuantity", "value": 12000.0, "unit": "g", "span": None},
                                        "span": None,
                                    },
                                ],
                                "span": None,
                            },
                            "bind": "sep_group",
                        },
                        deps=[],
                        gate=None,
                        span=None,
                    ),
                    PlanStep(
                        step_id="p0.s1",
                        op="img",
                        args={
                            "sample": {
                                "kind": "IRIndex",
                                "base": {"kind": "IRIdentifier", "name": "sep_group", "span": None},
                                "index": {"kind": "IRQuantity", "value": 0.0, "unit": None, "span": None},
                                "span": None,
                            },
                            "quantity": {"kind": "IRIdentifier", "name": "fluorescence", "span": None},
                            "save_raw": {"kind": "IRBoolean", "value": False, "span": None},
                            "bind": "img_obs",
                        },
                        deps=["p0.s0"],
                        gate=None,
                        span=None,
                    ),
                ],
            )
        ]
    )
    state = init_state(plan)
    state.artifacts["material_state"] = {
        "containers": {
            "lysate": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {"DNA": 10.0}, "metadata": {}},
        },
        "content_registry": {
            "DNA": {"content_kind": "bio_molecule_or_virus", "content_type": "dna"}
        },
    }

    result = run(plan=plan, driver=StubDriver(), state=state)
    assert result.ok
    data_id = result.state.artifacts["data_bindings"]["img_obs"]
    record = result.state.artifacts["data_objects"][data_id]
    slot0_id = result.state.artifacts["material_state"]["indexed_bindings"]["sep_group"]["0"]
    assert record["resolved_sample"] == slot0_id


def test_runtime_records_grouped_img_observation_binding_and_result_envelope():
    plan = _build_plan_from_source(
        """
protocol T {
  let t1 = tube(label = "T1", capacity = 500uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):10uL]);
  let t2 = tube(label = "T2", capacity = 500uL, load = [content(kind = "biosample", code = "S2", type = "dna_sample"):10uL]);
  let wells = group([t1, t2]);
  let img_group = img(sample = wells, quantity = fluorescence, save_raw = true);
}
"""
    )
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    group_id = result.state.artifacts["data_group_bindings"]["img_group"]
    group_record = result.state.artifacts["data_groups"][group_id]
    assert group_record["family"] == "img"
    assert group_record["binding"] == "img_group"
    assert len(group_record["observation_ids"]) == 2
    first_obs = result.state.artifacts["data_objects"][group_record["observation_ids"][0]]
    second_obs = result.state.artifacts["data_objects"][group_record["observation_ids"][1]]
    assert first_obs["family"] == "img"
    assert first_obs["result"] == {"signal": None, "channel": None}
    assert first_obs["raw_artifact"]["artifact_id"].endswith("::raw")
    assert first_obs["export_refs"]["driver_profile"]["export_id"].endswith("::driver_profile")
    assert first_obs["export_refs"]["driver_profile"]["kind"] == "img"
    assert first_obs["export_refs"]["driver_profile"]["artifact_id"] == first_obs["raw_artifact"]["artifact_id"]
    assert first_obs["binding"] is None
    assert first_obs["resolved_sample"] == "T1"
    assert second_obs["resolved_sample"] == "T2"
    completed = [e for e in result.events if e.kind == "STEP_COMPLETED"][-1]
    assert completed.payload["observation_delta"]["binding"] == "img_group"
    assert completed.payload["observation_delta"]["observation_ids"] == group_record["observation_ids"]
    indexed = result.state.artifacts["data_group_indexed_bindings"]["img_group"]
    assert indexed["0"] == group_record["observation_ids"][0]
    assert indexed["1"] == group_record["observation_ids"][1]


def test_runtime_records_grouped_img_data_group_binding_as_canonical_handle():
    plan = _build_plan_from_source(
        """
protocol T {
  let t1 = tube(label = "T1", capacity = 500uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):10uL]);
  let t2 = tube(label = "T2", capacity = 500uL, load = [content(kind = "biosample", code = "S2", type = "dna_sample"):10uL]);
  let wells = group([t1, t2]);
  let img_group = img(sample = wells, quantity = fluorescence);
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    group_id = result.state.artifacts["data_group_bindings"]["img_group"]
    group_record = result.state.artifacts["data_groups"][group_id]
    assert group_record["kind"] == "data_group_ref"
    assert group_record["data_kind"] == "observation"
    assert group_record["contract_kind"] == "fluorescence"
    assert len(group_record["item_ids"]) == 2
    first = result.state.artifacts["data_objects"][group_record["item_ids"][0]]
    second = result.state.artifacts["data_objects"][group_record["item_ids"][1]]
    assert first["resolved_sample"] == "T1"
    assert second["resolved_sample"] == "T2"


def test_runtime_records_grouped_img_from_plate_selector_in_row_major_order():
    plan = _build_plan_from_source(
        """
protocol T {
  let plate96 = plate(label = "Assay", format = "96well", carrier_id = "PlateA");
  let img_group = img(sample = plate96[A1:B2], quantity = fluorescence);
}
"""
    )
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    group_id = result.state.artifacts["data_group_bindings"]["img_group"]
    group_record = result.state.artifacts["data_groups"][group_id]
    assert group_record["resolved_samples"] == [
        "Assay_A1",
        "Assay_A2",
        "Assay_B1",
        "Assay_B2",
    ]


def test_runtime_plate_selector_well_inherits_capacity_for_case06_volume():
    plan = _build_plan_from_source(
        """
protocol T {
  let plate24 = plate(label = "Editing", format = "24well", carrier_id = "Editing24", capacity = 3mL);
  let well_a1 = plate24[A1];
  let culture = tube(
    label = "Culture",
    capacity = 2mL,
    load = [content(kind = bio_cellular, type = cell_line, code = "HEK293T"):1mL]
  );
  well_a1 << [culture:1mL];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    well = result.state.artifacts["material_state"]["containers"]["Editing_A1"]
    assert well["metadata"]["capacity_uL"] == 3000.0
    assert well["volume_uL"] == 1000.0


def test_runtime_static_plate_group_index_aliases_original_selected_well():
    plan = _build_plan_from_source(
        """
protocol T {
  let plate96 = plate(label = "Clones", format = "96well", carrier_id = "ClonePlate", capacity = 200uL);
  let selected_wells = plate96[A3:A5];
  let selected_clone_a_well = selected_wells[0];
  let clone_material = tube(
    label = "CloneMaterial",
    capacity = 200uL,
    load = [content(kind = bio_cellular, type = cell_population, code = "CLONE_A"):100uL]
  );
  selected_clone_a_well << [clone_material:100uL];
}
"""
    )

    mutation = next(step for step in plan.plans[0].steps if step.op == "Mutation")
    assert mutation.args["target"]["name"] == "__lw_plate_plate96_A3"

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material = result.state.artifacts["material_state"]
    assert material["containers"]["Clones_A3"]["components"]["CLONE_A"] == 100.0


def test_runtime_observation_if_executes_then_branch_when_predicate_true():
    plan = _build_plan_from_source(
        """
protocol T {
  let obs = img(sample = tube_a, quantity = fluorescence);
  if obs.result.signal >= 1000 {
    img(sample = tube_a, quantity = fluorescence);
  } else {
    img(sample = tube_a, quantity = fluorescence);
  }
}
"""
    )
    result = run(plan=plan, driver=StubDriver(op_payloads={"img": {"result": {"signal": 1250}}}))
    assert result.ok
    statuses = result.state.step_status
    assert statuses["p0.s1.then.s0"] == "completed"
    assert statuses["p0.s1.else.s0"] == "skipped"
    skip_reasons = result.state.artifacts["skip_reasons"]
    assert skip_reasons["p0.s1.else.s0"] == "runtime_condition_false"


def test_runtime_observation_if_executes_else_branch_when_predicate_false():
    plan = _build_plan_from_source(
        """
protocol T {
  let obs = img(sample = tube_a, quantity = fluorescence);
  if obs.result.signal >= 1000 {
    img(sample = tube_a, quantity = fluorescence);
  } else {
    img(sample = tube_a, quantity = fluorescence);
  }
}
"""
    )
    result = run(plan=plan, driver=StubDriver(op_payloads={"img": {"result": {"signal": 800}}}))
    assert result.ok
    statuses = result.state.step_status
    assert statuses["p0.s1.then.s0"] == "skipped"
    assert statuses["p0.s1.else.s0"] == "completed"


def test_runtime_continue_skips_only_current_repeat_iteration_tail():
    plan = _build_plan_from_source(
        """
protocol T {
  repeat 2 {
    let obs = img(sample = tube_a, quantity = fluorescence);
    if obs.result.signal >= 1000 {
      continue;
    }
    img(sample = tube_a, quantity = fluorescence);
  }
}
"""
    )
    result = run(
        plan=plan,
        driver=StubDriver(
            step_payloads={
                "p0.s0.i0.s0": {"result": {"signal": 1250}},
                "p0.s0.i1.s0": {"result": {"signal": 800}},
            }
        ),
    )
    assert result.ok
    statuses = result.state.step_status
    assert statuses["p0.s0.i0.s1.then.s0"] == "completed"
    assert statuses["p0.s0.i0.s2"] == "skipped"
    assert statuses["p0.s0.i1.s1.then.s0"] == "skipped"
    assert statuses["p0.s0.i1.s2"] == "completed"
    assert result.state.artifacts["skip_reasons"]["p0.s0.i0.s2"] == "runtime_continue"


def test_runtime_break_skips_later_repeat_iterations():
    plan = _build_plan_from_source(
        """
protocol T {
  repeat 3 {
    let obs = img(sample = tube_a, quantity = fluorescence);
    if obs.result.signal >= 1000 {
      break;
    }
    img(sample = tube_a, quantity = fluorescence);
  }
}
"""
    )
    result = run(
        plan=plan,
        driver=StubDriver(
            step_payloads={
                "p0.s0.i0.s0": {"result": {"signal": 800}},
                "p0.s0.i1.s0": {"result": {"signal": 1250}},
            }
        ),
    )
    assert result.ok
    statuses = result.state.step_status
    assert statuses["p0.s0.i0.s2"] == "completed"
    assert statuses["p0.s0.i1.s1.then.s0"] == "completed"
    assert statuses["p0.s0.i1.s2"] == "skipped"
    assert statuses["p0.s0.i2.s0"] == "skipped"
    assert result.state.artifacts["skip_reasons"]["p0.s0.i2.s0"] == "runtime_break"


def test_runtime_grouped_observation_indexed_predicate_branches_correctly():
    plan = _build_plan_from_source(
        """
protocol T {
  let plate96 = plate(label = "Assay", format = "96well", carrier_id = "PlateA");
  let obs_group = img(sample = plate96[A1:A2], quantity = fluorescence);
  let first_obs = obs_group[0];
  if first_obs.result.signal >= 1000 {
    img(sample = tube_a, quantity = fluorescence);
  } else {
    img(sample = tube_b, quantity = fluorescence);
  }
}
"""
    )
    result = run(plan=plan, driver=StubDriver(op_payloads={"img": {"result": {"signal": 1200}}}))
    assert result.ok
    branch_steps = [step for step in plan.plans[0].steps if step.op == "img" and isinstance(step.gate, dict) and "runtime_conditions" in step.gate]
    assert len(branch_steps) == 2
    completed = [step for step in branch_steps if result.state.step_status[step.step_id] == "completed"]
    skipped = [step for step in branch_steps if result.state.step_status[step.step_id] == "skipped"]
    assert len(completed) == 1
    assert len(skipped) == 1
    assert completed[0].args["sample"]["name"] == "tube_a"
    assert skipped[0].args["sample"]["name"] == "tube_b"


def test_runtime_executes_constructor_binding_before_mutation_without_seed_state():
    plan = _build_plan_from_source(
        """
protocol T {
  let src = tube(label = "SRC", capacity = 500uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):100uL]);
  let dst = tube(label = "DST", capacity = 500uL);
  dst << [src:25uL];
}
"""
    )
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    material = result.state.artifacts["material_state"]
    assert material["bindings"]["src"] == "SRC"
    assert material["bindings"]["dst"] == "DST"
    assert material["containers"]["SRC"]["volume_uL"] == 75.0
    assert material["containers"]["DST"]["volume_uL"] == 25.0


def test_runtime_allows_self_transfer_mutation_without_material_change():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube_a = tube(label = "TubeA", capacity = 500uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):100uL]);
  tube_a << [tube_a:25uL];
}
"""
    )
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    material = result.state.artifacts["material_state"]
    assert material["bindings"]["tube_a"] == "TubeA"
    assert material["containers"]["TubeA"]["volume_uL"] == 100.0
    assert material["containers"]["TubeA"]["mass_mg"] == 100.0
    assert material["containers"]["TubeA"]["components"]["S1"] == 100.0


def test_runtime_executes_constructor_load_before_core_sep():
    plan = _build_plan_from_source(
        """
protocol T {
  let sample_tube = tube(label = "SampleTube", capacity = 500uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):100uL]);
  let sep_group = sep(sample = sample_tube, program = centrifuge_program(drive = 12000g));
}
"""
    )
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    material = result.state.artifacts["material_state"]
    assert material["bindings"]["sample_tube"] == "SampleTube"
    slots = material["indexed_bindings"]["sep_group"]
    assert set(slots.keys()) == {"0", "1"}
    assert material["containers"][slots["0"]]["volume_uL"] == 100.0
    assert material["containers"][slots["1"]]["volume_uL"] == 0.0


def test_runtime_cell_count_load_and_volume_transfer_keep_count_independent():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 300uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  let target = tube(label = "Target", capacity = 200uL);
  target << [source:100uL];
  return target;
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    containers = result.state.artifacts["material_state"]["containers"]
    assert containers["Source"]["volume_uL"] == 200.0
    assert containers["Target"]["volume_uL"] == 100.0
    assert round(containers["Source"]["component_quantities"]["RPE1"]["value"], 6) == 66666.666667
    assert round(containers["Target"]["component_quantities"]["RPE1"]["value"], 6) == 33333.333333
    returned = result.state.artifacts["protocol_outputs"]["T"]["value"]
    assert returned["count_cells"] == 33333.333333
    assert returned["component_quantities"]["RPE1"] == {
        "dimension": "count",
        "unit": "cells",
        "value": 33333.333333,
    }
    assert returned["material_relationships"][0]["subtype"] == "cell_suspension"


def test_runtime_cell_suspension_transfer_merges_with_preloaded_target():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 300uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  let target = tube(label = "Target", capacity = 200uL, load = [
    content(kind = formulation, type = buffer, code = "PBS"):50uL
  ]);
  target << [source:100uL];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    containers = result.state.artifacts["material_state"]["containers"]
    source = containers["Source"]
    target = containers["Target"]

    assert source["volume_uL"] == 200.0
    assert target["volume_uL"] == 150.0
    assert source["component_quantities"]["RPE1"]["value"] == pytest.approx(66666.666667)
    assert target["component_quantities"]["RPE1"] == {
        "dimension": "count",
        "unit": "cells",
        "value": pytest.approx(33333.333333),
    }
    assert target["component_quantities"]["MEDIUM"] == {
        "dimension": "volume",
        "unit": "uL",
        "value": 100.0,
    }
    assert target["component_quantities"]["PBS"] == {
        "dimension": "volume",
        "unit": "uL",
        "value": 50.0,
    }
    assert source["component_quantities"]["RPE1"]["value"] + target["component_quantities"]["RPE1"]["value"] == pytest.approx(
        100000.0
    )
    assert source["volume_uL"] + target["volume_uL"] == 350.0


def test_runtime_direct_cell_count_transfer_resolves_default_suspension_volume():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 200uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells
  ]);
  let target = tube(label = "Target", capacity = 50uL);
  target << [source:25000cells];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    containers = result.state.artifacts["material_state"]["containers"]
    assert containers["Source"]["volume_uL"] == 75.0
    assert containers["Target"]["volume_uL"] == 25.0
    assert containers["Source"]["component_quantities"]["RPE1"]["value"] == 75000.0
    assert containers["Target"]["component_quantities"]["RPE1"]["value"] == 25000.0
    assert containers["Target"]["material_relationships"][0]["concentration"]["value"] == 1000.0
    assert containers["Target"]["material_relationships"][0]["concentration"]["source"] == "default"
    assert "ASSUMED_CELL_SUSPENSION_CONCENTRATION" in [d.code for d in result.diagnostics]


def test_runtime_marks_default_suspension_concentration_as_derived_after_dilution():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 200uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells
  ]);
  let target = tube(label = "Target", capacity = 100uL, load = [
    content(kind = formulation, type = buffer, code = "PBS"):50uL
  ]);
  target << [source:25000cells];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    relationship = result.state.artifacts["material_state"]["containers"]["Target"]["material_relationships"][0]
    assert relationship["carrier_volume_uL"] == 75.0
    assert relationship["concentration"]["value"] == pytest.approx(25000.0 / 75.0)
    assert relationship["concentration"]["source"] == "derived"
    assert relationship["assumption_policy_ids"] == ["default_cell_suspension_concentration"]


def test_runtime_does_not_treat_formulation_supplement_as_cell_carrier():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 200uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = supplement, code = "SUPPLEMENT"):50uL
  ]);
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    source = result.state.artifacts["material_state"]["containers"]["Source"]
    relationship = source["material_relationships"][0]
    assert relationship["carrier_component_ids"] == ["__implicit_cell_carrier__::Source"]
    assert relationship["carrier_volume_uL"] == 100.0
    assert relationship["concentration"]["value"] == 1000.0
    assert source["volume_uL"] == 150.0


def test_runtime_cell_count_transfer_uses_explicit_carrier_concentration_and_moves_all_contents():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 250uL, load = [
    content(kind = formulation, type = medium, code = "MEDIUM"):200uL,
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells
  ]);
  let target = tube(label = "Target", capacity = 100uL);
  target << [source:25000cells];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    containers = result.state.artifacts["material_state"]["containers"]
    assert containers["Source"]["volume_uL"] == 150.0
    assert containers["Target"]["volume_uL"] == 50.0
    assert containers["Target"]["component_quantities"]["RPE1"]["value"] == 25000.0
    assert containers["Target"]["component_quantities"]["MEDIUM"]["value"] == 50.0
    relationship = containers["Target"]["material_relationships"][0]
    assert relationship["concentration"]["value"] == 500.0
    assert relationship["concentration"]["source"] == "derived"


def test_runtime_count_transfer_uses_carrier_volume_not_cross_axis_bulk_proxy():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 500uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL,
    content(kind = chemical, type = inorganic_compound, code = "SALT"):10mg
  ]);
  let target = tube(label = "Target", capacity = 100uL);
  target << [source:25000cells];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    target = result.state.artifacts["material_state"]["containers"]["Target"]
    assert target["volume_uL"] == 77.5
    assert target["component_quantities"]["MEDIUM"]["value"] == 75.0
    assert target["component_quantities"]["SALT"]["value"] == 2.5
    relationship = target["material_relationships"][0]
    assert relationship["carrier_volume_uL"] == 75.0
    assert relationship["concentration"]["value"] == pytest.approx(100000.0 / 300.0)

    mutation_step_id = next(
        step.step_id for protocol in plan.plans for step in protocol.steps if step.op == "Mutation"
    )
    mutation_event = next(
        event for event in result.events if event.kind == "STEP_COMPLETED" and event.step_id == mutation_step_id
    )
    transfer_delta = mutation_event.payload["material_delta"]["sources"][0]["transfer_delta"]
    assert transfer_delta["resolved_transfer_volume_uL"] == 75.0
    assert transfer_delta["moved_bulk_volume_uL"] == 77.5
    assert transfer_delta["component_ratio"] == 0.25
    assert transfer_delta["concentration_cells_per_uL"] == pytest.approx(100000.0 / 300.0)


def test_runtime_count_transfer_capacity_uses_physical_carrier_volume():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 500uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL,
    content(kind = chemical, type = inorganic_compound, code = "SALT"):10mg
  ]);
  let target = tube(label = "Target", capacity = 76uL);
  target << [source:25000cells];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    target = result.state.artifacts["material_state"]["containers"]["Target"]
    assert target["component_quantities"]["MEDIUM"]["value"] == 75.0
    assert target["volume_uL"] == 77.5


def test_runtime_resolves_cell_count_to_volume_before_driver_execution():
    class CapturingHumanDriver:
        def __init__(self):
            self.delegate = HumanDriver()
            self.executed_steps = []

        def check(self, step):
            return self.delegate.check(step)

        def execute(self, step):
            self.executed_steps.append(step)
            return self.delegate.execute(step)

    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 500uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  let target = tube(label = "Target", capacity = 100uL);
  target << [source:25000cells];
}
"""
    )
    driver = CapturingHumanDriver()

    result = run(plan=plan, driver=driver)

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    mutation_step = next(step for step in driver.executed_steps if step.op == "Mutation")
    assert mutation_step.args["sources"][0]["right"]["unit"] == "uL"
    assert mutation_step.args["sources"][0]["right"]["value"] == 75.0
    resolution = mutation_step.args["_runtime_material_resolution"]["sources"][0]
    assert resolution["requested"]["value"] == 25000.0
    assert resolution["requested"]["unit"] == "cells"
    mutation_event = next(
        event for event in result.events if event.kind == "STEP_COMPLETED" and event.step_id == mutation_step.step_id
    )
    assert mutation_event.payload["driver_payload"]["binding"]["pipette_label"] == "P200 single-channel pipette"
    assert "25000.0cells corresponds to 75.0uL" in " ".join(
        mutation_event.payload["driver_payload"]["instruction"]["details"]
    )


def test_runtime_does_not_dispatch_internal_constructor_finalizer_to_driver():
    class FinalizerRejectingDriver:
        def __init__(self):
            self.delegate = StubDriver()
            self.executed_ops = []

        def check(self, step):
            assert step.op != "FinalizeContainerContents"
            return self.delegate.check(step)

        def execute(self, step):
            assert step.op != "FinalizeContainerContents"
            self.executed_ops.append(step.op)
            return self.delegate.execute(step)

    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 200uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells
  ]);
}
"""
    )
    driver = FinalizerRejectingDriver()

    result = run(plan=plan, driver=driver)

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    assert "FinalizeContainerContents" not in driver.executed_ops
    finalize_event = next(
        event
        for event in result.events
        if event.kind == "STEP_COMPLETED" and event.payload.get("driver_code") == "RUNTIME_MATERIAL_INTERNAL"
    )
    assert finalize_event.payload["driver_payload"] == {
        "op": "FinalizeContainerContents",
        "internal": True,
    }


def test_runtime_rejects_cell_count_transfer_from_adherent_cells_without_resuspension():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = surface(label = "Culture", load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1", attrs = { state: adherent }):100000cells
  ]);
  let target = tube(label = "Target", capacity = 100uL);
  target << [source:25000cells];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert "MAT_COUNT_TRANSFER_SOURCE_NOT_SUSPENSION" in [d.code for d in result.diagnostics]
    source = result.state.artifacts["material_state"]["containers"]["Culture"]
    assert source["volume_uL"] == 0.0
    assert source["material_relationships"][0]["material_state"] == "adherent"


@pytest.mark.parametrize("declared_attrs", ["state: adherent", "culture_state: adherent_monolayer"])
def test_runtime_volume_transfer_releases_adherent_cells_from_the_source_surface(declared_attrs):
    plan = _build_plan_from_source(
        f"""
protocol T {{
  let source = tube(label = "Culture", capacity = 200uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1", attrs = {{ {declared_attrs} }}):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):200uL
  ]);
  let target = tube(label = "Lysate", capacity = 100uL);
  target << [source:100uL];
  let separated = sep(sample = target, program = centrifuge_program(drive = 12000g));
}}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material = result.state.artifacts["material_state"]
    source = material["containers"]["Culture"]
    slots = material["indexed_bindings"]["separated"]
    supernatant = material["containers"][slots["0"]]
    pellet = material["containers"][slots["1"]]
    assert source["component_quantities"]["RPE1"]["value"] == 50000.0
    assert source["material_relationships"][0]["material_state"] == "adherent"
    assert supernatant["component_quantities"]["RPE1"]["value"] == 0.0
    assert pellet["component_quantities"]["RPE1"]["value"] == 50000.0
    assert supernatant["material_relationships"] == []
    assert pellet["material_relationships"][0]["material_state"] == "pellet"


def test_runtime_adherent_transfer_replaces_stale_retained_fraction_before_centrifugation():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Culture", capacity = 200uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1", attrs = { state: adherent }):100000cells,
    content(kind = formulation, type = medium, code = "CULTURE_MEDIUM"):100uL
  ]);
  sep(
    sample = source,
    program = filtration_program(membrane = "adherent_cell_surface", drive = "aspiration")
  );
  let lysis_buffer = tube(label = "LysisBuffer", capacity = 100uL, load = [
    content(kind = formulation, type = buffer, code = "LYSIS_BUFFER", attrs = { role: lysis }):100uL
  ]);
  source << [lysis_buffer:100uL];
  let lysate = tube(label = "Lysate", capacity = 200uL);
  lysate << [source:200uL];
  let separated = sep(sample = lysate, program = centrifuge_program(drive = 12000g));
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material = result.state.artifacts["material_state"]
    slots = material["indexed_bindings"]["separated"]
    supernatant = material["containers"][slots["0"]]
    pellet = material["containers"][slots["1"]]
    assert supernatant["component_quantities"]["RPE1"]["value"] == 0.0
    assert pellet["component_quantities"]["RPE1"]["value"] == 100000.0
    assert supernatant["metadata"]["component_partition_classes"]["RPE1"] == "pelletable_cells"


def test_runtime_rejects_ambiguous_count_transfer_with_multiple_cell_populations():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 200uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):50000cells,
    content(kind = bio_cellular, type = cell_line, code = "HEK293"):50000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):100uL
  ]);
  let target = tube(label = "Target", capacity = 50uL);
  target << [source:25000cells];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert "MAT_COUNT_TRANSFER_AMBIGUOUS" in [d.code for d in result.diagnostics]


def test_runtime_count_diagnostic_order_is_shared_and_material_error_prevents_dispatch():
    class CapturingDriver:
        def __init__(self):
            self.delegate = StubDriver()
            self.executed_ops = []

        def check(self, step):
            return self.delegate.check(step)

        def execute(self, step):
            self.executed_ops.append(step.op)
            return self.delegate.execute(step)

    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 200uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):50000cells,
    content(kind = bio_cellular, type = cell_line, code = "HEK293"):50000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):100uL
  ]);
  let target = tube(label = "Target", capacity = 200uL);
  target << [source:200000cells];
}
"""
    )
    driver = CapturingDriver()

    result = run(plan=plan, driver=driver)

    assert not result.ok
    codes = [d.code for d in result.diagnostics]
    assert "MAT_COUNT_TRANSFER_AMBIGUOUS" in codes
    assert "MAT_INSUFFICIENT_COUNT" not in codes
    assert "Mutation" not in driver.executed_ops


def test_runtime_frac_rebuilds_transferable_suspension_relationships():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 100uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):100uL
  ]);
  let fractions = frac(
    sample = source,
    program = density_gradient_program(axis = density, order = top_to_bottom, bins = 4)
  );
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    material = result.state.artifacts["material_state"]
    slots = material["indexed_bindings"]["fractions"]
    for slot_id in slots.values():
        fraction = material["containers"][slot_id]
        assert fraction["volume_uL"] == 25.0
        assert fraction["component_quantities"]["RPE1"]["value"] == 25000.0
        relationship = fraction["material_relationships"][0]
        assert relationship["material_state"] == "suspension"
        assert relationship["transferability"] == "homogeneous_aliquot"
        assert relationship["concentration"]["value"] == 1000.0


def test_runtime_authored_fate_contents_count_transfer_uses_shared_carrier_resolution_fields():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 300uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  sep(
    sample = source,
    program = centrifuge_program(drive = 12000g),
    component_fates = { RPE1: { supernatant: 1%, pellet: 99% } }
  );
  let target = tube(label = "Target", capacity = 200uL);
  target << [source.contents[0]:500cells];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    target = result.state.artifacts["material_state"]["containers"]["Target"]
    assert target["component_quantities"]["RPE1"]["value"] == 500.0
    assert target["component_quantities"]["MEDIUM"]["value"] == 150.0

    mutation_step_id = next(
        step.step_id for protocol in plan.plans for step in protocol.steps if step.op == "Mutation"
    )
    mutation_event = next(
        event for event in result.events if event.kind == "STEP_COMPLETED" and event.step_id == mutation_step_id
    )
    transfer_delta = mutation_event.payload["material_delta"]["sources"][0]
    assert transfer_delta["mode"] == "contents_state_count_resolved_volume"
    assert transfer_delta["resolved_transfer_volume_uL"] == 150.0
    assert transfer_delta["moved_bulk_volume_uL"] == 150.0
    assert transfer_delta["component_ratio"] == 0.5
    assert transfer_delta["concentration_cells_per_uL"] == pytest.approx(1000.0 / 300.0)
    assert transfer_delta["concentration_source"] == "derived"
    assert transfer_delta["policy_id"] == "explicit_carrier_volume"
    contents_part = result.state.artifacts["material_state"]["contents_states"]["Source"]["parts"]["0"]
    assert contents_part["component_quantities"]["RPE1"]["value"] == 500.0
    assert contents_part["component_quantities"]["MEDIUM"]["value"] == 150.0
    assert contents_part["material_relationships"][0]["carrier_volume_uL"] == 150.0


def test_runtime_centrifuge_routes_cell_count_to_pellet_and_allows_downstream_transfer():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 300uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  let separated = sep(
    sample = source,
    program = centrifuge_program(drive = 12000g)
  );
  let pellet = tube(label = "Pellet", capacity = 20uL);
  pellet << [separated[1]];
  return pellet;
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    material = result.state.artifacts["material_state"]
    slots = material["indexed_bindings"]["separated"]
    supernatant = material["containers"][slots["0"]]
    pellet = material["containers"]["Pellet"]

    assert supernatant["volume_uL"] == 300.0
    assert pellet["volume_uL"] == 0.0
    assert supernatant["mass_mg"] == 300.0
    assert pellet["mass_mg"] == 0.0
    assert supernatant["component_quantities"]["RPE1"] == {
        "dimension": "count",
        "unit": "cells",
        "value": 0.0,
    }
    assert pellet["component_quantities"]["RPE1"] == {
        "dimension": "count",
        "unit": "cells",
        "value": 100000.0,
    }
    assert supernatant["component_quantities"]["MEDIUM"]["value"] == 300.0
    assert pellet["component_quantities"]["MEDIUM"]["value"] == 0.0
    assert supernatant["component_quantities"]["RPE1"]["value"] + pellet["component_quantities"]["RPE1"]["value"] == 100000.0
    assert supernatant["volume_uL"] + pellet["volume_uL"] == 300.0
    assert supernatant["mass_mg"] + pellet["mass_mg"] == 300.0
    returned = result.state.artifacts["protocol_outputs"]["T"]["value"]
    assert returned["count_cells"] == 100000.0
    assert supernatant["material_relationships"] == []
    cell_relationship = next(
        relationship
        for relationship in pellet["material_relationships"]
        if relationship.get("subtype") == "cell_suspension"
    )
    assert cell_relationship["material_state"] == "pellet"
    assert cell_relationship["transferability"] == "non_homogeneous"


def test_runtime_centrifuge_supernatant_report_does_not_select_zero_cell_component():
    plan = _build_plan_from_source(
        """
protocol T returns (clarified) {
  let source = tube(label = "Source", capacity = 300uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  let separated = sep(sample = source, program = centrifuge_program(drive = 12000g));
  let clarified = tube(label = "Clarified", capacity = 200uL);
  clarified << [separated[0]:100uL];
  return clarified = clarified;
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    assert result.user_result is not None
    clarified = next(
        item for item in result.user_result["materials"]["final_products"] if item["name"] == "Clarified"
    )
    assert clarified["primary_component"] == "MEDIUM"
    assert "count_cells" not in clarified


def test_runtime_rejects_count_aliquot_from_centrifuge_pellet():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 300uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  let separated = sep(sample = source, program = centrifuge_program(drive = 12000g));
  let target = tube(label = "Target", capacity = 100uL);
  target << [separated[1]:25000cells];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert "MAT_COUNT_TRANSFER_SOURCE_NOT_SUSPENSION" in [d.code for d in result.diagnostics]


@pytest.mark.parametrize("use_contents", [False, True])
def test_runtime_zero_cell_transfer_is_a_shared_noop(use_contents):
    separation = (
        'sep(sample = source, program = centrifuge_program(drive = 12000g));'
        if use_contents
        else 'let separated = sep(sample = source, program = centrifuge_program(drive = 12000g));'
    )
    source_expr = "source.contents[1]" if use_contents else "separated[1]"
    plan = _build_plan_from_source(
        f"""
protocol T {{
  let source = tube(label = "Source", capacity = 300uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  {separation}
  let target = tube(label = "Target", capacity = 100uL);
  target << [{source_expr}:0cells];
}}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    target = result.state.artifacts["material_state"]["containers"]["Target"]
    assert target["volume_uL"] == 0.0
    assert target.get("component_quantities", {}) == {}


def test_runtime_rejects_count_aliquot_from_precipitate():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 300uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  let parts = sep(
    sample = source,
    program = precipitation_program(reagent = "x"),
    component_fates = {
      RPE1: { precipitate: 100%, supernatant: 0% }
    }
  );
  let target = tube(label = "Target", capacity = 300uL);
  target << [parts[0]:25000cells];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert "MAT_COUNT_TRANSFER_SOURCE_NOT_SUSPENSION" in [d.code for d in result.diagnostics]
    material = result.state.artifacts["material_state"]
    precipitate_id = material["indexed_bindings"]["parts"]["0"]
    relationship = material["containers"][precipitate_id]["material_relationships"][0]
    assert relationship["material_state"] == "precipitate"
    assert relationship["transferability"] == "non_homogeneous"


def test_runtime_filtration_partitions_cell_count_and_carrier_volume_independently():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 300uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1", attrs = { filter_retains: true }):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  let filtered = sep(sample = source, program = filtration_program(membrane = "0.2um", drive = "pressure"));
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    material = result.state.artifacts["material_state"]
    slots = material["indexed_bindings"]["filtered"]
    filtrate = material["containers"][slots["0"]]
    retentate = material["containers"][slots["1"]]
    assert filtrate["volume_uL"] == 300.0
    assert retentate["volume_uL"] == 0.0
    assert filtrate["mass_mg"] == 300.0
    assert retentate["mass_mg"] == 0.0
    assert filtrate["component_quantities"]["RPE1"]["value"] == 0.0
    assert retentate["component_quantities"]["RPE1"]["value"] == 100000.0
    assert retentate["material_relationships"][0]["material_state"] == "suspension"


def test_runtime_aspiration_keeps_adherent_cells_and_contents_transfer_preserves_conservation():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 300uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1", attrs = { state: adherent }):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  sep(
    sample = source,
    program = filtration_program(membrane = "adherent_cell_surface", drive = "aspiration")
  );
  let removed = tube(label = "Removed", capacity = 300uL);
  removed << [source.contents[0]];
  let retained = tube(label = "Retained", capacity = 10uL);
  retained << [source.contents[1]];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    containers = result.state.artifacts["material_state"]["containers"]
    assert containers["Removed"]["component_quantities"]["RPE1"]["value"] == 0.0
    assert containers["Retained"]["component_quantities"]["RPE1"]["value"] == 100000.0
    assert containers["Removed"]["component_quantities"]["MEDIUM"]["value"] == 300.0
    assert containers["Retained"]["component_quantities"]["MEDIUM"]["value"] == 0.0
    assert containers["Retained"]["material_relationships"][0]["material_state"] == "suspension"
    assert (
        containers["Removed"]["component_quantities"]["RPE1"]["value"]
        + containers["Retained"]["component_quantities"]["RPE1"]["value"]
        == 100000.0
    )


def test_runtime_author_component_fates_override_reference_prediction_with_semantic_slot_names():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 300uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  let filtered = sep(
    sample = source,
    program = filtration_program(membrane = "adherent_cell_surface", drive = "aspiration"),
    component_fates = {
      RPE1: { filtrate: 25%, retentate: 75% }
    }
  );
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material = result.state.artifacts["material_state"]
    slots = material["indexed_bindings"]["filtered"]
    filtrate = material["containers"][slots["0"]]
    retentate = material["containers"][slots["1"]]
    assert filtrate["component_quantities"]["RPE1"]["value"] == 25000.0
    assert retentate["component_quantities"]["RPE1"]["value"] == 75000.0

    sep_step_id = next(step.step_id for protocol in plan.plans for step in protocol.steps if step.op == "sep")
    sep_event = next(
        event for event in result.events if event.kind == "STEP_COMPLETED" and event.step_id == sep_step_id
    )
    fate = sep_event.payload["material_delta"]["partition"]["fates_by_component"]["RPE1"]
    assert fate["source"] == "author_explicit_fate"
    assert fate["ratios"] == {"0": 0.25, "1": 0.75}


def test_runtime_volume_transfer_uses_bulk_projected_from_author_component_fate():
    plan = _build_plan_from_source(
        """
protocol T returns (supernatant) {
  let source = tube(label = "Source", capacity = 100uL, load = [
    content(kind = bio_molecule_or_virus, type = dna, code = "AMPLIFIED_CDNA"):100uL
  ]);
  let supernatant = tube(label = "Supernatant", capacity = 100uL);
  let parts = sep(
    sample = source,
    program = magnetic_program(duration = 2min),
    component_fates = {
      AMPLIFIED_CDNA: { bound: 1%, flowthrough: 99% }
    }
  );
  supernatant << [parts[1]:90uL];
  return supernatant = supernatant;
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material = result.state.artifacts["material_state"]
    supernatant = material["containers"][material["bindings"]["supernatant"]]
    assert supernatant["volume_uL"] == 90.0
    assert supernatant["component_quantities"]["AMPLIFIED_CDNA"]["value"] == 90.0


@pytest.mark.parametrize(
    ("rule", "expected_code"),
    [
        ("{ RPE1: { filtrate: 20%, retentate: 70% } }", "SEM_SEPARATION_FATE_RULE_TOTAL_INVALID"),
        ("{ RPE1: { liquid: 20%, retentate: 80% } }", "SEM_SEPARATION_FATE_RULE_SLOT_INVALID"),
        ("{ RPE1: { filtrate: 20% } }", "SEM_SEPARATION_FATE_RULE_SHAPE_INVALID"),
        ("{ RPE1: { filtrate: 20uL, retentate: 80% } }", "SEM_SEPARATION_FATE_RULE_VALUE_INVALID"),
    ],
)
def test_frontend_rejects_invalid_author_component_fates(rule, expected_code):
    source = f"""
protocol T {{
  let source = tube(label = "Source", capacity = 300uL);
  let filtered = sep(
    sample = source,
    program = filtration_program(membrane = "0.2um", drive = "pressure"),
    component_fates = {rule}
  );
}}
"""
    compile_result = _compile_ast(resolve_program(parse(source)).prepared_program)
    sem = _validate(compile_result.ir, analysis=compile_result.analysis)

    assert expected_code in [diagnostic.code for diagnostic in sem.diagnostics]


def test_runtime_rejects_author_fate_for_content_not_present_in_source():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 100uL, load = [
    content(kind = formulation, type = medium, code = "MEDIUM"):100uL
  ]);
  sep(
    sample = source,
    program = filtration_program(membrane = "0.2um", drive = "pressure"),
    component_fates = { MISSING: { filtrate: 100%, retentate: 0% } }
  );
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert not result.ok
    assert "MAT_SEPARATION_FATE_COMPONENT_NOT_FOUND" in [
        diagnostic.code for diagnostic in result.diagnostics
    ]


def test_runtime_sep_preserves_bulk_with_count_volume_and_mass_components():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 500uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL,
    content(kind = chemical, type = inorganic_compound, code = "SALT"):10mg
  ]);
  let separated = sep(sample = source, program = centrifuge_program(drive = 12000g));
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material = result.state.artifacts["material_state"]
    slots = material["indexed_bindings"]["separated"]
    outputs = [material["containers"][slots[index]] for index in ("0", "1")]
    assert sum(output["volume_uL"] for output in outputs) == 310.0
    assert sum(output["mass_mg"] for output in outputs) == 310.0
    assert sum(output["component_quantities"]["RPE1"]["value"] for output in outputs) == 100000.0


def test_runtime_source_partition_preserves_mixed_axis_bulk_and_components():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 500uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL,
    content(kind = chemical, type = inorganic_compound, code = "SALT"):10mg
  ]);
  let target = tube(label = "Target", capacity = 500uL);
  target << [source.partition(centrifuge_program(drive = 12000g))[1]];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    containers = result.state.artifacts["material_state"]["containers"]
    source = containers["Source"]
    target = containers["Target"]
    assert source["volume_uL"] + target["volume_uL"] == 310.0
    assert source["mass_mg"] + target["mass_mg"] == 310.0
    for component_id, expected in {"RPE1": 100000.0, "MEDIUM": 300.0, "SALT": 10.0}.items():
        assert (
            source["component_quantities"][component_id]["value"]
            + target["component_quantities"][component_id]["value"]
            == expected
        )
    assert target["material_relationships"][0]["material_state"] == "pellet"


def test_runtime_magnetic_source_partition_count_transfer_uses_shared_carrier_resolution():
    plan = _build_plan_from_source(
        """
protocol T {
  let source = tube(label = "Source", capacity = 300uL, load = [
    content(kind = bio_cellular, type = cell_line, code = "RPE1"):100000cells,
    content(kind = formulation, type = medium, code = "MEDIUM"):300uL
  ]);
  let target = tube(label = "Target", capacity = 200uL);
  target << [source.partition(magnetic_program(duration = 2min))[1]:500cells];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    target = result.state.artifacts["material_state"]["containers"]["Target"]
    assert target["component_quantities"]["RPE1"]["value"] == pytest.approx(500.0)
    assert target["component_quantities"]["MEDIUM"]["value"] == pytest.approx(1.5)
    assert target["material_relationships"][0]["carrier_volume_uL"] == pytest.approx(1.5)

    mutation_step_id = next(
        step.step_id for protocol in plan.plans for step in protocol.steps if step.op == "Mutation"
    )
    mutation_event = next(
        event for event in result.events if event.kind == "STEP_COMPLETED" and event.step_id == mutation_step_id
    )
    transfer_delta = mutation_event.payload["material_delta"]["sources"][0]["transfer_delta"]["transfer"]
    assert transfer_delta["mode"] == "count_resolved_volume"
    assert transfer_delta["resolved_transfer_volume_uL"] == pytest.approx(1.5)
    assert transfer_delta["moved_bulk_volume_uL"] == pytest.approx(1.5)
    assert transfer_delta["component_ratio"] == pytest.approx(500.0 / 100000.0)


def test_runtime_executes_centrifugal_filtration_with_filtration_slots():
    plan = _build_plan_from_source(
        """
protocol T {
  let column = tube(label = "SpinColumn", capacity = 500uL, load = [
    content(kind = "biosample", code = "DNA", type = "dna_sample", attrs = { filter_retains: true }):100uL,
    buffer(code = "WASH", type = "buffer"):100uL
  ]);
  let filter_group = sep(
    sample = column,
    program = centrifugal_filtration_program(
      membrane = "silica",
      drive = 8000g,
      duration = 1min
    )
  );
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok, [d.to_dict() for d in result.diagnostics]
    material = result.state.artifacts["material_state"]
    slots = material["indexed_bindings"]["filter_group"]
    assert material["containers"][slots["0"]]["components"] == {"DNA": 0.0, "WASH": 100.0}
    assert material["containers"][slots["1"]]["components"] == {"DNA": 100.0, "WASH": 0.0}


def test_runtime_append_mutates_data_group_items():
    plan = _build_plan_from_source(
        """
protocol T {
  let reads = data_group_ref(kind = sequence_read);
  let read = data_ref(kind = sequence_read);
  reads.items.append(read);
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    reads = result.state.artifacts["local_bindings"]["reads"]
    assert reads["kind"] == "data_group_ref"
    assert len(reads["items"]) == 1
    assert reads["items"][0]["kind"] == "data_ref"


def test_runtime_materializes_marker_panel_ref_shell():
    plan = _build_plan_from_source(
        """
protocol T {
  let panel = markers(["CD3", "CD19"]);
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    panel = result.state.artifacts["local_bindings"]["panel"]
    assert panel["kind"] == "marker_panel_ref"
    assert panel["label"] == "panel"
    assert panel["items"] == ["CD3", "CD19"]


def test_runtime_materializes_stream_shell_with_seeded_items():
    plan = _build_plan_from_source(
        """
protocol T {
  let cells = tube(label = "Cells", capacity = 500uL);
  let panel = markers(["CD3", "CD19"]);
  let events = stream(sample = cells, unit = single_cell, panel = panel);
}
"""
    )
    state = init_state(plan)
    state.artifacts["stream_units"] = {"events": ["cell_0", "cell_1"]}

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert result.ok
    panel = result.state.artifacts["local_bindings"]["panel"]
    events = result.state.artifacts["local_bindings"]["events"]
    assert panel["kind"] == "marker_panel_ref"
    assert events["kind"] == "unit_stream_ref"
    assert events["id"] == "events"
    assert events["unit_kind"] == "single_cell"
    assert events["panel_ref"]["kind"] == "marker_panel_ref"
    assert events["panel_ref"]["label"] == "panel"
    assert [item["id"] for item in events["items"]] == ["cell_0", "cell_1"]
    assert all(item["kind"] == "unit_ref" for item in events["items"])
    assert all(item["stream_ref"] == "events" for item in events["items"])
    assert all(item["unit_kind"] == "single_cell" for item in events["items"])


def test_runtime_repeat_bind_executes_body_once_per_seeded_unit():
    plan = _build_plan_from_source(
        """
protocol T {
  let cells = tube(label = "Cells", capacity = 500uL);
  let events = stream(sample = cells, unit = single_cell);
  let reads = data_group_ref(kind = sequence_read);
  repeat cell in events {
    let read = data_ref(kind = sequence_read, subject_ref = cell);
    reads.items.append(read);
  }
}
"""
    )
    state = init_state(plan)
    state.artifacts["stream_units"] = {"events": ["cell_0", "cell_1"]}

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert result.ok
    reads = result.state.artifacts["local_bindings"]["reads"]
    assert [item["subject_ref"]["id"] for item in reads["items"]] == ["cell_0", "cell_1"]
    assert "cell" not in result.state.artifacts["local_bindings"]


def test_runtime_repeat_bind_break_stops_later_iterations():
    plan = _build_plan_from_source(
        """
protocol T {
  let cells = tube(label = "Cells", capacity = 500uL);
  let events = stream(sample = cells, unit = single_cell);
  let reads = data_group_ref(kind = sequence_read);
  repeat cell in events {
    let read = data_ref(kind = sequence_read, subject_ref = cell);
    reads.items.append(read);
    break;
  }
}
"""
    )
    state = init_state(plan)
    state.artifacts["stream_units"] = {"events": ["cell_0", "cell_1", "cell_2"]}

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert result.ok
    reads = result.state.artifacts["local_bindings"]["reads"]
    assert [item["subject_ref"]["id"] for item in reads["items"]] == ["cell_0"]


def test_runtime_repeat_bind_continue_skips_only_current_iteration_tail():
    plan = _build_plan_from_source(
        """
protocol T {
  let cells = tube(label = "Cells", capacity = 500uL);
  let events = stream(sample = cells, unit = single_cell);
  let reads = data_group_ref(kind = sequence_read);
  repeat cell in events {
    if cell.id == "cell_0" {
      continue;
    }
    let read = data_ref(kind = sequence_read, subject_ref = cell);
    reads.items.append(read);
  }
}
"""
    )
    state = init_state(plan)
    state.artifacts["stream_units"] = {"events": ["cell_0", "cell_1"]}

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert result.ok
    reads = result.state.artifacts["local_bindings"]["reads"]
    assert [item["subject_ref"]["id"] for item in reads["items"]] == ["cell_1"]


def test_runtime_repeat_bind_can_collect_unit_into_container():
    plan = _build_plan_from_source(
        """
protocol T {
  let cells = tube(label = "Cells", capacity = 500uL);
  let keep_tube = tube(label = "Keep", capacity = 500uL);
  let events = stream(sample = cells, unit = single_cell);
  repeat cell in events {
    keep_tube << [cell];
  }
}
"""
    )
    state = init_state(plan)
    state.artifacts["stream_units"] = {"events": ["cell_0", "cell_1"]}

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert result.ok
    material = result.state.artifacts["material_state"]
    keep_id = material["bindings"]["keep_tube"]
    keep = material["containers"][keep_id]
    assert [unit["id"] for unit in keep["metadata"]["collected_units"]] == ["cell_0", "cell_1"]
    assert keep["metadata"]["unit_count"] == 2


def test_runtime_repeat_bind_rejects_quantified_unit_source():
    plan = _build_plan_from_source(
        """
protocol T {
  let cells = tube(label = "Cells", capacity = 500uL);
  let keep_tube = tube(label = "Keep", capacity = 500uL);
  let events = stream(sample = cells, unit = single_cell);
  repeat cell in events {
    keep_tube << [cell:1uL];
  }
}
"""
    )
    state = init_state(plan)
    state.artifacts["stream_units"] = {"events": ["cell_0"]}

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert not result.ok
    assert "MAT_UNIT_QUANTITY_UNSUPPORTED" in [d.code for d in result.diagnostics]


def test_runtime_append_auto_creates_nested_result_list():
    plan = _build_plan_from_source(
        """
protocol T {
  let read = data_ref(kind = sequence_read);
  read.result.sequence.append("A");
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    read = result.state.artifacts["local_bindings"]["read"]
    assert read["result"]["sequence"] == ["A"]


def test_runtime_data_ref_constructor_seeds_result_from_schema_ref():
    plan = _build_plan_from_source(
        """
protocol T {
  let seq_schema = data_schema(label = "Seq", fields = [sequence, signal]);
  let read = data_ref(kind = sequence_read, schema_ref = seq_schema);
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    read = result.state.artifacts["local_bindings"]["read"]
    assert read["result"]["sequence"] is None
    assert read["result"]["signal"] is None


def test_runtime_member_assignment_writes_nested_data_result_fields():
    plan = _build_plan_from_source(
        """
protocol T {
  let read = data_ref(kind = sequence_read);
  read.result.hit = true;
  read.result.sequence = [];
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    read = result.state.artifacts["local_bindings"]["read"]
    assert read["result"]["hit"] is True
    assert read["result"]["sequence"] == []


def test_runtime_detects_predicate_reads_runtime_sensing_hook():
    plan = _build_plan_from_source(
        """
protocol T {
  let detector_surface = surface(label = "Detector_Surface");
  let ion = data_ref(kind = ion_event);
  if detector_surface.detects(ion) {
    let hit_record = data_ref(kind = ion_hit);
  }
}
"""
    )
    state = init_state(plan)
    state.artifacts["detect_hits"] = {"detector_surface": ["ion"]}

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert result.ok
    assert "hit_record" in result.state.artifacts["local_bindings"]


def test_runtime_readout_schema_ref_seeds_and_accepts_driver_payload_fields():
    plan = _build_plan_from_source(
        """
protocol T {
  let detector_surface = surface(label = "Detector_Surface");
  let current_schema = data_schema(label = "MS_Current_Obs", fields = [current_pulse, arrival_time]);
  let obs = phy(sample = detector_surface, quantity = current, schema_ref = current_schema);
}
"""
    )
    result = run(
        plan=plan,
        driver=StubDriver(
            op_payloads={
                "phy": {
                    "result": {
                        "current_pulse": 12.5,
                        "arrival_time": 4.2,
                    }
                }
            }
        ),
    )

    assert result.ok
    data_id = result.state.artifacts["data_bindings"]["obs"]
    record = result.state.artifacts["data_objects"][data_id]
    assert record["result"]["current"] is None
    assert record["result"]["current_pulse"] == 12.5
    assert record["result"]["arrival_time"] == 4.2


def test_runtime_detects_predicate_defaults_false_without_hit():
    plan = _build_plan_from_source(
        """
protocol T {
  let detector_surface = surface(label = "Detector_Surface");
  let ion = data_ref(kind = ion_event);
  if detector_surface.detects(ion) {
    let hit_record = data_ref(kind = ion_hit);
  }
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    branch_step = [step for protocol in plan.plans for step in protocol.steps if step.args.get("target") == "hit_record"][0]
    assert result.state.step_status[branch_step.step_id] == "skipped"
    assert result.state.artifacts["skip_reasons"][branch_step.step_id] == "runtime_condition_false"
    assert "hit_record" not in result.state.artifacts["local_bindings"]


def test_runtime_captures_named_protocol_outputs():
    plan = _build_plan_from_source(
        """
protocol T(sample = "A") returns (prepared_out, seq_out) {
  let reads = data_group_ref(kind = sequence_read);
  return prepared_out = sample, seq_out = reads;
}
"""
    )
    result = run(plan=plan, driver=StubDriver(), state=_runtime_state_with_source(plan))

    assert result.ok
    outputs = result.state.artifacts["protocol_outputs"]["T"]
    assert outputs["returns"] == ["prepared_out", "seq_out"]
    assert outputs["bindings"]["prepared_out"] == "A"
    assert outputs["bindings"]["seq_out"]["kind"] == "data_group_ref"


def test_runtime_captures_single_protocol_return_value():
    plan = _build_plan_from_source(
        """
protocol T() returns (prepared_out) {
  let stock = tube(label = "Stock", capacity = 100uL, load = [content(kind = "biosample", code = "DNA001", type = "dna_sample"):100uL]);
  let prepared = tube(label = "Prepared", capacity = 100uL);
  prepared << [stock:40uL];
  return prepared;
}
"""
    )
    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    outputs = result.state.artifacts["protocol_outputs"]["T"]
    assert outputs == {
        "protocol_id": "p0",
        "protocol_name": "T",
        "returns": ["prepared_out"],
        "value": {
            "kind": "container_ref",
            "id": "Prepared",
            "volume_uL": 40,
            "mass_mg": 40,
            "container_kind": "tube",
            "label": "Prepared",
        },
    }
    assert result.state.artifacts["material_state"]["containers"]["Prepared"]["components"]["DNA001"] == 40.0


def test_runtime_captures_named_protocol_output_container_ref():
    plan = _build_plan_from_source(
        """
protocol T() returns (prepared_out, seq_out) {
  let stock = tube(label = "Stock", capacity = 100uL, load = [content(kind = "biosample", code = "DNA001", type = "dna_sample"):100uL]);
  let prepared = tube(label = "Prepared", capacity = 100uL);
  let reads = data_group_ref(kind = sequence_read);
  prepared << [stock:25uL];
  return prepared_out = prepared, seq_out = reads;
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    outputs = result.state.artifacts["protocol_outputs"]["T"]
    assert outputs == {
        "protocol_id": "p0",
        "protocol_name": "T",
        "returns": ["prepared_out", "seq_out"],
        "bindings": {
            "prepared_out": {
                "kind": "container_ref",
                "id": "Prepared",
                "volume_uL": 25,
                "mass_mg": 25,
                "container_kind": "tube",
                "label": "Prepared",
            },
            "seq_out": {
                "kind": "data_group_ref",
                "data_kind": "sequence_read",
                "schema_ref": None,
                "items": [],
                "result": {},
            },
        },
    }
    assert result.state.artifacts["material_state"]["containers"]["Prepared"]["components"]["DNA001"] == 25.0


def test_runtime_captures_indexed_container_return_as_container_ref():
    plan = _build_plan_from_source(
        """
protocol T() returns (supernatant_out) {
  let sample_tube = tube(label = "SampleTube", capacity = 100uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):100uL]);
  let sep_group = sep(sample = sample_tube, program = centrifuge_program(drive = 12000g));
  return sep_group[0];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    outputs = result.state.artifacts["protocol_outputs"]["T"]
    assert outputs == {
        "protocol_id": "p0",
        "protocol_name": "T",
        "returns": ["supernatant_out"],
        "value": {
            "kind": "container_ref",
            "id": "p0.s1::0",
            "volume_uL": 100,
            "mass_mg": 100,
        },
    }
    assert result.state.artifacts["material_state"]["containers"]["p0.s1::0"]["components"]["S1"] == 100.0


def test_runtime_captures_direct_container_group_return():
    plan = _build_plan_from_source(
        """
protocol T() returns (wells_out) {
  let a1 = well(label = "A1", capacity = 50uL);
  let a2 = well(label = "A2", capacity = 50uL);
  let mix = tube(label = "Mix", capacity = 100uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):50uL]);
  a1 << [mix:20uL];
  a2 << [mix:20uL];
  return wells_out = group([a1, a2]);
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    group = result.state.artifacts["protocol_outputs"]["T"]["bindings"]["wells_out"]
    assert group["kind"] == "container_group_ref"
    assert group["member_count"] == 2
    assert [member["id"] for member in group["members"]] == ["A1", "A2"]
    assert [member["container_kind"] for member in group["members"]] == ["well", "well"]
    assert [member["volume_uL"] for member in group["members"]] == [20, 20]


def test_runtime_captures_let_bound_container_group_return():
    plan = _build_plan_from_source(
        """
protocol T() returns (wells_out) {
  let a1 = well(label = "A1", capacity = 50uL);
  let a2 = well(label = "A2", capacity = 50uL);
  let mix = tube(label = "Mix", capacity = 100uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):50uL]);
  a1 << [mix:10uL];
  a2 << [mix:15uL];
  let wells = group([a1, a2]);
  return wells_out = wells;
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    group = result.state.artifacts["protocol_outputs"]["T"]["bindings"]["wells_out"]
    assert group["kind"] == "container_group_ref"
    assert group["member_count"] == 2
    assert [member["id"] for member in group["members"]] == ["A1", "A2"]
    assert [member["volume_uL"] for member in group["members"]] == [10, 15]


def test_runtime_captures_sep_group_return_as_container_group_ref():
    plan = _build_plan_from_source(
        """
protocol T() returns (fractions_out) {
  let sample_tube = tube(label = "SampleTube", capacity = 100uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):100uL]);
  let sep_group = sep(sample = sample_tube, program = centrifuge_program(drive = 12000g));
  return fractions_out = sep_group;
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    group = result.state.artifacts["protocol_outputs"]["T"]["bindings"]["fractions_out"]
    assert group["kind"] == "container_group_ref"
    assert group["member_count"] == 2
    assert [member["id"] for member in group["members"]] == ["p0.s1::0", "p0.s1::1"]
    assert [member["volume_uL"] for member in group["members"]] == [100, 0]


def test_runtime_captures_frac_group_return_as_container_group_ref():
    plan = _build_plan_from_source(
        """
protocol T() returns (fractions_out) {
  let sample_tube = tube(label = "SampleTube", capacity = 120uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):120uL]);
  let fractions = frac(sample = sample_tube, program = density_gradient_program(axis = density, order = top_to_bottom, bins = 3));
  return fractions_out = fractions;
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    group = result.state.artifacts["protocol_outputs"]["T"]["bindings"]["fractions_out"]
    assert group["kind"] == "container_group_ref"
    assert group["member_count"] == 3
    assert [member["id"] for member in group["members"]] == ["p0.s1::0", "p0.s1::1", "p0.s1::2"]
    assert [member["volume_uL"] for member in group["members"]] == [40, 40, 40]


def test_runtime_captures_plate_selector_group_return_as_container_group_ref():
    plan = _build_plan_from_source(
        """
protocol T() returns (wells_out) {
  let plate96 = plate(label = "QPCR96", format = "96well", carrier_id = "PlateA");
  let mix = tube(label = "Mix", capacity = 100uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):50uL]);
  plate96[A1:A2] << [mix:10uL];
  let wells = plate96[A1:A2];
  return wells_out = wells;
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    group = result.state.artifacts["protocol_outputs"]["T"]["bindings"]["wells_out"]
    assert group["kind"] == "container_group_ref"
    assert group["member_count"] == 2
    assert [member["id"] for member in group["members"]] == ["QPCR96_A1", "QPCR96_A2"]
    assert [member["container_kind"] for member in group["members"]] == ["well", "well"]
    assert [member["volume_uL"] for member in group["members"]] == [10, 10]


def test_runtime_captures_direct_plate_selector_return_as_container_group_ref():
    plan = _build_plan_from_source(
        """
protocol T() returns (wells_out) {
  let plate96 = plate(label = "QPCR96", format = "96well", carrier_id = "PlateA");
  let mix = tube(label = "Mix", capacity = 100uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):50uL]);
  plate96[A1:A2] << [mix:10uL];
  return wells_out = plate96[A1:A2];
}
"""
    )

    result = run(plan=plan, driver=StubDriver())

    assert result.ok
    group = result.state.artifacts["protocol_outputs"]["T"]["bindings"]["wells_out"]
    assert group["kind"] == "container_group_ref"
    assert group["member_count"] == 2
    assert [member["id"] for member in group["members"]] == ["QPCR96_A1", "QPCR96_A2"]
    assert [member["container_kind"] for member in group["members"]] == ["well", "well"]
    assert [member["volume_uL"] for member in group["members"]] == [10, 10]


def test_runtime_sequencing_style_read_accumulation_closes_minimal_loop():
    plan = _build_plan_from_source(
        """
protocol T() returns (seq_out) {
  let prepared_tube = tube(label = "Prepared", capacity = 100uL);
  let molecules = stream(sample = prepared_tube, unit = molecule);
  let seq_data = data_group_ref(kind = sequence_read);
  let sig_A = "A";
  let sig_T = "T";
  let sig_C = "C";

  repeat mol in molecules {
    let read_chamber = tube(label = "ReadChamber", capacity = 100uL);
    read_chamber << [mol];
    let read = data_ref(kind = sequence_read, subject_ref = mol, context_ref = read_chamber);
    read.result.sequence = [];

    repeat cycle in schedule(start = 1, end = 3, step = 1) {
      let obs = img(sample = read_chamber, quantity = fluorescence);
      if obs.result.signal == sig_A {
        read.result.sequence.append("A");
      } else {
        if obs.result.signal == sig_T {
          read.result.sequence.append("T");
        } else {
          if obs.result.signal == sig_C {
            read.result.sequence.append("C");
          } else {
            read.result.sequence.append("G");
          }
        }
      }
    }

    seq_data.items.append(read);
  }

  return seq_out = seq_data;
}
"""
    )
    state = init_state(plan)
    state.artifacts["stream_units"] = {"molecules": [{"id": "mol_0"}]}

    result = run(
        plan=plan,
        driver=StubDriver(op_payloads={"img": {"result": {"signal": "A"}}}),
        state=state,
    )

    assert result.ok
    outputs = result.state.artifacts["protocol_outputs"]["T"]
    seq_out = outputs["bindings"]["seq_out"]
    assert seq_out["kind"] == "data_group_ref"
    assert len(seq_out["items"]) == 1
    assert seq_out["items"][0]["result"]["sequence"] == ["A", "A", "A"]


def test_runtime_mass_spec_style_event_recording_closes_minimal_loop():
    plan = _build_plan_from_source(
        """
protocol T() returns (spectrum_out) {
  let ion_chamber = tube(label = "IonChamber", capacity = 100uL);
  let ions = stream(sample = ion_chamber, unit = ion);
  let mz_a = 1;
  let mz_t0 = 0;
  let mz_b = 0;
  let current_schema = data_schema(label = "MS_Current_Obs", fields = [current_pulse, arrival_time]);
  let event_schema = data_schema(label = "MS_Ion_Event", fields = [hit, current_pulse, arrival_time, intensity, mz]);
  let spectrum_schema = data_schema(label = "MS_Spectrum", fields = [records]);
  let spectrum_out = data_ref(kind = spectrum, context_ref = ion_chamber, schema_ref = spectrum_schema);
  spectrum_out.result.records = [];

  with env(field = mz_separation) {
    let detector_surface = surface(label = "Detector_Surface");
    repeat ion in ions {
      if detector_surface.detects(ion) {
        let event = data_ref(kind = ion_event, subject_ref = ion, context_ref = detector_surface, schema_ref = event_schema);
        event.result.hit = true;
        let obs = phy(sample = detector_surface, quantity = current, schema_ref = current_schema);
        event.result.current_pulse = obs.result.current_pulse;
        event.result.arrival_time = obs.result.arrival_time;
        event.result.intensity = event.result.current_pulse;
        event.result.mz =
          mz_a
          * (event.result.arrival_time - mz_t0)
          * (event.result.arrival_time - mz_t0)
          + mz_b;
        spectrum_out.result.records.append(event.result);
      }
    }
  }

  return spectrum_out = spectrum_out;
}
"""
    )
    state = init_state(plan)
    state.artifacts["stream_units"] = {"ions": [{"id": "ion_0"}]}
    state.artifacts["detect_hits"] = {"detector_surface": ["ion_0"]}

    result = run(
        plan=plan,
        driver=StubDriver(
            op_payloads={
                "phy": {
                    "result": {
                        "current_pulse": 12.5,
                        "arrival_time": 4.0,
                    }
                }
            }
        ),
        state=state,
    )

    assert result.ok
    outputs = result.state.artifacts["protocol_outputs"]["T"]
    spectrum_out = outputs["bindings"]["spectrum_out"]
    assert spectrum_out["kind"] == "data_ref"
    assert len(spectrum_out["result"]["records"]) == 1
    event = spectrum_out["result"]["records"][0]
    assert event["hit"] is True
    assert event["current_pulse"] == 12.5
    assert event["arrival_time"] == 4.0
    assert event["intensity"] == 12.5
    assert event["mz"] == 16.0


def test_runtime_executes_agit_step_as_normal_driver_step():
    plan = _build_plan_from_source(
        """
protocol T {
  let tube = tube(label = "Tube", capacity = 100uL);
  agit(sample = tube, mode = shake, duration = 30s, rate = 800rpm);
}
"""
    )
    result = run(plan=plan, driver=StubDriver(), state=init_state(plan))

    assert result.ok
    steps = [step for protocol in plan.plans for step in protocol.steps]
    assert [step.op for step in steps] == ["AllocContainer", "agit"]
    agit_step = next(step for step in steps if step.op == "agit")
    assert result.state.step_status[agit_step.step_id] == "completed"
