from __future__ import annotations

from pathlib import Path

from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_files, resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run


def _q(value: float, unit: str) -> dict:
    return {"kind": "IRQuantity", "value": value, "unit": unit, "span": None}


def _plan_from_source(source: str, *, entry_args: dict | None = None, enforce_binding: bool = True):
    frontend = resolve_program(parse(source), include_bundled_stdlib=False)
    compiled = compile_ast(frontend.prepared_program)
    sem = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=enforce_binding)
    assert sem.ok, [d.to_dict() for d in sem.diagnostics]
    typ = typecheck(sem.ir)
    assert typ.ok, [d.to_dict() for d in typ.diagnostics]
    plan = lower_ir_to_plan(typ.ir, entry_args_by_protocol=entry_args)
    assert not plan.diagnostics, [d.to_dict() for d in plan.diagnostics]
    return plan


def _plan_from_unvalidated_source(source: str, *, entry_args: dict | None = None):
    frontend = resolve_program(parse(source), include_bundled_stdlib=False)
    compiled = compile_ast(frontend.prepared_program)
    plan = lower_ir_to_plan(compiled.ir, entry_args_by_protocol=entry_args)
    assert not plan.diagnostics, [d.to_dict() for d in plan.diagnostics]
    return plan


def test_formal_params_flow_from_frontend_file_to_runtime_payloads(tmp_path: Path):
    source = tmp_path / "formal_params.culs"
    source.write_text(
        """
protocol T(capacity = 100uL, temp = 37C, duration = 10min) {
  let tube_a = tube(label = "A", capacity = capacity);
  with env(thermal = temp, duration = duration) {
    hold(sample = tube_a);
  }
  return tube_a;
}
""",
        encoding="utf-8",
    )

    frontend = resolve_files([source], include_bundled_stdlib=False)
    compiled = compile_ast(frontend.prepared_program)
    sem = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    assert sem.ok, [d.to_dict() for d in sem.diagnostics]
    typ = typecheck(sem.ir)
    assert typ.ok, [d.to_dict() for d in typ.diagnostics]
    plan = lower_ir_to_plan(
        typ.ir,
        entry_args_by_protocol={
            "T": {
                "capacity": _q(250.0, "uL"),
                "temp": _q(42.0, "C"),
                "duration": _q(7.0, "min"),
            }
        },
    )

    assert not plan.diagnostics
    alloc = plan.plans[0].steps[0]
    env_hold = next(step for step in plan.plans[0].steps if step.op == "env_hold")
    assert alloc.args["capacity"]["value"] == 250.0
    assert env_hold.gate["env"]["thermal"]["value"] == 42.0
    assert env_hold.gate["env"]["duration"]["value"] == 7.0

    result = run(plan=plan, driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_formal_params_drive_all_plan_time_static_control_surfaces():
    plan = _plan_from_source(
        """
protocol T(use_cycles = true, cycles = 3, duration = 90min) {
  let tube_a = tube(label = "A", capacity = 100uL);
  let feed = tube(label = "Feed", capacity = 100uL);
  if use_cycles {
    repeat cycle in schedule(start = 1, end = cycles, step = 1) {
      tube_a << [feed:1uL];
    }
  } else {
    tube_a << [feed:2uL];
  }
  with env(thermal = 37C, duration = duration) {
    repeat tick in schedule(start = 30min, step = 30min) {
      tube_a << [feed:1uL];
    }
  }
}
""",
        entry_args={"T": {"use_cycles": True, "cycles": 2, "duration": _q(60.0, "min")}},
    )

    steps = plan.plans[0].steps
    mutations = [step for step in steps if step.op == "Mutation"]
    assert len(mutations) == 4
    assert all("runtime_conditions" not in step.gate for step in steps)


def test_formal_params_drive_reference_and_continuous_schedule_static_boundaries():
    ast = parse(
        """
protocol Child(duration = 2h) {
  let tube_a = tube(label = "A", capacity = 100uL);
  let feed = tube(label = "Feed", capacity = 100uL);
  repeat perf in schedule(start = 0h, duration = duration, mode = "continuous") {
    repeat tick in schedule(start = 30min, step = 30min) {
      tube_a << [feed:tick];
    }
  }
}
protocol Root {
  lib.Child(duration = 90min);
}
""",
    )
    ast.protocols[0].module = "lib"
    ast.protocols[1].module = "lib"
    frontend = resolve_program(ast, include_bundled_stdlib=False)
    compiled = compile_ast(frontend.prepared_program)
    sem = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=False)
    assert sem.ok, [d.to_dict() for d in sem.diagnostics]
    typ = typecheck(sem.ir)
    assert typ.ok, [d.to_dict() for d in typ.diagnostics]
    plan = lower_ir_to_plan(typ.ir)
    assert not plan.diagnostics, [d.to_dict() for d in plan.diagnostics]

    steps = plan.plans[0].steps
    mutations = [step for step in steps if step.op == "Mutation"]
    assert [step.args["sources"][0]["right"]["value"] for step in mutations] == [30.0, 60.0, 90.0]
    assert all("runtime_conditions" not in step.gate for step in steps)


def test_formal_params_use_shared_plan_env_across_remaining_statement_handlers():
    plan = _plan_from_unvalidated_source(
        """
protocol T(v = 3, volume = 1uL, temp = 37C, schema = "schema-A", use_static = true) returns (out) {
  let tube_a = tube(label = "A", capacity = 100uL);
  let feed = tube(label = "Feed", capacity = 100uL);
  let local = v;
  Step(value = local);
  local = v + 1;
  with constraint(customized, schema_ref = schema) {
    Step(value = v);
  }
  with env(thermal = temp, duration = 10min) {
    hold(sample = tube_a);
  }
  tube_a << [feed:volume];
  if use_static {
    Step(value = v);
  } else {
    Step(value = local);
  }
  return out = v;
}
""",
        entry_args={
            "T": {
                "v": 7,
                "volume": _q(3.0, "uL"),
                "temp": _q(30.0, "C"),
                "schema": "schema-B",
                "use_static": True,
            }
        },
    )

    steps = plan.plans[0].steps
    custom_steps = [step for step in steps if step.op == "Step"]
    assign_step = next(step for step in steps if step.op == "assign_local")
    constraint_step = next(step for step in custom_steps if "constraint" in step.gate)
    env_hold = next(step for step in steps if step.op == "env_hold")
    mutation_step = next(step for step in steps if step.op == "Mutation")

    assert custom_steps[0].args["value"] == 7
    assert assign_step.args["value"]["left"] == 7
    assert constraint_step.args["value"] == 7
    assert constraint_step.gate["constraint"]["options"]["schema_ref"] == "schema-B"
    assert env_hold.gate["env"]["thermal"]["value"] == 30.0
    assert mutation_step.args["sources"][0]["right"]["value"] == 3.0
    assert custom_steps[-1].args["value"] == 7
    assert plan.plans[0].return_bindings["out"] == 7
