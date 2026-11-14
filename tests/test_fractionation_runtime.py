"""Direct tests of fractionation preparation, allocation, and publication."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

import pytest

from culsma.driver.stub import StubDriver
from culsma.pipeline.ir_nodes import IRIdentifier, IRQuantity, IRString
from culsma.pipeline.validate.separation import static_allocation_ratio
from culsma.runtime.executor import run
from culsma.runtime.material.compute import MaterialCompute
from culsma.runtime.material.fractionation import (
    FractionationRequest, allocate_equal_fraction_parts, allocate_fraction_parts,
    equal_fraction_ratio, resolve_fractionation_request,
)
from culsma.runtime.material.scientific_model_adapter import MaterialEffectFailure
from culsma.runtime.material.separation_fate import runtime_allocation_ratio, parse_explicit_content_fates
from test_fractionation_fates import DECLARATIONS, PROGRAM, FATES
from test_kernel_runtime import _build_plan_from_source


@pytest.fixture
def fractionation_input():
    plan = _build_plan_from_source("protocol T {" + DECLARATIONS + "}")
    result = run(plan, StubDriver())
    assert result.ok
    state = result.state.artifacts["material_state"]
    step = _build_plan_from_source("protocol T {" + DECLARATIONS +
        f"frac(sample=s,program={PROGRAM},component_fates={FATES});}}").plans[0].steps[-1]
    manager = MaterialCompute().state_manager.indexed_parts_state_manager
    return manager, state, step


def test_resolve_fractionation_request(fractionation_input):
    _, state, step = fractionation_input
    before = deepcopy(state)
    request = resolve_fractionation_request(step, state)
    assert isinstance(request, FractionationRequest)
    assert request.bins == 3
    assert request.program_kind == "density_gradient_program"
    assert request.bind_name is None
    assert request.fates["PBMC"] == (0, 1, 0)
    assert request.source_id in state["containers"]
    assert state == before


@pytest.mark.parametrize("changes,code", [
    ({"program":None}, "MAT_BINDING_NOT_FOUND"),
    ({"sample":"missing"}, "MAT_BINDING_NOT_FOUND"),
    ({"program":{"kind":"IRCall", "name":"density_gradient_program", "args":[]}}, "MAT_BINDING_NOT_FOUND"),
    ({"component_fates":{"missing":[0,1,0]}}, "MAT_FRACTION_FATE_COMPONENT_NOT_FOUND"),
    ({"component_fates":{"PBMC":[0,1]}}, "MAT_FRACTION_FATE_RULE_SHAPE_INVALID"),
])
def test_request_errors_precede_allocation(fractionation_input, changes, code):
    manager, state, step = fractionation_input
    step = replace(step, args={**step.args, **changes})
    before = deepcopy(state)
    assert resolve_fractionation_request(step, state).code == code
    result = manager.apply_frac(step, state)
    assert result.diagnostics[0].code == code
    assert state == before
    assert result.material_state == before


@pytest.mark.parametrize("initial,current,expected", [
    ((120,200,300),(120,200,300),1/3),
    ((120,200,300),(80,200,300),0.5),
    ((0,120,300),(0,80,300),0.5),
    ((0,0,300),(0,0,200),0.5),
    ((0,0,0),(0,0,0),0),
])
def test_equal_fraction_ratio_preserves_axis_precedence(initial, current, expected):
    assert equal_fraction_ratio(initial, current, 3) == expected


def test_allocate_equal_fraction_parts(fractionation_input):
    manager, state, step = fractionation_input
    request = resolve_fractionation_request(step, state)
    parts = allocate_equal_fraction_parts(
        state=state, source_id=request.source_id, bins=3, step_id=step.step_id,
        material_effect_adapter=manager.material_effect_adapter,
    )
    assert not isinstance(parts, MaterialEffectFailure)
    assert list(parts) == ["0", "1", "2"]
    for part in parts.values():
        assert part["volume_uL"] == pytest.approx(12500)
        assert part["components"]["PBMC"] == pytest.approx(100)
    assert state["containers"][request.source_id]["volume_uL"] == 0


def test_equal_allocation_missing_source_is_diagnostic():
    result = allocate_equal_fraction_parts(
        state={"containers":{}}, source_id="missing", bins=3, step_id="frac",
        material_effect_adapter=None,
    )
    assert result.code == "MAT_BINDING_NOT_FOUND"


@pytest.mark.parametrize("bind_name", [None, "fractions"])
@pytest.mark.parametrize("authored", [False, True])
def test_publish_frac_shares_output_contract(fractionation_input, bind_name, authored):
    manager, state, step = fractionation_input
    request = replace(resolve_fractionation_request(step, state), bind_name=bind_name)
    if authored:
        parts = allocate_fraction_parts(
            state=state, source=state["containers"][request.source_id], source_id=request.source_id,
            bins=request.bins, fates=request.fates, step_id=step.step_id,
            material_effect_adapter=manager.material_effect_adapter,
        )
    else:
        request = replace(request, fates={})
        parts = allocate_equal_fraction_parts(
            state=state, source_id=request.source_id, bins=3, step_id=step.step_id,
            material_effect_adapter=manager.material_effect_adapter,
        )
    result = manager.publish_frac(step=step, state=state, request=request, parts=parts)
    assert result.ok
    if bind_name is None:
        record = state["contents_states"][request.source_id]
        middle = record["parts"]["1"]
        assert state["containers"][request.source_id]["volume_uL"] == 37500
        assert all(f"{step.step_id}::{index}" not in state["containers"] for index in range(3))
        assert result.delta["mode"] == "contents_state"
    else:
        middle = state["containers"][result.delta["slots"]["1"]]
        assert state["containers"][request.source_id]["volume_uL"] == 0
        assert result.delta["bind"] == bind_name
    assert middle["components"]["PBMC"] == pytest.approx(300 if authored else 100)
    assert ("split_ratio" in result.delta) is not authored


def test_record_fraction_contents_directly(fractionation_input):
    manager, state, step = fractionation_input
    request = resolve_fractionation_request(step, state)
    parts = allocate_equal_fraction_parts(
        state=state, source_id=request.source_id, bins=3, step_id=step.step_id,
        material_effect_adapter=manager.material_effect_adapter,
    )
    transition = manager.record_fraction_contents(
        step=step, state=state, source=state["containers"][request.source_id],
        source_id=request.source_id, parts=parts, program_kind=request.program_kind,
    )
    assert transition.contents_state["slots"] == ["0", "1", "2"]
    assert transition.split_ratio is None  # Publication never invents equal allocation metadata.
    assert state["contents_states"][request.source_id]["valid"]
    assert state["containers"][request.source_id]["volume_uL"] == 37500


@pytest.mark.parametrize("authored", [False, True])
def test_apply_frac_discards_failed_candidate(fractionation_input, authored):
    manager, state, step = fractionation_input
    if not authored:
        step = replace(step, args={key:value for key,value in step.args.items() if key != "component_fates"})
    before = deepcopy(state)
    adapter = manager.material_effect_adapter
    original = adapter.resolve_movement
    failure = MaterialEffectFailure("MAT_SCIENTIFIC_MODEL_UNRESOLVED", "second output rejected")
    with patch.object(adapter, "resolve_movement") as movement:
        movement.side_effect = lambda **kwargs: original(**kwargs) if movement.call_count == 1 else failure
        result = manager.apply_frac(step, state)
    assert result.diagnostics[0].code == failure.code
    assert movement.call_count == 2
    assert result.material_state == before
    assert state == before


@pytest.mark.parametrize("value,expected", [
    (IRQuantity(50,"%"),0.5), (IRQuantity(0.5,None),0.5),
    (IRQuantity(50,"uL"),None), (IRString("50%"),None), (IRQuantity(float("nan"),None),None),
])
def test_separation_static_ratio_uses_shared_contract(value, expected):
    assert static_allocation_ratio(IRIdentifier("share"), {"share":value}) == expected


@pytest.mark.parametrize("value,expected", [
    (0.5,0.5), ({"kind":"IRQuantity","value":50,"unit":"%"},0.5),
    ({"kind":"IRQuantity","value":0.5,"unit":"mL"},None),
    (True,None), (float("nan"),None), (float("inf"),None), ("50%",None),
])
def test_separation_runtime_ratio_uses_shared_contract(value, expected):
    assert runtime_allocation_ratio(value) == expected


@pytest.mark.parametrize("ratios,error", [
    ((0.25,0.75),None), ((0.25,0.5),"TOTAL_INVALID"),
    ((float("nan"),1),"VALUE_INVALID"), ((-1,2),"VALUE_INVALID"),
])
def test_separation_retains_two_output_validation(ratios,error):
    fates, issues = parse_explicit_content_fates(
        {"C":{"supernatant":ratios[0],"pellet":ratios[1]}},
        slot_contract={"0":"supernatant","1":"pellet"}, known_components={"C"},
    )
    if error:
        assert not fates
        assert any(issue.code == "MAT_SEPARATION_FATE_RULE_"+error for issue in issues)
    else:
        assert not issues
        assert fates["C"].ratios == ratios
