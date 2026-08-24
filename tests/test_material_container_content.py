from __future__ import annotations

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material_compute import apply_step


def _ir_string(value: str) -> dict[str, object]:
    return {"kind": "IRString", "value": value, "span": None}


def _ir_quantity(value: float, unit: str) -> dict[str, object]:
    return {"kind": "IRQuantity", "value": value, "unit": unit, "span": None}


def _count_only_loaded_state() -> dict[str, object]:
    defined = apply_step(
        step=PlanStep(
            step_id="define",
            op="DefineContent",
            args={
                "kind": _ir_string("bio_cellular"),
                "code": _ir_string("RPE1"),
                "type": _ir_string("cell_line"),
            },
        ),
        material_state={"containers": {}, "content_registry": {}, "content_bindings": {}},
    )
    loaded = apply_step(
        step=PlanStep(
            step_id="load",
            op="LoadContent",
            args={
                "container": _ir_string("TubeA"),
                "content": _ir_string("RPE1"),
                "amount": _ir_quantity(100000, "cells"),
            },
        ),
        material_state=defined.material_state,
    )
    return loaded.material_state


def test_runtime_detects_container_content_state_conflict():
    """CF-CNT-005: runtime/material layer owns container-content state conflict diagnostics."""
    define = PlanStep(
        step_id="p0.s0",
        op="DefineContent",
        args={
            "kind": _ir_string("biosample"),
            "code": _ir_string("S1"),
            "type": _ir_string("whole_blood"),
        },
        deps=[],
        gate=None,
        span=None,
    )
    state = {"containers": {}, "content_registry": {}, "content_bindings": {}}
    define_ok = apply_step(step=define, material_state=state)
    assert define_ok.ok

    conflict = PlanStep(
        step_id="p0.s1",
        op="DefineContent",
        args={
            "kind": _ir_string("reagent"),
            "code": _ir_string("S1"),
        },
        deps=[],
        gate=None,
        span=None,
    )
    conflict_result = apply_step(step=conflict, material_state=define_ok.material_state)
    assert not conflict_result.ok
    assert [d.code for d in conflict_result.diagnostics] == ["MAT_CONTENT_METADATA_CONFLICT"]

    missing_load = PlanStep(
        step_id="p0.s2",
        op="LoadContent",
        args={
            "container": _ir_string("TubeA"),
            "content": _ir_string("MISSING"),
            "amount": _ir_quantity(10, "uL"),
        },
        deps=[],
        gate=None,
        span=None,
    )
    missing_result = apply_step(step=missing_load, material_state=define_ok.material_state)
    assert not missing_result.ok
    assert [d.code for d in missing_result.diagnostics] == ["MAT_CONTENT_NOT_FOUND"]


def test_runtime_loads_cell_count_without_adding_container_volume():
    define = PlanStep(
        step_id="define",
        op="DefineContent",
        args={
            "kind": _ir_string("bio_cellular"),
            "code": _ir_string("RPE1"),
            "type": _ir_string("cell_line"),
        },
    )
    defined = apply_step(step=define, material_state={"containers": {}, "content_registry": {}, "content_bindings": {}})
    load = PlanStep(
        step_id="load",
        op="LoadContent",
        args={
            "container": _ir_string("TubeA"),
            "content": _ir_string("RPE1"),
            "amount": _ir_quantity(100000, "cells"),
        },
    )

    result = apply_step(step=load, material_state=defined.material_state)

    assert result.ok
    container = result.material_state["containers"]["TubeA"]
    assert container["volume_uL"] == 0.0
    assert container["mass_mg"] == 0.0
    assert container["components"]["RPE1"] == 100000.0
    assert container["component_quantities"]["RPE1"] == {
        "dimension": "count",
        "unit": "cells",
        "value": 100000.0,
    }


def test_runtime_finalizes_count_only_cells_as_implicit_suspension_without_erasing_count():
    define = PlanStep(
        step_id="define",
        op="DefineContent",
        args={
            "kind": _ir_string("bio_cellular"),
            "code": _ir_string("RPE1"),
            "type": _ir_string("cell_line"),
        },
    )
    defined = apply_step(step=define, material_state={"containers": {}, "content_registry": {}, "content_bindings": {}})
    loaded = apply_step(
        step=PlanStep(
            step_id="load",
            op="LoadContent",
            args={
                "container": _ir_string("TubeA"),
                "content": _ir_string("RPE1"),
                "amount": _ir_quantity(100000, "cells"),
            },
        ),
        material_state=defined.material_state,
    )

    result = apply_step(
        step=PlanStep(
            step_id="finalize",
            op="FinalizeContainerContents",
            args={"container": _ir_string("TubeA")},
        ),
        material_state=loaded.material_state,
    )

    assert result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["ASSUMED_CELL_SUSPENSION_CONCENTRATION"]
    container = result.material_state["containers"]["TubeA"]
    assert container["volume_uL"] == 100.0
    assert container["mass_mg"] == 100.0
    assert container["component_quantities"]["RPE1"]["value"] == 100000.0
    relationship = container["material_relationships"][0]
    assert relationship["dispersed_component_ids"] == ["RPE1"]
    assert relationship["material_state_source"] == "policy_default"
    assert relationship["assumption_policy_ids"] == ["default_cell_suspension_concentration"]
    assert relationship["concentration"] == {
        "value": 1000.0,
        "unit": "cells_per_uL",
        "source": "default",
        "policy_id": "default_cell_suspension_concentration",
    }


def test_runtime_uses_configured_default_cell_suspension_concentration():
    define = PlanStep(
        step_id="define",
        op="DefineContent",
        args={
            "kind": _ir_string("bio_cellular"),
            "code": _ir_string("RPE1"),
            "type": _ir_string("cell_line"),
        },
    )
    defined = apply_step(step=define, material_state={"containers": {}, "content_registry": {}})
    loaded = apply_step(
        step=PlanStep(
            step_id="load",
            op="LoadContent",
            args={
                "container": _ir_string("TubeA"),
                "content": _ir_string("RPE1"),
                "amount": _ir_quantity(100000, "cells"),
            },
        ),
        material_state=defined.material_state,
    )
    loaded.material_state["material_policy"] = {
        "cell_suspension": {"default_concentration_cells_per_uL": 500.0}
    }

    result = apply_step(
        step=PlanStep(
            step_id="finalize",
            op="FinalizeContainerContents",
            args={"container": _ir_string("TubeA")},
        ),
        material_state=loaded.material_state,
    )

    assert result.ok
    container = result.material_state["containers"]["TubeA"]
    assert container["volume_uL"] == 200.0
    assert container["material_relationships"][0]["concentration"]["value"] == 500.0


def test_runtime_rejects_invalid_configured_cell_suspension_concentration():
    state = _count_only_loaded_state()
    state["material_policy"] = {
        "cell_suspension": {"default_concentration_cells_per_uL": "invalid"}
    }

    result = apply_step(
        step=PlanStep(
            step_id="finalize",
            op="FinalizeContainerContents",
            args={"container": _ir_string("TubeA")},
        ),
        material_state=state,
    )

    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "MAT_INVALID_CELL_SUSPENSION_CONCENTRATION"
    ]


def test_runtime_can_disable_implicit_carrier_without_rejecting_constructor():
    state = _count_only_loaded_state()
    state["material_policy"] = {"cell_suspension": {"allow_implicit_carrier": False}}

    result = apply_step(
        step=PlanStep(
            step_id="finalize",
            op="FinalizeContainerContents",
            args={"container": _ir_string("TubeA")},
        ),
        material_state=state,
    )

    assert result.ok
    assert result.diagnostics == []
    container = result.material_state["containers"]["TubeA"]
    assert container["volume_uL"] == 0.0
    assert container["material_relationships"][0]["transferability"] == "non_homogeneous"


def test_runtime_detects_container_overflow():
    step = PlanStep(
        step_id="p0.s0",
        op="Mutation",
        args={
            "target": {"kind": "IRIdentifier", "name": "B", "span": None},
            "sources": [
                {
                    "kind": "IRPair",
                    "left": {"kind": "IRIdentifier", "name": "A", "span": None},
                    "right": _ir_quantity(2, "uL"),
                    "span": None,
                }
            ],
        },
        deps=[],
        gate=None,
        span=None,
    )
    state = {
        "containers": {
            "A": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {"X": 100.0}, "metadata": {}},
            "B": {
                "volume_uL": 9.0,
                "mass_mg": 9.0,
                "components": {"Y": 9.0},
                "metadata": {"capacity_uL": 10.0},
            },
        }
    }
    result = apply_step(step=step, material_state=state)
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["MAT_CONTAINER_OVERFLOW"]


def test_runtime_detects_invalid_capacity():
    step = PlanStep(
        step_id="p0.s0",
        op="Mutation",
        args={
            "target": {"kind": "IRIdentifier", "name": "B", "span": None},
            "sources": [
                {
                    "kind": "IRPair",
                    "left": {"kind": "IRIdentifier", "name": "A", "span": None},
                    "right": _ir_quantity(1, "uL"),
                    "span": None,
                }
            ],
        },
        deps=[],
        gate=None,
        span=None,
    )
    state = {
        "containers": {
            "A": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {"X": 100.0}, "metadata": {}},
            "B": {
                "volume_uL": 0.0,
                "mass_mg": 0.0,
                "components": {},
                "metadata": {"capacity_uL": "bad"},
            },
        }
    }
    result = apply_step(step=step, material_state=state)
    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["MAT_INVALID_CAPACITY"]
