"""Surface spreading is a transfer requirement, not a separate material operation."""

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


def compile_source(body, *, target='surface(label = "TargetSurface")'):
    source = """protocol T {
        let source = tube(label = "Source", capacity = 1mL, load = [
            content(kind = ContentKind.FORMULATION, type = ContentType.BUFFER,
                    code = "BUFFER"):200uL
        ]);
        let target = """ + target + ";\n    " + body + "\n}"
    return compile_ast(resolve_program(parse(source)).prepared_program)


def build_plan(body):
    compiled = compile_source(body)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    assert semantic.ok, semantic.diagnostics
    typed = typecheck(semantic.ir, analysis=compiled.analysis)
    assert typed.ok, typed.diagnostics
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
    assert not plan.diagnostics
    return plan


def transfer_payloads(result):
    return [
        event.payload["driver_payload"]
        for event in result.events
        if event.kind == "STEP_COMPLETED"
        and event.payload.get("driver_payload", {}).get("op") == "Mutation"
    ]


def container_by_label(result, label):
    return next(
        container
        for container in result.state.artifacts["material_state"]["containers"].values()
        if container.get("metadata", {}).get("label") == label
    )


@pytest.mark.parametrize("driver_type", [HumanDriver, RobotDriver])
@pytest.mark.parametrize("form", ["trailing", "block"])
@pytest.mark.parametrize("selection,moved", [("source:150uL", 150), ("source", 200)])
def test_spread_is_delivered_to_driver_and_preserves_transfer_amount(
    driver_type, form, selection, moved
):
    transfer = f"target << [{selection}]"
    body = (
        transfer + " with constraint(spread);"
        if form == "trailing"
        else "with constraint(spread) { " + transfer + "; }"
    )
    plan = build_plan(body)
    mutation = next(
        step for protocol in plan.plans for step in protocol.steps if step.op == "Mutation"
    )
    assert mutation.gate["constraint"]["requirements"] == ["spread"]

    result = run(plan=plan, driver=driver_type(supported_requirements={"spread"}))
    assert result.ok, result.diagnostics
    assert container_by_label(result, "Source")["volume_uL"] == 200 - moved
    assert container_by_label(result, "TargetSurface")["volume_uL"] == moved
    assert container_by_label(result, "TargetSurface")["components"]["BUFFER"] == moved

    payload, = transfer_payloads(result)
    if driver_type is HumanDriver:
        assert any("evenly across the receiving surface" in line for line in payload["instruction"]["details"])
    else:
        assert payload["binding"]["requirement_flags"] == ["spread"]
        assert payload["binding"]["action"] == "material.transfer"


@pytest.mark.parametrize("driver_type", [HumanDriver, RobotDriver])
def test_driver_without_spread_support_fails_before_moving_material(driver_type):
    plan = build_plan("target << [source:150uL] with constraint(spread);")
    result = run(plan=plan, driver=driver_type(supported_requirements={"aseptic"}))

    assert not result.ok
    assert "RT_DRIVER_REQUIREMENT_UNSUPPORTED" in [d.code for d in result.diagnostics]
    assert container_by_label(result, "Source")["volume_uL"] == 200
    assert container_by_label(result, "TargetSurface")["volume_uL"] == 0
    assert transfer_payloads(result) == []


def test_spread_combines_with_aseptic():
    plan = build_plan(
        "target << [source:150uL] with constraint(spread, aseptic);"
    )
    result = run(
        plan=plan,
        driver=HumanDriver(supported_requirements={"spread", "aseptic"}),
    )

    assert result.ok, result.diagnostics
    payload, = transfer_payloads(result)
    details = payload["instruction"]["details"]
    assert any("evenly across the receiving surface" in line for line in details)
    assert any("aseptic" in line for line in details)


def test_spread_rejects_a_known_non_surface_target():
    compiled = compile_source(
        "target << [source:150uL] with constraint(spread);",
        target='tube(label = "TargetTube", capacity = 1mL)',
    )
    result = validate(compiled.ir, analysis=compiled.analysis)

    assert not result.ok
    assert "SEM_SPREAD_TARGET_NOT_SURFACE" in [d.code for d in result.diagnostics]


def test_spread_rejects_a_non_surface_target_bound_through_a_protocol_call():
    source = """
protocol ApplySpread(target, source) {
  target << [source:150uL] with constraint(spread);
}
protocol Entry {
  let source = tube(label = "Source", capacity = 1mL, load = [
    content(kind = ContentKind.FORMULATION, type = ContentType.BUFFER,
            code = "BUFFER"):200uL
  ]);
  let target = tube(label = "TargetTube", capacity = 1mL);
  ApplySpread(target = target, source = source);
}
Entry();
"""
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)

    assert not semantic.ok
    assert "SEM_SPREAD_TARGET_NOT_SURFACE" in [d.code for d in semantic.diagnostics]


@pytest.mark.parametrize(
    "operation",
    [
        'agit(sample = source, mode = "shake", duration = 1s);',
        'sep(sample = source, program = centrifuge_program(drive = 12000g));',
    ],
)
def test_spread_rejects_unrelated_operation_families(operation):
    compiled = compile_source("with constraint(spread) { " + operation + " }")
    result = validate(compiled.ir, analysis=compiled.analysis)

    assert not result.ok
    assert "SEM_CONSTRAINT_ACTION_FAMILY_MISMATCH" in [d.code for d in result.diagnostics]
