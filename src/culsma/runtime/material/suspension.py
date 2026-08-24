"""Cell-suspension material relationships and count-to-volume resolution."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.args import arg_string
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.ledger import check_capacity_guard, ensure_container
from culsma.runtime.material.refs import resolve_or_create_container_ref
from culsma.runtime.material.result import MaterialUpdateResult


DEFAULT_CELL_SUSPENSION_CONCENTRATION_CELLS_PER_UL = 1000.0
IMPLICIT_CELL_CARRIER_PREFIX = "__implicit_cell_carrier__::"


@dataclass(frozen=True)
class CellSuspensionPolicy:
    """Runtime assumptions used only when a cell count has no explicit carrier."""

    default_concentration_cells_per_uL: float = DEFAULT_CELL_SUSPENSION_CONCENTRATION_CELLS_PER_UL
    allow_implicit_carrier: bool = True
    unspecified_state: str = "suspension"


@dataclass(frozen=True)
class CountAliquotResolution:
    requested_cells: float
    available_cells: float
    component_ratio: float
    carrier_volume_uL: float
    resolved_transfer_volume_uL: float
    moved_bulk_volume_uL: float
    moved_bulk_mass_mg: float
    concentration_cells_per_uL: float
    concentration_source: str
    policy_id: str


def cell_suspension_policy(state: dict[str, Any]) -> CellSuspensionPolicy:
    raw_policy = state.get("material_policy")
    raw = raw_policy.get("cell_suspension") if isinstance(raw_policy, dict) else None
    if not isinstance(raw, dict):
        return CellSuspensionPolicy()
    concentration = raw.get(
        "default_concentration_cells_per_uL",
        DEFAULT_CELL_SUSPENSION_CONCENTRATION_CELLS_PER_UL,
    )
    try:
        parsed_concentration = float(concentration)
    except (TypeError, ValueError):
        parsed_concentration = float("nan")
    allow_implicit = raw.get("allow_implicit_carrier", True)
    unspecified_state = raw.get("unspecified_state", "suspension")
    return CellSuspensionPolicy(
        default_concentration_cells_per_uL=parsed_concentration,
        allow_implicit_carrier=bool(allow_implicit),
        unspecified_state=str(unspecified_state),
    )


def apply_finalize_container_contents(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    container_name = arg_string(step.args.get("container"))
    if container_name is None:
        return diagnostic_result(
            step,
            state,
            "MAT_CONTAINER_NOT_FOUND",
            "FinalizeContainerContents requires a container",
        )
    container_id = resolve_or_create_container_ref(state, container_name)
    container = ensure_container(state, container_id)
    policy = cell_suspension_policy(state)
    count_ids = _count_component_ids(container)
    if not count_ids:
        refresh_cell_suspension_relationship(state, container_id)
        return MaterialUpdateResult(
            material_state=state,
            diagnostics=[],
            delta={"op": "FinalizeContainerContents", "container": container_id, "relationships": []},
        )

    material_state, material_state_source = _inferred_cell_state_details(
        state, count_ids, policy.unspecified_state
    )
    carrier_ids = _carrier_component_ids(state, container)
    implicit_volume_uL = 0.0
    diagnostics: list[Diagnostic] = []
    if material_state == "suspension" and not carrier_ids:
        if policy.allow_implicit_carrier and (
            not isfinite(policy.default_concentration_cells_per_uL)
            or policy.default_concentration_cells_per_uL <= 0
        ):
            return diagnostic_result(
                step,
                state,
                "MAT_INVALID_CELL_SUSPENSION_CONCENTRATION",
                "Default cell-suspension concentration must be greater than zero",
            )
        if policy.allow_implicit_carrier:
            implicit_volume_uL = _total_count_cells(container) / policy.default_concentration_cells_per_uL
            cap_diag = check_capacity_guard(
                step=step,
                state=state,
                container_id=container_id,
                added_uL=implicit_volume_uL,
            )
            if cap_diag is not None:
                return diagnostic_result(
                    step,
                    state,
                    "MAT_IMPLICIT_CARRIER_OVERFLOW",
                    f"Implicit cell carrier would exceed capacity of container '{container_id}'",
                )
            carrier_id = _add_implicit_carrier(state, container_id, container, implicit_volume_uL)
            carrier_ids = [carrier_id]
            diagnostics.append(
                Diagnostic(
                    code="ASSUMED_CELL_SUSPENSION_CONCENTRATION",
                    message=(
                        f"Assumed {policy.default_concentration_cells_per_uL:g} cells/uL for "
                        f"count-only cellular content in '{container_id}'"
                    ),
                    span=step.span,
                    severity="warning",
                    node_id=step.step_id,
                )
            )

    relationship = refresh_cell_suspension_relationship(
        state,
        container_id,
        forced_state=material_state,
        concentration_source="default" if implicit_volume_uL > 0 else "derived",
        material_state_source=material_state_source,
    )
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=diagnostics,
        delta={
            "op": "FinalizeContainerContents",
            "container": container_id,
            "implicit_carrier_volume_uL": implicit_volume_uL,
            "relationships": [relationship] if relationship is not None else [],
        },
    )


def refresh_cell_suspension_relationship(
    state: dict[str, Any],
    container_id: str,
    *,
    forced_state: str | None = None,
    concentration_source: str | None = None,
    material_state_source: str | None = None,
) -> dict[str, Any] | None:
    """Rebuild the derived relationship without inventing any new material."""

    containers = state.get("containers")
    container = containers.get(container_id) if isinstance(containers, dict) else None
    if not isinstance(container, dict):
        return None
    return refresh_cell_suspension_relationship_record(
        state,
        container,
        forced_state=forced_state,
        concentration_source=concentration_source,
        material_state_source=material_state_source,
    )


def refresh_cell_suspension_relationship_record(
    state: dict[str, Any],
    container: dict[str, Any],
    *,
    forced_state: str | None = None,
    concentration_source: str | None = None,
    material_state_source: str | None = None,
) -> dict[str, Any] | None:
    """Rebuild the derived relationship on a container or tracked contents part."""

    existing = cell_suspension_relationship(container)
    count_ids = _count_component_ids(container)
    relationships = container.setdefault("material_relationships", [])
    if not isinstance(relationships, list):
        container["material_relationships"] = []
        relationships = container["material_relationships"]
    relationships[:] = [
        relationship
        for relationship in relationships
        if not (isinstance(relationship, dict) and relationship.get("subtype") == "cell_suspension")
    ]
    if not count_ids or _total_count_cells(container) <= 0:
        return None

    carrier_ids = _carrier_component_ids(state, container)
    policy = cell_suspension_policy(state)
    material_state = forced_state
    state_source = material_state_source
    if material_state is not None and state_source is None:
        state_source = "runtime_transition"
    if material_state is None and isinstance(existing, dict):
        previous_state = existing.get("material_state")
        if isinstance(previous_state, str):
            material_state = previous_state
            previous_state_source = existing.get("material_state_source")
            if isinstance(previous_state_source, str):
                state_source = previous_state_source
    if material_state is None:
        material_state, state_source = _inferred_cell_state_details(
            state, count_ids, policy.unspecified_state
        )
    carrier_volume_uL = _carrier_volume_from_ids(container, carrier_ids)
    transferable = material_state == "suspension" and carrier_volume_uL > 0
    concentration = _total_count_cells(container) / carrier_volume_uL if transferable else None
    source = concentration_source
    if source is None and isinstance(existing, dict):
        previous_concentration = existing.get("concentration")
        previous_source = (
            previous_concentration.get("source") if isinstance(previous_concentration, dict) else None
        )
        previous_value = (
            previous_concentration.get("value") if isinstance(previous_concentration, dict) else None
        )
        if (
            isinstance(previous_source, str)
            and isinstance(previous_value, (int, float))
            and isinstance(concentration, (int, float))
            and abs(float(previous_value) - float(concentration)) <= 1e-12
        ):
            source = previous_source
    if source is None:
        source = "derived"
    assumption_policy_ids = (
        ["default_cell_suspension_concentration"]
        if any(carrier_id.startswith(IMPLICIT_CELL_CARRIER_PREFIX) for carrier_id in carrier_ids)
        else []
    )
    relationship = {
        "kind": "dispersion",
        "subtype": "cell_suspension",
        "dispersed_component_ids": count_ids,
        "carrier_component_ids": carrier_ids,
        "carrier_volume_uL": carrier_volume_uL,
        "material_state": material_state,
        "material_state_source": state_source or "runtime_transition",
        "transferability": "homogeneous_aliquot" if transferable else "non_homogeneous",
        "assumption_policy_ids": assumption_policy_ids,
        "concentration": {
            "value": concentration,
            "unit": "cells_per_uL",
            "source": source,
            "policy_id": (
                "default_cell_suspension_concentration" if source == "default" else "explicit_carrier_volume"
            ),
        },
    }
    relationships.append(relationship)
    return relationship


def resolve_count_aliquot(
    *,
    step: PlanStep,
    state: dict[str, Any],
    container: dict[str, Any],
    source_id: str,
    requested_cells: float,
    relationship: dict[str, Any] | None,
) -> CountAliquotResolution | MaterialUpdateResult:
    """Resolve a cell-count request into component ratio and carrier volume."""

    if requested_cells < 0 or not requested_cells.is_integer():
        return diagnostic_result(
            step,
            state,
            "MAT_CELL_COUNT_VALUE_INVALID",
            "Transferred cell count must be a non-negative integer",
        )
    if requested_cells == 0:
        concentration_record = relationship.get("concentration") if isinstance(relationship, dict) else None
        return CountAliquotResolution(
            requested_cells=0.0,
            available_cells=_total_count_cells(container),
            component_ratio=0.0,
            carrier_volume_uL=0.0,
            resolved_transfer_volume_uL=0.0,
            moved_bulk_volume_uL=0.0,
            moved_bulk_mass_mg=0.0,
            concentration_cells_per_uL=float(
                concentration_record.get("value", 0.0)
                if isinstance(concentration_record, dict)
                and isinstance(concentration_record.get("value"), (int, float))
                else 0.0
            ),
            concentration_source=str(
                concentration_record.get("source", "derived")
                if isinstance(concentration_record, dict)
                else "derived"
            ),
            policy_id=str(
                concentration_record.get("policy_id", "explicit_carrier_volume")
                if isinstance(concentration_record, dict)
                else "explicit_carrier_volume"
            ),
        )
    count_ids = _count_component_ids(container)
    if len(count_ids) != 1:
        return diagnostic_result(
            step,
            state,
            "MAT_COUNT_TRANSFER_AMBIGUOUS",
            f"Count transfer from '{source_id}' requires exactly one cellular count component",
        )
    available_cells = _total_count_cells(container)
    if available_cells + 1e-12 < requested_cells:
        return diagnostic_result(
            step,
            state,
            "MAT_INSUFFICIENT_COUNT",
            f"Insufficient source cell count in '{source_id}'",
        )
    if (
        not isinstance(relationship, dict)
        or relationship.get("transferability") != "homogeneous_aliquot"
    ):
        return diagnostic_result(
            step,
            state,
            "MAT_COUNT_TRANSFER_SOURCE_NOT_SUSPENSION",
            f"Cell count in '{source_id}' is not a transferable homogeneous suspension",
        )
    raw_carrier_ids = relationship.get("carrier_component_ids")
    carrier_ids = [item for item in raw_carrier_ids if isinstance(item, str)] if isinstance(raw_carrier_ids, list) else []
    carrier_volume_uL = _carrier_volume_from_ids(container, carrier_ids)
    if carrier_volume_uL <= 0:
        return diagnostic_result(
            step,
            state,
            "MAT_COUNT_TRANSFER_SOURCE_NOT_SUSPENSION",
            f"Cell suspension in '{source_id}' has no transferable carrier volume",
        )
    ratio = 0.0 if available_cells == 0 else requested_cells / available_cells
    concentration = available_cells / carrier_volume_uL
    concentration_record = relationship.get("concentration")
    concentration_source = (
        concentration_record.get("source") if isinstance(concentration_record, dict) else "derived"
    )
    policy_id = (
        concentration_record.get("policy_id")
        if isinstance(concentration_record, dict)
        else "explicit_carrier_volume"
    )
    return CountAliquotResolution(
        requested_cells=requested_cells,
        available_cells=available_cells,
        component_ratio=ratio,
        carrier_volume_uL=carrier_volume_uL,
        resolved_transfer_volume_uL=carrier_volume_uL * ratio,
        moved_bulk_volume_uL=float(container.get("volume_uL", 0.0)) * ratio,
        moved_bulk_mass_mg=float(container.get("mass_mg", 0.0)) * ratio,
        concentration_cells_per_uL=concentration,
        concentration_source=str(concentration_source),
        policy_id=str(policy_id),
    )


def cell_suspension_relationship(container: Any) -> dict[str, Any] | None:
    if not isinstance(container, dict):
        return None
    relationships = container.get("material_relationships")
    if not isinstance(relationships, list):
        return None
    for relationship in relationships:
        if isinstance(relationship, dict) and relationship.get("subtype") == "cell_suspension":
            return relationship
    return None


def count_component_ids(container: Any) -> list[str]:
    return _count_component_ids(container) if isinstance(container, dict) else []


def total_count_cells(container: Any) -> float:
    return _total_count_cells(container) if isinstance(container, dict) else 0.0


def _count_component_ids(container: dict[str, Any]) -> list[str]:
    quantities = container.get("component_quantities")
    if not isinstance(quantities, dict):
        return []
    return sorted(
        content_id
        for content_id, quantity in quantities.items()
        if isinstance(content_id, str)
        and isinstance(quantity, dict)
        and quantity.get("dimension") == "count"
        and quantity.get("unit") == "cells"
        and float(quantity.get("value", 0.0)) > 0
    )


def _total_count_cells(container: dict[str, Any]) -> float:
    quantities = container.get("component_quantities")
    if not isinstance(quantities, dict):
        return 0.0
    return sum(
        float(quantity.get("value", 0.0))
        for quantity in quantities.values()
        if isinstance(quantity, dict)
        and quantity.get("dimension") == "count"
        and quantity.get("unit") == "cells"
    )


def _carrier_component_ids(state: dict[str, Any], container: dict[str, Any]) -> list[str]:
    quantities = container.get("component_quantities")
    registry = state.get("content_registry")
    if not isinstance(quantities, dict):
        return []
    carrier_ids: list[str] = []
    for content_id, quantity in quantities.items():
        if not isinstance(content_id, str) or not isinstance(quantity, dict):
            continue
        if quantity.get("dimension") != "volume" or float(quantity.get("value", 0.0)) <= 0:
            continue
        record = registry.get(content_id) if isinstance(registry, dict) else None
        if content_id.startswith(IMPLICIT_CELL_CARRIER_PREFIX) or (
            isinstance(record, dict)
            and record.get("content_kind") == "formulation"
            and record.get("content_type") in {"medium", "buffer"}
        ):
            carrier_ids.append(content_id)
    return sorted(carrier_ids)


def _carrier_volume_from_ids(container: dict[str, Any], carrier_ids: list[str]) -> float:
    quantities = container.get("component_quantities")
    if not isinstance(quantities, dict):
        return 0.0
    return sum(
        float(quantity.get("value", 0.0))
        for content_id in carrier_ids
        for quantity in [quantities.get(content_id)]
        if isinstance(quantity, dict)
        and quantity.get("dimension") == "volume"
        and quantity.get("unit") == "uL"
    )


def _inferred_cell_state(state: dict[str, Any], count_ids: list[str], default: str) -> str:
    return _inferred_cell_state_details(state, count_ids, default)[0]


def _inferred_cell_state_details(
    state: dict[str, Any], count_ids: list[str], default: str
) -> tuple[str, str]:
    registry = state.get("content_registry")
    states: set[str] = set()
    for content_id in count_ids:
        record = registry.get(content_id) if isinstance(registry, dict) else None
        attrs = record.get("content_attrs") if isinstance(record, dict) else None
        raw = attrs.get("state") or attrs.get("culture_state") if isinstance(attrs, dict) else None
        if isinstance(raw, str) and raw.strip():
            normalized = raw.strip().lower()
            if normalized in {"suspended", "suspension"}:
                normalized = "suspension"
            states.add(normalized)
    if not states:
        return default, "policy_default"
    if len(states) == 1:
        return next(iter(states)), "content_metadata"
    return "mixed", "content_metadata"


def _add_implicit_carrier(
    state: dict[str, Any],
    container_id: str,
    container: dict[str, Any],
    volume_uL: float,
) -> str:
    carrier_id = f"{IMPLICIT_CELL_CARRIER_PREFIX}{container_id}"
    registry = state.setdefault("content_registry", {})
    if isinstance(registry, dict):
        registry[carrier_id] = {
            "content_kind": "formulation",
            "content_type": "medium",
            "content_code": carrier_id,
            "content_name": "implicit cell carrier",
            "content_attrs": {
                "role": "implicit_cell_carrier",
                "provenance": "default_cell_suspension_concentration",
            },
        }
    components = container.setdefault("components", {})
    if isinstance(components, dict):
        components[carrier_id] = float(components.get(carrier_id, 0.0)) + volume_uL
    quantities = container.setdefault("component_quantities", {})
    if isinstance(quantities, dict):
        quantities[carrier_id] = {"dimension": "volume", "unit": "uL", "value": volume_uL}
    container["volume_uL"] = float(container.get("volume_uL", 0.0)) + volume_uL
    container["mass_mg"] = float(container.get("mass_mg", 0.0)) + volume_uL
    index = state.setdefault("container_content_index", {})
    if isinstance(index, dict):
        contents = index.setdefault(container_id, {})
        if isinstance(contents, dict):
            contents[carrier_id] = {
                "volume_uL": volume_uL,
                "mass_mg": volume_uL,
                "count_cells": 0.0,
                "axis": "volume",
                "unit": "uL",
            }
    return carrier_id
