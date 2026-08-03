from __future__ import annotations

from culsma.driver.stub import StubDriver
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.runtime.executor import run
from culsma.runtime.material_compute import apply_step
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
) -> PlanStep:
    program_args = [
        _ir_arg("drive", _ir_quantity(12000.0, "g")),
    ]
    if keep_source is not None:
        program_args.append(_ir_arg("keep_source", _ir_string(keep_source)))
    return PlanStep(
        step_id=step_id,
        op="sep",
        args={
            "sample": _ir_identifier("lysate"),
            "program": _ir_call(program_name, program_args),
            "bind": "sep_group",
        },
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
) -> dict[str, object]:
    return {
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
        }
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert set(slots) == {"0", "1"}
    assert result.material_state["containers"][slots["0"]]["volume_uL"] == 50.0
    assert result.material_state["containers"][slots["1"]]["volume_uL"] == 50.0
    assert {
        (movement.source, movement.destination, movement.volume_uL, movement.mass_mg)
        for movement in result.movements
    } == {
        ("lysate", slots["0"], 50.0, 50.0),
        ("lysate", slots["1"], 50.0, 50.0),
    }


def test_sep_keep_source_pellet_reuses_source_container_for_slot_1():
    step = _sep_step(keep_source="pellet")
    state = {
        "containers": {
            "lysate": {"volume_uL": 100.0, "mass_mg": 100.0, "components": {"DNA": 10.0}, "metadata": {}},
        }
    }

    result = apply_step(step=step, material_state=state)

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert slots["1"] == "lysate"
    assert result.material_state["containers"]["lysate"]["volume_uL"] == 50.0
    assert result.material_state["containers"][slots["0"]]["volume_uL"] == 50.0


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
        "CELLS": 1.0,
        "MEDIUM": 99.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "CELLS": 99.0,
        "MEDIUM": 1.0,
    }


def test_sep_phase_partition_sends_target_phase_material_away_from_extraction_reagent():
    result = apply_step(
        step=_sep_step(program_name="phase_partition_program"),
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
        "DNA": 99.0,
        "PCI": 1.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "DNA": 1.0,
        "PCI": 99.0,
    }


def test_sep_phase_partition_uses_equal_split_for_unsupported_supported_classes():
    result = apply_step(
        step=_sep_step(program_name="phase_partition_program"),
        material_state=_partition_state(
            components={"REAGENT": 100.0},
            registry={"REAGENT": ("chemical", "organic_compound")},
        ),
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {"REAGENT": 50.0}
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {"REAGENT": 50.0}
    assert result.delta["partition"]["ratios_by_class"] == {"soluble_compound": {"0": 0.5, "1": 0.5}}
    assert [d.code for d in result.diagnostics] == ["MAT_CONTENT_PARTITION_FALLBACK"]
    assert result.diagnostics[0].severity == "warning"


def test_sep_precipitation_sends_target_to_precipitate_and_liquid_to_supernatant():
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

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.delta["partition"]["slot_contract"] == {"0": "precipitate", "1": "supernatant"}
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {
        "DNA": 95.0,
        "ETOH": 1.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "DNA": 5.0,
        "ETOH": 99.0,
    }
    slot0_classes = result.material_state["containers"][slots["0"]]["metadata"]["component_partition_classes"]
    assert slot0_classes["DNA"] == "retained_fraction"


def test_sep_filtration_sends_liquid_to_filtrate_and_target_to_retentate():
    result = apply_step(
        step=_sep_step(program_name="filtration_program"),
        material_state=_partition_state(
            components={"DNA": 100.0, "WASH": 100.0},
            registry={
                "DNA": ("bio_molecule_or_virus", "dna"),
                "WASH": ("formulation", "buffer"),
            },
        ),
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.delta["partition"]["slot_contract"] == {"0": "filtrate", "1": "retentate"}
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {
        "DNA": 1.0,
        "WASH": 99.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "DNA": 99.0,
        "WASH": 1.0,
    }
    slot1_classes = result.material_state["containers"][slots["1"]]["metadata"]["component_partition_classes"]
    assert slot1_classes["DNA"] == "retained_fraction"


def test_sep_magnetic_sends_target_and_beads_to_bound_fraction():
    result = apply_step(
        step=_sep_step(program_name="magnetic_program"),
        material_state=_partition_state(
            components={"DNA": 100.0, "BEADS": 100.0, "WASH": 100.0},
            registry={
                "DNA": ("bio_molecule_or_virus", "dna"),
                "BEADS": ("particulate", "beads"),
                "WASH": ("formulation", "buffer"),
            },
        ),
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.delta["partition"]["slot_contract"] == {"0": "bound", "1": "flowthrough"}
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {
        "BEADS": 99.0,
        "DNA": 99.0,
        "WASH": 1.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "BEADS": 1.0,
        "DNA": 1.0,
        "WASH": 99.0,
    }
    slot0_classes = result.material_state["containers"][slots["0"]]["metadata"]["component_partition_classes"]
    assert slot0_classes["DNA"] == "retained_fraction"
    assert slot0_classes["BEADS"] == "retained_fraction"


def test_sep_disrupt_sends_released_material_to_lysate_and_cells_to_residue():
    result = apply_step(
        step=_sep_step(program_name="disrupt_program"),
        material_state=_partition_state(
            components={"DNA": 100.0, "CELLS": 100.0},
            registry={
                "DNA": ("bio_molecule_or_virus", "dna"),
                "CELLS": ("bio_cellular", "cell_population"),
            },
        ),
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert result.delta["partition"]["slot_contract"] == {"0": "lysate", "1": "debris_or_residue"}
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {
        "CELLS": 5.0,
        "DNA": 95.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "CELLS": 95.0,
        "DNA": 5.0,
    }


def test_sep_field_sends_target_to_band_fraction_and_stain_to_non_target_fraction():
    result = apply_step(
        step=_sep_step(program_name="field_program"),
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
        "DNA": 95.0,
        "STAIN": 5.0,
    }
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {
        "DNA": 5.0,
        "STAIN": 95.0,
    }


def test_sep_custom_components_use_conservative_equal_split_by_default():
    result = apply_step(
        step=_sep_step(program_name="magnetic_program"),
        material_state=_partition_state(
            components={"CUSTOM": 100.0},
            registry={"CUSTOM": ("biosample", "custom_material")},
        ),
    )

    assert result.ok
    slots = result.material_state["indexed_bindings"]["sep_group"]
    assert _rounded_components(result.material_state["containers"][slots["0"]]) == {"CUSTOM": 50.0}
    assert _rounded_components(result.material_state["containers"][slots["1"]]) == {"CUSTOM": 50.0}
    assert result.delta["partition"]["ratios_by_class"] == {"custom": {"0": 0.5, "1": 0.5}}
    assert result.delta["partition"]["ratios_by_component"] == {"CUSTOM": {"0": 0.5, "1": 0.5}}
    assert [d.code for d in result.diagnostics] == ["MAT_CONTENT_PARTITION_FALLBACK"]
    assert result.diagnostics[0].severity == "warning"


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
