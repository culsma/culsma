"""Normalize material operation semantics into accounting movements."""

from __future__ import annotations

from typing import Any

from culsma.runtime.material.result import MaterialMovementSpec


EPSILON = 1e-9


def material_quantities_changed(
    *,
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> bool:
    before = _containers(before_state)
    after = _containers(after_state)
    for container_id in set(before) | set(after):
        before_volume, before_mass = _container_quantity(before.get(container_id))
        after_volume, after_mass = _container_quantity(after.get(container_id))
        if abs(after_volume - before_volume) > EPSILON or abs(after_mass - before_mass) > EPSILON:
            return True
    return False


def derive_material_movements(
    *,
    delta: dict[str, Any],
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> list[MaterialMovementSpec]:
    explicit = delta.get("movements")
    if isinstance(explicit, list):
        movements = [_movement_from_dict(item) for item in explicit]
        return [movement for movement in movements if movement is not None]

    if delta.get("op") == "Mutation":
        movements: list[MaterialMovementSpec] = []
        for source_delta in delta.get("sources", []):
            movement = _mutation_source_movement(source_delta, default_target=delta.get("target"))
            if movement is not None:
                movements.append(movement)
        return movements

    source = delta.get("source")
    slots = delta.get("slots")
    if delta.get("op") in {"sep", "frac"} and isinstance(source, str) and isinstance(slots, dict):
        return _source_to_slots_movements(
            source=source,
            slots=slots,
            before_state=before_state,
            after_state=after_state,
        )
    return []


def _mutation_source_movement(raw: Any, *, default_target: Any) -> MaterialMovementSpec | None:
    if not isinstance(raw, dict):
        return None
    nested = raw.get("transfer_delta")
    if isinstance(nested, dict):
        movement = _mutation_source_movement(nested, default_target=raw.get("target", default_target))
        if movement is not None:
            return movement
    transfer = raw.get("transfer")
    if isinstance(transfer, dict):
        movement = _movement_from_dict(
            transfer,
            default_source=raw.get("source"),
            default_target=raw.get("target", default_target),
        )
        if movement is not None:
            return movement
    return _movement_from_dict(raw, default_target=default_target)


def _movement_from_dict(
    raw: Any,
    *,
    default_source: Any = None,
    default_target: Any = None,
) -> MaterialMovementSpec | None:
    if not isinstance(raw, dict):
        return None
    source = raw.get("source", default_source)
    destination = raw.get("destination", raw.get("dest", raw.get("target", default_target)))
    if not isinstance(source, str) or not isinstance(destination, str) or source == destination:
        return None
    movement = MaterialMovementSpec(
        source=source,
        destination=destination,
        volume_uL=_first_number(raw, "moved_uL", "removed_uL", "requested_uL", "converted_uL"),
        mass_mg=_first_number(raw, "moved_mg", "removed_mg", "requested_mg", "converted_mg"),
    )
    return movement if movement.volume_uL > EPSILON or movement.mass_mg > EPSILON else None


def _source_to_slots_movements(
    *,
    source: str,
    slots: dict[str, Any],
    before_state: dict[str, Any],
    after_state: dict[str, Any],
) -> list[MaterialMovementSpec]:
    before = _containers(before_state)
    after = _containers(after_state)
    movements: list[MaterialMovementSpec] = []
    for destination in sorted({value for value in slots.values() if isinstance(value, str)}):
        if destination == source:
            continue
        before_volume, before_mass = _container_quantity(before.get(destination))
        after_volume, after_mass = _container_quantity(after.get(destination))
        movement = MaterialMovementSpec(
            source=source,
            destination=destination,
            volume_uL=max(0.0, after_volume - before_volume),
            mass_mg=max(0.0, after_mass - before_mass),
        )
        if movement.volume_uL > EPSILON or movement.mass_mg > EPSILON:
            movements.append(movement)
    return movements


def _first_number(raw: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, (int, float)) and float(value) > EPSILON:
            return float(value)
    return 0.0


def _containers(state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    containers = state.get("containers")
    return containers if isinstance(containers, dict) else {}


def _container_quantity(raw: Any) -> tuple[float, float]:
    if not isinstance(raw, dict):
        return 0.0, 0.0
    return float(raw.get("volume_uL", 0.0)), float(raw.get("mass_mg", 0.0))
