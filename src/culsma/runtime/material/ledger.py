"""Material ledger mutation and lookup services."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import Any

from culsma.pipeline.content_vocab import ContainerKind
from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.args import arg_quantity
from culsma.runtime.material.component_entries import (
    ComponentEntryRelationError,
    container_component_entries,
    relocate_component_entries,
    normalize_component_entries,
    project_component_entries,
    quantities_compatible,
    replace_component_entries,
    retain_component_entry_ratio,
)
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.result import MaterialUpdateResult
from culsma.runtime.material.units import COUNT_TO_CELLS, MASS_TO_MG, VOLUME_TO_UL


CONSERVATION_ABS_EPS = 1e-12


@dataclass(frozen=True)
class MaterialLedgerValidationFailure:
    code: str
    message: str

DEFAULT_CONTAINER_CAPACITY_UL: dict[str, float] = {
    "container": 1000.0,
    ContainerKind.TUBE.value: 1500.0,
    ContainerKind.WELL.value: 200.0,
    ContainerKind.CHAMBER.value: 1000.0,
}


class MaterialLedger:
    @staticmethod
    def set_container_material(
        container: dict[str, Any],
        *,
        components: dict[str, float],
        component_classes: dict[str, str] | None = None,
        component_quantities: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        set_container_material(
            container,
            components=components,
            component_classes=component_classes,
            component_quantities=component_quantities,
        )

    @staticmethod
    def move_ratio(
        src: dict[str, Any],
        dst: dict[str, Any],
        ratio: float,
        destination_id: str | None = None,
    ) -> None:
        move_ratio(src, dst, ratio, destination_id=destination_id)

    @staticmethod
    def move_explicit(
        src: dict[str, Any],
        dst: dict[str, Any],
        component_ratio: float,
        destination_id: str | None = None,
    ) -> None:
        move_explicit(
            src,
            dst,
            component_ratio,
            destination_id=destination_id,
        )

    @staticmethod
    def component_quantity_merge_conflict(src: dict[str, Any], dst: dict[str, Any]) -> str | None:
        return component_quantity_merge_conflict(src, dst)

    @staticmethod
    def container_component_classes(container: dict[str, Any], *, create: bool = False) -> dict[str, Any] | None:
        return container_component_classes(container, create=create)

    @staticmethod
    def remove_ratio(source: dict[str, Any], ratio: float) -> None:
        remove_ratio(source, ratio)

    @staticmethod
    def collect_unit_into_container(
        *,
        step: PlanStep,
        state: dict[str, Any],
        target_id: str,
        unit: dict[str, Any],
    ) -> MaterialUpdateResult:
        return collect_unit_into_container(step=step, state=state, target_id=target_id, unit=unit)

    @staticmethod
    def check_capacity_guard(
        *,
        step: PlanStep,
        state: dict[str, Any],
        container_id: str,
        added_uL: float,
    ) -> MaterialUpdateResult | None:
        return check_capacity_guard(step=step, state=state, container_id=container_id, added_uL=added_uL)

    @staticmethod
    def container(state: dict[str, Any], container_id: str) -> dict[str, Any] | None:
        return container(state, container_id)

    @staticmethod
    def ensure_container(state: dict[str, Any], container_id: str) -> dict[str, Any]:
        return ensure_container(state, container_id)


def set_container_material(
    container: dict[str, Any],
    *,
    components: dict[str, float],
    component_classes: dict[str, str] | None = None,
    component_quantities: dict[str, dict[str, Any]] | None = None,
) -> None:
    container["components"] = dict(components)
    if component_quantities is not None:
        container["component_quantities"] = deepcopy(component_quantities)
    metadata = container.setdefault("metadata", {})
    if isinstance(metadata, dict):
        if component_classes:
            metadata["component_partition_classes"] = {
                name: component_classes[name] for name in components if name in component_classes
            }
        else:
            metadata.pop("component_partition_classes", None)
    relationships = container.get("material_relationships")
    if isinstance(relationships, list):
        container["material_relationships"] = [
            relationship
            for relationship in relationships
            if not (
                isinstance(relationship, dict)
                and relationship.get("subtype")
                in {"scientific_model_relation", "cell_suspension"}
            )
        ]
    container.pop("component_entries", None)
    replace_component_entries(container, container_component_entries(container))
    refresh_container_aggregates(container)


def move_ratio(
    src: dict[str, Any],
    dst: dict[str, Any],
    ratio: float,
    *,
    destination_id: str | None = None,
) -> None:
    move_explicit(
        src=src,
        dst=dst,
        component_ratio=ratio,
        destination_id=destination_id,
    )


def move_explicit(
    src: dict[str, Any],
    dst: dict[str, Any],
    component_ratio: float,
    *,
    destination_id: str | None = None,
) -> None:
    """Compatibility wrapper for an already-resolved entry relocation."""

    relocate_material(
        src=src,
        dst=dst,
        component_ratio=component_ratio,
        destination_id=destination_id,
    )


def relocate_material(
    src: dict[str, Any],
    dst: dict[str, Any],
    component_ratio: float,
    *,
    destination_id: str | None = None,
) -> None:
    """Relocate pre-resolved entries for snapshots or container aliasing."""

    relocate_component_entries(
        src,
        dst,
        ratio=component_ratio,
        destination_id=destination_id,
    )
    refresh_container_aggregates(src)
    refresh_container_aggregates(dst)


def component_quantity_merge_conflict(src: dict[str, Any], dst: dict[str, Any]) -> str | None:
    """Return the first component whose source and destination axes cannot merge."""

    source_entries = container_component_entries(src)
    target_entries = container_component_entries(dst)
    for source_entry in source_entries:
        content_ref = str(source_entry.get("content_ref", ""))
        for target_entry in target_entries:
            if target_entry.get("content_ref") != content_ref:
                continue
            if not quantities_compatible(
                source_entry.get("quantity"),
                target_entry.get("quantity"),
            ):
                return content_ref

    return None


def container_component_classes(container: dict[str, Any], *, create: bool = False) -> dict[str, Any] | None:
    metadata = container.setdefault("metadata", {}) if create else container.get("metadata")
    if not isinstance(metadata, dict):
        if not create:
            return None
        container["metadata"] = {}
        metadata = container["metadata"]
    classes = metadata.setdefault("component_partition_classes", {}) if create else metadata.get("component_partition_classes")
    if not isinstance(classes, dict):
        if not create:
            return None
        metadata["component_partition_classes"] = {}
        classes = metadata["component_partition_classes"]
    return classes


def container_component_quantities(container: dict[str, Any], *, create: bool = False) -> dict[str, Any] | None:
    quantities = container.setdefault("component_quantities", {}) if create else container.get("component_quantities")
    if not isinstance(quantities, dict):
        if not create:
            return None
        container["component_quantities"] = {}
        quantities = container["component_quantities"]
    return quantities


def container_count_cells(container: Any) -> float:
    return container_component_quantity_total(container, "count")


def container_component_quantity_total(container: Any, dimension: str) -> float:
    """Project one canonical quantity-axis total from authoritative component detail."""

    if not isinstance(container, dict):
        return 0.0
    quantities = container_component_quantities(container)
    if not isinstance(quantities, dict):
        return 0.0
    total = 0.0
    for quantity in quantities.values():
        if not isinstance(quantity, dict) or quantity.get("dimension") != dimension:
            continue
        value = float(quantity.get("value", 0.0))
        unit = str(quantity.get("unit", ""))
        if dimension == "volume" and unit in VOLUME_TO_UL:
            total += value * VOLUME_TO_UL[unit]
        elif dimension == "mass" and unit in MASS_TO_MG:
            total += value * MASS_TO_MG[unit]
        elif dimension == "count" and unit in COUNT_TO_CELLS:
            total += value * COUNT_TO_CELLS[unit]
    return total


def container_detail_aggregates(container: Any) -> tuple[float, float]:
    """Project compatibility volume and mass exclusively from quantity detail."""

    if not isinstance(container, dict):
        return 0.0, 0.0
    quantities = container_component_quantities(container)
    if not isinstance(quantities, dict):
        return 0.0, 0.0
    container_density = density_mg_per_uL(container)
    volume_uL = 0.0
    mass_mg = 0.0
    for quantity in quantities.values():
        if not isinstance(quantity, dict):
            continue
        dimension = quantity.get("dimension")
        value = float(quantity.get("value", 0.0))
        unit = str(quantity.get("unit", ""))
        raw_density = quantity.get("density_mg_per_uL")
        try:
            quantity_density = float(raw_density) if raw_density is not None else None
        except (TypeError, ValueError):
            quantity_density = None
        cross_axis_projection = quantity.get("cross_axis_projection", True) is not False
        density = quantity_density or container_density or (1.0 if cross_axis_projection else None)
        if density is not None and density <= 0.0:
            density = None
        if dimension == "volume" and unit in VOLUME_TO_UL:
            native_volume = value * VOLUME_TO_UL[unit]
            volume_uL += native_volume
            if density is not None:
                mass_mg += native_volume * density
        elif dimension == "mass" and unit in MASS_TO_MG:
            native_mass = value * MASS_TO_MG[unit]
            mass_mg += native_mass
            if density is not None:
                volume_uL += native_mass / density
    return volume_uL, mass_mg


def refresh_container_aggregates(container: Any) -> None:
    """Refresh aggregate compatibility fields from the authoritative detail ledger."""

    if not isinstance(container, dict):
        return
    volume_uL, mass_mg = container_detail_aggregates(container)
    container["volume_uL"] = volume_uL
    container["mass_mg"] = mass_mg


def normalize_material_state_detail_ledger(
    state: dict[str, Any],
) -> MaterialLedgerValidationFailure | None:
    """Normalize compatibility-only API input into component quantity detail."""

    containers = state.get("containers")
    if not isinstance(containers, dict):
        return None
    for container_id, raw_container in containers.items():
        if not isinstance(raw_container, dict):
            continue
        error = _component_quantity_validation_error(str(container_id), raw_container)
        if error is not None:
            return MaterialLedgerValidationFailure(
                code="MAT_INVALID_COMPONENT_QUANTITY",
                message=error,
            )
    for container_id, raw_container in containers.items():
        if isinstance(raw_container, dict):
            try:
                if isinstance(raw_container.get("component_entries"), list):
                    replace_component_entries(
                        raw_container,
                        normalize_component_entries(
                            raw_container,
                            state=state,
                            container_id=str(container_id),
                        ),
                    )
                    refresh_container_aggregates(raw_container)
                else:
                    _normalize_container_detail_ledger(str(container_id), raw_container)
                    replace_component_entries(
                        raw_container,
                        normalize_component_entries(
                            raw_container,
                            state=state,
                            container_id=str(container_id),
                        ),
                    )
            except ComponentEntryRelationError as exc:
                return MaterialLedgerValidationFailure(
                    code="MAT_STATE_INVARIANT_VIOLATION",
                    message=f"Container '{container_id}' {exc}",
                )
    return None


def _component_quantity_validation_error(container_id: str, container: dict[str, Any]) -> str | None:
    quantities = container.get("component_quantities")
    if quantities is None:
        return None
    if not isinstance(quantities, dict):
        return f"Container '{container_id}' component_quantities must be a mapping"
    unit_maps = {"volume": VOLUME_TO_UL, "mass": MASS_TO_MG, "count": COUNT_TO_CELLS}
    for component_id, quantity in quantities.items():
        if not isinstance(quantity, dict):
            return f"Container '{container_id}' quantity for '{component_id}' must be a mapping"
        dimension = quantity.get("dimension")
        unit_map = unit_maps.get(str(dimension))
        if unit_map is None:
            return f"Container '{container_id}' quantity for '{component_id}' has invalid dimension '{dimension}'"
        unit = str(quantity.get("unit", ""))
        if unit not in unit_map:
            return f"Container '{container_id}' quantity for '{component_id}' has invalid unit '{unit}'"
        value = quantity.get("value")
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(float(value))
            or float(value) < 0.0
        ):
            return f"Container '{container_id}' quantity for '{component_id}' must have a non-negative numeric value"
        raw_density = quantity.get("density_mg_per_uL")
        if raw_density is not None and (
            not isinstance(raw_density, (int, float))
            or isinstance(raw_density, bool)
            or not isfinite(float(raw_density))
            or float(raw_density) <= 0.0
        ):
            return f"Container '{container_id}' quantity for '{component_id}' has invalid density"
    return None


def refresh_material_state_aggregates(state: dict[str, Any]) -> None:
    """Reproject every runtime container aggregate from authoritative detail."""

    containers = state.get("containers")
    if not isinstance(containers, dict):
        return
    for raw_container in containers.values():
        refresh_container_aggregates(raw_container)


def _normalize_container_detail_ledger(container_id: str, container: dict[str, Any]) -> None:
    supplied_volume = max(0.0, float(container.get("volume_uL", 0.0)))
    supplied_mass = max(0.0, float(container.get("mass_mg", 0.0)))
    components = container.setdefault("components", {})
    if not isinstance(components, dict):
        container["components"] = {}
        components = container["components"]
    quantities = container_component_quantities(container, create=True)
    assert isinstance(quantities, dict)
    for component_id, quantity in quantities.items():
        if component_id not in components and isinstance(quantity, dict):
            components[str(component_id)] = float(quantity.get("value", 0.0))

    _apply_declared_density(quantities, density_mg_per_uL(container))

    projected_volume, projected_mass = container_detail_aggregates(container)
    missing_component_ids = [
        str(component_id)
        for component_id in components
        if not isinstance(quantities.get(str(component_id)), dict)
    ]
    compatibility_only_input = not quantities and (
        supplied_volume > CONSERVATION_ABS_EPS or supplied_mass > CONSERVATION_ABS_EPS
    )
    if missing_component_ids or compatibility_only_input:
        residual_volume = max(0.0, supplied_volume - projected_volume)
        residual_mass = max(0.0, supplied_mass - projected_mass)
    else:
        residual_volume = 0.0
        residual_mass = 0.0
    if residual_volume > CONSERVATION_ABS_EPS or residual_mass > CONSERVATION_ABS_EPS:
        recipients = missing_component_ids or [_compatibility_residual_id(container_id, components, quantities)]
        weights = _component_weights(components, recipients)
        dimension = "volume" if residual_volume > CONSERVATION_ABS_EPS else "mass"
        total = residual_volume if dimension == "volume" else residual_mass
        unit = "uL" if dimension == "volume" else "mg"
        declared_density = density_mg_per_uL(container)
        residual_density = declared_density if declared_density is not None and declared_density > 0.0 else None
        if (
            residual_density is None
            and residual_volume > CONSERVATION_ABS_EPS
            and residual_mass > CONSERVATION_ABS_EPS
        ):
            residual_density = residual_mass / residual_volume
        for component_id, weight in zip(recipients, weights, strict=True):
            if component_id not in components:
                components[component_id] = total * weight
            normalized_quantity = {
                "dimension": dimension,
                "unit": unit,
                "value": total * weight,
                "source": "compatibility_input_normalization",
            }
            if residual_density is not None:
                normalized_quantity["density_mg_per_uL"] = residual_density
            else:
                normalized_quantity["cross_axis_projection"] = False
            quantities[component_id] = normalized_quantity
    refresh_container_aggregates(container)


def _component_weights(components: dict[str, Any], component_ids: list[str]) -> list[float]:
    raw_weights = [max(0.0, float(components.get(component_id, 0.0))) for component_id in component_ids]
    total = sum(raw_weights)
    if total <= CONSERVATION_ABS_EPS:
        return [1.0 / len(component_ids)] * len(component_ids)
    return [weight / total for weight in raw_weights]


def _apply_declared_density(quantities: dict[str, Any], container_density: float | None) -> None:
    if container_density is not None and container_density > 0.0:
        for quantity in quantities.values():
            if isinstance(quantity, dict) and quantity.get("dimension") in {"volume", "mass"}:
                quantity.setdefault("density_mg_per_uL", container_density)


def _compatibility_residual_id(
    container_id: str,
    components: dict[str, Any],
    quantities: dict[str, Any],
) -> str:
    base = f"__compatibility_residual__::{container_id}"
    candidate = base
    ordinal = 1
    while candidate in components or candidate in quantities:
        candidate = f"{base}::{ordinal}"
        ordinal += 1
    return candidate


def remove_ratio(source: dict[str, Any], ratio: float) -> None:
    retain_component_entry_ratio(source, 1.0 - ratio)
    refresh_container_aggregates(source)


def primary_concentration(container: dict[str, Any]) -> float | None:
    volume = float(container.get("volume_uL", 0.0))
    if volume <= 0:
        return None
    comp = container.get("components")
    if not isinstance(comp, dict) or not comp:
        return None
    first = next(iter(comp.values()))
    return float(first) / volume


def quantity_to_uL(qty: dict[str, Any]) -> float | None:
    unit = str(qty["unit"])
    if unit not in VOLUME_TO_UL:
        return None
    return float(qty["value"]) * VOLUME_TO_UL[unit]


def density_mg_per_uL(container: dict[str, Any]) -> float | None:
    metadata = container.get("metadata")
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("density_g_per_mL")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def collect_unit_into_container(
    *,
    step: PlanStep,
    state: dict[str, Any],
    target_id: str,
    unit: dict[str, Any],
) -> MaterialUpdateResult:
    target = container(state, target_id)
    if target is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown collection target '{target_id}'")
    metadata = target.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        target["metadata"] = {}
        metadata = target["metadata"]
    collected_units = metadata.setdefault("collected_units", [])
    if not isinstance(collected_units, list):
        metadata["collected_units"] = []
        collected_units = metadata["collected_units"]
    collected_units.append(deepcopy(unit))
    metadata["unit_count"] = len(collected_units)
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={
            "op": "unit_collect",
            "target": target_id,
            "unit_id": unit.get("id"),
            "unit_count": metadata["unit_count"],
        },
    )


def check_capacity_guard(
    *,
    step: PlanStep,
    state: dict[str, Any],
    container_id: str,
    added_uL: float,
) -> MaterialUpdateResult | None:
    target = container(state, container_id)
    if target is None:
        return diagnostic_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown target container '{container_id}'")
    metadata = target.get("metadata", {})
    if not isinstance(metadata, dict):
        return diagnostic_result(step, state, "MAT_INVALID_CAPACITY", f"Invalid capacity metadata for '{container_id}'")
    if "capacity_uL" not in metadata:
        return None
    raw = metadata.get("capacity_uL")
    try:
        capacity_uL = float(raw)
    except (TypeError, ValueError):
        return diagnostic_result(step, state, "MAT_INVALID_CAPACITY", f"Invalid capacity value for '{container_id}'")
    if capacity_uL <= 0:
        return diagnostic_result(step, state, "MAT_INVALID_CAPACITY", f"Invalid capacity value for '{container_id}'")
    current_uL = container_physical_volume_uL(target)
    if current_uL + float(added_uL) > capacity_uL + 1e-12:
        return diagnostic_result(
            step,
            state,
            "MAT_CONTAINER_OVERFLOW",
            f"Container '{container_id}' capacity exceeded ({current_uL + float(added_uL)}uL > {capacity_uL}uL)",
        )
    return None


def container_physical_volume_uL(container_value: dict[str, Any]) -> float:
    """Return physical volume from the same authoritative detail projection."""

    volume_uL, _ = container_detail_aggregates(container_value)
    return volume_uL


def default_container_capacity_uL(kind: str | None) -> float | None:
    if kind is None:
        return DEFAULT_CONTAINER_CAPACITY_UL["container"]
    if kind == ContainerKind.SURFACE.value:
        return None
    return DEFAULT_CONTAINER_CAPACITY_UL.get(kind, DEFAULT_CONTAINER_CAPACITY_UL["container"])


def normalize_capacity_uL(value: Any) -> float | None:
    qty = arg_quantity(value)
    if qty is None:
        return None
    unit = str(qty["unit"])
    if unit not in VOLUME_TO_UL:
        return None
    capacity_uL = float(qty["value"]) * VOLUME_TO_UL[unit]
    if capacity_uL <= 0:
        return None
    return capacity_uL


def container(state: dict[str, Any], container_id: str) -> dict[str, Any] | None:
    containers = state.setdefault("containers", {})
    obj = containers.get(container_id)
    return obj if isinstance(obj, dict) else None


def ensure_container(state: dict[str, Any], container_id: str) -> dict[str, Any]:
    containers = state.setdefault("containers", {})
    obj = containers.setdefault(
        container_id,
        {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
    )
    if not isinstance(obj, dict):
        containers[container_id] = {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}}
    return containers[container_id]
