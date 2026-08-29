"""Primary Runtime boundary for material separation decisions and application."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from culsma.pipeline.program_registry import get_separation_slot_contract
from culsma.scientific_model import ProviderProvenance
from culsma.runtime.material.ledger import refresh_container_aggregates, set_container_material
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
    ScientificModelPartitionAdapter,
)
from culsma.runtime.material.separation_fate import (
    ExplicitContentFate,
    SeparationOperationContract,
    resolve_content_physical_state,
    resolve_separation_operation_contract,
)


SCIENTIFIC_MODEL_SEPARATION_PROGRAMS = frozenset(
    {
        "centrifuge_program",
        "filtration_program",
        "centrifugal_filtration_program",
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
    components_by_part: dict[str, dict[str, float]]
    quantities_by_part: dict[str, dict[str, dict[str, Any]]]
    classes_by_part: dict[str, dict[str, str]]


@dataclass(frozen=True)
class SeparationApplicationResult:
    record: dict[str, Any]
    effect: ResolvedMaterialEffect | None = None
    failure: MaterialEffectFailure | None = None


def project_resolved_material_effect(
    effect: ResolvedMaterialEffect,
    *,
    source_quantities: dict[str, Any],
    source_classes: dict[str, str],
) -> MaterialSeparationCandidate:
    """Project one resolved effect without mutating Runtime material state."""

    components_by_part = {output.part_id: {} for output in effect.outputs}
    quantities_by_part = {output.part_id: {} for output in effect.outputs}
    classes_by_part = {output.part_id: {} for output in effect.outputs}
    for component in effect.component_effects:
        source_quantity = source_quantities.get(component.source_component_id)
        source_class = source_classes.get(component.source_component_id)
        for output in component.outputs:
            output_components = components_by_part[output.part_id]
            output_components[component.source_component_id] = (
                output_components.get(component.source_component_id, 0.0)
                + component.source_amount * output.fraction
            )
            if isinstance(source_quantity, dict):
                projected_quantity = dict(source_quantity)
                projected_quantity["value"] = (
                    float(source_quantity.get("value", component.source_amount))
                    * output.fraction
                )
                quantities_by_part[output.part_id][
                    component.source_component_id
                ] = projected_quantity
            if source_class is not None:
                classes_by_part[output.part_id][
                    component.source_component_id
                ] = source_class
    return MaterialSeparationCandidate(
        effect=effect,
        components_by_part=components_by_part,
        quantities_by_part=quantities_by_part,
        classes_by_part=classes_by_part,
    )


def commit_separation_candidate(
    candidate: MaterialSeparationCandidate,
    *,
    source: dict[str, Any],
    outputs_by_part: dict[str, dict[str, Any]],
) -> dict[str, str]:
    """Commit an already-resolved separation candidate to Runtime containers."""

    expected_parts = {output.part_id for output in candidate.effect.outputs}
    if set(outputs_by_part) != expected_parts:
        raise ValueError(
            "Separation output containers do not match the resolved effect contract"
        )
    for part_id, output_container in outputs_by_part.items():
        set_container_material(
            output_container,
            components=candidate.components_by_part[part_id],
            component_classes=candidate.classes_by_part[part_id],
            component_quantities=candidate.quantities_by_part[part_id],
        )
    refresh_container_aggregates(outputs_by_part["0"])
    refresh_container_aggregates(outputs_by_part["1"])
    if all(source is not output for output in outputs_by_part.values()):
        set_container_material(source, components={}, component_quantities={})
    return {"volume": "detail_ledger_projection", "mass": "detail_ledger_projection"}


def provider_provenance_record(
    provenance: ProviderProvenance | None,
) -> dict[str, Any] | None:
    if provenance is None:
        return None
    return {
        "provider_id": provenance.provider_id,
        "provider_version": provenance.provider_version,
        "model_id": provenance.model_id,
        "model_version": provenance.model_version,
        "configuration": dict(provenance.configuration),
    }


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
        ratios_by_component[component.source_component_id] = ratios
        fates_by_component[component.source_component_id] = (
            resolved_component_fate_record(component)
        )
        transitions_by_component[component.source_component_id] = (
            resolved_component_transition_records(component)
        )
        class_name = source_classes.get(component.source_component_id)
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
    material_effect_adapter: ScientificModelPartitionAdapter | None = None,
    request_id: str = "material-separation",
    source_id: str | None = None,
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
    source_components = source.setdefault("components", {})
    source_quantities = source.get("component_quantities")
    source_quantities = (
        source_quantities if isinstance(source_quantities, dict) else {}
    )
    if not isinstance(source_components, dict):
        source_components = {}
    author_fates = explicit_fates or {}
    components: dict[str, RuntimePartitionComponent] = {}
    for name, amount in list(source_components.items()):
        component_id = str(name)
        explicit_fate = author_fates.get(component_id)
        if explicit_fate is None:
            legacy_ratios = component_partition_ratios(source, component_id)
            if legacy_ratios is not None:
                explicit_fate = ExplicitContentFate(
                    component_id=component_id,
                    ratios=legacy_ratios,
                    declared_slots=("0", "1"),
                    source="source_metadata_override",
                )
        components[component_id] = RuntimePartitionComponent(
            component_id=component_id,
            amount=float(amount),
            explicit_fate=explicit_fate,
            physical_state=resolve_content_physical_state(
                state, source, component_id
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
    )
    if isinstance(resolution, MaterialEffectFailure):
        return SeparationApplicationResult(
            record=unresolved_separation_record(
                program_kind, slot_contract, operation_contract, resolution
            ),
            failure=resolution,
        )
    candidate = project_resolved_material_effect(
        resolution,
        source_quantities=source_quantities,
        source_classes=source_component_classes(source),
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
            component.source_component_id: component
            for component in effect.component_effects
        }
        if effect is not None
        else {}
    )
    states: set[str] = set()
    for component_id, quantity in quantities.items():
        if not isinstance(quantity, dict) or quantity.get("dimension") != "count":
            continue
        if abs(float(quantity.get("value", 0.0))) <= 1e-12:
            continue
        component_effect = effects_by_component.get(component_id)
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
        fate = fates.get(component_id) if isinstance(fates, dict) else None
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
