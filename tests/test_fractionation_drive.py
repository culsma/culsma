"""PM 164: centrifugal requirements survive fractionation without changing allocation."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from culsma.domains.separation import CentrifugalDriveRule, validate_centrifugal_drive
from culsma.driver.human import HumanDriver
from culsma.driver.robot import RobotDriver
from culsma.driver.stub import StubDriver
from culsma.driver.framework.mapping_core import normalize_step, value_to_text
from culsma.driver.human_driver.translators import render_program_aware_separation_summary
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.external_boundary import DEFAULT_EXTERNAL_PARAMETER_NORMALIZER as NORMALIZER
from culsma.pipeline.ir_nodes import IRQuantity
from culsma.pipeline.plan_nodes import PlanStep
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.typecheck.expressions import DEFAULT_TYPECHECK_EXPRESSION_SERVICES as TYPES
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.runtime.replay import replay_events
from test_kernel_runtime import _build_plan_from_source, _container_id_by_label


FIXTURE = Path(__file__).parent / "fixtures_material" / "fractionation_allocation.culs"
PROGRAM = "density_gradient_program(axis=DensityGradientAxis.DENSITY, order=DensityGradientOrder.TOP_TO_BOTTOM, bins=3, drive=DRIVE)"


@pytest.mark.parametrize("value", [(1200, "g"), (4000, "rpm"), (0.5, "g")])
def test_centrifugal_drive_preserves_valid_settings(value):
    assert validate_centrifugal_drive(value) is None


@pytest.mark.parametrize("value", [None, "1200g", (1200, None), (1, "mg"), (1, "min"),
                                  (0, "g"), (-1, "rpm"), (True, "g"),
                                  (float("inf"), "g"), (float("nan"), "rpm")])
def test_centrifugal_drive_rejects_invalid_settings(value):
    with pytest.raises(ValueError):
        validate_centrifugal_drive(value)


def test_centrifugal_rule_allows_omission_and_deferral_but_checks_resolved_values():
    rule = CentrifugalDriveRule()
    rule.validate({}, frozenset())
    rule.validate({}, frozenset({"drive"}))
    rule.validate({"drive": (1200, "g")}, frozenset({"drive"}))
    with pytest.raises(ValueError):
        rule.validate({"drive": None}, frozenset({"drive"}))


@pytest.mark.parametrize("program", ["centrifuge_program", "centrifugal_filtration_program", "density_gradient_program"])
def test_centrifugal_programs_share_bound_quantity_validation(program):
    quantity = {"kind": "IRQuantity", "value": 1200, "unit": "g"}
    assert NORMALIZER.normalize_runtime_arguments(program, {"drive": quantity})["drive"] == quantity
    symbolic = {"kind": "IRIdentifier", "name": "force", "bound": True}
    assert NORMALIZER.normalize_plan_arguments(program, {"drive": symbolic})["drive"] == symbolic
    for invalid in (symbolic, {**quantity, "value": 0}, {**quantity, "unit": "mg"}, None):
        with pytest.raises(ValueError):
            NORMALIZER.normalize_runtime_arguments(program, {"drive": invalid})


@pytest.mark.parametrize("value,unit,code", [
    (1200, "g", None), (4000, "rpm", None),
    (0, "g", "TYPE_PROGRAM_FIELD_VALUE_INVALID"),
    (-1, "g", "TYPE_PROGRAM_FIELD_VALUE_INVALID"),
    (float("inf"), "g", "TYPE_PROGRAM_FIELD_VALUE_INVALID"),
    (True, "g", "TYPE_PROGRAM_FIELD_VALUE_INVALID"),
    (1, "mg", "TYPE_PROGRAM_FIELD_DIMENSION_MISMATCH"),
])
def test_centrifugal_quantity_typecheck_direct(value, unit, code):
    diagnostics = TYPES.validate_centrifuge_speed_quantity(
        IRQuantity(value, unit), field_name="drive", program_name="density_gradient_program",
        span=None, node_id="test",
    )
    assert [item.code for item in diagnostics] == ([] if code is None else [code])


@pytest.mark.parametrize("drive,code", [
    ("1200g", None), ("4000rpm", None), ("0g", "TYPE_PROGRAM_FIELD_VALUE_INVALID"),
    ("-2g", "TYPE_PROGRAM_FIELD_VALUE_INVALID"),
    ("2min", "TYPE_PROGRAM_FIELD_DIMENSION_MISMATCH"),
    ("2mg", "TYPE_PROGRAM_FIELD_DIMENSION_MISMATCH"),
    ('"1200g"', "TYPE_PROGRAM_FIELD_KIND_MISMATCH"),
    ("1200", "TYPE_PROGRAM_FIELD_KIND_MISMATCH"),
])
def test_fraction_drive_source_validation_through_binding(drive, code):
    source = f'protocol T(sample) {{ let force={drive}; let p={PROGRAM.replace("DRIVE", "force")}; frac(sample=sample,program=p); }}'
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    assert semantic.ok, semantic.diagnostics
    typed = typecheck(semantic.ir, analysis=compiled.analysis)
    assert (typed.ok if code is None else code in {item.code for item in typed.diagnostics})


@pytest.mark.parametrize("driver_type", [StubDriver, HumanDriver, RobotDriver])
@pytest.mark.parametrize("form", ["scoped", "standalone", "group"])
def test_fraction_drive_reaches_driver_and_preserves_allocations(driver_type, form):
    source = FIXTURE.read_text().replace("RBC: [0%, 0%, 100%]", "RBC: [0%, 1%, 99%]")
    source = source.replace("sample.contents[1]:1mL", "sample.contents[1]")
    baseline = run(_build_plan_from_source(source), StubDriver())
    assert baseline.ok, baseline.diagnostics
    source = source.replace("bins = 3", "bins = 3, drive = 1200g")
    source = source.replace("  with frac(", "  with env(thermal=20C, duration=10min) {\n  with frac(")
    source = source.replace("  return", "  }\n  return")
    if form != "scoped":
        source = source.replace("with frac(", "let fractions = frac(" if form == "group" else "frac(")
        source = source.replace("  ) {", "  );").replace("  }\n  }\n  return", "  }\n  return")
        if form == "group":
            source = source.replace("sample.contents[", "fractions[")
    plan = _build_plan_from_source(source)
    driver = driver_type()
    with patch.object(driver, "execute", wraps=driver.execute) as execute:
        result = run(plan, driver)
    assert result.ok, result.diagnostics
    fractions = [call.args[0] for call in execute.call_args_list if call.args[0].op == "frac"]
    assert len(fractions) == 1
    record = normalize_step(fractions[0])
    assert {key: record.program_args["drive"][key] for key in ("kind", "value", "unit")} == {
        "kind": "IRQuantity", "value": 1200, "unit": "g"}
    assert record.env["thermal"]["value"] == 20
    assert record.env["duration"]["value"] == 10
    assert record.env["duration"]["unit"] == "min"
    if driver_type in (HumanDriver, RobotDriver):
        projection = driver.project_step(fractions[0])
        if driver_type is HumanDriver:
            assert value_to_text(record.program_args["drive"]) in projection.summary
            assert projection.payload["program_args"]["drive"] == record.program_args["drive"]
        else:
            projected = projection.payload["semantic_args"]["program"]
            assert f"drive={value_to_text(record.program_args['drive'])}" in projected
    material = result.state.artifacts["material_state"]
    for label in ("Upper", "Middle", "Lower"):
        actual_id = _container_id_by_label(material["containers"], label)
        expected_id = _container_id_by_label(baseline.state.artifacts["material_state"]["containers"], label)
        assert material["containers"][actual_id]["components"] == pytest.approx(
            baseline.state.artifacts["material_state"]["containers"][expected_id]["components"])
        actual_lots = {result.material_accounting.input_lots[key].content_id: value
                       for key, value in result.material_accounting.container_allocation(actual_id).items()}
        expected_lots = {baseline.material_accounting.input_lots[key].content_id: value
                         for key, value in baseline.material_accounting.container_allocation(expected_id).items()}
        assert actual_lots == expected_lots
    assert replay_events(result.events).artifacts["material_state"] == material


def test_fraction_summary_preserves_legacy_and_displays_supplied_drive():
    args = [{"name": key, "value": value} for key, value in {"axis": "density", "order": "top_to_bottom", "bins": 3}.items()]
    step = PlanStep("f", "frac", {"program": {"kind": "IRCall", "name": "density_gradient_program", "args": args}})
    assert render_program_aware_separation_summary(normalize_step(step), "S") == "Collect 3 ordered fractions from S along the density axis (top_to_bottom)."
    args.append({"name": "drive", "value": {"kind": "IRQuantity", "value": 1200, "unit": "g"}})
    assert "at 1200g" in render_program_aware_separation_summary(normalize_step(step), "S")


@pytest.mark.parametrize("setting,unit", [("1200g", "g"), ("4000rpm", "rpm")])
def test_fraction_drive_survives_protocol_argument_and_program_binding(setting, unit):
    source = f'''
protocol Spin(sample, force) {{
  let program = {PROGRAM.replace("DRIVE", "force")};
  with env(thermal=20C, duration=10min) {{
    frac(sample=sample, program=program);
  }}
  return sample;
}}
let sample = tube(capacity=100uL, load=[content(kind=ContentKind.FORMULATION,
    type=ContentType.BUFFER, code="B"):60uL]);
let result = Spin(sample=sample, force={setting});
return result;
'''
    plan = _build_plan_from_source(source)
    driver = StubDriver()
    with patch.object(driver, "execute", wraps=driver.execute) as execute:
        result = run(plan, driver)
    assert result.ok, result.diagnostics
    record = normalize_step(next(call.args[0] for call in execute.call_args_list if call.args[0].op == "frac"))
    assert record.program_args["drive"]["unit"] == unit
    assert record.program_args["drive"]["value"] == (1200 if unit == "g" else 4000)


def test_fraction_omitted_drive_has_no_invented_default():
    driver = StubDriver()
    with patch.object(driver, "execute", wraps=driver.execute) as execute:
        result = run(_build_plan_from_source(FIXTURE.read_text()), driver)
    assert result.ok, result.diagnostics
    record = normalize_step(next(call.args[0] for call in execute.call_args_list if call.args[0].op == "frac"))
    assert "drive" not in record.program_args


@pytest.mark.parametrize("drive", [0, -1, float("inf")])
def test_fraction_rejects_invalid_serialized_drive_before_execution(drive):
    plan = deepcopy(_build_plan_from_source(FIXTURE.read_text()))
    step = next(step for step in plan.plans[0].steps if step.op == "frac")
    step.args["program"]["args"].append({"name": "drive", "value": {"kind": "IRQuantity", "value": drive, "unit": "g"}})
    driver = StubDriver()
    with patch.object(driver, "execute", wraps=driver.execute) as execute:
        result = run(plan, driver)
    assert not result.ok
    assert "RT_EXTERNAL_ENUM_INVALID" in {item.code for item in result.diagnostics}
    assert not any(call.args[0].op == "frac" for call in execute.call_args_list)
    material = result.state.artifacts["material_state"]
    source = material["containers"][_container_id_by_label(material["containers"], "Source")]
    assert source["volume_uL"] == 40000
    assert not material.get("contents_states")
