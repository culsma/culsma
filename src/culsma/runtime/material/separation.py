"""Primary Runtime boundary for material separation decisions and application."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from culsma.pipeline.program_registry import get_separation_slot_contract
from culsma.scientific_model.material import AssociationTarget, AssociationTargetKind
from culsma.runtime.material.component_entries import (
    ComponentEntryRelationError,
    container_component_entries,
    merge_transferred_entries,
    normalize_component_entries,
    replace_component_entries,
    validate_component_entry_set,
)
from culsma.runtime.material.ledger import refresh_container_aggregates
from culsma.runtime.material.partition import (
    apply_legacy_partition_material,
    component_partition_ratios,
    legacy_separation_cell_material_state,
)
from culsma.runtime.material.scientific_model_adapter import (
    MaterialEffectFailure,
    ResolvedComponentEffect,
    ResolvedMaterialEffect,
    RuntimePartitionComponent,
    ScientificModelMaterialAdapter,
    provider_provenance_record,
)
from culsma.runtime.material.separation_fate import (
    ContentPhysicalState,
    ExplicitContentFate,
    SeparationOperationContract,
    resolve_separation_operation_contract,
)


SCIENTIFIC_MODEL_SEPARATION_PROGRAMS = frozenset(
    {
        "sep_program",
        "centrifuge_program",
        "filtration_program",
        "centrifugal_filtration_program",
        "precipitation_program",
        "magnetic_program",
        "phase_partition_program",
        "field_program",
        "disrupt_program",
    }
)

CELL_MATERIAL_STATE_BY_RELATION = {
    "free": "suspension",
    "container_surface": "adherent",
    "pellet": "pellet",
    "precipitate": "precipitate",
    "bead_bound": "retained",
    "membrane_bound": "retained",
    "cell_bound": "retained",
    "field_retained": "retained",
    "disrupted": "lysate",
}


@dataclass(frozen=True)
class MaterialSeparationCandidate:
    effect: ResolvedMaterialEffect
    entries_by_part: dict[str, list[dict[str, Any]]]
    components_by_part: dict[str, dict[str, float]]
    quantities_by_part: dict[str, dict[str, dict[str, Any]]]
    classes_by_part: dict[str, dict[str, str]]
    retired_quantities: dict[str, dict[str, Any]]


@dataclass(frozen=True)
class SeparationApplicationResult:
    record: dict[str, Any]
    effect: ResolvedMaterialEffect | None = None
    failure: MaterialEffectFailure | None = None


@dataclass(frozen=True)
class MaterialCandidateValidationError(ValueError):
    reason: str

    def __str__(self) -> str:
        return self.reason


def validate_separation_candidate(candidate: MaterialSeparationCandidate) -> None:
    """Enforce the Stage 3 contract before any Runtime material commit."""

    expected_parts = {output.part_id for output in candidate.effect.outputs}
    if set(candidate.entries_by_part) != expected_parts:
        raise MaterialCandidateValidationError(
            "Candidate parts do not match the resolved output contract"
        )
    for part_id, entries in candidate.entries_by_part.items():
        try:
            validate_component_entry_set(
                entries,
                owner=f"Candidate part '{part_id}'",
            )
        except (ComponentEntryRelationError, ValueError) as exc:
            raise MaterialCandidateValidationError(str(exc)) from exc


def project_resolved_material_effect(
    effect: ResolvedMaterialEffect,
    *,
    source_quantities: dict[str, Any],
    source_classes: dict[str, str],
    source_entries: list[dict[str, Any]] | None = None,
    output_ids_by_part: dict[str, str] | None = None,
) -> MaterialSeparationCandidate:
    """Project one resolved effect without mutating Runtime material state."""

    entries_by_part = {output.part_id: [] for output in effect.outputs}
    retired_quantities: dict[str, dict[str, Any]] = {}
    entries_by_id = {
        str(entry.get("entry_id")): entry
        for entry in (source_entries or [])
        if isinstance(entry, dict) and isinstance(entry.get("entry_id"), str)
    }
    for component in effect.component_effects:
        source_entry = entries_by_id.get(component.source_entry_id, {})
        content_ref = component.source_content_ref or str(
            source_entry.get("content_ref", component.source_entry_id)
        )
        source_quantity = source_entry.get("quantity")
        if not isinstance(source_quantity, dict):
            source_quantity = source_quantities.get(content_ref)
        source_class = source_entry.get("partition_class")
        if not isinstance(source_class, str):
            source_class = source_classes.get(content_ref)
        for output in component.outputs:
            if output.retire_quantity:
                retired = retired_quantities.setdefault(
                    component.source_entry_id,
                    {
                        "component_amount": 0.0,
                        "dimension": (
                            source_quantity.get("dimension")
                            if isinstance(source_quantity, dict)
                            else None
                        ),
                        "unit": (
                            source_quantity.get("unit")
                            if isinstance(source_quantity, dict)
                            else None
                        ),
                        "value": 0.0,
                    },
                )
                retired["component_amount"] = float(
                    retired["component_amount"]
                ) + component.source_amount * output.fraction
                if isinstance(source_quantity, dict):
                    retired["value"] = float(retired["value"]) + float(
                        source_quantity.get("value", component.source_amount)
                    ) * output.fraction
                continue
            entries_by_part[output.part_id].append(
                resolved_output_component_entry(
                    component,
                    output,
                    content_ref=content_ref,
                    source_quantity=source_quantity,
                    source_class=source_class,
                    source_entry=source_entry,
                    output_id=(output_ids_by_part or {}).get(output.part_id),
                )
            )

    components_by_part: dict[str, dict[str, float]] = {}
    quantities_by_part: dict[str, dict[str, dict[str, Any]]] = {}
    classes_by_part: dict[str, dict[str, str]] = {}
    for part_id, entries in entries_by_part.items():
        compressed_entries: list[dict[str, Any]] = []
        merge_transferred_entries(compressed_entries, entries)
        entries_by_part[part_id] = compressed_entries
        projected: dict[str, Any] = {"metadata": {}}
        replace_component_entries(projected, compressed_entries)
        components_by_part[part_id] = dict(projected.get("components", {}))
        quantities_by_part[part_id] = dict(projected.get("component_quantities", {}))
        metadata = projected.get("metadata")
        classes = (
            metadata.get("component_partition_classes")
            if isinstance(metadata, dict)
            else None
        )
        classes_by_part[part_id] = dict(classes) if isinstance(classes, dict) else {}
    candidate = MaterialSeparationCandidate(
        effect=effect,
        entries_by_part=entries_by_part,
        components_by_part=components_by_part,
        quantities_by_part=quantities_by_part,
        classes_by_part=classes_by_part,
        retired_quantities=retired_quantities,
    )
    validate_separation_candidate(candidate)
    return candidate


def resolved_output_component_entry(
    component: ResolvedComponentEffect,
    output: Any,
    *,
    content_ref: str,
    source_quantity: Any,
    source_class: str | None,
    source_entry: dict[str, Any],
    output_id: str | None = None,
) -> dict[str, Any]:
    projected_quantity = None
    if isinstance(source_quantity, dict):
        projected_quantity = dict(source_quantity)
        projected_quantity["value"] = (
            float(source_quantity.get("value", component.source_amount))
            * output.fraction
        )
    provenance = provider_provenance_record(output.transition_provenance)
    next_relation = (
        "free"
        if output.next_relation is None and output.fraction <= 1e-12
        else output.next_relation or component.source_relation
    )
    association_target = output.next_association_target
    if (
        association_target is None
        and next_relation != "free"
        and next_relation not in {"bead_bound", "membrane_bound", "cell_bound"}
        and isinstance(output_id, str)
        and output_id
    ):
        association_target = AssociationTarget(
            kind=AssociationTargetKind.CONTAINER,
            id=output_id,
        )
    entry: dict[str, Any] = {
        "entry_id": component.source_entry_id,
        "content_ref": content_ref,
        "amount": component.source_amount * output.fraction,
        "quantity": projected_quantity,
        "relation": next_relation,
        "associated_with": (
            association_target.id
            if association_target is not None
            else None
        ),
        "association_target_kind": (
            association_target.kind.value
            if association_target is not None
            else None
        ),
        "preservation": source_entry.get("preservation") or component.source_preservation,
        "label": output.next_label,
        "relationship_source": "scientific_model",
        "material_state_source": "scientific_model_provider",
    }
    if source_class is not None:
        entry["partition_class"] = source_class
    if provenance is not None:
        entry["provenance"] = provenance
    return entry


def commit_separation_candidate(
    candidate: MaterialSeparationCandidate,
    *,
    source: dict[str, Any],
    outputs_by_part: dict[str, dict[str, Any]],
) -> dict[str, str]:
    """Commit an already-resolved separation candidate to Runtime containers."""

    validate_separation_candidate(candidate)
    expected_parts = {output.part_id for output in candidate.effect.outputs}
    if set(outputs_by_part) != expected_parts:
        raise ValueError(
            "Separation output containers do not match the resolved effect contract"
        )
    for part_id, output_container in outputs_by_part.items():
        replace_component_entries(output_container, candidate.entries_by_part[part_id])
    refresh_container_aggregates(outputs_by_part["0"])
    refresh_container_aggregates(outputs_by_part["1"])
    if all(source is not output for output in outputs_by_part.values()):
        replace_component_entries(source, [])
    return {"volume": "detail_ledger_projection", "mass": "detail_ledger_projection"}


def resolved_component_fate_record(
    component: ResolvedComponentEffect,
) -> dict[str, Any]:
    outputs = {output.part_id: output for output in component.outputs}
    first_output = component.outputs[0]
    return {
        "ratios": {
            "0": outputs["0"].fraction,
            "1": outputs["1"].fraction,
        },
        "source": first_output.decision_source,
        "association": component.source_relation,
        "accessibility": component.source_accessibility,
        "preservation_state": component.source_preservation,
        "provenance": provider_provenance_record(first_output.fate_provenance),
    }


def resolved_component_transition_records(
    component: ResolvedComponentEffect,
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for output in component.outputs:
        if output.next_relation is None:
            continue
        records[output.part_id] = {
            "next_relation": output.next_relation,
            "next_label": output.next_label,
            "next_association_target": (
                {
                    "kind": output.next_association_target.kind.value,
                    "id": output.next_association_target.id,
                }
                if output.next_association_target is not None
                else None
            ),
            "retire_quantity": output.retire_quantity,
            "replacement_quantity": (
                {
                    "value": output.replacement_quantity.value,
                    "unit": output.replacement_quantity.unit,
                }
                if output.replacement_quantity is not None
                else None
            ),
            "source": "scientific_model_provider",
            "provenance": provider_provenance_record(
                output.transition_provenance
            ),
        }
    return records


def source_component_classes(container: dict[str, Any]) -> dict[str, str]:
    metadata = container.get("metadata")
    classes = (
        metadata.get("component_partition_classes")
        if isinstance(metadata, dict)
        else None
    )
    if not isinstance(classes, dict):
        return {}
    return {
        str(component_id): value
        for component_id, value in classes.items()
        if isinstance(value, str)
    }


def resolved_effect_separation_record(
    candidate: MaterialSeparationCandidate,
    *,
    operation_contract: SeparationOperationContract,
    bulk_quantity_policy: dict[str, str],
) -> dict[str, Any]:
    ratios_by_component: dict[str, dict[str, float]] = {}
    fates_by_component: dict[str, dict[str, Any]] = {}
    transitions_by_component: dict[str, dict[str, dict[str, Any]]] = {}
    class_counts: dict[str, int] = {}
    ratios_by_class: dict[str, dict[str, float]] = {}
    source_classes = {
        component_id: class_name
        for classes in candidate.classes_by_part.values()
        for component_id, class_name in classes.items()
    }
    for component in candidate.effect.component_effects:
        outputs = {output.part_id: output for output in component.outputs}
        ratios = {"0": outputs["0"].fraction, "1": outputs["1"].fraction}
        ratios_by_component[component.source_entry_id] = ratios
        fates_by_component[component.source_entry_id] = (
            resolved_component_fate_record(component)
        )
        transitions_by_component[component.source_entry_id] = (
            resolved_component_transition_records(component)
        )
        class_name = source_classes.get(
            component.source_content_ref or component.source_entry_id
        )
        if class_name is not None:
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
            ratios_by_class[class_name] = ratios
    record = {
        "mode": "program_partition",
        "strategy": candidate.effect.program_kind,
        "slot_contract": {
            output.part_id: output.semantic_role
            for output in candidate.effect.outputs
        },
        "classes": class_counts,
        "ratios_by_class": ratios_by_class,
        "ratios_by_component": ratios_by_component,
        "fates_by_component": fates_by_component,
        "transitions_by_component": transitions_by_component,
        "retired_quantities": {
            component_id: dict(retired)
            for component_id, retired in candidate.retired_quantities.items()
        },
        "fallback_components": [],
        "bulk_quantity_policy": bulk_quantity_policy,
        "operation_contract": operation_contract.to_dict(),
    }
    if operation_contract.preservation_contract is not None:
        record["preservation_contract"] = dict(
            operation_contract.preservation_contract
        )
    return record


def apply_separation_material(
    *,
    state: dict[str, Any],
    source: dict[str, Any],
    slot0: dict[str, Any],
    slot1: dict[str, Any],
    program: dict[str, Any],
    explicit_fates: dict[str, ExplicitContentFate] | None = None,
    material_effect_adapter: ScientificModelMaterialAdapter | None = None,
    request_id: str = "material-separation",
    source_id: str | None = None,
    output_ids_by_part: dict[str, str] | None = None,
) -> SeparationApplicationResult:
    """Resolve and apply one separation through the primary Runtime boundary."""

    program_kind = (
        str(program.get("name"))
        if isinstance(program.get("name"), str)
        else "sep_program"
    )
    if program_kind not in SCIENTIFIC_MODEL_SEPARATION_PROGRAMS:
        return SeparationApplicationResult(
            record=apply_legacy_partition_material(
                state=state,
                source=source,
                slot0=slot0,
                slot1=slot1,
                program=program,
                explicit_fates=explicit_fates,
            )
        )

    slot_contract = separation_slot_contract(program_kind)
    operation_contract = resolve_separation_operation_contract(
        program,
        slot_contract=slot_contract,
    )
    source_quantities = source.get("component_quantities")
    source_quantities = (
        source_quantities if isinstance(source_quantities, dict) else {}
    )
    author_fates = explicit_fates or {}
    source_entries = normalize_component_entries(
        source,
        state=state,
        container_id=source_id,
    )
    components: dict[str, RuntimePartitionComponent] = {}
    for entry in source_entries:
        component_id = str(entry.get("entry_id"))
        content_ref = str(entry.get("content_ref"))
        amount = float(entry.get("amount", 0.0))
        explicit_fate = author_fates.get(content_ref)
        if explicit_fate is None:
            legacy_ratios = component_partition_ratios(source, content_ref)
            if legacy_ratios is not None:
                explicit_fate = ExplicitContentFate(
                    component_id=content_ref,
                    ratios=legacy_ratios,
                    declared_slots=("0", "1"),
                    source="source_metadata_override",
                )
        physical_state = ContentPhysicalState(
            association=str(entry.get("relation", "free")),
            accessibility=(
                "accessible"
                if entry.get("relation", "free") == "free"
                else "immobilized"
            ),
            preservation_state=str(entry.get("preservation") or "derived"),
            source="component_entry",
        )
        components[component_id] = RuntimePartitionComponent(
            component_id=component_id,
            amount=float(amount),
            explicit_fate=explicit_fate,
            physical_state=physical_state,
            content_ref=content_ref,
            quantity=(
                dict(entry["quantity"])
                if isinstance(entry.get("quantity"), dict)
                else None
            ),
            associated_with=(
                str(entry["associated_with"])
                if isinstance(entry.get("associated_with"), str)
                else None
            ),
            association_target_kind=(
                str(entry["association_target_kind"])
                if isinstance(entry.get("association_target_kind"), str)
                else None
            ),
            preservation=(
                str(entry["preservation"])
                if isinstance(entry.get("preservation"), str)
                else None
            ),
            label=(
                str(entry["label"])
                if isinstance(entry.get("label"), str)
                else None
            ),
        )

    if material_effect_adapter is None:
        failure = MaterialEffectFailure(
            code="MAT_SCIENTIFIC_MODEL_UNAVAILABLE",
            message="Runtime did not provide a scientific-model adapter",
        )
        return SeparationApplicationResult(
            record=unresolved_separation_record(
                program_kind, slot_contract, operation_contract, failure
            ),
            failure=failure,
        )

    resolution = material_effect_adapter.resolve(
        state=state,
        source=source,
        source_quantities=source_quantities,
        components=components,
        operation_contract=operation_contract,
        request_id=request_id,
        source_id=source_id,
        output_ids_by_part=output_ids_by_part,
    )
    if isinstance(resolution, MaterialEffectFailure):
        return SeparationApplicationResult(
            record=unresolved_separation_record(
                program_kind, slot_contract, operation_contract, resolution
            ),
            failure=resolution,
        )
    try:
        candidate = project_resolved_material_effect(
            resolution,
            source_quantities=source_quantities,
            source_classes=source_component_classes(source),
            source_entries=source_entries,
            output_ids_by_part=output_ids_by_part,
        )
    except MaterialCandidateValidationError as exc:
        failure = MaterialEffectFailure(
            code="MAT_STATE_INVARIANT_VIOLATION",
            message=str(exc),
        )
        return SeparationApplicationResult(
            record=unresolved_separation_record(
                program_kind, slot_contract, operation_contract, failure
            ),
            failure=failure,
        )
    bulk_quantity_policy = commit_separation_candidate(
        candidate,
        source=source,
        outputs_by_part={"0": slot0, "1": slot1},
    )
    return SeparationApplicationResult(
        record=resolved_effect_separation_record(
            candidate,
            operation_contract=operation_contract,
            bulk_quantity_policy=bulk_quantity_policy,
        ),
        effect=resolution,
    )


def unresolved_separation_record(
    program_kind: str,
    slot_contract: dict[str, str],
    operation_contract: SeparationOperationContract,
    failure: MaterialEffectFailure,
) -> dict[str, Any]:
    return {
        "mode": "scientific_model_unresolved",
        "strategy": program_kind,
        "slot_contract": dict(slot_contract),
        "scientific_model_error": {
            "code": failure.code,
            "message": failure.message,
        },
        "operation_contract": operation_contract.to_dict(),
    }


def separation_cell_material_state(
    program_kind: str,
    *,
    slot: str,
    partition: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    effect: ResolvedMaterialEffect | None = None,
) -> str:
    """Return the cellular material state for one separation output."""

    default_state = (
        "suspension"
        if effect is not None
        else legacy_separation_cell_material_state(program_kind, slot=slot)
    )
    if not isinstance(partition, dict) or not isinstance(output, dict):
        return default_state
    quantities = output.get("component_quantities")
    fates = partition.get("fates_by_component")
    if not isinstance(quantities, dict):
        return default_state
    if effect is None and not isinstance(fates, dict):
        return default_state
    effects_by_component = (
        {
            component.source_entry_id: component
            for component in effect.component_effects
        }
        if effect is not None
        else {}
    )
    states: set[str] = set()
    entry_rows = (
        [
            (
                str(entry.get("entry_id", "")),
                str(entry.get("content_ref", "")),
                entry.get("quantity"),
            )
            for entry in container_component_entries(output)
        ]
        if effect is not None
        else [(str(component_id), str(component_id), quantity) for component_id, quantity in quantities.items()]
    )
    for entry_id, content_ref, quantity in entry_rows:
        if not isinstance(quantity, dict) or quantity.get("dimension") != "count":
            continue
        if abs(float(quantity.get("value", 0.0))) <= 1e-12:
            continue
        component_effect = effects_by_component.get(entry_id)
        slot_effect = (
            next(
                (
                    component_output
                    for component_output in component_effect.outputs
                    if component_output.part_id == slot
                ),
                None,
            )
            if component_effect is not None
            else None
        )
        next_relation = slot_effect.next_relation if slot_effect is not None else None
        resolved_state = CELL_MATERIAL_STATE_BY_RELATION.get(next_relation)
        if resolved_state is not None:
            states.add(resolved_state)
            continue
        fate = fates.get(entry_id) if isinstance(fates, dict) else None
        if fate is None and isinstance(fates, dict):
            fate = fates.get(content_ref)
        if (
            isinstance(fate, dict)
            and fate.get("association") == "container_surface"
            and fate.get("retained_slot") == slot
        ):
            states.add("adherent")
        else:
            states.add(default_state)
    if len(states) == 1:
        return next(iter(states))
    if len(states) > 1:
        return "mixed"
    return default_state


def separation_slot_contract(program_kind: str) -> dict[str, str]:
    """Return semantic output names for one separation program."""

    return get_separation_slot_contract(program_kind) or {
        "0": "fraction_0",
        "1": "fraction_1",
    }
