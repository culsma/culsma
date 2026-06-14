"""Material reference resolution and binding services."""

from __future__ import annotations

from typing import Any

from culsma.runtime.material.args import arg_string
from culsma.runtime.material.ledger import ensure_container
from culsma.runtime.material.units import MASS_TO_MG, VOLUME_TO_UL


class MaterialRefResolver:
    @staticmethod
    def initialize_bindings(state: dict[str, Any]) -> None:
        initialize_bindings(state)

    @staticmethod
    def inventory_check_enabled(state: dict[str, Any]) -> bool:
        return inventory_check_enabled(state)

    @staticmethod
    def resolve_container_ref(state: dict[str, Any], name: str) -> str | None:
        return resolve_container_ref(state, name)

    @staticmethod
    def resolve_target_ref(state: dict[str, Any], value: Any) -> str | None:
        return resolve_target_ref(state, value)

    @staticmethod
    def resolve_source_ref(state: dict[str, Any], value: Any, qty: dict[str, Any] | None) -> str | None:
        return resolve_source_ref(state, value, qty)

    @staticmethod
    def resolve_structured_ref(
        state: dict[str, Any],
        value: Any,
        *,
        create_if_identifier: bool,
    ) -> str | None:
        return resolve_structured_ref(state, value, create_if_identifier=create_if_identifier)

    @staticmethod
    def resolve_content_ref(state: dict[str, Any], name: str) -> str | None:
        return resolve_content_ref(state, name)

    @staticmethod
    def resolve_or_create_container_ref(state: dict[str, Any], name: str) -> str:
        return resolve_or_create_container_ref(state, name)

    @staticmethod
    def bind_name(state: dict[str, Any], name: str, container_id: str, step_id: str | None) -> list[dict[str, Any]]:
        return bind_name(state, name, container_id, step_id)

    @staticmethod
    def bind_indexed_group(
        state: dict[str, Any],
        group_name: str,
        slots: dict[str, str],
        step_id: str | None,
    ) -> list[dict[str, Any]]:
        return bind_indexed_group(state, group_name, slots, step_id)


def initialize_bindings(state: dict[str, Any]) -> None:
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


def inventory_check_enabled(state: dict[str, Any]) -> bool:
    raw = state.get("_inventory_check")
    if isinstance(raw, bool):
        return raw
    return True


def resolve_container_ref(state: dict[str, Any], name: str) -> str | None:
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


def resolve_target_ref(state: dict[str, Any], value: Any) -> str | None:
    name = arg_string(value)
    if name is not None:
        return resolve_or_create_container_ref(state, name)
    return resolve_structured_ref(state, value, create_if_identifier=True)


def resolve_source_ref(state: dict[str, Any], value: Any, qty: dict[str, Any] | None) -> str | None:
    name = arg_string(value)
    if name is not None:
        resolved = resolve_container_ref(state, name)
        if resolved is not None:
            return resolved
        if inventory_check_enabled(state):
            return None
        if qty is not None:
            return provision_source_for_estimate(state=state, name=name, qty=qty)
        return resolve_or_create_container_ref(state, name)
    return resolve_structured_ref(state, value, create_if_identifier=not inventory_check_enabled(state))


def resolve_structured_ref(state: dict[str, Any], value: Any, *, create_if_identifier: bool) -> str | None:
    if not isinstance(value, dict):
        return None
    kind = value.get("kind")
    if kind == "IRIdentifier":
        name = value.get("name")
        if not isinstance(name, str):
            return None
        if create_if_identifier:
            return resolve_or_create_container_ref(state, name)
        return resolve_container_ref(state, name)
    if kind != "IRIndex":
        return None
    base = value.get("base")
    index = value.get("index")
    if not isinstance(base, dict) or base.get("kind") != "IRIdentifier":
        return None
    group_name = base.get("name")
    if not isinstance(group_name, str):
        return None
    slot = static_index_key(index)
    if slot is None:
        return None
    indexed_bindings = state.setdefault("indexed_bindings", {})
    if not isinstance(indexed_bindings, dict):
        return None
    group = indexed_bindings.get(group_name)
    if not isinstance(group, dict):
        return None
    bound = group.get(slot)
    if isinstance(bound, str) and _container_exists(state, bound):
        return bound
    return None


def resolve_content_ref(state: dict[str, Any], name: str) -> str | None:
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


def resolve_or_create_container_ref(state: dict[str, Any], name: str) -> str:
    resolved = resolve_container_ref(state, name)
    if resolved is not None:
        return resolved
    if _is_qualified_name(name):
        ensure_container(state, name)
        return name
    ensure_container(state, name)
    bind_name(state, name, name, step_id=None)
    return name


def static_index_key(value: Any) -> str | None:
    if not isinstance(value, dict) or value.get("kind") != "IRQuantity":
        return None
    unit = value.get("unit")
    raw = value.get("value")
    if unit is not None or not isinstance(raw, (int, float)):
        return None
    if float(raw) < 0 or not float(raw).is_integer():
        return None
    return str(int(raw))


def bind_name(state: dict[str, Any], name: str, container_id: str, step_id: str | None) -> list[dict[str, Any]]:
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


def bind_indexed_group(
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


def ref_display(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return "<invalid-ref>"
    kind = value.get("kind")
    if kind == "IRIdentifier":
        name = value.get("name")
        return name if isinstance(name, str) else "<identifier>"
    if kind == "IRIndex":
        base = ref_display(value.get("base"))
        slot = static_index_key(value.get("index"))
        return f"{base}[{slot if slot is not None else '?'}]"
    if kind == "IRSourcePartitionRef":
        source = ref_display(value.get("source"))
        program = value.get("program")
        program_name = program.get("name") if isinstance(program, dict) else None
        index = static_index_key(value.get("index"))
        return f"{source}.partition({program_name or '?'})[{index if index is not None else '?'}]"
    if kind == "IRString":
        inner = value.get("value")
        return inner if isinstance(inner, str) else "<string>"
    return f"<{kind or 'unknown-ref'}>"


def is_serialized_pair(value: Any) -> bool:
    return isinstance(value, dict) and value.get("kind") == "IRPair"


def is_unit_ref(value: Any) -> bool:
    return isinstance(value, dict) and value.get("kind") == "unit_ref"


def provision_source_for_estimate(state: dict[str, Any], name: str, qty: dict[str, Any]) -> str:
    source_id = resolve_or_create_container_ref(state, name)
    source = ensure_container(state, source_id)
    unit = str(qty["unit"])
    value = float(qty["value"])
    if unit in VOLUME_TO_UL:
        requested_uL = value * VOLUME_TO_UL[unit]
        top_up_source_for_estimate(source=source, qty=requested_uL, mode="volume", source_name=name)
    elif unit in MASS_TO_MG:
        requested_mg = value * MASS_TO_MG[unit]
        top_up_source_for_estimate(source=source, qty=requested_mg, mode="mass", source_name=name)
    return source_id


def top_up_source_for_estimate(source: dict[str, Any], qty: float, mode: str, source_name: str) -> None:
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


def _is_qualified_name(name: str) -> bool:
    if "::" not in name:
        return False
    head, tail = name.split("::", 1)
    return bool(head) and bool(tail)


def _container_exists(state: dict[str, Any], container_id: str) -> bool:
    containers = state.setdefault("containers", {})
    return isinstance(containers.get(container_id), dict)
