"""Shared material-state support helpers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.content_vocab import ContainerKind
from culsma.pipeline.plan_nodes import PlanStep


_VOLUME_TO_UL: dict[str, float] = {
    "uL": 1.0,
    "ul": 1.0,
    "mL": 1000.0,
    "ml": 1000.0,
    "L": 1_000_000.0,
}

_MASS_TO_MG: dict[str, float] = {
    "ug": 0.001,
    "mg": 1.0,
    "g": 1000.0,
    "kg": 1_000_000.0,
}

_DEFAULT_CONTAINER_CAPACITY_UL: dict[str, float] = {
    "container": 1000.0,
    ContainerKind.TUBE.value: 1500.0,
    ContainerKind.WELL.value: 200.0,
    ContainerKind.CHAMBER.value: 1000.0,
}

_CONSERVATION_ABS_EPS = 1e-12
_CONSERVATION_REL_EPS = 1e-9
_CONSERVATION_OPS = {"Mutation", "sep", "frac"}


@dataclass(frozen=True)
class MaterialUpdateResult:
    material_state: dict[str, Any]
    diagnostics: list[Diagnostic] = field(default_factory=list)
    delta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)


class MaterialArgReader:
    @staticmethod
    def arg_string(value: Any) -> str | None:
        return _arg_string(value)

    @staticmethod
    def arg_numeric(value: Any) -> float | None:
        return _arg_numeric(value)

    @staticmethod
    def arg_bool(value: Any) -> bool | None:
        return _arg_bool(value)

    @staticmethod
    def arg_quantity(value: Any) -> dict[str, Any] | None:
        return _arg_quantity(value)

    @staticmethod
    def arg_call(value: Any) -> dict[str, Any] | None:
        return _arg_call(value)

    @staticmethod
    def call_arg_value(call: dict[str, Any], name: str) -> Any:
        return _call_arg_value(call, name)

    @staticmethod
    def call_arg_string(call: dict[str, Any], name: str) -> str | None:
        return _call_arg_string(call, name)

    @staticmethod
    def call_arg_int(call: dict[str, Any], name: str) -> int | None:
        return _call_arg_int(call, name)


class MaterialRefResolver:
    @staticmethod
    def initialize_bindings(state: dict[str, Any]) -> None:
        _initialize_bindings(state)

    @staticmethod
    def inventory_check_enabled(state: dict[str, Any]) -> bool:
        return _inventory_check_enabled(state)

    @staticmethod
    def resolve_container_ref(state: dict[str, Any], name: str) -> str | None:
        return _resolve_container_ref(state, name)

    @staticmethod
    def resolve_target_ref(state: dict[str, Any], value: Any) -> str | None:
        return _resolve_target_ref(state, value)

    @staticmethod
    def resolve_source_ref(state: dict[str, Any], value: Any, qty: dict[str, Any] | None) -> str | None:
        return _resolve_source_ref(state, value, qty)

    @staticmethod
    def resolve_structured_ref(
        state: dict[str, Any],
        value: Any,
        *,
        create_if_identifier: bool,
    ) -> str | None:
        return _resolve_structured_ref(state, value, create_if_identifier=create_if_identifier)

    @staticmethod
    def resolve_content_ref(state: dict[str, Any], name: str) -> str | None:
        return _resolve_content_ref(state, name)

    @staticmethod
    def resolve_or_create_container_ref(state: dict[str, Any], name: str) -> str:
        return _resolve_or_create_container_ref(state, name)

    @staticmethod
    def bind_name(state: dict[str, Any], name: str, container_id: str, step_id: str | None) -> list[dict[str, Any]]:
        return _bind_name(state, name, container_id, step_id)

    @staticmethod
    def bind_indexed_group(
        state: dict[str, Any],
        group_name: str,
        slots: dict[str, str],
        step_id: str | None,
    ) -> list[dict[str, Any]]:
        return _bind_indexed_group(state, group_name, slots, step_id)


class MaterialLedger:
    @staticmethod
    def set_container_material(
        container: dict[str, Any],
        *,
        volume_uL: float,
        mass_mg: float,
        components: dict[str, float],
        component_classes: dict[str, str] | None = None,
    ) -> None:
        _set_container_material(
            container,
            volume_uL=volume_uL,
            mass_mg=mass_mg,
            components=components,
            component_classes=component_classes,
        )

    @staticmethod
    def move_ratio(src: dict[str, Any], dst: dict[str, Any], ratio: float) -> None:
        _move_ratio(src, dst, ratio)

    @staticmethod
    def move_explicit(
        src: dict[str, Any],
        dst: dict[str, Any],
        moved_volume_uL: float,
        moved_mass_mg: float,
        component_ratio: float,
    ) -> None:
        _move_explicit(src, dst, moved_volume_uL, moved_mass_mg, component_ratio)

    @staticmethod
    def container_component_classes(container: dict[str, Any], *, create: bool = False) -> dict[str, Any] | None:
        return _container_component_classes(container, create=create)

    @staticmethod
    def remove_ratio(source: dict[str, Any], ratio: float) -> None:
        _remove_ratio(source, ratio)

    @staticmethod
    def collect_unit_into_container(
        *,
        step: PlanStep,
        state: dict[str, Any],
        target_id: str,
        unit: dict[str, Any],
    ) -> MaterialUpdateResult:
        return _collect_unit_into_container(step=step, state=state, target_id=target_id, unit=unit)

    @staticmethod
    def check_capacity_guard(
        *,
        step: PlanStep,
        state: dict[str, Any],
        container_id: str,
        added_uL: float,
    ) -> MaterialUpdateResult | None:
        return _check_capacity_guard(step=step, state=state, container_id=container_id, added_uL=added_uL)

    @staticmethod
    def container(state: dict[str, Any], container_id: str) -> dict[str, Any] | None:
        return _container(state, container_id)

    @staticmethod
    def ensure_container(state: dict[str, Any], container_id: str) -> dict[str, Any]:
        return _ensure_container(state, container_id)


class MaterialConservation:
    @staticmethod
    def state_totals(state: dict[str, Any]) -> dict[str, float]:
        return _state_totals(state)

    @staticmethod
    def totals_conserved(before: dict[str, float], after: dict[str, float]) -> bool:
        return _totals_conserved(before, after)



def _set_container_material(
    container: dict[str, Any],
    *,
    volume_uL: float,
    mass_mg: float,
    components: dict[str, float],
    component_classes: dict[str, str] | None = None,
) -> None:
    container["volume_uL"] = volume_uL
    container["mass_mg"] = mass_mg
    container["components"] = dict(components)
    metadata = container.setdefault("metadata", {})
    if isinstance(metadata, dict):
        if component_classes:
            metadata["component_partition_classes"] = {
                name: component_classes[name] for name in components if name in component_classes
            }
        else:
            metadata.pop("component_partition_classes", None)



def _move_ratio(src: dict[str, Any], dst: dict[str, Any], ratio: float) -> None:
    moved_volume = ratio * float(src.get("volume_uL", 0.0))
    moved_mass = ratio * float(src.get("mass_mg", 0.0))
    _move_explicit(src=src, dst=dst, moved_volume_uL=moved_volume, moved_mass_mg=moved_mass, component_ratio=ratio)


def _move_explicit(
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
    src_classes = _container_component_classes(src)
    dst_classes = _container_component_classes(dst, create=True)
    for name, amount in list(src_comp.items()):
        moved = component_ratio * float(amount)
        src_comp[name] = float(amount) - moved
        dst_comp[name] = float(dst_comp.get(name, 0.0)) + moved
        if moved > _CONSERVATION_ABS_EPS and isinstance(dst_classes, dict):
            src_class = src_classes.get(name) if isinstance(src_classes, dict) else None
            if isinstance(src_class, str) and src_class:
                dst_classes[name] = src_class
        if abs(float(src_comp[name])) <= _CONSERVATION_ABS_EPS:
            src_comp[name] = 0.0
            if isinstance(src_classes, dict):
                src_classes.pop(name, None)


def _container_component_classes(container: dict[str, Any], *, create: bool = False) -> dict[str, Any] | None:
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


def _remove_ratio(source: dict[str, Any], ratio: float) -> None:
    source["volume_uL"] = float(source.get("volume_uL", 0.0)) * (1.0 - ratio)
    source["mass_mg"] = float(source.get("mass_mg", 0.0)) * (1.0 - ratio)
    comp = source.setdefault("components", {})
    for name, amount in list(comp.items()):
        comp[name] = float(amount) * (1.0 - ratio)


def _primary_concentration(container: dict[str, Any]) -> float | None:
    volume = float(container.get("volume_uL", 0.0))
    if volume <= 0:
        return None
    comp = container.get("components")
    if not isinstance(comp, dict) or not comp:
        return None
    first = next(iter(comp.values()))
    return float(first) / volume


def _quantity_to_uL(qty: dict[str, Any]) -> float | None:
    unit = str(qty["unit"])
    if unit not in _VOLUME_TO_UL:
        return None
    return float(qty["value"]) * _VOLUME_TO_UL[unit]


def _density_mg_per_uL(container: dict[str, Any]) -> float | None:
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


def _is_qualified_name(name: str) -> bool:
    if "::" not in name:
        return False
    head, tail = name.split("::", 1)
    return bool(head) and bool(tail)


def _is_serialized_pair(value: Any) -> bool:
    return isinstance(value, dict) and value.get("kind") == "IRPair"


def _is_unit_ref(value: Any) -> bool:
    return isinstance(value, dict) and value.get("kind") == "unit_ref"


def _initialize_bindings(state: dict[str, Any]) -> None:
    bindings = state.setdefault("bindings", {})
    if not isinstance(bindings, dict):
        state["bindings"] = {}
        bindings = state["bindings"]
    containers = state.setdefault("containers", {})
    for container_id in containers:
        if isinstance(container_id, str) and container_id not in bindings:
            bindings[container_id] = container_id
    indexed_bindings = state.setdefault("indexed_bindings", {})
    if not isinstance(indexed_bindings, dict):
        state["indexed_bindings"] = {}


def _inventory_check_enabled(state: dict[str, Any]) -> bool:
    raw = state.get("_inventory_check")
    if isinstance(raw, bool):
        return raw
    return True


def _provision_source_for_estimate(state: dict[str, Any], name: str, qty: dict[str, Any]) -> str:
    source_id = _resolve_or_create_container_ref(state, name)
    source = _ensure_container(state, source_id)
    unit = str(qty["unit"])
    value = float(qty["value"])
    if unit in _VOLUME_TO_UL:
        requested_uL = value * _VOLUME_TO_UL[unit]
        _top_up_source_for_estimate(source=source, qty=requested_uL, mode="volume", source_name=name)
    elif unit in _MASS_TO_MG:
        requested_mg = value * _MASS_TO_MG[unit]
        _top_up_source_for_estimate(source=source, qty=requested_mg, mode="mass", source_name=name)
    return source_id


def _top_up_source_for_estimate(source: dict[str, Any], qty: float, mode: str, source_name: str) -> None:
    if qty <= 0:
        return
    comps = source.setdefault("components", {})
    if mode == "volume":
        source["volume_uL"] = float(source.get("volume_uL", 0.0)) + qty
        source["mass_mg"] = float(source.get("mass_mg", 0.0)) + qty
        comps[source_name] = float(comps.get(source_name, 0.0)) + qty
    else:
        source["mass_mg"] = float(source.get("mass_mg", 0.0)) + qty
        source["volume_uL"] = float(source.get("volume_uL", 0.0)) + qty
        comps[source_name] = float(comps.get(source_name, 0.0)) + qty


def _resolve_container_ref(state: dict[str, Any], name: str) -> str | None:
    containers = state.setdefault("containers", {})
    if _is_qualified_name(name):
        return name if isinstance(containers.get(name), dict) else None
    bindings = state.setdefault("bindings", {})
    bound = bindings.get(name) if isinstance(bindings, dict) else None
    if isinstance(bound, str) and isinstance(containers.get(bound), dict):
        return bound
    if isinstance(containers.get(name), dict):
        return name
    return None


def _resolve_target_ref(state: dict[str, Any], value: Any) -> str | None:
    name = _arg_string(value)
    if name is not None:
        return _resolve_or_create_container_ref(state, name)
    return _resolve_structured_ref(state, value, create_if_identifier=True)


def _resolve_source_ref(state: dict[str, Any], value: Any, qty: dict[str, Any] | None) -> str | None:
    name = _arg_string(value)
    if name is not None:
        resolved = _resolve_container_ref(state, name)
        if resolved is not None:
            return resolved
        if _inventory_check_enabled(state):
            return None
        if qty is not None:
            return _provision_source_for_estimate(state=state, name=name, qty=qty)
        return _resolve_or_create_container_ref(state, name)
    return _resolve_structured_ref(state, value, create_if_identifier=not _inventory_check_enabled(state))


def _resolve_structured_ref(state: dict[str, Any], value: Any, *, create_if_identifier: bool) -> str | None:
    if not isinstance(value, dict):
        return None
    kind = value.get("kind")
    if kind == "IRIdentifier":
        name = value.get("name")
        if not isinstance(name, str):
            return None
        if create_if_identifier:
            return _resolve_or_create_container_ref(state, name)
        return _resolve_container_ref(state, name)
    if kind != "IRIndex":
        return None
    base = value.get("base")
    index = value.get("index")
    if not isinstance(base, dict) or base.get("kind") != "IRIdentifier":
        return None
    group_name = base.get("name")
    if not isinstance(group_name, str):
        return None
    slot = _static_index_key(index)
    if slot is None:
        return None
    indexed_bindings = state.setdefault("indexed_bindings", {})
    if not isinstance(indexed_bindings, dict):
        return None
    group = indexed_bindings.get(group_name)
    if not isinstance(group, dict):
        return None
    bound = group.get(slot)
    if isinstance(bound, str) and _container(state, bound) is not None:
        return bound
    return None


def _resolve_content_ref(state: dict[str, Any], name: str) -> str | None:
    registry = state.setdefault("content_registry", {})
    bindings = state.setdefault("content_bindings", {})
    if isinstance(bindings, dict):
        bound = bindings.get(name)
        if isinstance(bound, str):
            if isinstance(registry, dict) and isinstance(registry.get(bound), dict):
                return bound
    if isinstance(registry, dict) and isinstance(registry.get(name), dict):
        return name
    return None


def _collect_unit_into_container(
    *,
    step: PlanStep,
    state: dict[str, Any],
    target_id: str,
    unit: dict[str, Any],
) -> MaterialUpdateResult:
    container = _container(state, target_id)
    if container is None:
        return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown collection target '{target_id}'")
    metadata = container.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        container["metadata"] = {}
        metadata = container["metadata"]
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


def _check_capacity_guard(
    *,
    step: PlanStep,
    state: dict[str, Any],
    container_id: str,
    added_uL: float,
) -> MaterialUpdateResult | None:
    container = _container(state, container_id)
    if container is None:
        return _diag_result(step, state, "MAT_BINDING_NOT_FOUND", f"Unknown target container '{container_id}'")
    metadata = container.get("metadata", {})
    if not isinstance(metadata, dict):
        return _diag_result(step, state, "MAT_INVALID_CAPACITY", f"Invalid capacity metadata for '{container_id}'")
    if "capacity_uL" not in metadata:
        return None
    raw = metadata.get("capacity_uL")
    try:
        capacity_uL = float(raw)
    except (TypeError, ValueError):
        return _diag_result(step, state, "MAT_INVALID_CAPACITY", f"Invalid capacity value for '{container_id}'")
    if capacity_uL <= 0:
        return _diag_result(step, state, "MAT_INVALID_CAPACITY", f"Invalid capacity value for '{container_id}'")
    current_uL = float(container.get("volume_uL", 0.0))
    if current_uL + float(added_uL) > capacity_uL + 1e-12:
        return _diag_result(
            step,
            state,
            "MAT_CONTAINER_OVERFLOW",
            f"Container '{container_id}' capacity exceeded ({current_uL + float(added_uL)}uL > {capacity_uL}uL)",
        )
    return None


def _default_container_capacity_uL(kind: str | None) -> float | None:
    if kind is None:
        return _DEFAULT_CONTAINER_CAPACITY_UL["container"]
    if kind == ContainerKind.SURFACE.value:
        return None
    return _DEFAULT_CONTAINER_CAPACITY_UL.get(kind, _DEFAULT_CONTAINER_CAPACITY_UL["container"])


def _normalize_capacity_uL(value: Any) -> float | None:
    qty = _arg_quantity(value)
    if qty is None:
        return None
    unit = str(qty["unit"])
    if unit not in _VOLUME_TO_UL:
        return None
    capacity_uL = float(qty["value"]) * _VOLUME_TO_UL[unit]
    if capacity_uL <= 0:
        return None
    return capacity_uL


def _resolve_or_create_container_ref(state: dict[str, Any], name: str) -> str:
    resolved = _resolve_container_ref(state, name)
    if resolved is not None:
        return resolved
    if _is_qualified_name(name):
        _ensure_container(state, name)
        return name
    _ensure_container(state, name)
    _bind_name(state, name, name, step_id=None)
    return name


def _static_index_key(value: Any) -> str | None:
    if not isinstance(value, dict) or value.get("kind") != "IRQuantity":
        return None
    unit = value.get("unit")
    raw = value.get("value")
    if unit is not None or not isinstance(raw, (int, float)):
        return None
    if float(raw) < 0 or not float(raw).is_integer():
        return None
    return str(int(raw))


def _bind_name(state: dict[str, Any], name: str, container_id: str, step_id: str | None) -> list[dict[str, Any]]:
    bindings = state.setdefault("bindings", {})
    if not isinstance(bindings, dict):
        state["bindings"] = {}
        bindings = state["bindings"]
    previous = bindings.get(name)
    bindings[name] = container_id
    if isinstance(previous, str) and previous != container_id:
        return [
            {
                "event": "BINDING_OVERWRITTEN",
                "name": name,
                "old_container_id": previous,
                "new_container_id": container_id,
                "step_id": step_id,
            }
        ]
    return []


def _bind_indexed_group(
    state: dict[str, Any],
    group_name: str,
    slots: dict[str, str],
    step_id: str | None,
) -> list[dict[str, Any]]:
    indexed_bindings = state.setdefault("indexed_bindings", {})
    if not isinstance(indexed_bindings, dict):
        state["indexed_bindings"] = {}
        indexed_bindings = state["indexed_bindings"]
    previous = indexed_bindings.get(group_name)
    indexed_bindings[group_name] = dict(slots)

    if not isinstance(previous, dict):
        return []

    events: list[dict[str, Any]] = []
    for slot, new_container_id in slots.items():
        old_container_id = previous.get(slot)
        if isinstance(old_container_id, str) and old_container_id != new_container_id:
            events.append(
                {
                    "event": "BINDING_OVERWRITTEN",
                    "name": f"{group_name}[{slot}]",
                    "old_container_id": old_container_id,
                    "new_container_id": new_container_id,
                    "step_id": step_id,
                }
            )
    return events


def _state_totals(state: dict[str, Any]) -> dict[str, float]:
    total_volume = 0.0
    total_mass = 0.0
    total_components = 0.0
    containers = state.setdefault("containers", {})
    for obj in containers.values():
        if not isinstance(obj, dict):
            continue
        volume_uL = float(obj.get("volume_uL", 0.0))
        mass_mg = float(obj.get("mass_mg", 0.0))
        density = _density_mg_per_uL(obj)
        if density is not None and density > 0:
            total_volume += max(volume_uL, mass_mg / density)
            total_mass += max(mass_mg, volume_uL * density)
        else:
            total_volume += volume_uL
            total_mass += mass_mg
        comp = obj.get("components", {})
        if isinstance(comp, dict):
            total_components += sum(float(v) for v in comp.values())
    return {"volume_uL": total_volume, "mass_mg": total_mass, "components": total_components}


def _close_enough(before: float, after: float) -> bool:
    delta = abs(before - after)
    if delta <= _CONSERVATION_ABS_EPS:
        return True
    scale = max(abs(before), abs(after), _CONSERVATION_ABS_EPS)
    return (delta / scale) <= _CONSERVATION_REL_EPS


def _totals_conserved(before: dict[str, float], after: dict[str, float]) -> bool:
    return all(
        _close_enough(float(before.get(key, 0.0)), float(after.get(key, 0.0)))
        for key in ("volume_uL", "mass_mg", "components")
    )


def _container(state: dict[str, Any], container_id: str) -> dict[str, Any] | None:
    containers = state.setdefault("containers", {})
    obj = containers.get(container_id)
    return obj if isinstance(obj, dict) else None


def _ensure_container(state: dict[str, Any], container_id: str) -> dict[str, Any]:
    containers = state.setdefault("containers", {})
    obj = containers.setdefault(
        container_id,
        {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}},
    )
    if not isinstance(obj, dict):
        containers[container_id] = {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}}
    return containers[container_id]


def _arg_string(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value.get("kind") == "IRString":
            inner = value.get("value")
            return inner if isinstance(inner, str) else None
        if value.get("kind") == "IRIdentifier":
            inner = value.get("name")
            return inner if isinstance(inner, str) else None
    return None


def _arg_numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        if value.get("kind") == "IRQuantity":
            inner = value.get("value")
            if isinstance(inner, (int, float)):
                return float(inner)
    return None


def _arg_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict) and value.get("kind") == "IRBoolean":
        inner = value.get("value")
        return inner if isinstance(inner, bool) else None
    return None


def _arg_quantity(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and value.get("kind") == "IRQuantity":
        v = value.get("value")
        u = value.get("unit")
        if isinstance(v, (int, float)) and isinstance(u, str):
            return {"value": float(v), "unit": u}
    return None


def _arg_call(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and value.get("kind") == "IRCall":
        return value
    return None


def _call_arg_value(call: dict[str, Any], name: str) -> Any:
    args = call.get("args")
    if not isinstance(args, list):
        return None
    for arg in args:
        if isinstance(arg, dict) and arg.get("kind") == "IRArg" and arg.get("name") == name:
            return arg.get("value")
    return None


def _call_arg_string(call: dict[str, Any], name: str) -> str | None:
    return _arg_string(_call_arg_value(call, name))


def _call_arg_int(call: dict[str, Any], name: str) -> int | None:
    value = _call_arg_value(call, name)
    if isinstance(value, dict) and value.get("kind") == "IRQuantity":
        raw = value.get("value")
        unit = value.get("unit")
        if unit is None and isinstance(raw, (int, float)) and float(raw).is_integer():
            return int(raw)
    return None


def _diag_result(step: PlanStep, state: dict[str, Any], code: str, message: str) -> MaterialUpdateResult:
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[Diagnostic(code=code, message=message, span=step.span, node_id=step.step_id)],
        delta={},
    )


def _ref_display(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return "<invalid-ref>"
    kind = value.get("kind")
    if kind == "IRIdentifier":
        name = value.get("name")
        return name if isinstance(name, str) else "<identifier>"
    if kind == "IRIndex":
        base = _ref_display(value.get("base"))
        slot = _static_index_key(value.get("index"))
        return f"{base}[{slot if slot is not None else '?'}]"
    if kind == "IRSourcePartitionRef":
        source = _ref_display(value.get("source"))
        program = value.get("program")
        program_name = program.get("name") if isinstance(program, dict) else None
        index = _static_index_key(value.get("index"))
        return f"{source}.partition({program_name or '?'})[{index if index is not None else '?'}]"
    if kind == "IRString":
        inner = value.get("value")
        return inner if isinstance(inner, str) else "<string>"
    return f"<{kind or 'unknown-ref'}>"
