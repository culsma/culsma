"""Material conservation checks."""

from __future__ import annotations

from typing import Any

from culsma.runtime.material.ledger import CONSERVATION_ABS_EPS, container_count_cells, density_mg_per_uL
from culsma.runtime.material.units import COUNT_TO_CELLS


CONSERVATION_REL_EPS = 1e-9
CONSERVATION_OPS = {"Mutation", "sep", "frac"}


class MaterialConservation:
    @staticmethod
    def state_totals(state: dict[str, Any]) -> dict[str, float]:
        return state_totals(state)

    @staticmethod
    def totals_conserved(before: dict[str, float], after: dict[str, float]) -> bool:
        return totals_conserved(before, after)

    @staticmethod
    def totals_conserved_with_declared_retirements(
        before: dict[str, float],
        after: dict[str, float],
        delta: dict[str, Any],
    ) -> bool:
        return totals_conserved_with_declared_retirements(before, after, delta)


def state_totals(state: dict[str, Any]) -> dict[str, float]:
    total_volume = 0.0
    total_mass = 0.0
    total_components = 0.0
    total_cells = 0.0
    containers = state.setdefault("containers", {})
    for obj in containers.values():
        if not isinstance(obj, dict):
            continue
        volume_uL = float(obj.get("volume_uL", 0.0))
        mass_mg = float(obj.get("mass_mg", 0.0))
        density = density_mg_per_uL(obj)
        if density is not None and density > 0:
            total_volume += max(volume_uL, mass_mg / density)
            total_mass += max(mass_mg, volume_uL * density)
        else:
            total_volume += volume_uL
            total_mass += mass_mg
        comp = obj.get("components", {})
        if isinstance(comp, dict):
            total_components += sum(float(v) for v in comp.values())
        total_cells += container_count_cells(obj)
    return {
        "volume_uL": total_volume,
        "mass_mg": total_mass,
        "count_cells": total_cells,
        "components": total_components,
    }


def totals_conserved(before: dict[str, float], after: dict[str, float]) -> bool:
    return all(
        _close_enough(float(before.get(key, 0.0)), float(after.get(key, 0.0)))
        for key in ("volume_uL", "mass_mg", "count_cells", "components")
    )


def totals_conserved_with_declared_retirements(
    before: dict[str, float],
    after: dict[str, float],
    delta: dict[str, Any],
) -> bool:
    retirements = declared_quantity_retirements(delta)
    if not retirements:
        return totals_conserved(before, after)
    expected = dict(before)
    for retirement in retirements:
        expected["components"] = max(
            0.0,
            float(expected.get("components", 0.0))
            - float(retirement.get("component_amount", 0.0)),
        )
        if retirement.get("dimension") != "count":
            return False
        unit = str(retirement.get("unit", ""))
        if unit not in COUNT_TO_CELLS:
            return False
        expected["count_cells"] = max(
            0.0,
            float(expected.get("count_cells", 0.0))
            - float(retirement.get("value", 0.0)) * COUNT_TO_CELLS[unit],
        )
    return totals_conserved(expected, after)


def declared_quantity_retirements(delta: Any) -> list[dict[str, Any]]:
    if isinstance(delta, list):
        return [
            retirement
            for item in delta
            for retirement in declared_quantity_retirements(item)
        ]
    if not isinstance(delta, dict):
        return []
    retirements: list[dict[str, Any]] = []
    raw = delta.get("retired_quantities")
    if isinstance(raw, dict):
        retirements.extend(
            retirement
            for retirement in raw.values()
            if isinstance(retirement, dict)
        )
    for key, value in delta.items():
        if key == "retired_quantities":
            continue
        retirements.extend(declared_quantity_retirements(value))
    return retirements


def _close_enough(before: float, after: float) -> bool:
    delta = abs(before - after)
    if delta <= CONSERVATION_ABS_EPS:
        return True
    scale = max(abs(before), abs(after), CONSERVATION_ABS_EPS)
    return (delta / scale) <= CONSERVATION_REL_EPS
