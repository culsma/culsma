"""Authoritative Runtime component-entry state and transfer transactions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import Any

from culsma.scientific_model.material import (
    AssociationTarget,
    AssociationTargetKind,
    MaterialRelation,
)
from culsma.runtime.material.units import COUNT_TO_CELLS, MASS_TO_MG, VOLUME_TO_UL


ENTRY_EPSILON = 1e-12
COMPONENT_ENTRIES_KEY = "component_entries"
MATERIAL_BOUND_RELATIONS = frozenset(
    {"bead_bound", "membrane_bound", "cell_bound"}
)


@dataclass(frozen=True)
class ComponentEntryMergeConflict(ValueError):
    content_ref: str
    reason: str

    def __str__(self) -> str:
        return f"Component '{self.content_ref}' cannot be merged: {self.reason}"


@dataclass(frozen=True)
class ComponentEntryRelationError(ValueError):
    relation: str

    def __str__(self) -> str:
        return f"Unknown committed material relation '{self.relation}'"


@dataclass(frozen=True)
class ComponentEntryTransfer:
    moved_entries: tuple[dict[str, Any], ...]
    source_entries: tuple[dict[str, Any], ...]
    target_entries: tuple[dict[str, Any], ...]


def validate_component_entry_set(
    entries: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    owner: str,
) -> None:
    """Validate one complete authoritative entry set before commit."""

    entry_ids: set[str] = set()
    for entry in entries:
        entry_id = entry.get("entry_id")
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError(f"{owner} contains an entry without entry_id")
        if entry_id in entry_ids:
            raise ValueError(f"{owner} contains duplicate entry_id '{entry_id}'")
        entry_ids.add(entry_id)
    for entry in entries:
        entry_id = entry.get("entry_id")
        content_ref = entry.get("content_ref")
        if not isinstance(content_ref, str) or not content_ref:
            raise ValueError(f"Entry '{entry_id}' has no content_ref")
        amount = entry.get("amount")
        if (
            isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not isfinite(float(amount))
            or float(amount) < 0
        ):
            raise ValueError(f"Entry '{entry_id}' has an invalid amount")
        quantity = entry.get("quantity")
        if quantity is not None:
            value = quantity.get("value") if isinstance(quantity, dict) else None
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(float(value))
                or float(value) < 0
            ):
                raise ValueError(f"Entry '{entry_id}' has an invalid quantity")
        relation = normalize_entry_relation(entry.get("relation"))
        associated_with = entry.get("associated_with")
        target_kind = entry.get("association_target_kind")
        if relation != "free" and not isinstance(associated_with, str):
            raise ValueError(
                f"Entry '{entry_id}' in relation '{relation}' has no association"
            )
        if relation != "free" and not associated_with:
            raise ValueError(
                f"Entry '{entry_id}' in relation '{relation}' has no association"
            )
        if relation == "free":
            if associated_with is not None or target_kind is not None:
                raise ValueError(
                    f"Free entry '{entry_id}' cannot retain an association"
                )
            continue
        expected_kind = association_target_kind_for_relation(relation).value
        if target_kind != expected_kind:
            raise ValueError(
                f"Entry '{entry_id}' in relation '{relation}' requires "
                f"association target kind '{expected_kind}'"
            )
        if (
            target_kind == AssociationTargetKind.COMPONENT_ENTRY.value
            and associated_with not in entry_ids
        ):
            raise ValueError(
                f"Entry '{entry_id}' references missing component entry "
                f"'{associated_with}'"
            )


def association_target_kind_for_relation(
    relation: str,
) -> AssociationTargetKind:
    """Return the only valid association-target kind for a non-free relation."""

    normalized = normalize_entry_relation(relation)
    return (
        AssociationTargetKind.COMPONENT_ENTRY
        if normalized in MATERIAL_BOUND_RELATIONS
        else AssociationTargetKind.CONTAINER
    )


def association_target_record(value: Any) -> AssociationTarget | None:
    """Parse the typed target carried by a resolved model decision."""

    if isinstance(value, AssociationTarget):
        return value
    if not isinstance(value, dict):
        return None
    try:
        kind = AssociationTargetKind(str(value.get("kind")))
    except ValueError:
        return None
    target_id = value.get("id")
    if not isinstance(target_id, str) or not target_id:
        return None
    return AssociationTarget(kind=kind, id=target_id)


def entry_association_target(entry: dict[str, Any]) -> AssociationTarget | None:
    """Read the typed association represented by one authoritative entry."""

    relation = normalize_entry_relation(entry.get("relation"))
    target_id = entry.get("associated_with")
    if relation == "free" or not isinstance(target_id, str) or not target_id:
        return None
    raw_kind = entry.get("association_target_kind")
    if raw_kind is None:
        kind = association_target_kind_for_relation(relation)
    else:
        try:
            kind = AssociationTargetKind(str(raw_kind))
        except ValueError:
            return None
    return AssociationTarget(kind=kind, id=target_id)


def container_component_entries(
    container: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return authoritative entries, hydrating a legacy 1.x container once."""

    existing = container.get(COMPONENT_ENTRIES_KEY)
    if isinstance(existing, list) and all(isinstance(entry, dict) for entry in existing):
        return existing

    components = container.get("components")
    components = components if isinstance(components, dict) else {}
    quantities = container.get("component_quantities")
    quantities = quantities if isinstance(quantities, dict) else {}
    metadata = container.get("metadata")
    classes = (
        metadata.get("component_partition_classes")
        if isinstance(metadata, dict)
        else None
    )
    classes = classes if isinstance(classes, dict) else {}

    entries: list[dict[str, Any]] = []
    content_refs = list(dict.fromkeys([*components, *quantities]))
    for raw_content_ref in content_refs:
        content_ref = str(raw_content_ref)
        quantity = quantities.get(raw_content_ref)
        amount = components.get(raw_content_ref)
        if not isinstance(amount, (int, float)):
            amount = quantity.get("value", 0.0) if isinstance(quantity, dict) else 0.0
        relation = legacy_relationship_for_component(
            container,
            content_ref,
            state=state,
        )
        entry: dict[str, Any] = {
            "entry_id": next_component_entry_id(entries, content_ref),
            "content_ref": content_ref,
            "amount": float(amount),
            "quantity": deepcopy(quantity) if isinstance(quantity, dict) else None,
            "relation": relation["relation"],
            "associated_with": relation.get("associated_with"),
            "association_target_kind": relation.get(
                "association_target_kind"
            ),
            "preservation": relation.get("preservation"),
            "label": relation.get("label"),
            "relationship_source": relation.get("relationship_source"),
            "material_state_source": relation.get("material_state_source"),
        }
        partition_class = classes.get(raw_content_ref)
        if not isinstance(partition_class, str):
            partition_class = content_registry_partition_class(state, content_ref)
        if isinstance(partition_class, str):
            entry["partition_class"] = partition_class
        entries.append(entry)

    container[COMPONENT_ENTRIES_KEY] = entries
    return entries


def legacy_relationship_for_component(
    container: dict[str, Any],
    content_ref: str,
    *,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    relationships = container.get("material_relationships")
    if not isinstance(relationships, list):
        return content_registry_relationship(state, content_ref)

    suspension_state: str | None = None
    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue
        component_ids = relationship.get("dispersed_component_ids")
        if not isinstance(component_ids, list) or content_ref not in component_ids:
            continue
        material_state = relationship.get("material_state")
        if not isinstance(material_state, str):
            continue
        if relationship.get("subtype") == "scientific_model_relation":
            return {
                "relation": normalize_entry_relation(material_state),
                "associated_with": relationship.get("associated_with"),
                "association_target_kind": relationship.get(
                    "association_target_kind"
                ),
                "preservation": relationship.get("preservation"),
                "label": relationship.get("label"),
                "relationship_source": "scientific_model",
                "material_state_source": relationship.get("material_state_source"),
            }
        if relationship.get("subtype") == "cell_suspension":
            suspension_state = material_state

    if suspension_state is not None:
        return {
            "relation": normalize_entry_relation(suspension_state),
            "relationship_source": "cell_suspension",
        }
    return content_registry_relationship(state, content_ref)


def content_registry_relationship(
    state: dict[str, Any] | None,
    content_ref: str,
) -> dict[str, Any]:
    registry = state.get("content_registry") if isinstance(state, dict) else None
    content = registry.get(content_ref) if isinstance(registry, dict) else None
    attrs = content.get("content_attrs") if isinstance(content, dict) else None
    attrs = attrs if isinstance(attrs, dict) else {}
    raw_relation = attrs.get("association")
    if (
        raw_relation is None
        and isinstance(content, dict)
        and content.get("content_kind") == "bio_cellular"
    ):
        raw_relation = attrs.get("state") or attrs.get("culture_state")
    if raw_relation is None:
        return {"relation": "free"}
    return {
        "relation": normalize_entry_relation(raw_relation),
        "preservation": "declared",
        "relationship_source": "content_registry",
    }


def content_registry_partition_class(
    state: dict[str, Any] | None,
    content_ref: str,
) -> str | None:
    """Return a 1.x compatibility class only for an unambiguous registry kind."""

    registry = state.get("content_registry") if isinstance(state, dict) else None
    content = registry.get(content_ref) if isinstance(registry, dict) else None
    if isinstance(content, dict) and content.get("content_kind") == "bio_cellular":
        return "pelletable_cells"
    return None


def normalize_entry_relation(value: Any) -> str:
    token = str(value or "free").strip().lower()
    aliases = {
        "suspended": "free",
        "suspension": "free",
        "mixed": "free",
        "released": "free",
        "adherent": "container_surface",
        "adherent_monolayer": "container_surface",
        "surface_bound": "container_surface",
        "surface_associated": "container_surface",
        "pelleted": "pellet",
        "precipitated": "precipitate",
        "bead": "bead_bound",
        "membrane": "membrane_bound",
        "cell": "cell_bound",
        "lysate": "disrupted",
    }
    relation = aliases.get(token, token)
    allowed = {
        candidate.value
        for candidate in MaterialRelation
        if candidate is not MaterialRelation.UNRESOLVED
    }
    if relation not in allowed:
        raise ComponentEntryRelationError(relation)
    return relation


def next_component_entry_id(entries: list[dict[str, Any]], content_ref: str) -> str:
    used = {
        str(entry.get("entry_id"))
        for entry in entries
        if isinstance(entry.get("entry_id"), str)
    }
    if content_ref not in used:
        return content_ref
    ordinal = 1
    while f"{content_ref}::{ordinal}" in used:
        ordinal += 1
    return f"{content_ref}::{ordinal}"


def available_component_entry_id(
    entries: list[dict[str, Any]],
    incoming: dict[str, Any],
) -> str:
    preferred = incoming.get("entry_id")
    used = {
        str(entry.get("entry_id"))
        for entry in entries
        if isinstance(entry.get("entry_id"), str)
    }
    if isinstance(preferred, str) and preferred and preferred not in used:
        return preferred
    return next_component_entry_id(entries, str(incoming.get("content_ref", "")))


def quantity_conversion_factor(source_unit: str, target_unit: str) -> float | None:
    for unit_map in (VOLUME_TO_UL, MASS_TO_MG, COUNT_TO_CELLS):
        if source_unit in unit_map and target_unit in unit_map:
            return float(unit_map[source_unit]) / float(unit_map[target_unit])
    return 1.0 if source_unit == target_unit else None


def quantities_compatible(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    if left.get("dimension") != right.get("dimension"):
        return False
    return quantity_conversion_factor(
        str(right.get("unit", "")),
        str(left.get("unit", "")),
    ) is not None


def entry_states_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_relation = normalize_entry_relation(left.get("relation"))
    right_relation = normalize_entry_relation(right.get("relation"))
    if left_relation != right_relation:
        return False
    if left.get("label") != right.get("label"):
        return False
    left_class = left.get("partition_class")
    right_class = right.get("partition_class")
    if left_class is not None and right_class is not None and left_class != right_class:
        return False
    if left_relation == "free":
        left_preservation = left.get("preservation")
        right_preservation = right.get("preservation")
        return not (
            left_preservation is not None
            and right_preservation is not None
            and left_preservation != right_preservation
        )
    return (
        left.get("associated_with") == right.get("associated_with")
        and entry_association_target(left) == entry_association_target(right)
        and left.get("preservation") == right.get("preservation")
    )


def entries_can_compress(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get("content_ref") == right.get("content_ref")
        and quantities_compatible(left.get("quantity"), right.get("quantity"))
        and entry_states_compatible(left, right)
    )


def merge_component_entry(
    entries: list[dict[str, Any]],
    incoming: dict[str, Any],
) -> str:
    content_ref = str(incoming.get("content_ref", ""))
    same_content = [entry for entry in entries if entry.get("content_ref") == content_ref]
    for existing in same_content:
        if not quantities_compatible(existing.get("quantity"), incoming.get("quantity")):
            raise ComponentEntryMergeConflict(content_ref, "incompatible quantity dimensions or units")
    for existing in same_content:
        if not entries_can_compress(existing, incoming):
            continue
        amount_factor = 1.0
        existing_quantity = existing.get("quantity")
        incoming_quantity = incoming.get("quantity")
        if isinstance(existing_quantity, dict) and isinstance(incoming_quantity, dict):
            converted = quantity_conversion_factor(
                str(incoming_quantity.get("unit", "")),
                str(existing_quantity.get("unit", "")),
            )
            if converted is not None:
                amount_factor = converted
        existing["amount"] = float(existing.get("amount", 0.0)) + float(
            incoming.get("amount", 0.0)
        ) * amount_factor
        merge_entry_quantity(existing, incoming)
        if existing.get("partition_class") is None:
            existing["partition_class"] = incoming.get("partition_class")
        if existing.get("preservation") is None:
            existing["preservation"] = incoming.get("preservation")
        merge_entry_provenance(existing, incoming)
        if (
            existing.get("relationship_source") != "scientific_model"
            and incoming.get("relationship_source") == "scientific_model"
        ):
            existing["relationship_source"] = "scientific_model"
            existing["material_state_source"] = incoming.get("material_state_source")
            if isinstance(incoming.get("provenance"), dict):
                existing["provenance"] = deepcopy(incoming["provenance"])
        elif existing.get("relationship_source") is None:
            existing["relationship_source"] = incoming.get("relationship_source")
            existing["material_state_source"] = incoming.get("material_state_source")
            if isinstance(incoming.get("provenance"), dict):
                existing["provenance"] = deepcopy(incoming["provenance"])
        return str(existing["entry_id"])

    kept = deepcopy(incoming)
    kept["entry_id"] = available_component_entry_id(entries, incoming)
    entries.append(kept)
    return str(kept["entry_id"])


def merge_entry_provenance(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> None:
    """Preserve distinct decision lineage when compatible entries compress."""

    records: list[dict[str, Any]] = []
    for entry in (existing, incoming):
        history = entry.get("provenance_history")
        candidates = history if isinstance(history, list) else [entry.get("provenance")]
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate not in records:
                records.append(deepcopy(candidate))
    if len(records) > 1:
        existing["provenance_history"] = records


def compress_component_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compressed: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, dict):
            merge_component_entry(compressed, entry)
    return compressed


def normalize_component_entries(
    container: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
    container_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return one canonical entry set for either 1.x views or current entries."""

    entries = compress_component_entries(
        deepcopy(container_component_entries(container, state=state))
    )
    for entry in entries:
        relation = normalize_entry_relation(entry.get("relation"))
        entry["relation"] = relation
        if relation == "free":
            entry["associated_with"] = None
            entry["association_target_kind"] = None
        elif not isinstance(entry.get("associated_with"), str) and container_id:
            entry["associated_with"] = container_id
        if relation != "free" and not isinstance(
            entry.get("association_target_kind"), str
        ):
            entry["association_target_kind"] = (
                association_target_kind_for_relation(relation).value
            )
    return entries


def merge_entry_quantity(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    left = existing.get("quantity")
    right = incoming.get("quantity")
    if left is None and right is None:
        return
    if not isinstance(left, dict) or not isinstance(right, dict):
        raise ComponentEntryMergeConflict(
            str(existing.get("content_ref", "")),
            "incompatible quantity records",
        )
    factor = quantity_conversion_factor(str(right.get("unit", "")), str(left.get("unit", "")))
    if factor is None or left.get("dimension") != right.get("dimension"):
        raise ComponentEntryMergeConflict(
            str(existing.get("content_ref", "")),
            "incompatible quantity dimensions or units",
        )
    left["value"] = float(left.get("value", 0.0)) + float(right.get("value", 0.0)) * factor


def transition_entry_for_move(
    entry: dict[str, Any],
    *,
    destination_id: str | None,
    next_relation: str,
    next_label: str | None,
    next_association_target: AssociationTarget | None,
    provenance: dict[str, Any] | None,
    scientific_decision: bool,
) -> dict[str, Any]:
    """Apply one already-resolved movement transition to an entry copy."""

    moved = deepcopy(entry)
    relation = normalize_entry_relation(next_relation)
    moved["relation"] = relation
    moved["label"] = next_label
    if relation == "free":
        moved["associated_with"] = None
        moved["association_target_kind"] = None
        moved["preservation"] = None
    else:
        target = next_association_target
        if target is None and not scientific_decision:
            current = entry_association_target(moved)
            target = (
                current
                if relation in MATERIAL_BOUND_RELATIONS and current is not None
                else AssociationTarget(
                    kind=association_target_kind_for_relation(relation),
                    id=str(destination_id or moved.get("associated_with") or ""),
                )
            )
        if target is None or not target.id:
            raise ValueError(
                f"Entry '{moved.get('entry_id')}' has no resolved association target"
            )
        expected_kind = association_target_kind_for_relation(relation)
        if target.kind is not expected_kind:
            raise ValueError(
                f"Entry '{moved.get('entry_id')}' in relation '{relation}' "
                f"cannot use association target kind '{target.kind.value}'"
            )
        moved["associated_with"] = target.id
        moved["association_target_kind"] = target.kind.value
    if scientific_decision:
        previous = {
            "provenance": moved.get("provenance"),
            "provenance_history": deepcopy(moved.get("provenance_history")),
        }
        moved["relationship_source"] = "scientific_model"
        moved["material_state_source"] = "scientific_model_provider"
        if provenance is not None:
            moved["provenance"] = deepcopy(provenance)
            merge_entry_provenance(moved, previous)
    return moved


def merge_transferred_entries(
    target_entries: list[dict[str, Any]],
    moved_entries: list[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Merge moved entries while preserving component-entry target identity."""

    referenced_ids = {
        str(entry.get("associated_with"))
        for entry in moved_entries
        if entry.get("association_target_kind")
        == AssociationTargetKind.COMPONENT_ENTRY.value
    }
    ordered = [
        *[
            entry
            for entry in moved_entries
            if str(entry.get("entry_id")) in referenced_ids
        ],
        *[
            entry
            for entry in moved_entries
            if str(entry.get("entry_id")) not in referenced_ids
        ],
    ]
    committed_ids: dict[str, str] = {}
    committed: list[dict[str, Any]] = []
    for entry in ordered:
        projected = deepcopy(entry)
        source_entry_id = str(projected.get("entry_id"))
        target_id = projected.get("associated_with")
        if (
            projected.get("association_target_kind")
            == AssociationTargetKind.COMPONENT_ENTRY.value
            and isinstance(target_id, str)
            and target_id in committed_ids
        ):
            projected["associated_with"] = committed_ids[target_id]
        committed_entry_id = merge_component_entry(target_entries, projected)
        committed_ids[source_entry_id] = committed_entry_id
        projected["entry_id"] = committed_entry_id
        committed.append(projected)
    return tuple(committed)


def split_component_entry(entry: dict[str, Any], ratio: float) -> tuple[dict[str, Any], dict[str, Any]]:
    remaining = deepcopy(entry)
    moved = deepcopy(entry)
    amount = float(entry.get("amount", 0.0))
    moved_amount = clamp_entry_value(amount * ratio)
    remaining["amount"] = clamp_entry_value(amount - moved_amount)
    moved["amount"] = moved_amount
    quantity = entry.get("quantity")
    if isinstance(quantity, dict):
        value = float(quantity.get("value", amount))
        remaining_quantity = deepcopy(quantity)
        moved_quantity = deepcopy(quantity)
        moved_value = clamp_entry_value(value * ratio)
        remaining_quantity["value"] = clamp_entry_value(value - moved_value)
        moved_quantity["value"] = moved_value
        remaining["quantity"] = remaining_quantity
        moved["quantity"] = moved_quantity
    return remaining, moved


def component_entry_has_quantity(entry: dict[str, Any]) -> bool:
    quantity = entry.get("quantity")
    if isinstance(quantity, dict):
        return abs(float(quantity.get("value", 0.0))) > ENTRY_EPSILON
    return abs(float(entry.get("amount", 0.0))) > ENTRY_EPSILON


def plan_component_entry_transfer(
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    ratio: float,
    destination_id: str | None,
    transitions_by_entry_id: dict[str, dict[str, Any]] | None = None,
) -> ComponentEntryTransfer:
    if not isfinite(ratio) or ratio < 0.0 or ratio > 1.0:
        raise ValueError("Component transfer ratio must be finite and between 0 and 1")
    source_entries = normalize_component_entries(source)
    target_entries = normalize_component_entries(target)
    remaining_entries: list[dict[str, Any]] = []
    moved_entries: list[dict[str, Any]] = []
    for source_entry in source_entries:
        remaining, moved = split_component_entry(source_entry, ratio)
        if component_entry_has_quantity(remaining):
            remaining_entries.append(remaining)
        if not component_entry_has_quantity(moved):
            if ratio > 0.0 and not any(
                entry.get("content_ref") == moved.get("content_ref")
                for entry in target_entries
            ):
                compatibility_zero = deepcopy(moved)
                compatibility_zero["relation"] = "free"
                compatibility_zero["associated_with"] = None
                compatibility_zero["association_target_kind"] = None
                compatibility_zero["preservation"] = None
                compatibility_zero["label"] = None
                compatibility_zero["relationship_source"] = None
                compatibility_zero["material_state_source"] = None
                merge_component_entry(target_entries, compatibility_zero)
            continue
        transition = (
            transitions_by_entry_id.get(str(moved.get("entry_id")))
            if isinstance(transitions_by_entry_id, dict)
            else None
        )
        if not isinstance(transition, dict):
            raise ComponentEntryRelationError(
                f"unresolved move for entry '{moved.get('entry_id')}'"
            )
        transitioned = transition_entry_for_move(
            moved,
            destination_id=destination_id,
            next_relation=str(transition.get("next_relation", "unresolved")),
            next_label=(
                str(transition["next_label"])
                if isinstance(transition.get("next_label"), str)
                else None
            ),
            next_association_target=association_target_record(
                transition.get("next_association_target")
            ),
            provenance=(
                dict(transition["provenance"])
                if isinstance(transition.get("provenance"), dict)
                else None
            ),
            scientific_decision=transition.get("scientific_decision") is True,
        )
        moved_entries.append(transitioned)
    committed_moved_entries = merge_transferred_entries(
        target_entries,
        moved_entries,
    )
    return ComponentEntryTransfer(
        moved_entries=committed_moved_entries,
        source_entries=tuple(remaining_entries),
        target_entries=tuple(target_entries),
    )


def commit_component_entry_transfer(
    source: dict[str, Any],
    target: dict[str, Any],
    transfer: ComponentEntryTransfer,
) -> None:
    replace_component_entries(source, list(transfer.source_entries))
    replace_component_entries(target, list(transfer.target_entries))


def move_component_entries(
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    ratio: float,
    destination_id: str | None,
    transitions_by_entry_id: dict[str, dict[str, Any]] | None = None,
) -> ComponentEntryTransfer:
    transfer = plan_component_entry_transfer(
        source,
        target,
        ratio=ratio,
        destination_id=destination_id,
        transitions_by_entry_id=transitions_by_entry_id,
    )
    commit_component_entry_transfer(source, target, transfer)
    return transfer


def relocate_component_entries(
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    ratio: float,
    destination_id: str | None,
) -> ComponentEntryTransfer:
    """Relocate entries after their physical transition has already been decided."""

    transitions = {
        str(entry.get("entry_id")): {
            "next_relation": normalize_entry_relation(entry.get("relation")),
            "next_label": entry.get("label"),
            "next_association_target": relocation_association_target_record(
                entry,
                destination_id=destination_id,
            ),
            "provenance": entry.get("provenance"),
            "scientific_decision": False,
        }
        for entry in normalize_component_entries(source)
        if isinstance(entry.get("entry_id"), str)
    }
    return move_component_entries(
        source,
        target,
        ratio=ratio,
        destination_id=destination_id,
        transitions_by_entry_id=transitions,
    )


def relocation_association_target_record(
    entry: dict[str, Any],
    *,
    destination_id: str | None,
) -> dict[str, str] | None:
    """Build the association target for an already-resolved relocation."""

    relation = normalize_entry_relation(entry.get("relation"))
    if relation == "free":
        return None
    current = entry_association_target(entry)
    target = (
        current
        if relation in MATERIAL_BOUND_RELATIONS
        else AssociationTarget(
            kind=AssociationTargetKind.CONTAINER,
            id=str(destination_id or entry.get("associated_with") or ""),
        )
    )
    if target is None or not target.id:
        return None
    return {"kind": target.kind.value, "id": target.id}


def subtract_component_entries(
    container: dict[str, Any],
    removed_entries: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    *,
    preserve_zero_entries: bool = False,
) -> None:
    entries = deepcopy(container_component_entries(container))
    for removed in removed_entries:
        match = next(
            (
                entry
                for entry in entries
                if entry.get("entry_id") == removed.get("entry_id")
                and entry_states_compatible(entry, removed)
            ),
            None,
        )
        if match is None:
            match = next(
                (
                    entry
                    for entry in entries
                    if entry.get("content_ref") == removed.get("content_ref")
                    and entry_states_compatible(entry, removed)
                ),
                None,
            )
        if match is None:
            amount = float(removed.get("amount", 0.0))
            sufficient = [
                entry
                for entry in entries
                if entry.get("content_ref") == removed.get("content_ref")
                and quantities_compatible(entry.get("quantity"), removed.get("quantity"))
                and float(entry.get("amount", 0.0)) + ENTRY_EPSILON >= amount
            ]
            if len(sufficient) == 1:
                match = sufficient[0]
        if match is None:
            raise ComponentEntryMergeConflict(
                str(removed.get("content_ref", "")),
                "source entry is missing",
            )
        match["amount"] = clamp_entry_value(
            float(match.get("amount", 0.0)) - float(removed.get("amount", 0.0))
        )
        match_quantity = match.get("quantity")
        removed_quantity = removed.get("quantity")
        if isinstance(match_quantity, dict) and isinstance(removed_quantity, dict):
            factor = quantity_conversion_factor(
                str(removed_quantity.get("unit", "")),
                str(match_quantity.get("unit", "")),
            )
            if factor is None:
                raise ComponentEntryMergeConflict(
                    str(removed.get("content_ref", "")),
                    "incompatible quantity units during subtraction",
                )
            match_quantity["value"] = clamp_entry_value(
                float(match_quantity.get("value", 0.0))
                - float(removed_quantity.get("value", 0.0)) * factor
            )
    replace_component_entries(
        container,
        (
            entries
            if preserve_zero_entries
            else [entry for entry in entries if component_entry_has_quantity(entry)]
        ),
    )


def retain_component_entry_ratio(container: dict[str, Any], ratio: float) -> None:
    if not isfinite(ratio) or ratio < 0.0 or ratio > 1.0:
        raise ValueError("Component retention ratio must be finite and between 0 and 1")
    retained: list[dict[str, Any]] = []
    for entry in deepcopy(container_component_entries(container)):
        _removed, kept = split_component_entry(entry, ratio)
        if component_entry_has_quantity(kept):
            retained.append(kept)
    replace_component_entries(container, retained)


def replace_component_entries(
    container: dict[str, Any],
    entries: list[dict[str, Any]],
) -> None:
    container[COMPONENT_ENTRIES_KEY] = compress_component_entries(deepcopy(entries))
    project_component_entries(container)


def project_component_entries(container: dict[str, Any]) -> None:
    entries = container.get(COMPONENT_ENTRIES_KEY)
    if not isinstance(entries, list):
        return
    components: dict[str, float] = {}
    quantities: dict[str, dict[str, Any]] = {}
    classes: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        content_ref = str(entry.get("content_ref", ""))
        quantity = entry.get("quantity")
        existing_quantity = quantities.get(content_ref)
        amount_factor = 1.0
        if isinstance(quantity, dict) and isinstance(existing_quantity, dict):
            converted = quantity_conversion_factor(
                str(quantity.get("unit", "")),
                str(existing_quantity.get("unit", "")),
            )
            if converted is not None:
                amount_factor = converted
        components[content_ref] = components.get(content_ref, 0.0) + float(
            entry.get("amount", 0.0)
        ) * amount_factor
        if isinstance(quantity, dict):
            if existing_quantity is None:
                quantities[content_ref] = deepcopy(quantity)
            else:
                factor = quantity_conversion_factor(
                    str(quantity.get("unit", "")),
                    str(existing_quantity.get("unit", "")),
                )
                if factor is None or existing_quantity.get("dimension") != quantity.get("dimension"):
                    raise ComponentEntryMergeConflict(
                        content_ref,
                        "legacy projection cannot represent incompatible quantities",
                    )
                existing_quantity["value"] = float(existing_quantity.get("value", 0.0)) + float(
                    quantity.get("value", 0.0)
                ) * factor
        partition_class = entry.get("partition_class")
        if isinstance(partition_class, str):
            classes[content_ref] = partition_class

    container["components"] = components
    container["component_quantities"] = quantities
    metadata = container.setdefault("metadata", {})
    if isinstance(metadata, dict):
        if classes:
            metadata["component_partition_classes"] = classes
        else:
            metadata.pop("component_partition_classes", None)
    project_scientific_relationships(container, entries)


def project_scientific_relationships(
    container: dict[str, Any],
    entries: list[dict[str, Any]],
) -> None:
    relationships = container.get("material_relationships")
    relationships = relationships if isinstance(relationships, list) else []
    projected = [
        deepcopy(relationship)
        for relationship in relationships
        if not (
            isinstance(relationship, dict)
            and relationship.get("subtype") == "scientific_model_relation"
        )
        and relationship_references_live_entry(relationship, entries)
    ]
    for entry in entries:
        if not isinstance(entry, dict) or not component_entry_has_quantity(entry):
            continue
        relation = normalize_entry_relation(entry.get("relation"))
        if relation == "free" or entry.get("relationship_source") != "scientific_model":
            continue
        content_ref = str(entry.get("content_ref", ""))
        relationship: dict[str, Any] = {
            "kind": "association",
            "subtype": "scientific_model_relation",
            "dispersed_component_ids": [content_ref],
            "material_state": relation,
            "associated_with": entry.get("associated_with"),
        }
        if isinstance(entry.get("material_state_source"), str):
            relationship["material_state_source"] = entry["material_state_source"]
        entry_id = str(entry.get("entry_id", content_ref))
        if entry_id != content_ref:
            relationship["component_entry_ids"] = [entry_id]
        if entry.get("label") is not None:
            relationship["label"] = entry["label"]
        if entry.get("preservation") not in {None, "declared", "derived", "unspecified"}:
            relationship["preservation"] = entry["preservation"]
        if isinstance(entry.get("provenance"), dict):
            relationship["provenance"] = deepcopy(entry["provenance"])
        if isinstance(entry.get("provenance_history"), list):
            relationship["provenance_history"] = deepcopy(entry["provenance_history"])
        projected.append(relationship)
    container["material_relationships"] = projected


def relationship_references_live_entry(
    relationship: Any,
    entries: list[dict[str, Any]],
) -> bool:
    if not isinstance(relationship, dict):
        return True
    component_ids = relationship.get("dispersed_component_ids")
    if not isinstance(component_ids, list):
        return True
    live_content_refs = {
        str(entry.get("content_ref", ""))
        for entry in entries
        if isinstance(entry, dict) and component_entry_has_quantity(entry)
    }
    return any(
        isinstance(component_id, str) and component_id in live_content_refs
        for component_id in component_ids
    )


def append_free_component_quantity(
    container: dict[str, Any],
    *,
    content_ref: str,
    amount: float,
    quantity: dict[str, Any],
) -> None:
    append_component_quantity(
        container,
        content_ref=content_ref,
        amount=amount,
        quantity=quantity,
        relation="free",
    )


def append_component_quantity(
    container: dict[str, Any],
    *,
    content_ref: str,
    amount: float,
    quantity: dict[str, Any],
    relation: str,
    associated_with: str | None = None,
    association_target_kind: str | None = None,
    preservation: str | None = None,
    relationship_source: str | None = None,
    material_state_source: str | None = None,
    partition_class: str | None = None,
) -> None:
    """Append one occurrence with its authoritative state already attached."""

    normalized_relation = normalize_entry_relation(relation)
    entries = normalize_component_entries(container)
    merge_component_entry(
        entries,
        {
            "entry_id": content_ref,
            "content_ref": content_ref,
            "amount": float(amount),
            "quantity": deepcopy(quantity),
            "relation": normalized_relation,
            "associated_with": (
                None if normalized_relation == "free" else associated_with
            ),
            "association_target_kind": (
                None
                if normalized_relation == "free"
                else association_target_kind
                or association_target_kind_for_relation(
                    normalized_relation
                ).value
            ),
            "preservation": preservation,
            "label": None,
            "relationship_source": relationship_source,
            "material_state_source": material_state_source,
            "partition_class": partition_class,
        },
    )
    replace_component_entries(container, entries)


def clamp_entry_value(value: float) -> float:
    if value < -ENTRY_EPSILON:
        raise ValueError("Component entry quantity became negative")
    return 0.0 if abs(value) <= ENTRY_EPSILON else value
