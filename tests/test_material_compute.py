from __future__ import annotations

from culsma.driver.stub import StubDriver
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.runtime.executor import run
from culsma.runtime.material_compute import apply_step
from culsma.runtime.material.ledger import move_ratio
from culsma.runtime.state import init_state


def _ir_string(value: str) -> dict[str, object]:
    return {"kind": "IRString", "value": value, "span": None}


def _ir_quantity(value: float, unit: str | None) -> dict[str, object]:
    return {"kind": "IRQuantity", "value": value, "unit": unit, "span": None}


def _ir_identifier(name: str) -> dict[str, object]:
    return {"kind": "IRIdentifier", "name": name, "span": None}


def _ir_index(base: str, slot: int) -> dict[str, object]:
    return {"kind": "IRIndex", "base": _ir_identifier(base), "index": _ir_quantity(float(slot), None), "span": None}


def _ir_arg(name: str, value: dict[str, object]) -> dict[str, object]:
    return {"kind": "IRArg", "name": name, "value": value, "span": None}


def _ir_call(name: str, args: list[dict[str, object]]) -> dict[str, object]:
    return {"kind": "IRCall", "name": name, "args": args, "span": None}


def _ir_group(elements: list[dict[str, object]]) -> dict[str, object]:
    return {"kind": "IRGroup", "elements": elements, "span": None}


def _mutation_step(
    target: dict[str, object],
    sources: list[dict[str, object]],
    *,
    tool: str = "Pipette",
    tip: str | None = None,
) -> PlanStep:
    return PlanStep(
        step_id="p0.s0",
        op="Mutation",
        args={"target": target, "sources": sources},
        deps=[],
        gate=None,
        span=None,
    )


def _unit_ref(unit_id: str) -> dict[str, object]:
    return {"kind": "unit_ref", "id": unit_id, "unit_kind": "single_cell", "stream_ref": "events"}


def _sep_step(
    *,
    keep_source: str | None = None,
    step_id: str = "p0.s0",
    program_name: str = "centrifuge_program",
    program_args_override: list[dict[str, object]] | None = None,
    component_fates: dict[str, dict[str, float]] | None = None,
) -> PlanStep:
    program_args = program_args_override or [_ir_arg("drive", _ir_quantity(12000.0, "g"))]
    if keep_source is not None:
        program_args.append(_ir_arg("keep_source", _ir_string(keep_source)))
    step_args: dict[str, object] = {
        "sample": _ir_identifier("lysate"),
        "program": _ir_call(program_name, program_args),
        "bind": "sep_group",
    }
    if component_fates is not None:
        step_args["component_fates"] = component_fates
    return PlanStep(
        step_id=step_id,
        op="sep",
        args=step_args,
        deps=[],
        gate=None,
        span=None,
    )


def _frac_step(*, bins: int = 4) -> PlanStep:
    return PlanStep(
        step_id="p0.s0",
        op="frac",
        args={
            "sample": _ir_identifier("gradient_tube"),
            "program": _ir_call(
                "density_gradient_program",
                [
                    _ir_arg("axis", _ir_identifier("density")),
                    _ir_arg("order", _ir_identifier("top_to_bottom")),
                    _ir_arg("bins", _ir_quantity(float(bins), None)),
                ],
            ),
            "bind": "frac_group",
        },
        deps=[],
        gate=None,
        span=None,
    )


def _partition_state(
    *,
    components: dict[str, float],
    registry: dict[str, tuple[str, str]],
    metadata: dict[str, object] | None = None,
    component_quantities: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    state: dict[str, object] = {
        "containers": {
            "lysate": {
                "volume_uL": 200.0,
                "mass_mg": 200.0,
                "components": dict(components),
                "metadata": metadata or {},
            },
        },
        "content_registry": {
            code: {"content_kind": kind, "content_type": content_type, "content_code": code}
            for code, (kind, content_type) in registry.items()
        },
    }
    if component_quantities is not None:
        state["containers"]["lysate"]["component_quantities"] = component_quantities
    return state


def _rounded_components(container: dict[str, object]) -> dict[str, float]:
    components = container["components"]
    assert isinstance(components, dict)
    return {str(key): round(float(value), 6) for key, value in sorted(components.items())}


def test_mutation_full_source_moves_all_content():
    step = _mutation_step(_ir_identifier("B"), [_ir_identifier("A")], tool="Vortex")
    state = {
        "containers": {
            "A": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {"DNA": 10.0}, "metadata": {}},
            "B": {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
        }
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    assert result.delta["op"] == "Mutation"
    assert result.material_state["containers"]["A"]["volume_uL"] == 0.0
    assert result.material_state["containers"]["B"]["volume_uL"] == 100.0


def test_mutation_rejects_same_content_code_with_different_quantity_axes_before_merge():
    step = _mutation_step(_ir_identifier("B"), [_ir_identifier("A")])
    state = {
        "containers": {
            "A": {
                "volume_uL": 10.0,
                "mass_mg": 10.0,
                "components": {"AB1": 1000.0},
                "component_quantities": {
                    "AB1": {"dimension": "count", "unit": "cells", "value": 1000.0}
                },
                "metadata": {},
            },
            "B": {
                "volume_uL": 10.0,
                "mass_mg": 10.0,
                "components": {"AB1": 10.0},
                "component_quantities": {
                    "AB1": {"dimension": "volume", "unit": "uL", "value": 10.0}
                },
                "metadata": {},
            },
        }
    }

    result = apply_step(step=step, material_state=state)

    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["MAT_CONTENT_QUANTITY_AXIS_CONFLICT"]
    assert result.material_state["containers"]["A"]["component_quantities"]["AB1"]["value"] == 1000.0
    assert result.material_state["containers"]["B"]["component_quantities"]["AB1"]["value"] == 10.0


def test_agit_group_resolution_failure_has_no_partial_effects():
    step = PlanStep(
        step_id="p0.s0",
        op="agit",
        args={"sample": _ir_group([_ir_identifier("A"), _ir_identifier("Missing")])},
        deps=[],
        gate=None,
        span=None,
    )
    state = {
        "containers": {
            "A": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {}, "metadata": {}},
        },
        "contents_states": {
            "A": {"valid": True, "kind": "partitioned", "program_kind": "magnetic"},
        },
    }

    result = apply_step(step=step, material_state=state)

    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["MAT_BINDING_NOT_FOUND"]
    assert result.material_state["contents_states"]["A"] == state["contents_states"]["A"]


def test_alloc_container_preserves_open_metadata():
    step = PlanStep(
        step_id="p0.s0",
        op="AllocContainer",
        args={
            "kind": _ir_identifier("tube"),
            "label": _ir_string("Tube_Open"),
            "open": {"kind": "IRBoolean", "value": True, "span": None},
            "bind": "tube_open",
        },
        deps=[],
        gate=None,
        span=None,
    )
    state = {"containers": {}}

    result = apply_step(step=step, material_state=state)

    assert result.ok
    metadata = result.material_state["containers"]["Tube_Open"]["metadata"]
    assert metadata["open"] is True
    assert metadata["label"] == "Tube_Open"


def test_alloc_container_injects_default_capacity_for_generic_container():
    step = PlanStep(
        step_id="p0.s0",
        op="AllocContainer",
        args={
            "kind": _ir_identifier("container"),
            "label": _ir_string("Generic"),
            "bind": "generic",
        },
        deps=[],
        gate=None,
        span=None,
    )

    result = apply_step(step=step, material_state={"containers": {}})

    assert result.ok
    metadata = result.material_state["containers"]["Generic"]["metadata"]
    assert metadata["capacity_uL"] == 1000.0


def test_alloc_container_injects_default_capacity_for_omitted_generic_surface():
    step = PlanStep(
        step_id="p0.s0",
        op="AllocContainer",
        args={
            "label": _ir_string("Generic"),
            "bind": "generic",
        },
        deps=[],
        gate=None,
        span=None,
    )

    result = apply_step(step=step, material_state={"containers": {}})

    assert result.ok
    metadata = result.material_state["containers"]["Generic"]["metadata"]
    assert metadata["capacity_uL"] == 1000.0


def test_alloc_container_injects_default_capacity_for_tube():
    step = PlanStep(
        step_id="p0.s0",
        op="AllocContainer",
        args={
            "kind": _ir_identifier("tube"),
            "label": _ir_string("Tube1"),
            "bind": "tube1",
        },
        deps=[],
        gate=None,
        span=None,
    )

    result = apply_step(step=step, material_state={"containers": {}})

    assert result.ok
    metadata = result.material_state["containers"]["Tube1"]["metadata"]
    assert metadata["capacity_uL"] == 1500.0


def test_alloc_container_injects_default_capacity_for_well():
    step = PlanStep(
        step_id="p0.s0",
        op="AllocContainer",
        args={
            "kind": _ir_identifier("well"),
            "label": _ir_string("A1"),
            "bind": "a1",
        },
        deps=[],
        gate=None,
        span=None,
    )

    result = apply_step(step=step, material_state={"containers": {}})

    assert result.ok
    metadata = result.material_state["containers"]["A1"]["metadata"]
    assert metadata["capacity_uL"] == 200.0


def test_alloc_container_injects_default_capacity_for_chamber():
    step = PlanStep(
        step_id="p0.s0",
        op="AllocContainer",
        args={
            "kind": _ir_identifier("chamber"),
            "label": _ir_string("ReadChamber"),
            "bind": "read_chamber",
        },
        deps=[],
        gate=None,
        span=None,
    )

    result = apply_step(step=step, material_state={"containers": {}})

    assert result.ok
    metadata = result.material_state["containers"]["ReadChamber"]["metadata"]
    assert metadata["capacity_uL"] == 1000.0


def test_alloc_container_surface_does_not_inject_volume_capacity():
    step = PlanStep(
        step_id="p0.s0",
        op="AllocContainer",
        args={
            "kind": _ir_identifier("surface"),
            "label": _ir_string("DetectorSurface"),
            "bind": "detector_surface",
        },
        deps=[],
        gate=None,
        span=None,
    )

    result = apply_step(step=step, material_state={"containers": {}})

    assert result.ok
    metadata = result.material_state["containers"]["DetectorSurface"]["metadata"]
    assert "capacity_uL" not in metadata


def test_alloc_container_surface_rejects_explicit_capacity():
    step = PlanStep(
        step_id="p0.s0",
        op="AllocContainer",
        args={
            "kind": _ir_identifier("surface"),
            "label": _ir_string("DetectorSurface"),
            "capacity": _ir_quantity(50.0, "uL"),
            "bind": "detector_surface",
        },
        deps=[],
        gate=None,
        span=None,
    )

    result = apply_step(step=step, material_state={"containers": {}})

    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["MAT_INVALID_CAPACITY"]


def test_alloc_container_explicit_capacity_overrides_default():
    step = PlanStep(
        step_id="p0.s0",
        op="AllocContainer",
        args={
            "kind": _ir_identifier("tube"),
            "label": _ir_string("Tube1"),
            "capacity": _ir_quantity(250.0, "uL"),
            "bind": "tube1",
        },
        deps=[],
        gate=None,
        span=None,
    )

    result = apply_step(step=step, material_state={"containers": {}})

    assert result.ok
    metadata = result.material_state["containers"]["Tube1"]["metadata"]
    assert metadata["capacity_uL"] == 250.0


def test_mutation_quantified_source_moves_requested_volume():
    step = _mutation_step(
        _ir_identifier("B"),
        [{"kind": "IRPair", "left": _ir_identifier("A"), "right": _ir_quantity(25.0, "uL"), "span": None}],
    )
    state = {
        "containers": {
            "A": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {"DNA": 20.0}, "metadata": {}},
            "B": {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
        }
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    assert result.material_state["containers"]["A"]["volume_uL"] == 75.0
    assert result.material_state["containers"]["B"]["volume_uL"] == 25.0
    assert [
        (movement.source, movement.destination, movement.volume_uL, movement.mass_mg)
        for movement in result.movements
    ] == [("A", "B", 25.0, 0.0)]


def test_unit_collect_stales_existing_contents_state_via_classifier():
    step = _mutation_step(_ir_identifier("Tube"), [_unit_ref("cell_0")])
    state = {
        "containers": {
            "Tube": {
                "volume_uL": 0.0,
                "mass_mg": 0.0,
                "components": {},
                "metadata": {},
            }
        },
        "contents_states": {
            "Tube": {
                "kind": "partitioned",
                "producer_op": "sep",
                "program_kind": "test_program",
                "source": "Tube",
                "slot_contract": {"0": "retained", "1": "flowthrough"},
                "parts": {"0": {"components": {}}, "1": {"components": {}}},
                "valid": True,
                "step_id": "p0.s0",
            }
        },
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    tube = result.material_state["containers"]["Tube"]
    assert tube["metadata"]["unit_count"] == 1
    contents_state = result.material_state["contents_states"]["Tube"]
    assert contents_state["valid"] is False
    assert contents_state["invalid_reason"] == "missing_material_snapshot"


def test_mutation_quantified_self_transfer_is_noop():
    step = _mutation_step(
        _ir_identifier("A"),
        [{"kind": "IRPair", "left": _ir_identifier("A"), "right": _ir_quantity(25.0, "uL"), "span": None}],
    )
    state = {
        "containers": {
            "A": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {"DNA": 20.0}, "metadata": {}},
        }
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    assert result.delta["sources"][0]["mode"] == "quantified_self_noop"
    assert result.material_state["containers"]["A"]["volume_uL"] == 100.0
    assert result.material_state["containers"]["A"]["mass_mg"] == 100.0
    assert result.material_state["containers"]["A"]["components"]["DNA"] == 20.0


def test_mutation_quantified_mass_reuses_density_bridge_rules():
    step = _mutation_step(
        _ir_identifier("B"),
        [{"kind": "IRPair", "left": _ir_identifier("A"), "right": _ir_quantity(100.0, "mg"), "span": None}],
        tool="Spatula",
    )
    state = {
        "containers": {
            "A": {
                "volume_uL": 1000.0,
                "mass_mg": 0.0,
                "components": {"DNA": 100.0},
                "metadata": {"density_g_per_mL": 1.0},
            },
            "B": {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
        }
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    assert result.delta["sources"][0]["transfer_delta"]["mode"] == "bridge_mass_to_volume"
    assert result.material_state["containers"]["B"]["mass_mg"] == 100.0


def test_mutation_reports_insufficient_volume():
    step = _mutation_step(
        _ir_identifier("B"),
        [{"kind": "IRPair", "left": _ir_identifier("A"), "right": _ir_quantity(200.0, "uL"), "span": None}],
    )
    state = {
        "containers": {
            "A": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {"DNA": 10.0}, "metadata": {}},
            "B": {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
        }
    }

    result = apply_step(step=step, material_state=state)

    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["MAT_INSUFFICIENT_VOLUME"]


def test_mutation_reports_missing_density_for_mass_to_volume_bridge():
    step = _mutation_step(
        _ir_identifier("B"),
        [{"kind": "IRPair", "left": _ir_identifier("A"), "right": _ir_quantity(100.0, "mg"), "span": None}],
        tool="Spatula",
    )
    state = {
        "containers": {
            "A": {"volume_uL": 1000.0, "mass_mg": 0.0, "components": {"DNA": 100.0}, "metadata": {}},
            "B": {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
        }
    }

    result = apply_step(step=step, material_state=state)

    assert not result.ok
    assert [d.code for d in result.diagnostics] == ["MAT_MISSING_DENSITY"]


def test_mutation_structured_index_source_uses_indexed_bindings():
    step = _mutation_step(
        _ir_identifier("out_tube"),
        [{"kind": "IRPair", "left": _ir_index("sep_group", 0), "right": _ir_quantity(50.0, "uL"), "span": None}],
    )
    state = {
        "containers": {
            "sep_slot_0": {"volume_uL": 80.0, "mass_mg": 80.0, "components": {"DNA": 8.0}, "metadata": {}},
            "out_tube": {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
        },
        "indexed_bindings": {"sep_group": {"0": "sep_slot_0"}},
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    assert result.material_state["containers"]["sep_slot_0"]["volume_uL"] == 30.0
    assert result.material_state["containers"]["out_tube"]["volume_uL"] == 50.0


def test_mutation_full_self_transfer_is_noop():
    step = _mutation_step(_ir_identifier("A"), [_ir_identifier("A")], tool="Vortex")
    state = {
        "containers": {
            "A": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {"DNA": 10.0}, "metadata": {}},
        }
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    assert result.delta["sources"][0]["mode"] == "full_self_noop"
    assert result.material_state["containers"]["A"]["volume_uL"] == 100.0
    assert result.material_state["containers"]["A"]["mass_mg"] == 100.0
    assert result.material_state["containers"]["A"]["components"]["DNA"] == 10.0


def test_sep_creates_two_slot_indexed_group_binding():
    step = _sep_step()
    state = {
        "containers": {
            "lysate": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {"DNA": 10.0}, "metadata": {}},
        },
        "content_registry": {
            "DNA": {"content_kind": "bio_molecule_or_virus", "content_type": "dna"}
        },
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert set(slots) == {"0", "1"}
    assert result.material_state["containers"][slots["0"]]["volume_uL"] == 100.0
    assert result.material_state["containers"][slots["1"]]["volume_uL"] == 0.0
    assert result.material_state["containers"][slots["0"]]["component_quantities"]["DNA"] == {
        "dimension": "volume",
        "unit": "uL",
        "value": 100.0,
        "source": "compatibility_input_normalization",
        "density_mg_per_uL": 1.0,
    }
    assert result.material_state["containers"][slots["1"]]["component_quantities"]["DNA"]["value"] == 0.0
    assert {
        (movement.source, movement.destination, movement.volume_uL, movement.mass_mg)
        for movement in result.movements
    } == {
        ("lysate", slots["0"], 100.0, 100.0),
    }


def test_sep_ignores_stale_source_aggregate_and_projects_only_from_detail():
    for supplied_aggregate in (25.0, 250.0):
        state = {
            "containers": {
                "lysate": {
                    "volume_uL": supplied_aggregate,
                    "mass_mg": supplied_aggregate,
                    "components": {"DNA": 100.0},
                    "component_quantities": {
                        "DNA": {"dimension": "volume", "unit": "uL", "value": 100.0}
                    },
                    "metadata": {},
                }
            },
            "content_registry": {
                "DNA": {"content_kind": "bio_molecule_or_virus", "content_type": "dna"}
            },
        }

        result = apply_step(step=_sep_step(), material_state=state)

        assert result.ok
        slots = result.material_state["indexed_bindings"]["sep_group"]
        assert [result.material_state["containers"][slots[key]]["volume_uL"] for key in ("0", "1")] == [
            100.0,
            0.0,
        ]
        assert result.delta["partition"]["bulk_quantity_policy"] == {
            "volume": "detail_ledger_projection",
            "mass": "detail_ledger_projection",
        }


def test_sep_routes_quantity_only_input_as_authoritative_component_detail():
    state = {
        "containers": {
            "lysate": {
                "volume_uL": 0.0,
                "mass_mg": 0.0,
                "component_quantities": {
                    "DNA": {"dimension": "volume", "unit": "uL", "value": 100.0}
                },
                "metadata": {},
            }
        },
        "content_registry": {
            "DNA": {"content_kind": "bio_molecule_or_virus", "content_type": "dna"}
        },
    }

    result = apply_step(step=_sep_step(), material_state=state)

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert [result.material_state["containers"][slots[key]]["volume_uL"] for key in ("0", "1")] == [100.0, 0.0]


def test_capacity_guard_uses_the_same_detail_projection_for_mass_only_content():
    step = _mutation_step(
        _ir_identifier("target"),
        [{"kind": "IRPair", "left": _ir_identifier("source"), "right": _ir_quantity(60.0, "uL"), "span": None}],
    )
    state = {
        "containers": {
            "source": {
                "components": {"BUFFER": 60.0},
                "component_quantities": {
                    "BUFFER": {"dimension": "volume", "unit": "uL", "value": 60.0}
                },
                "metadata": {},
            },
            "target": {
                "components": {"SALT": 150.0},
                "component_quantities": {
                    "SALT": {"dimension": "mass", "unit": "mg", "value": 150.0}
                },
                "metadata": {"capacity_uL": 200.0},
            },
        },
    }

    result = apply_step(step=step, material_state=state)

    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["MAT_CONTAINER_OVERFLOW"]


def test_compatibility_aggregate_becomes_movable_detail_before_separation():
    state = {
        "containers": {
            "lysate": {
                "volume_uL": 100.0,
                "mass_mg": 100.0,
                "components": {"DNA": 10.0},
                "metadata": {},
            }
        },
        "content_registry": {
            "DNA": {"content_kind": "bio_molecule_or_virus", "content_type": "dna"}
        },
    }

    result = apply_step(step=_sep_step(), material_state=state)

    assert result.ok
    slot_id = result.material_state["indexed_bindings"]["sep_group"]["0"]
    slot = result.material_state["containers"][slot_id]
    target = {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}}
    move_ratio(slot, target, 0.5)
    assert slot["component_quantities"]["DNA"]["value"] == 50.0
    assert slot["volume_uL"] == 50.0
    assert target["component_quantities"]["DNA"]["value"] == 50.0
    assert target["volume_uL"] == 50.0
    assert "legacy_residual_quantities" not in slot["metadata"]


def test_sep_keep_source_pellet_reuses_source_container_for_slot_1():
    step = _sep_step(keep_source="pellet")
    state = {
        "containers": {
            "lysate": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {"DNA": 10.0}, "metadata": {}},
        },
        "content_registry": {
            "DNA": {"content_kind": "bio_molecule_or_virus", "content_type": "dna"}
        },
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert slots["1"] == "lysate"
    assert result.material_state["containers"]["lysate"]["volume_uL"] == 0.0
    assert result.material_state["containers"][slots["0"]]["volume_uL"] == 100.0


def test_sep_centrifuge_partitions_liquid_to_supernatant_and_cells_to_pellet():
    result = apply_step(
        step=_sep_step(program_name="centrifuge_program"),
        material_state=_partition_state(
            components={"MEDIUM": 100.0, "CELLS": 100.0},
            registry={
                "MEDIUM": ("formulation", "medium"),
                "CELLS": ("bio_cellular", "cell_population"),
            },
        ),
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.delta["partition"]["slot_contract"] == {"0": "supernatant", "1": "pellet"}
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {
        "CELLS": 0.0,
        "MEDIUM": 100.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "CELLS": 100.0,
        "MEDIUM": 0.0,
    }


def test_sep_volume_only_bulk_is_projected_from_component_fates():
    state = _partition_state(
        components={"LYSIS_BUFFER": 2000.0, "CELL_PELLET": 1000.0},
        component_quantities={
            "LYSIS_BUFFER": {"dimension": "volume", "unit": "uL", "value": 2000.0},
            "CELL_PELLET": {"dimension": "volume", "unit": "uL", "value": 1000.0},
        },
        registry={
            "LYSIS_BUFFER": ("formulation", "buffer"),
            "CELL_PELLET": ("bio_cellular", "microbial_cells"),
        },
    )
    state["containers"]["lysate"]["volume_uL"] = 3000.0
    state["containers"]["lysate"]["mass_mg"] = 3000.0
    state["content_registry"]["LYSIS_BUFFER"]["content_attrs"] = {"role": "lysis"}
    state["content_registry"]["CELL_PELLET"]["content_attrs"] = {"state": "pellet"}

    result = apply_step(step=_sep_step(program_name="centrifuge_program"), material_state=state)

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    slots = result.material_state["indexed_bindings"]["sep_group"]
    supernatant = result.material_state["containers"][slots["0"]]
    pellet = result.material_state["containers"][slots["1"]]
    assert supernatant["component_quantities"]["LYSIS_BUFFER"]["value"] == 2000.0
    assert supernatant["component_quantities"]["CELL_PELLET"]["value"] == 0.0
    assert pellet["component_quantities"]["LYSIS_BUFFER"]["value"] == 0.0
    assert pellet["component_quantities"]["CELL_PELLET"]["value"] == 1000.0
    assert (supernatant["volume_uL"], pellet["volume_uL"]) == (2000.0, 1000.0)
    assert result.delta["partition"]["bulk_quantity_policy"]["volume"] == "detail_ledger_projection"


def test_sep_magnetic_bound_fate_requires_a_support_component_entry():
    state = _partition_state(
        components={"AMPLIFIED_CDNA": 100.0},
        component_quantities={
            "AMPLIFIED_CDNA": {"dimension": "volume", "unit": "uL", "value": 100.0},
        },
        registry={"AMPLIFIED_CDNA": ("bio_molecule_or_virus", "dna")},
    )
    state["containers"]["lysate"]["volume_uL"] = 100.0
    state["containers"]["lysate"]["mass_mg"] = 100.0
    result = apply_step(
        step=_sep_step(
            program_name="magnetic_program",
            component_fates={"AMPLIFIED_CDNA": {"bound": 1.0, "flowthrough": 0.0}},
        ),
        material_state=state,
    )

    assert not result.ok
    assert result.diagnostics[0].code == "MAT_SCIENTIFIC_MODEL_UNRESOLVED"
    assert "association target" in result.diagnostics[0].message


def test_material_compute_rejects_invalid_component_quantity_before_projection():
    invalid_quantities = (
        ({"dimension": "volume", "unit": "unsupported", "value": 100.0}, "invalid unit 'unsupported'"),
        ({"dimension": "volume", "unit": "uL", "value": float("nan")}, "non-negative numeric value"),
        (
            {"dimension": "volume", "unit": "uL", "value": 100.0, "density_mg_per_uL": float("inf")},
            "invalid density",
        ),
    )
    for quantity, expected_message in invalid_quantities:
        state = _partition_state(
            components={"AMPLIFIED_CDNA": 100.0},
            component_quantities={"AMPLIFIED_CDNA": quantity},
            registry={"AMPLIFIED_CDNA": ("bio_molecule_or_virus", "dna")},
        )

        result = apply_step(
            step=_sep_step(program_name="magnetic_program"),
            material_state=state,
        )

        assert not result.ok
        assert [diagnostic.code for diagnostic in result.diagnostics] == ["MAT_INVALID_COMPONENT_QUANTITY"]
        assert expected_message in result.diagnostics[0].message


def test_sep_count_aware_bulk_mass_follows_partitioned_carrier_volume():
    result = apply_step(
        step=_sep_step(program_name="centrifuge_program"),
        material_state=_partition_state(
            components={"MEDIUM": 200.0, "CELLS": 100000.0},
            component_quantities={
                "MEDIUM": {"dimension": "volume", "unit": "uL", "value": 200.0},
                "CELLS": {"dimension": "count", "unit": "cells", "value": 100000.0},
            },
            registry={
                "MEDIUM": ("formulation", "medium"),
                "CELLS": ("bio_cellular", "cell_population"),
            },
        ),
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    supernatant = result.material_state["containers"][slots["0"]]
    pellet = result.material_state["containers"][slots["1"]]
    assert (supernatant["volume_uL"], supernatant["mass_mg"]) == (200.0, 200.0)
    assert (pellet["volume_uL"], pellet["mass_mg"]) == (0.0, 0.0)
    assert result.delta["partition"]["bulk_quantity_policy"] == {
        "volume": "detail_ledger_projection",
        "mass": "detail_ledger_projection",
    }


def test_sep_count_aware_mixed_volume_and_mass_preserves_cross_axis_bulk_proxies():
    state = _partition_state(
        components={"MEDIUM": 300.0, "SALT": 10.0, "CELLS": 100000.0},
        component_quantities={
            "MEDIUM": {"dimension": "volume", "unit": "uL", "value": 300.0},
            "SALT": {"dimension": "mass", "unit": "mg", "value": 10.0},
            "CELLS": {"dimension": "count", "unit": "cells", "value": 100000.0},
        },
        registry={
            "MEDIUM": ("formulation", "medium"),
            "SALT": ("chemical", "inorganic_compound"),
            "CELLS": ("bio_cellular", "cell_population"),
        },
    )
    state["containers"]["lysate"]["volume_uL"] = 310.0
    state["containers"]["lysate"]["mass_mg"] = 310.0

    result = apply_step(step=_sep_step(program_name="centrifuge_program"), material_state=state)

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    slots = result.material_state["indexed_bindings"]["sep_group"]
    slot0 = result.material_state["containers"][slots["0"]]
    slot1 = result.material_state["containers"][slots["1"]]
    assert slot0["volume_uL"] + slot1["volume_uL"] == 310.0
    assert slot0["mass_mg"] + slot1["mass_mg"] == 310.0
    assert slot0["component_quantities"]["MEDIUM"]["value"] == 300.0
    assert slot1["component_quantities"]["MEDIUM"]["value"] == 0.0
    assert result.delta["partition"]["bulk_quantity_policy"] == {
        "volume": "detail_ledger_projection",
        "mass": "detail_ledger_projection",
    }


def test_sep_phase_partition_sends_target_phase_material_away_from_extraction_reagent():
    result = apply_step(
        step=_sep_step(
            program_name="phase_partition_program",
            component_fates={
                "DNA": {"target_phase": 1.0, "other_phase": 0.0},
                "PCI": {"target_phase": 0.0, "other_phase": 1.0},
            },
        ),
        material_state=_partition_state(
            components={"DNA": 100.0, "PCI": 100.0},
            registry={
                "DNA": ("bio_molecule_or_virus", "dna"),
                "PCI": ("chemical", "organic_compound"),
            },
            metadata={"component_partition_classes": {"PCI": "liquid_reagent"}},
        ),
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.delta["partition"]["slot_contract"] == {"0": "target_phase", "1": "other_phase"}
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {
        "DNA": 100.0,
        "PCI": 0.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "DNA": 0.0,
        "PCI": 100.0,
    }


def test_sep_phase_partition_does_not_guess_without_component_fates():
    result = apply_step(
        step=_sep_step(program_name="phase_partition_program"),
        material_state=_partition_state(
            components={"REAGENT": 100.0},
            registry={"REAGENT": ("chemical", "organic_compound")},
        ),
    )

    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "MAT_SCIENTIFIC_MODEL_UNRESOLVED"
    ]


def test_sep_precipitation_uses_declared_target_fate_and_exact_mobile_phase_rule():
    result = apply_step(
        step=_sep_step(
            program_name="precipitation_program",
            component_fates={"DNA": {"precipitate": 1.0, "supernatant": 0.0}},
        ),
        material_state=_partition_state(
            components={"DNA": 100.0, "ETOH": 100.0},
            registry={
                "DNA": ("bio_molecule_or_virus", "dna"),
                "ETOH": ("chemical", "organic_compound"),
            },
        ),
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.delta["partition"]["slot_contract"] == {"0": "precipitate", "1": "supernatant"}
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {
        "DNA": 100.0,
        "ETOH": 0.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "DNA": 0.0,
        "ETOH": 100.0,
    }
    assert result.delta["partition"]["fates_by_component"]["DNA"]["source"] == (
        "author_explicit_fate"
    )
    assert result.delta["partition"]["transitions_by_component"]["DNA"]["0"][
        "next_relation"
    ] == "precipitate"


def test_sep_precipitation_does_not_guess_free_target_fate():
    result = apply_step(
        step=_sep_step(program_name="precipitation_program"),
        material_state=_partition_state(
            components={"DNA": 100.0, "ETOH": 100.0},
            registry={
                "DNA": ("bio_molecule_or_virus", "dna"),
                "ETOH": ("chemical", "organic_compound"),
            },
        ),
    )

    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "MAT_SCIENTIFIC_MODEL_UNRESOLVED"
    ]


def test_sep_filtration_sends_liquid_to_filtrate_and_target_to_retentate():
    state = _partition_state(
        components={"DNA": 100.0, "WASH": 100.0},
        registry={
            "DNA": ("bio_molecule_or_virus", "dna"),
            "WASH": ("formulation", "buffer"),
        },
    )
    state["content_registry"]["DNA"]["content_attrs"] = {"filter_retains": True}
    result = apply_step(
        step=_sep_step(program_name="filtration_program"),
        material_state=state,
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.delta["partition"]["slot_contract"] == {"0": "filtrate", "1": "retentate"}
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {
        "DNA": 0.0,
        "WASH": 100.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "DNA": 100.0,
        "WASH": 0.0,
    }
    assert result.delta["partition"]["fates_by_component"]["DNA"]["source"] == (
        "scientific_model_provider"
    )


def test_sep_aspiration_preserves_surface_associated_content_on_its_native_count_axis():
    state = _partition_state(
        components={"RPE1": 100000.0, "MEDIUM": 300.0},
        component_quantities={
            "RPE1": {"dimension": "count", "unit": "cells", "value": 100000.0},
            "MEDIUM": {"dimension": "volume", "unit": "uL", "value": 300.0},
        },
        registry={
            "RPE1": ("bio_cellular", "cell_line"),
            "MEDIUM": ("formulation", "medium"),
        },
    )
    state["containers"]["lysate"]["volume_uL"] = 300.0
    state["containers"]["lysate"]["mass_mg"] = 300.0
    state["content_registry"]["RPE1"]["content_attrs"] = {"state": "adherent"}

    result = apply_step(
        step=_sep_step(
            program_name="filtration_program",
            program_args_override=[
                _ir_arg("membrane", _ir_string("adherent_cell_surface")),
                _ir_arg("drive", _ir_string("aspiration")),
            ],
        ),
        material_state=state,
    )

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    slots = result.material_state["indexed_bindings"]["sep_group"]
    filtrate = result.material_state["containers"][slots["0"]]
    retentate = result.material_state["containers"][slots["1"]]
    assert filtrate["component_quantities"]["RPE1"]["value"] == 0.0
    assert retentate["component_quantities"]["RPE1"]["value"] == 100000.0
    assert filtrate["component_quantities"]["MEDIUM"]["value"] == 300.0
    assert retentate["component_quantities"]["MEDIUM"]["value"] == 0.0
    fate = result.delta["partition"]["fates_by_component"]["RPE1"]
    assert fate["source"] == "scientific_model_provider"
    assert fate["association"] == "container_surface"
    assert result.delta["partition"]["transitions_by_component"]["RPE1"]["1"][
        "next_relation"
    ] == "container_surface"
    assert result.delta["partition"]["operation_contract"]["program_args"] == {
        "membrane": "adherent_cell_surface",
        "drive": "aspiration",
    }


def test_sep_aspiration_routes_free_cells_with_the_declared_free_phase():
    result = apply_step(
        step=_sep_step(
            program_name="filtration_program",
            program_args_override=[
                _ir_arg("membrane", _ir_string("adherent_cell_surface")),
                _ir_arg("drive", _ir_string("aspiration")),
            ],
        ),
        material_state=_partition_state(
            components={"RPE1": 100000.0},
            component_quantities={
                "RPE1": {"dimension": "count", "unit": "cells", "value": 100000.0},
            },
            registry={"RPE1": ("bio_cellular", "cell_line")},
        ),
    )

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.material_state["containers"][slots["0"]]["component_quantities"][
        "RPE1"
    ]["value"] == 100000.0
    assert result.material_state["containers"][slots["1"]]["component_quantities"][
        "RPE1"
    ]["value"] == 0.0


def test_sep_aspiration_routes_a_mixed_free_phase_while_retaining_surface_cells():
    state = _partition_state(
        components={
            "HEK293T": 200000.0,
            "MEDIUM": 1000.0,
            "RAB7DNA": 1.0,
            "PEI": 3.0,
        },
        component_quantities={
            "HEK293T": {
                "dimension": "count",
                "unit": "cells",
                "value": 200000.0,
            },
            "MEDIUM": {"dimension": "volume", "unit": "uL", "value": 1000.0},
            "RAB7DNA": {"dimension": "volume", "unit": "uL", "value": 1.0},
            "PEI": {"dimension": "volume", "unit": "uL", "value": 3.0},
        },
        registry={
            "HEK293T": ("bio_cellular", "cell_line"),
            "MEDIUM": ("formulation", "medium"),
            "RAB7DNA": ("bio_molecule_or_virus", "dna"),
            "PEI": ("chemical", "other_chemical"),
        },
    )
    state["containers"]["lysate"]["volume_uL"] = 1004.0
    state["containers"]["lysate"]["mass_mg"] = 1004.0
    state["content_registry"]["HEK293T"]["content_attrs"] = {"state": "adherent"}

    result = apply_step(
        step=_sep_step(
            program_name="filtration_program",
            program_args_override=[
                _ir_arg("membrane", _ir_string("adherent_cell_surface")),
                _ir_arg("drive", _ir_string("aspiration")),
            ],
        ),
        material_state=state,
    )

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    slots = result.material_state["indexed_bindings"]["sep_group"]
    filtrate = result.material_state["containers"][slots["0"]]
    retentate = result.material_state["containers"][slots["1"]]
    assert {
        component: filtrate["component_quantities"][component]["value"]
        for component in ("HEK293T", "MEDIUM", "RAB7DNA", "PEI")
    } == {
        "HEK293T": 0.0,
        "MEDIUM": 1000.0,
        "RAB7DNA": 1.0,
        "PEI": 3.0,
    }
    assert {
        component: retentate["component_quantities"][component]["value"]
        for component in ("HEK293T", "MEDIUM", "RAB7DNA", "PEI")
    } == {
        "HEK293T": 200000.0,
        "MEDIUM": 0.0,
        "RAB7DNA": 0.0,
        "PEI": 0.0,
    }


def test_sep_centrifugal_filtration_uses_filtrate_and_retentate_slots():
    state = _partition_state(
        components={"DNA": 100.0, "WASH": 100.0},
        registry={
            "DNA": ("bio_molecule_or_virus", "dna"),
            "WASH": ("formulation", "buffer"),
        },
    )
    state["content_registry"]["DNA"]["content_attrs"] = {"filter_retains": True}
    result = apply_step(
        step=_sep_step(
            program_name="centrifugal_filtration_program",
            program_args_override=[
                _ir_arg("membrane", _ir_string("silica")),
                _ir_arg("drive", _ir_quantity(8000.0, "g")),
                _ir_arg("duration", _ir_quantity(1.0, "min")),
            ],
        ),
        material_state=state,
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.delta["partition"]["slot_contract"] == {"0": "filtrate", "1": "retentate"}
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {
        "DNA": 0.0,
        "WASH": 100.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "DNA": 100.0,
        "WASH": 0.0,
    }


def test_sep_magnetic_sends_target_and_beads_to_bound_fraction():
    state = _partition_state(
        components={"DNA": 100.0, "BEADS": 100.0, "WASH": 100.0},
        registry={
            "DNA": ("bio_molecule_or_virus", "dna"),
            "BEADS": ("particulate", "beads"),
            "WASH": ("formulation", "buffer"),
        },
    )
    state["content_registry"]["BEADS"]["content_attrs"] = {"bead_property": "magnetic"}
    result = apply_step(
        step=_sep_step(
            program_name="magnetic_program",
            component_fates={"DNA": {"bound": 1.0, "flowthrough": 0.0}},
        ),
        material_state=state,
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.delta["partition"]["slot_contract"] == {"0": "bound", "1": "flowthrough"}
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {
        "BEADS": 100.0,
        "DNA": 100.0,
        "WASH": 0.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "BEADS": 0.0,
        "DNA": 0.0,
        "WASH": 100.0,
    }
    assert result.delta["partition"]["transitions_by_component"]["DNA"]["0"][
        "next_relation"
    ] == "bead_bound"
    assert result.delta["partition"]["transitions_by_component"]["BEADS"]["0"][
        "next_relation"
    ] == "field_retained"
    bound_entries = result.material_state["containers"][slots["0"]][
        "component_entries"
    ]
    dna_entry = next(
        entry for entry in bound_entries if entry["content_ref"] == "DNA"
    )
    bead_entry = next(
        entry for entry in bound_entries if entry["content_ref"] == "BEADS"
    )
    assert dna_entry["associated_with"] == bead_entry["entry_id"]
    assert dna_entry["association_target_kind"] == "component_entry"


def test_sep_magnetic_rejects_an_ambiguous_support_target() -> None:
    state = _partition_state(
        components={"DNA": 100.0, "BEADS_A": 50.0, "BEADS_B": 50.0},
        registry={
            "DNA": ("bio_molecule_or_virus", "dna"),
            "BEADS_A": ("particulate", "beads"),
            "BEADS_B": ("particulate", "beads"),
        },
    )
    state["content_registry"]["BEADS_A"]["content_attrs"] = {
        "bead_property": "magnetic"
    }
    state["content_registry"]["BEADS_B"]["content_attrs"] = {
        "bead_property": "magnetic"
    }

    result = apply_step(
        step=_sep_step(
            program_name="magnetic_program",
            component_fates={"DNA": {"bound": 1.0, "flowthrough": 0.0}},
        ),
        material_state=state,
    )

    assert not result.ok
    assert result.diagnostics[0].code == "MAT_SCIENTIFIC_MODEL_UNRESOLVED"
    assert "association target" in result.diagnostics[0].message


def test_sep_disrupt_is_state_transition_without_guessed_debris_fraction():
    state = _partition_state(
        components={"DNA": 100.0, "CELLS": 100.0},
        registry={
            "DNA": ("bio_molecule_or_virus", "dna"),
            "CELLS": ("bio_cellular", "cell_population"),
        },
    )
    state["content_registry"]["DNA"]["content_attrs"] = {
        "target_remains_identifiable": True
    }
    result = apply_step(
        step=_sep_step(program_name="disrupt_program"),
        material_state=state,
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.delta["partition"]["slot_contract"] == {"0": "lysate", "1": "debris_or_residue"}
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {
        "CELLS": 100.0,
        "DNA": 100.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "CELLS": 0.0,
        "DNA": 0.0,
    }
    assert result.delta["partition"]["fates_by_component"]["CELLS"]["source"] == (
        "state_transition_operation_shape"
    )


def test_sep_disrupt_retires_intact_cell_count_without_inventing_debris() -> None:
    state = _partition_state(
        components={"CELLS": 100000.0, "MEDIUM": 300.0},
        component_quantities={
            "CELLS": {"dimension": "count", "unit": "cells", "value": 100000.0},
            "MEDIUM": {"dimension": "volume", "unit": "uL", "value": 300.0},
        },
        registry={
            "CELLS": ("bio_cellular", "cell_population"),
            "MEDIUM": ("formulation", "medium"),
        },
    )
    state["containers"]["lysate"]["volume_uL"] = 300.0
    state["containers"]["lysate"]["mass_mg"] = 300.0

    result = apply_step(
        step=_sep_step(program_name="disrupt_program"),
        material_state=state,
    )

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    slots = result.material_state["indexed_bindings"]["sep_group"]
    lysate = result.material_state["containers"][slots["0"]]
    debris = result.material_state["containers"][slots["1"]]
    assert "CELLS" not in lysate["components"]
    assert lysate["component_quantities"]["MEDIUM"]["value"] == 300.0
    assert debris["component_quantities"]["MEDIUM"]["value"] == 0.0
    assert result.delta["partition"]["retired_quantities"] == {
        "CELLS": {
            "component_amount": 100000.0,
            "dimension": "count",
            "unit": "cells",
            "value": 100000.0,
        }
    }
    assert result.delta["partition"]["transitions_by_component"]["CELLS"]["0"][
        "next_relation"
    ] == "disrupted"


def test_sep_field_sends_target_to_band_fraction_and_stain_to_non_target_fraction():
    result = apply_step(
        step=_sep_step(
            program_name="field_program",
            component_fates={
                "DNA": {"target_band_fraction": 1.0, "non_target_fraction": 0.0},
                "STAIN": {"target_band_fraction": 0.0, "non_target_fraction": 1.0},
            },
        ),
        material_state=_partition_state(
            components={"DNA": 100.0, "STAIN": 100.0},
            registry={
                "DNA": ("bio_molecule_or_virus", "dna"),
                "STAIN": ("chemical", "dye"),
            },
        ),
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.delta["partition"]["slot_contract"] == {
        "0": "target_band_fraction",
        "1": "non_target_fraction",
    }
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {
        "DNA": 100.0,
        "STAIN": 0.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "DNA": 0.0,
        "STAIN": 100.0,
    }


def test_sep_magnetic_does_not_guess_custom_component_fate():
    result = apply_step(
        step=_sep_step(program_name="magnetic_program"),
        material_state=_partition_state(
            components={"CUSTOM": 100.0},
            registry={"CUSTOM": ("biosample", "custom_material")},
        ),
    )

    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "MAT_SCIENTIFIC_MODEL_UNRESOLVED"
    ]


def test_sep_custom_component_uses_configured_partition_ratio():
    result = apply_step(
        step=_sep_step(program_name="magnetic_program"),
        material_state=_partition_state(
            components={"CUSTOM": 100.0},
            registry={"CUSTOM": ("biosample", "custom_material")},
            metadata={"component_partition_ratios": {"CUSTOM": {"0": 0.2, "1": 0.8}}},
        ),
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {"CUSTOM": 20.0}
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {"CUSTOM": 80.0}
    assert result.delta["partition"]["ratios_by_component"] == {"CUSTOM": {"0": 0.2, "1": 0.8}}
    assert result.diagnostics == []


def test_frac_creates_ordered_indexed_bindings():
    step = _frac_step(bins=4)
    state = {
        "containers": {
            "gradient_tube": {"volume_uL": 120.0, "mass_mg": 120.0, "components": {"Cells": 12.0}, "metadata": {}},
        }
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    slots = result.material_state["indexed_bindings"]["frac_group"]
    assert list(slots.keys()) == ["0", "1", "2", "3"]
    assert all(result.material_state["containers"][slot_id]["volume_uL"] == 30.0 for slot_id in slots.values())


def test_frac_splits_count_only_cellular_material_across_bins():
    step = _frac_step(bins=4)
    state = {
        "containers": {
            "gradient_tube": {
                "volume_uL": 0.0,
                "mass_mg": 0.0,
                "components": {"CELLS": 100000.0},
                "component_quantities": {
                    "CELLS": {"dimension": "count", "unit": "cells", "value": 100000.0}
                },
                "metadata": {},
            }
        },
        "content_registry": {
            "CELLS": {"content_kind": "bio_cellular", "content_type": "cell_population"}
        },
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    slots = result.material_state["indexed_bindings"]["frac_group"]
    assert len(slots) == 4
    assert all(
        result.material_state["containers"][slot_id]["component_quantities"]["CELLS"]["value"] == 25000.0
        for slot_id in slots.values()
    )
    assert sum(movement.count_cells for movement in result.movements) == 100000.0


def test_runtime_emits_material_delta_on_current_material_success():
    step = _mutation_step(
        _ir_identifier("B"),
        [{"kind": "IRPair", "left": _ir_identifier("A"), "right": _ir_quantity(50.0, "uL"), "span": None}],
    )
    plan = PlanProgram(
        plans=[ProtocolPlan(protocol_id="p0", protocol_name="T", steps=[step], span=None)],
        diagnostics=[],
        span=None,
    )
    state = init_state(plan)
    state.artifacts["material_state"] = {
        "containers": {
            "A": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {"DNA": 10.0}, "metadata": {}},
            "B": {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
        }
    }

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert result.ok
    event = next(e for e in result.events if e.kind == "STEP_COMPLETED")
    assert "material_delta" in event.payload
    assert event.payload["material_delta"]["op"] == "Mutation"


def test_runtime_fails_step_on_current_material_bridge_error():
    step = _mutation_step(
        _ir_identifier("B"),
        [{"kind": "IRPair", "left": _ir_identifier("A"), "right": _ir_quantity(100.0, "mg"), "span": None}],
        tool="Spatula",
    )
    plan = PlanProgram(
        plans=[ProtocolPlan(protocol_id="p0", protocol_name="T", steps=[step], span=None)],
        diagnostics=[],
        span=None,
    )
    state = init_state(plan)
    state.artifacts["material_state"] = {
        "containers": {
            "A": {"volume_uL": 1000.0, "mass_mg": 0.0, "components": {"DNA": 100.0}, "metadata": {}},
            "B": {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
        }
    }

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert not result.ok
    assert result.state.step_status[step.step_id] == "failed"
    assert "MAT_MISSING_DENSITY" in [d.code for d in result.diagnostics]
