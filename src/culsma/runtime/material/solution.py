"""Declared homogeneous solution loads, using the existing component ledger.

A stock's unspecified liquid matrix has its own volume entry. Its solute has
an independent mass entry, with no mass-to-volume compatibility projection.
No solvent identity, density, or physical dissolution is inferred.
"""
from math import isfinite
from typing import Any

from .args import arg_quantity
from .component_entries import append_component_quantity
from .diagnostics import diagnostic_result
from .result import MaterialUpdateResult
from .units import VOLUME_TO_UL


def solution_state_error(state: dict[str, Any]) -> str | None:
    """Validate the bounded homogeneous-solution model before committing a step.

    Legacy bare masses have a compatibility volume, not a declared solution
    volume. They must not enter this model, even under a different identity.
    Inspect entries as well as totals so associations cannot disappear behind
    the per-content projection.
    """
    registry = state.get("content_registry", {})
    for container_id, container in state.get("containers", {}).items():
        if not has_solution_solutes(container):
            continue
        for entry in container.get("component_entries", []):
            quantity = entry.get("quantity", {})
            if quantity.get("value") == 0:
                continue
            content = registry.get(entry.get("content_ref"), {})
            physical_state = content.get("content_attrs", {}).get("state")
            supported_axis = (
                quantity.get("dimension") == "volume"
                or (quantity.get("dimension") == "mass" and quantity.get("solution_solute"))
            )
            if (quantity.get("status") == "unknown" or not supported_axis
                    or entry.get("relation", "free") != "free"
                    or content.get("content_kind") == "bio_cellular"
                    or physical_state not in (None, "liquid", "solution")):
                return (f"Container '{container_id}' cannot combine a declared solution with "
                        f"component '{entry.get('content_ref')}': only known free solution "
                        "solutes and liquid volume loads are supported")
    return None


def load_solution(step, state, container_id, content_id, amount):
    from .ledger import check_capacity_guard, refresh_container_aggregates
    from .contents_state import invalidate_contents_state

    concentration = arg_quantity(step.args.get("concentration"))
    volume = amount["value"] * VOLUME_TO_UL.get(amount["unit"], 0)
    if (amount["unit"] not in VOLUME_TO_UL or not isfinite(volume) or volume < 0
            or concentration is None or concentration["unit"] != "mg_per_uL"
            or not isfinite(concentration["value"]) or concentration["value"] < 0):
        return diagnostic_result(step, state, "MAT_INVALID_SOLUTION_CONCENTRATION",
                                 "Concentration requires a finite non-negative mass/volume value and volume load")
    mass = concentration["value"] * volume
    if not isfinite(mass):
        return diagnostic_result(step, state, "MAT_INVALID_SOLUTION_CONCENTRATION", "Derived solute mass is not finite")
    registry = state["content_registry"]
    if registry[content_id].get("content_kind") == "bio_cellular":
        return diagnostic_result(step, state, "MAT_INVALID_SOLUTION_CONCENTRATION",
                                 "Cellular materials use the existing count/carrier relationship")
    attrs = registry[content_id].get("content_attrs", {})
    if attrs.get("state") in {"solid", "powder", "pellet", "precipitate", "adherent"}:
        return diagnostic_result(step, state, "MAT_INVALID_SOLUTION_CONCENTRATION",
                                 "Solution concentration requires homogeneous liquid content")
    container = state["containers"][container_id]
    existing = container.get("component_quantities", {}).get(content_id)
    if existing and (existing.get("dimension") != "mass" or not existing.get("solution_solute")):
        return diagnostic_result(step, state, "MAT_CONTENT_LOAD_AXIS_MISMATCH",
                                 "Cannot combine a solution solute with an undeclared quantity basis")
    guard = check_capacity_guard(step=step, state=state, container_id=container_id, added_uL=volume)
    if guard is not None:
        return guard
    # The load step identity, unlike the material code, cannot collide with an
    # authored content code. Repeated calls have namespaced step identities.
    carrier = f"__solution_matrix__::{container_id}::{step.step_id}"
    while carrier in registry:
        carrier += "_"
    registry[carrier] = {"content_kind": "formulation", "content_type": "buffer",
                         "content_code": carrier, "content_name": "Unspecified stock solution matrix",
                         "content_attrs": {"role": "carrier", "implicit": True}}
    append_component_quantity(container, content_ref=carrier, amount=volume,
        quantity={"dimension": "volume", "unit": "uL", "value": volume,
                  "cross_axis_projection": False}, relation="free", partition_class="buffer")
    append_component_quantity(container, content_ref=content_id, amount=mass,
        quantity={"dimension": "mass", "unit": "mg", "value": mass,
                  "cross_axis_projection": False, "solution_solute": True},
        relation="free", partition_class="solute")
    refresh_container_aggregates(container)
    invalidate_contents_state(state, container_id, reason="solution_load")
    return MaterialUpdateResult(material_state=state, diagnostics=[],
        delta={"op": "LoadContent", "container": container_id, "content_id": content_id,
               "volume_uL": volume, "solute_mass_mg": mass,
               "declared_concentration": concentration})


def project_concentrations(container: dict[str, Any]) -> None:
    """Expose current per-solute concentrations, never original stock labels."""
    volume = sum(q.get("value", 0) * VOLUME_TO_UL.get(q.get("unit"), 0)
                 for q in container.get("component_quantities", {}).values()
                 if q.get("dimension") == "volume")
    values = {}
    for code, q in container.get("component_quantities", {}).items():
        if q.get("solution_solute"):
            values[code] = {"value": q["value"] / volume if volume > 0 and q.get("value") is not None else None,
                            "unit": "mg_per_uL", "source": "derived"}
    if values:
        container["component_concentrations"] = values
    else:
        container.pop("component_concentrations", None)


def has_solution_solutes(container: dict[str, Any]) -> bool:
    return any(q.get("solution_solute")
               for q in container.get("component_quantities", {}).values())
