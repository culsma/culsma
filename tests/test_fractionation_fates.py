"""PM #162: authored N-way allocation without a fractionation prediction model."""

from copy import deepcopy
from unittest.mock import patch

import pytest

from culsma.domains.material_allocation import allocation_ratio, validate_allocation_ratios
from culsma.pipeline.ir_nodes import IRArg, IRCall, IRIdentifier, IRList, IRQuantity, IRRecord
from culsma.pipeline.validate.fractionation import validate_fraction_fates_contract
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.validate import validate
from culsma.parser import parse
from culsma.frontend.resolver import resolve_program
from culsma.runtime.material.fractionation import allocate_fraction_parts, parse_fraction_fates
from culsma.runtime.material.compute import MaterialCompute
from culsma.runtime.material.contents_state import MaterialIndexedPartsStateManager
from culsma.runtime.material.scientific_model_adapter import MaterialEffectFailure
from culsma.driver.stub import StubDriver
from culsma.runtime.executor import run
from culsma.runtime.replay import replay_events
from test_kernel_runtime import _build_plan_from_source, _container_by_label


PROGRAM = "density_gradient_program(axis=DensityGradientAxis.DENSITY,order=DensityGradientOrder.TOP_TO_BOTTOM,bins=3)"
DECLARATIONS = '''
let s=tube(label="source",capacity=100mL,load=[
  content(kind=ContentKind.BIO_FLUID,type=ContentType.PLASMA,code="PLASMA"):10mL,
  content(kind=ContentKind.FORMULATION,type=ContentType.BUFFER,code="PBS"):12.5mL,
  content(kind=ContentKind.FORMULATION,type=ContentType.GRADIENT_MEDIUM,code="FICOLL"):15mL,
  content(kind=ContentKind.BIO_CELLULAR,type=ContentType.PRIMARY_CELLS,code="PBMC"):300cells
]);
let w=tube(label="collected",capacity=50mL);
'''
FATES = "{PLASMA:[95%,5%,0%],PBS:[96%,4%,0%],FICOLL:[0%,0%,100%],PBMC:[0%,100%,0%]}"


@pytest.mark.parametrize("value,unit,expected", [
    (0.5, None, 0.5), (50, "%", 0.5), (100, "pct", 1),
    (0.5, "mL", None), (True, None, None), ("0.5", None, None),
    (float("nan"), None, None), (float("inf"), None, None),
])
def test_allocation_ratio(value, unit, expected):
    assert allocation_ratio(value, unit) == expected


@pytest.mark.parametrize("ratios,bins,error", [
    ((0, 1, 0), 3, None), ((1,), 1, None), ((0.5, 0.5), 3, "SHAPE_INVALID"),
    ((-1, 2, 0), 3, "VALUE_INVALID"), ((None, 1, 0), 3, "VALUE_INVALID"),
    ((0, 0.2, 0), 3, "TOTAL_INVALID"), ((0, float("nan"), 0), 3, "VALUE_INVALID"),
    ((0, True, 0), 3, "VALUE_INVALID"),
])
def test_validate_allocation_ratios(ratios, bins, error):
    assert validate_allocation_ratios(ratios, bins) == error


@pytest.mark.parametrize("values,expected", [
    ([0, 1, 0], None),
    ({"kind":"IRList","elements":[{"kind":"IRQuantity","value":v,"unit":"%"} for v in (0,100,0)]}, None),
    ([0,1], "SHAPE_INVALID"), ([0,2,0], "VALUE_INVALID"),
    ([0,0,0], "TOTAL_INVALID"), ([0,{"kind":"IRQuantity","value":1,"unit":"mL"},0], "VALUE_INVALID"),
    ([0,True,0], "VALUE_INVALID"), ({"middle":1}, "SHAPE_INVALID"),
])
def test_parse_fraction_fates(values, expected):
    result = parse_fraction_fates({"C":values}, bins=3, known_components={"C"})
    if expected:
        assert result.code == "MAT_FRACTION_FATE_RULE_" + expected
    else:
        assert result == {"C":(0,1,0)}


def test_parse_fraction_fates_rejects_unknown_identity_and_nonrecord():
    assert parse_fraction_fates({"missing":[1]}, bins=1, known_components={"C"}).code == "MAT_FRACTION_FATE_COMPONENT_NOT_FOUND"
    assert parse_fraction_fates([], bins=1, known_components={"C"}).code == "MAT_FRACTION_FATE_RULE_SHAPE_INVALID"


@pytest.mark.parametrize("values,error", [
    ([IRQuantity(0,None),IRQuantity(100,"%"),IRQuantity(0,None)], None),
    ([IRQuantity(1,None)], "SHAPE_INVALID"),
    ([IRQuantity(0,None),IRQuantity(1,"mL"),IRQuantity(0,None)], "VALUE_INVALID"),
    ([IRQuantity(0,None)]*3, "TOTAL_INVALID"),
])
def test_validate_fraction_fates_contract(values, error):
    args = [IRArg("program",IRCall("density_gradient_program",[IRArg("bins",IRQuantity(3,None))])),
            IRArg("component_fates",IRRecord({"C":IRList(values)}))]
    diagnostics = validate_fraction_fates_contract(args, expr_bindings={}, node_id=None, span=None)
    assert [d.code for d in diagnostics] == ([] if error is None else ["SEM_FRACTION_FATE_RULE_"+error])


@pytest.mark.parametrize("form", ["standalone", "scoped", "group"])
@pytest.mark.parametrize("program", [PROGRAM, "chromatography_program(axis=ChromatographyAxis.RETENTION_TIME,order=ChromatographyOrder.EARLY_TO_LATE,bins=3)"])
def test_authored_fraction_composition_survives_collection_and_replay(form, program):
    call = f"frac(sample=s,program={program},component_fates={FATES})"
    body = {"standalone":call+";w << [s.contents[1]:1mL];",
            "scoped":"with "+call+" {w << [s.contents[1]:1mL];}",
            "group":"let g="+call+";w << [g[1]:1mL];"}[form]
    plan = _build_plan_from_source("protocol T {"+DECLARATIONS+body+"}")
    result = run(plan, StubDriver())
    assert result.ok, result.diagnostics
    state = result.state.artifacts["material_state"]
    collected = _container_by_label(state["containers"], "collected")
    assert collected["volume_uL"] == pytest.approx(1000)
    assert collected["components"] == pytest.approx({"PLASMA":500,"PBS":500,"PBMC":300})
    assert replay_events(result.events).artifacts["material_state"] == state
    if form == "scoped":
        assert not next(iter(state["contents_states"].values()))["valid"]


def test_unmentioned_components_keep_equal_split():
    plan = _build_plan_from_source("protocol T {"+DECLARATIONS+
        f"let g=frac(sample=s,program={PROGRAM},component_fates={{PBMC:[0%,100%,0%]}});w << [g[1]];}}")
    result = run(plan, StubDriver())
    assert result.ok, result.diagnostics
    collected = _container_by_label(result.state.artifacts["material_state"]["containers"], "collected")
    assert collected["components"] == pytest.approx({"PLASMA":10000/3,"PBS":12500/3,"FICOLL":5000,"PBMC":300})


def test_protocol_aliases_and_return_preserve_authored_fates():
    source = '''protocol Collect(sample, fates) {
      let program=density_gradient_program(axis=DensityGradientAxis.DENSITY,order=DensityGradientOrder.TOP_TO_BOTTOM,bins=3);
      let g=frac(sample=sample,program=program,component_fates=fates);
      return g;
    }
    protocol T {'''+DECLARATIONS+f'''
      let p={PROGRAM}; let middle=[0%,100%,0%]; let rules={{PBMC:middle}};
      let result=Collect(sample=s,fates=rules);
      w << [result[1]];
    }}
    T();'''
    result = run(_build_plan_from_source(source), StubDriver())
    assert result.ok, result.diagnostics
    assert _container_by_label(result.state.artifacts["material_state"]["containers"], "collected")["components"]["PBMC"] == 300


def test_runtime_rejects_unknown_component_atomically():
    plan = _build_plan_from_source("protocol T {"+DECLARATIONS+
        f"frac(sample=s,program={PROGRAM},component_fates={{MISSING:[0%,100%,0%]}});}}")
    result = run(plan, StubDriver())
    assert not result.ok
    assert any(d.code == "MAT_FRACTION_FATE_COMPONENT_NOT_FOUND" for d in result.diagnostics)
    state = result.state.artifacts["material_state"]
    assert _container_by_label(state["containers"], "source")["volume_uL"] == 37500
    assert not state.get("contents_states")


def test_allocate_fraction_parts_and_apply_frac_directly():
    plan = _build_plan_from_source("protocol T {"+DECLARATIONS+"}")
    result = run(plan, StubDriver())
    state = result.state.artifacts["material_state"]
    source_id = next(key for key,value in state["containers"].items() if value["metadata"].get("label")=="source")
    source = state["containers"][source_id]
    before = deepcopy(state)
    adapter = MaterialCompute().material_effect_adapter
    parts = allocate_fraction_parts(state=state, source=source, source_id=source_id,
        bins=3, fates={"PBMC":(0,1,0)}, step_id="fraction", material_effect_adapter=adapter)
    assert not isinstance(parts, MaterialEffectFailure), parts
    assert parts["1"]["components"]["PBMC"] == 300
    assert "PBMC" not in parts["0"]["components"]
    assert state == before

    operation = _build_plan_from_source("protocol T {"+DECLARATIONS+
        f"frac(sample=s,program={PROGRAM},component_fates={{PBMC:[0%,100%,0%]}});}}").plans[0].steps[-1]
    update = MaterialIndexedPartsStateManager(material_effect_adapter=adapter).apply_frac(operation, state)
    assert update.ok, update.diagnostics
    assert next(iter(update.material_state["contents_states"].values()))["parts"]["1"]["components"]["PBMC"] == 300
    assert state == before


@pytest.mark.parametrize("form", ["standalone", "scoped", "group"])
@pytest.mark.parametrize("rules,error", [
    ("{PBMC:[0%,100%]}", "SHAPE_INVALID"),
    ("{PBMC:[0%,0%,0%]}", "TOTAL_INVALID"),
    ("{PBMC:[0%,1mL,0%]}", "VALUE_INVALID"),
    ("{PBMC:[0%,101%,0%]}", "VALUE_INVALID"),
    ("{PBMC:{middle:100%}}", "SHAPE_INVALID"),
])
def test_invalid_fraction_fates_rejected_in_all_forms(form, rules, error):
    call = f"frac(sample=s,program={PROGRAM},component_fates={rules})"
    body = {"standalone":call+";", "scoped":"with "+call+" {}", "group":"let g="+call+";"}[form]
    compiled = compile_ast(resolve_program(parse("protocol T {"+DECLARATIONS+body+"}")).prepared_program)
    result = validate(compiled.ir, analysis=compiled.analysis)
    assert "SEM_FRACTION_FATE_RULE_"+error in [d.code for d in result.diagnostics]


def test_empty_rules_preserve_legacy_result():
    states = []
    for option in ("", ",component_fates={}"):
        plan = _build_plan_from_source("protocol T {"+DECLARATIONS+f"frac(sample=s,program={PROGRAM}{option});w << [s.contents[1]];}}")
        result = run(plan, StubDriver())
        assert result.ok, result.diagnostics
        states.append(result.state.artifacts["material_state"])
    assert states[0] == states[1]


def test_static_aliases_and_deferred_values_are_checked():
    args = [IRArg("program", IRIdentifier("p")), IRArg("component_fates", IRIdentifier("rules"))]
    bindings = {"p":IRCall("density_gradient_program",[IRArg("bins",IRQuantity(3,None))]),
                "rules":IRRecord({"C":IRIdentifier("ratios")}),
                "ratios":IRList([IRQuantity(0,None),IRIdentifier("middle"),IRQuantity(0,None)])}
    assert not validate_fraction_fates_contract(args, expr_bindings=bindings, defined_names={"middle"}, node_id=None, span=None)
    bindings["middle"] = IRQuantity(1,"mL")
    assert validate_fraction_fates_contract(args, expr_bindings=bindings, node_id=None, span=None)[0].code == "SEM_FRACTION_FATE_RULE_VALUE_INVALID"


@pytest.mark.parametrize("bins", [1, 2, 3, 7])
def test_fraction_projection_conserves_each_quantity_axis_without_prediction(bins):
    declarations = DECLARATIONS.replace("300cells", '300cells,content(kind=ContentKind.BIO_MOLECULE_OR_VIRUS,type=ContentType.PROTEIN,code="PROTEIN"):7mg')
    plan = _build_plan_from_source("protocol T {"+declarations+"}")
    state = run(plan, StubDriver()).state.artifacts["material_state"]
    source_id = next(key for key,value in state["containers"].items() if value["metadata"].get("label")=="source")
    source = state["containers"][source_id]
    # Runtime entries retain their native axes; allocating by carrier volume
    # must not implicitly allocate the counted cells in the same proportions.
    before = deepcopy(state)
    adapter = MaterialCompute().material_effect_adapter
    weights = tuple((index + 1) / (bins * (bins + 1) / 2) for index in range(bins))
    with patch.object(adapter, "resolve", side_effect=AssertionError("No separation prediction for frac")):
        parts = allocate_fraction_parts(state=state, source=source, source_id=source_id,
            bins=bins, fates={"PBMC":weights}, step_id="fraction", material_effect_adapter=adapter)
    assert not isinstance(parts, MaterialEffectFailure), parts
    for content_id, amount in source["components"].items():
        assert sum(part["components"].get(content_id,0) for part in parts.values()) == pytest.approx(amount)
    for index, weight in enumerate(weights):
        assert parts[str(index)]["components"]["PBMC"] == pytest.approx(300*weight)
    assert state == before


def test_fraction_projection_failure_does_not_publish_partial_outputs():
    plan = _build_plan_from_source("protocol T {"+DECLARATIONS+"}")
    state = run(plan, StubDriver()).state.artifacts["material_state"]
    source_id = next(key for key,value in state["containers"].items() if value["metadata"].get("label")=="source")
    source = state["containers"][source_id]
    before = deepcopy(state)
    adapter = MaterialCompute().material_effect_adapter
    resolve_movement = adapter.resolve_movement
    with patch.object(adapter, "resolve_movement") as movement:
        # Reject the second output after the first one has been projected.
        movement.side_effect = lambda **kwargs: resolve_movement(**kwargs) if movement.call_count == 1 else MaterialEffectFailure("MAT_SCIENTIFIC_MODEL_UNRESOLVED", "movement relation unresolved")
        parts = allocate_fraction_parts(state=state, source=source, source_id=source_id,
            bins=3, fates={key:(0.5,0.5,0) for key in source["components"]},
            step_id="fraction", material_effect_adapter=adapter)
    assert parts.code == "MAT_SCIENTIFIC_MODEL_UNRESOLVED"
    assert movement.call_count == 2
    assert state == before


def test_zero_destinations_do_not_receive_rounding_residue():
    plan = _build_plan_from_source("protocol T {"+DECLARATIONS+"}")
    state = run(plan, StubDriver()).state.artifacts["material_state"]
    source_id = next(key for key,value in state["containers"].items() if value["metadata"].get("label")=="source")
    source = state["containers"][source_id]
    parts = allocate_fraction_parts(state=state, source=source, source_id=source_id,
        bins=3, fates={key:(0.95,0.05,0) for key in source["components"]}, step_id="fraction",
        material_effect_adapter=MaterialCompute().material_effect_adapter)
    assert not isinstance(parts, MaterialEffectFailure), parts
    assert not parts["2"]["components"]
    for key, amount in source["components"].items():
        assert parts["0"]["components"][key] + parts["1"]["components"][key] == pytest.approx(amount)
