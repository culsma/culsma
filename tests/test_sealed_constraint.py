"""Plate sealing is an execution requirement on environment holds."""

from pathlib import Path

import pytest

from culsma.driver.human import HumanDriver
from culsma.driver.robot import RobotDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run


CASE_04 = Path(__file__).resolve().parents[1] / "archive/benchmarks-legacy/cases/04/protocol.culs"


def compile_sealed_source(body: str):
    source = f'''protocol T {{
  let elisa_plate = plate(label = "ELISA96", format = "96well", carrier_id = "ELISA96", capacity = 500uL);
  {body}
}}
'''
    return compile_ast(resolve_program(parse(source)).prepared_program)


def build_sealed_plan(body: str):
    compiled = compile_sealed_source(body)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    assert semantic.ok, semantic.diagnostics
    typed = typecheck(semantic.ir, analysis=compiled.analysis)
    assert typed.ok, typed.diagnostics
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
    assert not plan.diagnostics
    return plan


def completed_env_holds(result):
    return [
        event.payload["driver_payload"]
        for event in result.events
        if event.kind == "STEP_COMPLETED"
        and event.payload.get("driver_payload", {}).get("op") == "env_hold"
    ]


@pytest.mark.parametrize("driver_type", [HumanDriver, RobotDriver])
def test_sealed_reaches_environment_hold_driver(driver_type):
    plan = build_sealed_plan('''
  with constraint(sealed) {
    with env(thermal = 25C, duration = 2h) {
      hold(elisa_plate);
    }
  }
''')
    env_hold = plan.plans[0].steps[-1]
    assert env_hold.op == "env_hold"
    assert env_hold.gate["constraint"]["requirements"] == ["sealed"]

    result = run(plan=plan, driver=driver_type(supported_requirements={"sealed"}))
    assert result.ok, result.diagnostics
    payload, = completed_env_holds(result)
    if driver_type is HumanDriver:
        assert "Keep the target sealed throughout the hold." in payload["instruction"]["details"]
    else:
        assert payload["binding"]["requirement_flags"] == ["sealed"]
        assert payload["binding"]["action"] == "environment.hold"


@pytest.mark.parametrize("driver_type", [HumanDriver, RobotDriver])
def test_driver_without_sealed_support_fails_before_hold(driver_type):
    plan = build_sealed_plan('''
  with constraint(sealed) {
    with env(thermal = 25C, duration = 2h) {
      hold(elisa_plate);
    }
  }
''')
    result = run(plan=plan, driver=driver_type(supported_requirements={"dark_protected"}))
    assert not result.ok
    assert "RT_DRIVER_REQUIREMENT_UNSUPPORTED" in [diagnostic.code for diagnostic in result.diagnostics]
    assert completed_env_holds(result) == []


def test_sealed_is_rejected_for_unrelated_action_family():
    compiled = compile_sealed_source('''
  let source = tube(label = "Source", capacity = 1mL, load = [
    content(kind = ContentKind.CHEMICAL, type = ContentType.SOLVENT, code = "BUFFER"):100uL
  ]);
  with constraint(sealed) {
    elisa_plate[A1] << [source:10uL];
  }
''')
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    assert "SEM_CONSTRAINT_ACTION_FAMILY_MISMATCH" in [
        diagnostic.code for diagnostic in semantic.diagnostics
    ]


def test_sealed_does_not_leak_to_following_hold():
    plan = build_sealed_plan('''
  with constraint(sealed) {
    with env(thermal = 25C, duration = 2h) {
      hold(elisa_plate);
    }
  }
  with env(thermal = 25C, duration = 10min) {
    hold(elisa_plate);
  }
''')
    holds = [step for step in plan.plans[0].steps if step.op == "env_hold"]
    assert holds[0].gate["constraint"]["requirements"] == ["sealed"]
    assert "constraint" not in holds[1].gate


def test_case04_seals_five_plate_incubations():
    compiled = compile_ast(resolve_program(parse(CASE_04.read_text())).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    assert semantic.ok, semantic.diagnostics
    typed = typecheck(semantic.ir, analysis=compiled.analysis)
    assert typed.ok, typed.diagnostics
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
    assert not plan.diagnostics

    holds = [step for protocol in plan.plans for step in protocol.steps if step.op == "env_hold"]
    sealed_holds = [
        step
        for step in holds
        if "sealed" in step.gate.get("constraint", {}).get("requirements", [])
    ]
    assert len(holds) == 6
    assert len(sealed_holds) == 5
    for step in sealed_holds:
        target, = step.gate["env_targets"]
        assert target["name"] == "plate"
        carrier_id = next(
            arg["value"]["value"] for arg in target["args"] if arg["name"] == "carrier_id"
        )
        assert carrier_id == "ELISA96"
    assert sealed_holds[-1].gate["constraint"]["requirements"] == ["sealed", "dark_protected"]
