from __future__ import annotations

import pytest

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material_compute import apply_step
from culsma.runtime.material.container_content import allocation_container_id


def _ir_string(value: str) -> dict[str, object]:
    return {"kind": "IRString", "value": value, "span": None}


def _ir_quantity(value: float, unit: str) -> dict[str, object]:
    return {"kind": "IRQuantity", "value": value, "unit": unit, "span": None}


def test_alloc_container_qualifies_scoped_name_by_invocation_namespace() -> None:
    first = PlanStep(
        step_id="root.s0::prepare.s0::alloc",
        op="AllocContainer",
        args={
            "label": _ir_string("PBS"),
            "bind": "buffer",
            "container_namespace": "Bio.Prepare",
            "container_name": "buffer",
        },
    )
    second = PlanStep(
        step_id="root.s1::prepare.s0::alloc",
        op="AllocContainer",
        args={
            "label": _ir_string("PBS"),
            "bind": "buffer",
            "container_namespace": "Bio.Prepare",
            "container_name": "buffer",
        },
    )

    first_result = apply_step(step=first, material_state={"containers": {}})
    second_result = apply_step(step=second, material_state=first_result.material_state)

    first_id = first_result.delta["container_id"]
    second_id = second_result.delta["container_id"]
    assert first_id == "container/Bio.Prepare/root.s0%3A%3Aprepare.s0%3A%3Aalloc/buffer"
    assert second_id == "container/Bio.Prepare/root.s1%3A%3Aprepare.s0%3A%3Aalloc/buffer"
    assert first_id != second_id
    assert "::" not in first_id
    assert second_result.material_state["containers"][first_id]["metadata"]["label"] == "PBS"
    assert second_result.material_state["containers"][second_id]["metadata"]["label"] == "PBS"


@pytest.mark.parametrize(
    ("first_namespace", "first_invocation", "first_name", "second_namespace", "second_invocation", "second_name"),
    [
        pytest.param(
            "Workspace.Bio.Prepare",
            "root.s0::prepare.s0::alloc",
            "buffer",
            "Workspace.Bio.Prepare",
            "root.s1::prepare.s0::alloc",
            "buffer",
            id="same-protocol-called-twice",
        ),
        pytest.param(
            "Workspace.Bio.Leaf",
            "root.s0::middle.s0::leaf.s0::alloc",
            "buffer",
            "Workspace.Bio.Leaf",
            "root.s1::middle.s0::leaf.s0::alloc",
            "buffer",
            id="nested-protocol-called-through-different-parents",
        ),
        pytest.param(
            "Workspace.Bio.Prepare",
            "root.repeat.i0::prepare.s0::alloc",
            "buffer",
            "Workspace.Bio.Prepare",
            "root.repeat.i1::prepare.s0::alloc",
            "buffer",
            id="different-repeat-iterations",
        ),
        pytest.param(
            "Workspace.LibraryA.Prepare",
            "root.s0::prepare.s0::alloc",
            "buffer",
            "Workspace.LibraryB.Prepare",
            "root.s0::prepare.s0::alloc",
            "buffer",
            id="same-local-name-in-different-libraries",
        ),
        pytest.param(
            "Workspace.Bio.Prepare",
            "root.s0::prepare.s0::alloc",
            "wash_buffer",
            "Workspace.Bio.Prepare",
            "root.s0::prepare.s0::alloc",
            "elution_buffer",
            id="different-scoped-names-in-one-invocation",
        ),
    ],
)
def test_allocation_container_id_distinguishes_namespace_invocation_and_scoped_name(
    first_namespace: str,
    first_invocation: str,
    first_name: str,
    second_namespace: str,
    second_invocation: str,
    second_name: str,
) -> None:
    first_id = allocation_container_id(
        namespace=first_namespace,
        invocation_id=first_invocation,
        name=first_name,
    )
    second_id = allocation_container_id(
        namespace=second_namespace,
        invocation_id=second_invocation,
        name=second_name,
    )

    assert first_id != second_id
    assert first_id.startswith("container/")
    assert second_id.startswith("container/")
    assert "::" not in first_id
    assert "::" not in second_id


def test_allocation_container_id_is_deterministic_and_encodes_reserved_delimiters() -> None:
    identity = {
        "namespace": "Workspace/Library::Prepare",
        "invocation_id": "root.s0::prepare.s0::alloc",
        "name": "buffer/stock",
    }

    first_id = allocation_container_id(**identity)
    second_id = allocation_container_id(**identity)

    assert first_id == second_id
    assert first_id == (
        "container/Workspace%2FLibrary%3A%3APrepare/"
        "root.s0%3A%3Aprepare.s0%3A%3Aalloc/buffer%2Fstock"
    )
    assert "::" not in first_id


def test_alloc_container_identity_does_not_depend_on_label_or_barcode() -> None:
    identity_args = {
        "bind": "buffer",
        "container_namespace": "Workspace.Bio.Prepare",
        "container_name": "buffer",
    }
    first = PlanStep(
        step_id="root.s0::prepare.s0::alloc",
        op="AllocContainer",
        args={**identity_args, "label": _ir_string("PBS"), "barcode": _ir_string("BC-001")},
    )
    second = PlanStep(
        step_id=first.step_id,
        op="AllocContainer",
        args={**identity_args, "label": _ir_string("Phosphate Buffer"), "barcode": _ir_string("BC-999")},
    )

    first_result = apply_step(step=first, material_state={"containers": {}})
    second_result = apply_step(step=second, material_state={"containers": {}})

    assert first_result.delta["container_id"] == second_result.delta["container_id"]
    assert next(iter(first_result.material_state["containers"].values()))["metadata"]["label"] == "PBS"
    assert next(iter(second_result.material_state["containers"].values()))["metadata"]["label"] == "Phosphate Buffer"


def test_alloc_container_identity_is_driven_by_scoped_declaration_name() -> None:
    shared_args = {
        "label": _ir_string("PBS"),
        "barcode": _ir_string("BC-001"),
        "container_namespace": "Workspace.Bio.Prepare",
    }
    wash = PlanStep(
        step_id="root.s0::prepare.s0::alloc",
        op="AllocContainer",
        args={**shared_args, "bind": "wash_buffer", "container_name": "wash_buffer"},
    )
    elution = PlanStep(
        step_id=wash.step_id,
        op="AllocContainer",
        args={**shared_args, "bind": "elution_buffer", "container_name": "elution_buffer"},
    )

    wash_result = apply_step(step=wash, material_state={"containers": {}})
    elution_result = apply_step(step=elution, material_state={"containers": {}})

    wash_id = wash_result.delta["container_id"]
    elution_id = elution_result.delta["container_id"]
    assert wash_id == (
        "container/Workspace.Bio.Prepare/"
        "root.s0%3A%3Aprepare.s0%3A%3Aalloc/wash_buffer"
    )
    assert elution_id == (
        "container/Workspace.Bio.Prepare/"
        "root.s0%3A%3Aprepare.s0%3A%3Aalloc/elution_buffer"
    )
    assert wash_id != elution_id


def test_alloc_container_rejects_missing_canonical_identity_inputs() -> None:
    step = PlanStep(
        step_id="p0.s0::alloc",
        op="AllocContainer",
        args={"label": _ir_string("PBS"), "barcode": _ir_string("BC-001"), "bind": "buffer"},
    )

    result = apply_step(step=step, material_state={"containers": {}})

    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "MAT_CONTAINER_IDENTITY_MISSING"
    ]
    assert result.material_state["containers"] == {}


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
