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


def _sep_step(*, keep_source: str | None = None, step_id: str = "p0.s0") -> PlanStep:
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
            "program": _ir_call("centrifuge_program", program_args),
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
