"""Material ledger mutation and lookup services."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from culsma.pipeline.content_vocab import ContainerKind
from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.args import arg_quantity
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.result import MaterialUpdateResult
from culsma.runtime.material.units import VOLUME_TO_UL


CONSERVATION_ABS_EPS = 1e-12

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
        volume_uL: float,
        mass_mg: float,
        components: dict[str, float],
        component_classes: dict[str, str] | None = None,
        component_quantities: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        set_container_material(
            container,
            volume_uL=volume_uL,
            mass_mg=mass_mg,
            components=components,
            component_classes=component_classes,
            component_quantities=component_quantities,
        )

    @staticmethod
    def move_ratio(src: dict[str, Any], dst: dict[str, Any], ratio: float) -> None:
        move_ratio(src, dst, ratio)

    @staticmethod
    def move_explicit(
        src: dict[str, Any],
        dst: dict[str, Any],
        moved_volume_uL: float,
        moved_mass_mg: float,
        component_ratio: float,
    ) -> None:
        move_explicit(src, dst, moved_volume_uL, moved_mass_mg, component_ratio)

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
    volume_uL: float,
    mass_mg: float,
    components: dict[str, float],
    component_classes: dict[str, str] | None = None,
    component_quantities: dict[str, dict[str, Any]] | None = None,
) -> None:
    container["volume_uL"] = volume_uL
    container["mass_mg"] = mass_mg
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


def move_ratio(src: dict[str, Any], dst: dict[str, Any], ratio: float) -> None:
    moved_volume = ratio * float(src.get("volume_uL", 0.0))
    moved_mass = ratio * float(src.get("mass_mg", 0.0))
    move_explicit(src=src, dst=dst, moved_volume_uL=moved_volume, moved_mass_mg=moved_mass, component_ratio=ratio)


def move_explicit(
    src: dict[str, Any],
    dst: dict[str, Any],
    moved_volume_uL: float,
    moved_mass_mg: float,
    component_ratio: float,
) -> None:
    src["volume_uL"] = float(src.get("volume_uL", 0.0)) - moved_volume_uL
    dst["volume_uL"] = float(dst.get("volume_uL", 0.0)) + moved_volume_uL
    src["mass_mg"] = float(src.get("mass_mg", 0.0)) - moved_mass_mg
    dst["mass_mg"] = float(dst.get("mass_mg", 0.0)) + moved_mass_mg

    src_comp = src.setdefault("components", {})
    dst_comp = dst.setdefault("components", {})
    src_quantities = container_component_quantities(src)
    dst_quantities = container_component_quantities(dst, create=bool(src_quantities))
    src_classes = container_component_classes(src)
    dst_classes = container_component_classes(dst, create=True)
    for name, amount in list(src_comp.items()):
        moved = component_ratio * float(amount)
        src_comp[name] = float(amount) - moved
        dst_comp[name] = float(dst_comp.get(name, 0.0)) + moved
        if isinstance(src_quantities, dict) and isinstance(src_quantities.get(name), dict):
            source_quantity = src_quantities[name]
            moved_quantity_value = component_ratio * float(source_quantity.get("value", amount))
            source_quantity["value"] = float(source_quantity.get("value", amount)) - moved_quantity_value
            if isinstance(dst_quantities, dict):
                target_quantity = dst_quantities.get(name)
                if not isinstance(target_quantity, dict):
                    target_quantity = {
                        "dimension": source_quantity.get("dimension"),
                        "unit": source_quantity.get("unit"),
                        "value": 0.0,
                    }
                    dst_quantities[name] = target_quantity
                if (
                    target_quantity.get("dimension") == source_quantity.get("dimension")
                    and target_quantity.get("unit") == source_quantity.get("unit")
                ):
                    target_quantity["value"] = float(target_quantity.get("value", 0.0)) + moved_quantity_value
        if moved > CONSERVATION_ABS_EPS and isinstance(dst_classes, dict):
            src_class = src_classes.get(name) if isinstance(src_classes, dict) else None
            if isinstance(src_class, str) and src_class:
                dst_classes[name] = src_class
        if abs(float(src_comp[name])) <= CONSERVATION_ABS_EPS:
            src_comp[name] = 0.0
            if isinstance(src_quantities, dict) and isinstance(src_quantities.get(name), dict):
                src_quantities[name]["value"] = 0.0
            if isinstance(src_classes, dict):
                src_classes.pop(name, None)


def component_quantity_merge_conflict(src: dict[str, Any], dst: dict[str, Any]) -> str | None:
    """Return the first component whose source and destination axes cannot merge."""

    src_quantities = container_component_quantities(src)
    dst_quantities = container_component_quantities(dst)
    if not isinstance(src_quantities, dict) or not isinstance(dst_quantities, dict):
        return None
    for name, source_quantity in src_quantities.items():
        target_quantity = dst_quantities.get(name)
        if not isinstance(source_quantity, dict) or not isinstance(target_quantity, dict):
            continue
        if (
            source_quantity.get("dimension") != target_quantity.get("dimension")
            or source_quantity.get("unit") != target_quantity.get("unit")
        ):
            return str(name)
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
    if not isinstance(container, dict):
        return 0.0
    quantities = container_component_quantities(container)
    if not isinstance(quantities, dict):
        return 0.0
    total = 0.0
    for quantity in quantities.values():
        if not isinstance(quantity, dict) or quantity.get("dimension") != "count":
            continue
        if quantity.get("unit") == "cells":
            total += float(quantity.get("value", 0.0))
    return total


def remove_ratio(source: dict[str, Any], ratio: float) -> None:
    source["volume_uL"] = float(source.get("volume_uL", 0.0)) * (1.0 - ratio)
    source["mass_mg"] = float(source.get("mass_mg", 0.0)) * (1.0 - ratio)
    comp = source.setdefault("components", {})
    for name, amount in list(comp.items()):
        comp[name] = float(amount) * (1.0 - ratio)
    quantities = container_component_quantities(source)
    if isinstance(quantities, dict):
        for quantity in quantities.values():
            if isinstance(quantity, dict):
                quantity["value"] = float(quantity.get("value", 0.0)) * (1.0 - ratio)


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
    """Return physical volume without cross-axis bulk compatibility proxies."""

    quantities = container_value.get("component_quantities")
    if isinstance(quantities, dict):
        volume_uL = 0.0
        for quantity in quantities.values():
            if not isinstance(quantity, dict) or quantity.get("dimension") != "volume":
                continue
            unit = quantity.get("unit")
            raw_value = quantity.get("value")
            if unit not in VOLUME_TO_UL or not isinstance(raw_value, (int, float)):
                continue
            volume_uL += float(raw_value) * VOLUME_TO_UL[str(unit)]
        if quantities:
            return volume_uL
    return float(container_value.get("volume_uL", 0.0))


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
