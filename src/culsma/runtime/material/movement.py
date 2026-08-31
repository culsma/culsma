"""Scientific-model boundary for cross-container material movement."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from culsma.runtime.material.component_entries import (
    ComponentEntryRelationError,
    ComponentEntryTransfer,
    component_entry_has_quantity,
    normalize_component_entries,
    plan_component_entry_transfer,
    replace_component_entries,
    split_component_entry,
    validate_component_entry_set,
)
from culsma.runtime.material.ledger import refresh_container_aggregates
from culsma.runtime.material.scientific_model_adapter import (
    MaterialEffectFailure,
    ResolvedMaterialTransition,
    ScientificModelMaterialAdapter,
)


@dataclass(frozen=True)
class MaterialMovementCandidate:
    transition: ResolvedMaterialTransition
    transfer: ComponentEntryTransfer


@dataclass(frozen=True)
class MaterialMovementApplicationResult:
    transfer: ComponentEntryTransfer | None = None
    transition: ResolvedMaterialTransition | None = None
    failure: MaterialEffectFailure | None = None


def moved_component_entries(
    source: dict[str, Any],
    *,
    state: dict[str, Any],
    source_id: str,
    ratio: float,
) -> tuple[dict[str, Any], ...]:
    moved_entries: list[dict[str, Any]] = []
    for entry in normalize_component_entries(
        source,
        state=state,
        container_id=source_id,
    ):
        _remaining, moved = split_component_entry(entry, ratio)
        if component_entry_has_quantity(moved):
            moved_entries.append(moved)
    return tuple(moved_entries)


def project_material_movement(
    *,
    state: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
    source_id: str,
    destination_id: str,
    ratio: float,
    material_effect_adapter: ScientificModelMaterialAdapter,
    request_id: str,
) -> MaterialMovementCandidate | MaterialEffectFailure:
    if not isfinite(ratio) or ratio < 0.0 or ratio > 1.0:
        return MaterialEffectFailure(
            code="MAT_STATE_INVARIANT_VIOLATION",
            message="Material movement ratio must be finite and between 0 and 1",
        )
    moved_entries = moved_component_entries(
        source,
        state=state,
        source_id=source_id,
        ratio=ratio,
    )
    transition = material_effect_adapter.resolve_movement(
        state=state,
        source=source,
        entries=moved_entries,
        request_id=request_id,
        source_id=source_id,
        destination_id=destination_id,
    )
    if isinstance(transition, MaterialEffectFailure):
        return transition
    transition_records = material_effect_adapter.transition_records(transition)
    transfer = plan_component_entry_transfer(
        source,
        target,
        ratio=ratio,
        destination_id=destination_id,
        transitions_by_entry_id=transition_records,
    )
    try:
        validate_component_entry_set(
            transfer.source_entries,
            owner=f"Movement source '{source_id}'",
        )
        validate_component_entry_set(
            transfer.target_entries,
            owner=f"Movement target '{destination_id}'",
        )
    except (ComponentEntryRelationError, ValueError) as exc:
        return MaterialEffectFailure(
            code="MAT_STATE_INVARIANT_VIOLATION",
            message=str(exc),
        )
    return MaterialMovementCandidate(transition=transition, transfer=transfer)


def commit_material_movement(
    candidate: MaterialMovementCandidate,
    *,
    source: dict[str, Any],
    target: dict[str, Any],
) -> ComponentEntryTransfer:
    validate_component_entry_set(
        candidate.transfer.source_entries,
        owner="Movement source candidate",
    )
    validate_component_entry_set(
        candidate.transfer.target_entries,
        owner="Movement target candidate",
    )
    replace_component_entries(source, list(candidate.transfer.source_entries))
    replace_component_entries(target, list(candidate.transfer.target_entries))
    refresh_container_aggregates(source)
    refresh_container_aggregates(target)
    return candidate.transfer


def apply_material_movement(
    *,
    state: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
    source_id: str,
    destination_id: str,
    ratio: float,
    material_effect_adapter: ScientificModelMaterialAdapter | None,
    request_id: str,
) -> MaterialMovementApplicationResult:
    if source is target or source_id == destination_id:
        return MaterialMovementApplicationResult(
            failure=MaterialEffectFailure(
                code="MAT_STATE_INVARIANT_VIOLATION",
                message="Cross-container movement requires distinct source and target containers",
            )
        )
    if material_effect_adapter is None:
        return MaterialMovementApplicationResult(
            failure=MaterialEffectFailure(
                code="MAT_SCIENTIFIC_MODEL_UNAVAILABLE",
                message="Runtime did not provide a scientific-model adapter for movement",
            )
        )
    try:
        candidate = project_material_movement(
            state=state,
            source=source,
            target=target,
            source_id=source_id,
            destination_id=destination_id,
            ratio=ratio,
            material_effect_adapter=material_effect_adapter,
            request_id=request_id,
        )
    except (ComponentEntryRelationError, ValueError) as exc:
        return MaterialMovementApplicationResult(
            failure=MaterialEffectFailure(
                code="MAT_STATE_INVARIANT_VIOLATION",
                message=str(exc),
            )
        )
    if isinstance(candidate, MaterialEffectFailure):
        return MaterialMovementApplicationResult(failure=candidate)
    transfer = commit_material_movement(candidate, source=source, target=target)
    return MaterialMovementApplicationResult(
        transfer=transfer,
        transition=candidate.transition,
    )
