"""Material conservation checks."""

from __future__ import annotations

from typing import Any

from culsma.runtime.material.ledger import CONSERVATION_ABS_EPS, container_count_cells, density_mg_per_uL


CONSERVATION_REL_EPS = 1e-9
CONSERVATION_OPS = {"Mutation", "sep", "frac"}


class MaterialConservation:
    @staticmethod
    def state_totals(state: dict[str, Any]) -> dict[str, float]:
        return state_totals(state)

    @staticmethod
    def totals_conserved(before: dict[str, float], after: dict[str, float]) -> bool:
        return totals_conserved(before, after)


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


def _close_enough(before: float, after: float) -> bool:
    delta = abs(before - after)
    if delta <= CONSERVATION_ABS_EPS:
        return True
    scale = max(abs(before), abs(after), CONSERVATION_ABS_EPS)
    return (delta / scale) <= CONSERVATION_REL_EPS
