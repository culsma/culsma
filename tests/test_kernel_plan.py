from __future__ import annotations

import json
from pathlib import Path

import pytest

from culsma.frontend.resolver import resolve_program
from culsma.pipeline.compile import compile_ast as _compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.parser.parser import parse, parse_file, parse_files


ROOT = Path(__file__).resolve().parents[1]
PARSER_FIXTURES = ROOT / "tests" / "fixtures_parser"
LEGACY_PARSER_FIXTURES = ROOT / "tests" / "fixtures_parser_legacy"
PLAN_FIXTURES = ROOT / "tests" / "fixtures_plan"


def compile_to_ir(ast):
    return _compile_ast(resolve_program(ast).prepared_program).ir


def _load_golden(name: str) -> dict:
    return json.loads((PLAN_FIXTURES / name).read_text(encoding="utf-8"))


def test_lower_current_frontend_core_plan_smoke():
    ast = parse_file(PARSER_FIXTURES / "current_frontend_core.culs")
    ir = compile_to_ir(ast)
    plan = lower_ir_to_plan(ir)
    assert plan.plans
    assert plan.plans[0].protocol_name == "CurrentFrontendCore"
    assert [step.op for step in plan.plans[0].steps]


def test_lower_legacy_dna_extraction_fixture_is_rejected_by_current_source_gate():
    ast = parse_file(LEGACY_PARSER_FIXTURES / "dna_extraction.culs")
    with pytest.raises(ValueError, match="staining_method"):
        compile_to_ir(ast)


def test_linear_dependencies_are_explicit():
    ast = parse_file(PARSER_FIXTURES / "current_frontend_core.culs")
    ir = compile_to_ir(ast)
    plan = lower_ir_to_plan(ir)
    steps = plan.plans[0].steps
    assert steps[0].deps == []
    for idx in range(1, len(steps)):
        assert steps[idx].deps == [steps[idx - 1].step_id]


def test_include_reference_legacy_dna_extraction_fixture_is_rejected_by_current_source_gate():
    ast = parse_file(LEGACY_PARSER_FIXTURES / "dna_extraction.culs")
    with pytest.raises(ValueError, match="staining_method"):
        compile_to_ir(ast)


def test_include_nested_reference_expands_transitively():
    src = """
protocol C { Step3(); }
protocol B { include C; Step2(); }
protocol A { include B; Step1(); }
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    assert len(plan.plans) == 1
    assert plan.plans[0].protocol_name == "A"
    assert [s.op for s in plan.plans[0].steps] == ["Step3", "Step2", "Step1"]
    assert plan.diagnostics == []


def test_include_unknown_reference_emits_plan_unknown_reference():
    src = 'protocol A { include Missing; Step1(); }'
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    codes = [d.code for d in plan.diagnostics]
    assert "PLAN_UNKNOWN_REFERENCE" in codes
    assert [s.op for s in plan.plans[0].steps] == ["Step1"]


def test_include_cross_cycle_emits_plan_reference_cycle():
    src = """
protocol A { include B; Step1(); }
protocol B { include A; Step2(); }
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    codes = [d.code for d in plan.diagnostics]
    assert "PLAN_REFERENCE_CYCLE" in codes


def test_include_self_cycle_emits_plan_reference_cycle():
    src = "protocol A { include A; Step1(); }"
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    codes = [d.code for d in plan.diagnostics]
    assert "PLAN_REFERENCE_CYCLE" in codes


def test_python_style_module_protocol_call_expands_cross_file(tmp_path):
    core = tmp_path / "module_core.culs"
    pipeline = tmp_path / "module_pipeline.culs"
    core.write_text("protocol Base { StepBase(); }", encoding="utf-8")
    pipeline.write_text(
        '\n'.join(
            [
                'include "module_core.culs";',
                "protocol Root {",
                "  module_core.Base();",
                "  StepRoot();",
                "}",
            ]
        ),
        encoding="utf-8",
    )

    ast = parse_files([pipeline])
    ir = compile_to_ir(ast)
    plan = lower_ir_to_plan(ir)
    assert len(plan.plans) == 1
    assert plan.plans[0].protocol_name == "Root"
    assert [s.op for s in plan.plans[0].steps] == ["StepBase", "StepRoot"]
    assert plan.diagnostics == []


def test_python_style_module_protocol_call_unknown_target_emits_unknown_reference():
    src = "protocol Root { no_such_module.Missing(); StepRoot(); }"
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    codes = [d.code for d in plan.diagnostics]
    assert "PLAN_UNKNOWN_REFERENCE" in codes
    assert [s.op for s in plan.plans[0].steps] == ["StepRoot"]


def test_protocol_call_binds_named_args_and_defaults():
    src = """
protocol Base(input, ratio = 0.5) {
  StepBase(v = input);
  StepRatio(v = ratio);
}
protocol Root {
  core.Base(input = 3);
}
"""
    ast = parse(src)
    ast.protocols[0].module = "core"
    ast.protocols[1].module = "core"
    plan = lower_ir_to_plan(compile_to_ir(ast))
    assert [s.op for s in plan.plans[0].steps] == ["StepBase", "StepRatio"]
    assert plan.diagnostics == []


def test_protocol_call_missing_required_arg_emits_diagnostic():
    src = """
protocol Base(input) {
  StepBase(v = input);
}
protocol Root {
  core.Base();
}
"""
    ast = parse(src)
    ast.protocols[0].module = "core"
    ast.protocols[1].module = "core"
    plan = lower_ir_to_plan(compile_to_ir(ast))
    codes = [d.code for d in plan.diagnostics]
    assert "PLAN_CALL_ARG_MISSING" in codes


def test_protocol_call_unknown_arg_emits_diagnostic():
    src = """
protocol Base(input) { StepBase(v = input); }
protocol Root { core.Base(input = 1, extra = 2); }
"""
    ast = parse(src)
    ast.protocols[0].module = "core"
    ast.protocols[1].module = "core"
    plan = lower_ir_to_plan(compile_to_ir(ast))
    codes = [d.code for d in plan.diagnostics]
    assert "PLAN_CALL_ARG_UNKNOWN" in codes


def test_protocol_call_duplicate_arg_emits_diagnostic():
    src = """
protocol Base(input) { StepBase(v = input); }
protocol Root { core.Base(input = 1, input = 2); }
"""
    ast = parse(src)
    ast.protocols[0].module = "core"
    ast.protocols[1].module = "core"
    plan = lower_ir_to_plan(compile_to_ir(ast))
    codes = [d.code for d in plan.diagnostics]
    assert "PLAN_CALL_ARG_DUPLICATE" in codes


def test_protocol_param_redeclared_by_let_emits_diagnostic():
    src = """
protocol Base(input) {
  let input = 2;
  StepBase(v = input);
}
protocol Root { core.Base(input = 1); }
"""
    ast = parse(src)
    ast.protocols[0].module = "core"
    ast.protocols[1].module = "core"
    plan = lower_ir_to_plan(compile_to_ir(ast))
    codes = [d.code for d in plan.diagnostics]
    assert "PLAN_CALL_PARAM_REDECLARED" in codes


def test_protocol_call_no_longer_inherits_caller_let_values():
    src = """
protocol Base(input) { StepBase(v = input); }
protocol Root {
  let input = 99;
  core.Base();
}
"""
    ast = parse(src)
    ast.protocols[0].module = "core"
    ast.protocols[1].module = "core"
    plan = lower_ir_to_plan(compile_to_ir(ast))
    codes = [d.code for d in plan.diagnostics]
    assert "PLAN_CALL_ARG_MISSING" in codes


def test_entry_protocol_missing_required_param_emits_diagnostic():
    src = "protocol Root(input) { StepRoot(v = input); }"
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    codes = [d.code for d in plan.diagnostics]
    assert "PLAN_ENTRY_PARAM_MISSING" in codes


def test_protocol_param_default_unresolvable_emits_diagnostic():
    src = """
protocol Base(input = missing_symbol) {
  StepBase(v = input);
}
protocol Root { core.Base(); }
"""
    ast = parse(src)
    ast.protocols[0].module = "core"
    ast.protocols[1].module = "core"
    plan = lower_ir_to_plan(compile_to_ir(ast))
    codes = [d.code for d in plan.diagnostics]
    assert "PLAN_CALL_ARG_DEFAULT_EVAL_FAILED" in codes


def test_plan_materializes_let_bound_data_shells_into_local_runtime_steps():
    plan = lower_ir_to_plan(
        compile_to_ir(
            parse(
                """
protocol T {
  let reads = data_group_ref(kind = sequence_read);
  let read = data_ref(kind = sequence_read);
  let schema = data_schema(label = "SeqSignal", fields = [signal]);
  reads.items.append(read);
}
"""
            )
        )
    )
    steps = plan.plans[0].steps
    assert [step.op for step in steps] == ["assign_local", "assign_local", "assign_local", "append"]
    assert steps[0].args["target"] == "reads"
    assert steps[1].args["target"] == "read"
    assert steps[2].args["target"] == "schema"


def test_plan_lowers_member_assignment_to_assign_member_step():
    plan = lower_ir_to_plan(
        compile_to_ir(
            parse(
                """
protocol T {
  let read = data_ref(kind = sequence_read);
  read.result.hit = true;
}
"""
            )
        )
    )
    steps = plan.plans[0].steps
    assert [step.op for step in steps] == ["assign_local", "assign_member"]
    assert steps[1].args["target"]["kind"] == "IRMember"
    assert steps[1].args["target"]["member"] == "hit"


def test_plan_preserves_protocol_return_bindings_metadata():
    plan = lower_ir_to_plan(
        compile_to_ir(
            parse(
                """
protocol T(sample) returns (prepared_out, seq_out) {
  let x = sample;
  return prepared_out = x, seq_out = sample;
}
"""
            )
        )
    )
    proto = plan.plans[0]
    assert proto.returns == ["prepared_out", "seq_out"]
    assert set(proto.return_bindings.keys()) == {"prepared_out", "seq_out"}
    assert proto.return_value is None


def test_plan_materializes_let_bound_stream_and_marker_shells_into_local_runtime_steps():
    plan = lower_ir_to_plan(
        compile_to_ir(
            parse(
                """
protocol T {
  let cells = tube(label = "Cells", capacity = 500uL);
  let panel = markers(["CD3", "CD19"]);
  let events = stream(sample = cells, unit = single_cell, panel = panel);
}
"""
            )
        )
    )
    steps = plan.plans[0].steps
    assert [step.op for step in steps] == ["AllocContainer", "assign_local", "assign_local"]
    assert steps[1].args["target"] == "panel"
    assert steps[2].args["target"] == "events"


def test_plan_lowers_dynamic_repeat_over_stream_to_repeat_bind_step():
    plan = lower_ir_to_plan(
        compile_to_ir(
            parse(
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
        )
    )
    steps = plan.plans[0].steps
    assert [step.op for step in steps] == ["AllocContainer", "assign_local", "assign_local", "repeat_bind"]
    repeat_step = steps[-1]
    assert repeat_step.args["binding"] == "cell"
    assert repeat_step.args["iterable"]["kind"] == "IRIdentifier"
    assert repeat_step.args["iterable"]["name"] == "events"
    body_steps = repeat_step.args["body_steps"]
    assert [step.op for step in body_steps] == ["assign_local", "append"]


def test_plan_lowers_mutation_stmt_to_mutation_step():
    src = "protocol T { tube << [feed:1uL]; }"
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert len(steps) == 1
    assert steps[0].op == "Mutation"
    assert steps[0].args["target"]["kind"] == "IRIdentifier"
    assert steps[0].args["target"]["name"] == "tube"
    source = steps[0].args["sources"][0]
    assert source["kind"] == "IRPair"
    assert source["left"]["name"] == "feed"
    assert source["right"]["value"] == 1.0
    assert source["right"]["unit"] == "uL"


def test_plan_lowers_explicit_hold_with_env_to_env_hold():
    src = "protocol T { with env(thermal = 37C, duration = 10min) { hold(sample = tube); } }"
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert len(steps) == 1
    assert steps[0].op == "env_hold"
    assert steps[0].gate["env"]["thermal"]["value"] == 37.0
    assert steps[0].gate["env"]["duration"]["unit"] == "min"
    assert steps[0].gate["env_targets"][0]["name"] == "tube"


def test_plan_empty_with_env_requires_explicit_hold_and_keeps_stmt_shape():
    src = "protocol T { with env(thermal = 37C, duration = 10min) { hold(sample = tube); } }"
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert len(steps) == 1
    assert steps[0].op == "env_hold"


def test_plan_does_not_insert_env_hold_for_non_empty_with_env():
    src = """
protocol T {
  with env(thermal = 37C, duration = 10min) {
    tube << [feed:1uL];
  }
}
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert [step.op for step in steps] == ["Mutation"]


def test_plan_lowers_incubate_to_env_hold_path():
    src = "protocol T { Incubate(sample = tube_a, temp = 37C, duration = 10min); }"
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert len(steps) == 1
    assert steps[0].op == "env_hold"
    assert steps[0].gate["env_targets"][0]["name"] == "tube_a"


def test_plan_explicit_hold_with_thermal_program_lowers_to_single_env_hold():
    src = """
protocol T {
  with env(thermal = thermal_program(from = 95C, duration = 30s)) {
    hold(sample = tube);
  }
}
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert [step.op for step in steps] == ["env_hold"]


def test_plan_lowers_with_env_into_step_gate():
    src = """
protocol T {
  with env(thermal = 37C, duration = 10min) {
    tube << [feed:1uL];
    Step2();
  }
}
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert [step.op for step in steps] == ["Mutation", "Step2"]
    assert steps[0].deps == []
    assert steps[1].deps == [steps[0].step_id]
    for step in steps:
        assert step.gate["protocol_name"] == "T"
        assert step.gate["env"]["thermal"]["value"] == 37.0
        assert step.gate["env"]["thermal"]["unit"] == "C"
        assert step.gate["env"]["duration"]["value"] == 10.0
        assert step.gate["env_targets"][0]["name"] == "tube"


def test_plan_lowers_with_constraint_into_step_gate():
    src = """
protocol T {
  with constraint(gentle, preserve_boundary) {
    tube << [feed:1uL];
    Step2();
  }
}
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert [step.op for step in steps] == ["Mutation", "Step2"]
    for step in steps:
        assert step.gate["constraint"]["requirements"] == ["gentle", "preserve_boundary"]
        assert step.gate["constraint"]["options"] == {}


def test_plan_lowers_trailing_with_constraint_sugar_into_step_gate():
    src = """
protocol T {
  tube << [feed:1uL] with constraint(gentle, preserve_boundary);
}
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert [step.op for step in steps] == ["Mutation"]
    assert steps[0].gate["constraint"]["requirements"] == ["gentle", "preserve_boundary"]


def test_plan_merges_nested_constraint_scopes():
    src = """
protocol T {
  with constraint(gentle) {
    with constraint(preserve_boundary) {
      tube << [feed:1uL];
    }
  }
}
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    step = plan.plans[0].steps[0]
    assert step.gate["constraint"]["requirements"] == ["gentle", "preserve_boundary"]


def test_plan_keeps_single_body_execution_for_thermal_program_scope():
    src = """
protocol T {
  let tp = thermal_program(from = 95C, duration = 30s);
  with env(thermal = tp) {
    pcr_well << [mix:20uL];
  }
}
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert len(steps) == 1
    assert steps[0].op == "Mutation"
    assert steps[0].gate["env"]["thermal"]["kind"] == "IRCall"
    assert steps[0].gate["env"]["thermal"]["name"] == "thermal_program"


def test_plan_statement_pcr_lowers_to_env_hold_segments():
    src = 'protocol T { PCR(sample = pcr_well, primers = "Panel", cycles = 2, annealing_temp = 60C); }'
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    ops = [step.op for proto in plan.plans for step in proto.steps]
    assert ops == ["env_hold", "env_hold", "env_hold", "env_hold", "env_hold", "env_hold"]


def test_plan_statement_lyse_lowers_to_env_gate_and_no_legacy_lyse_step():
    src = 'protocol T { let lysed = Lyse(sample = sample_tube, buffer = lysis_input, duration = 10min, temp = 4C); let sep_group = sep(sample = lysed, program = sep_program(mode = "centrifuge", speed = 12000g, duration = 5min)); }'
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    ops = [step.op for step in steps]
    assert "Lyse" not in ops
    assert ops[:3] == ["Mutation", "sep", "Mutation"]
    assert steps[0].gate["env"]["thermal"]["value"] == 4.0
    assert steps[1].gate["env"]["duration"]["value"] == 10.0
    assert ops[-1] == "sep"


def test_plan_statement_extract_dna_precipitation_has_no_legacy_extractdna_step():
    src = """
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
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = [step for proto in plan.plans for step in proto.steps]
    ops = [step.op for step in steps]
    assert "ExtractDNA" not in ops
    assert "sep" in ops
    cleanup_steps = [step for step in steps if step.gate.get("env", {}).get("thermal", {}).get("value") == 25.0]
    assert cleanup_steps


def test_plan_statement_extract_dna_column_has_no_legacy_extractdna_step():
    src = """
protocol T {
  let lysate = tube(label = "Lysate", capacity = 2000uL, load = [content(kind = "biosample", code = "DNA_COL", type = "dna_lysate"):600uL]);
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
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = [step for proto in plan.plans for step in proto.steps]
    ops = [step.op for step in steps]
    assert "ExtractDNA" not in ops
    assert ops.count("sep") >= 2
    cleanup_steps = [step for step in steps if step.gate.get("env", {}).get("thermal", {}).get("value") == 25.0]
    assert cleanup_steps


def test_plan_expands_include_inside_with_env_and_keeps_gate():
    src = """
protocol B {
  tube << [feed:1uL];
}
protocol A {
  with env(thermal = 37C, duration = 1min) {
    include B;
  }
  Step2();
}
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    assert len(plan.plans) == 1
    assert plan.plans[0].protocol_name == "A"
    steps = plan.plans[0].steps
    assert [step.op for step in steps] == ["Mutation", "Step2"]
    assert steps[0].gate["protocol_name"] == "A"
    assert steps[0].gate["env"]["thermal"]["value"] == 37.0
    assert steps[0].gate["ref_meta"]["ref_protocol"] == "B"
    assert steps[1].deps == [steps[0].step_id]


def test_plan_materializes_let_bound_sep_call_into_runtime_step():
    src = """
protocol T {
  let sep_group = sep(sample = lysate, program = sep_program(mode = "centrifuge", speed = 12000g, duration = 10min));
}
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert len(steps) == 1
    assert steps[0].op == "sep"
    assert steps[0].args["bind"] == "sep_group"
    assert steps[0].args["program"]["kind"] == "IRCall"
    assert steps[0].args["program"]["name"] == "sep_program"


def test_plan_materializes_let_bound_img_call_into_runtime_step():
    src = """
protocol T {
  let obs = img(sample = tube, quantity = fluorescence, save_raw = true);
}
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert len(steps) == 1
    assert steps[0].op == "img"
    assert steps[0].args["bind"] == "obs"
    assert steps[0].args["save_raw"]["kind"] == "IRBoolean"
    assert steps[0].args["save_raw"]["value"] is True


def test_plan_runtime_if_attaches_runtime_conditions_to_branch_steps():
    src = """
protocol T {
  let obs = img(sample = tube, quantity = fluorescence);
  if obs.result.signal >= 1000 {
    Step(v = 1);
  } else {
    Step(v = 2);
  }
}
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert [step.op for step in steps] == ["img", "Step", "Step"]
    then_gate = steps[1].gate["runtime_conditions"][0]
    else_gate = steps[2].gate["runtime_conditions"][0]
    assert then_gate["expr"]["kind"] == "IRBinary"
    assert then_gate["negate"] is False
    assert else_gate["negate"] is True


def test_plan_let_bound_electrophoresis_stdlib_has_no_legacy_electrophoresis_step():
    src = """
protocol T {
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
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    ops = [step.op for step in steps]
    assert "Electrophoresis" not in ops
    assert ops == ["assign_local", "sep", "Mutation", "img"]
    assert steps[-1].args["bind"] == "gel_obs"
    assert steps[-1].args["quantity"]["name"] == "customized"
    assert steps[-1].args["schema_ref"]["kind"] == "IRIdentifier"


def test_plan_materializes_let_bound_container_constructor():
    src = 'protocol T { let tube_a = tube(label = "Tube_A", capacity = 500uL); }'
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert len(steps) == 1
    assert steps[0].op == "AllocContainer"
    assert steps[0].args["bind"] == "tube_a"
    assert steps[0].args["label"]["value"] == "Tube_A"


def test_plan_materializes_constructor_load_into_init_sequence():
    src = """
protocol T {
  let tube_a = tube(label = "Tube_A", capacity = 500uL, load = [content(kind = "biosample", code = "S1", type = "dna_sample"):100uL]);
}
"""
    plan = lower_ir_to_plan(compile_to_ir(parse(src)))
    steps = plan.plans[0].steps
    assert [step.op for step in steps] == ["AllocContainer", "DefineContent", "LoadContent"]
    assert steps[0].args["bind"] == "tube_a"
    assert steps[1].args["code"]["value"] == "S1"
    assert steps[2].args["container"]["kind"] == "IRIdentifier"
    assert steps[2].args["container"]["name"] == "tube_a"
    assert steps[2].args["content"]["value"] == "S1"
    assert steps[2].args["amount"]["value"] == 100.0
