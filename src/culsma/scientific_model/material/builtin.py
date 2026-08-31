"""Official built-in material Rulebook provider."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..contracts import (
    CapabilityDescriptor,
    ModelDiagnostic,
    ModelRequest,
    ModelResult,
    ProviderDescriptor,
    ProviderProvenance,
)
from .contracts import (
    MATERIAL_CONTRACT_VERSION,
    MATERIAL_SEPARATION_FATE,
    MATERIAL_STATE_TRANSITION,
    AssociationTarget,
    AssociationTargetKind,
    ComponentFate,
    MaterialModelPayload,
    RelationshipTransition,
    SeparationDecision,
    StateTransitionDecision,
)
from .classification import classify_component
from .rulebook import resolve_relationship_transition_rule, resolve_separation_fate_rule


BUILTIN_MATERIAL_RULEBOOK_PROVIDER_ID = "culsma.builtin.material_rulebook"

@dataclass(frozen=True)
class BuiltinMaterialRulebookProvider:
    provider_version: str = "1.0"

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=BUILTIN_MATERIAL_RULEBOOK_PROVIDER_ID,
            provider_version=self.provider_version,
            capabilities=(
                CapabilityDescriptor(
                    capability=MATERIAL_SEPARATION_FATE,
                    contract_version=MATERIAL_CONTRACT_VERSION,
                ),
                CapabilityDescriptor(
                    capability=MATERIAL_STATE_TRANSITION,
                    contract_version=MATERIAL_CONTRACT_VERSION,
                ),
            ),
        )

    def resolve(self, request: ModelRequest) -> ModelResult:
        provenance = ProviderProvenance.from_descriptor(self.descriptor)
        if not self.descriptor.supports(request.capability, request.contract_version):
            return ModelResult.not_applicable(
                provenance=provenance,
                diagnostics=(
                    ModelDiagnostic(
                        code="MATERIAL_RULEBOOK_CAPABILITY_NOT_APPLICABLE",
                        message=(
                            f"built-in material Rulebook does not support capability "
                            f"'{request.capability}' version '{request.contract_version}'"
                        ),
                        severity="warning",
                    ),
                ),
            )
        if not isinstance(request.payload, MaterialModelPayload):
            return self.unresolved(
                provenance,
                "built-in material Rulebook requires MaterialModelPayload",
            )
        if request.capability == MATERIAL_SEPARATION_FATE:
            return self.resolve_separation_fate(request.payload, provenance)
        if request.capability == MATERIAL_STATE_TRANSITION:
            return self.resolve_state_transition(request.payload, provenance)
        return self.unresolved(provenance, "material Rulebook capability is unresolved")

    def resolve_separation_fate(
        self,
        payload: MaterialModelPayload,
        provenance: ProviderProvenance,
    ) -> ModelResult:
        ordered_outputs = tuple(payload.operation.output_roles)
        if len(ordered_outputs) != 2:
            return self.unresolved(
                provenance,
                "Table 2 requires exactly two ordered outputs",
            )

        fates: list[ComponentFate] = []
        for component in payload.components:
            classification = classify_component(component)
            fate = resolve_separation_fate_rule(
                program_kind=payload.operation.program_kind,
                group=classification.group,
                current_relation=component.relationship.relation,
                filter_retains=context_predicate(
                    payload.context, "filter_retains", component.entry_id
                ),
                is_magnetic_support=context_predicate(
                    payload.context, "is_magnetic_support", component.entry_id
                ),
                surface_preserved=context_predicate(
                    payload.context, "surface_preserved", component.entry_id
                ),
            )
            if fate is None:
                return self.unresolved(
                    provenance,
                    (
                        f"Table 2 cannot resolve component '{component.entry_id}' for "
                        f"program '{payload.operation.program_kind}', group "
                        f"'{classification.group.value}', relation "
                        f"'{component.relationship.relation}'"
                    ),
                )
            fates.append(
                ComponentFate(
                    component_entry_id=component.entry_id,
                    fractions={
                        ordered_outputs[0].part_id: fate.ordered_fractions[0],
                        ordered_outputs[1].part_id: fate.ordered_fractions[1],
                    },
                )
            )

        decision = SeparationDecision(
            component_fates=tuple(fates),
            decision_source="provider",
            provenance=provenance,
        )
        return ModelResult.resolved(proposal=decision, provenance=provenance)

    def resolve_state_transition(
        self,
        payload: MaterialModelPayload,
        provenance: ProviderProvenance,
    ) -> ModelResult:
        if len(payload.operation.output_roles) != 1:
            return self.unresolved(
                provenance,
                "Table 3 requires exactly one selected output role per request",
            )
        output_role = payload.operation.output_roles[0].semantic_role
        raw_release_declared = payload.context.get("release_declared", False)
        if not isinstance(raw_release_declared, bool):
            return self.unresolved(
                provenance,
                "Table 3 context field 'release_declared' must be boolean",
            )

        transitions: list[RelationshipTransition] = []
        for component in payload.components:
            classification = classify_component(component)
            transition = resolve_relationship_transition_rule(
                group=classification.group,
                current_relation=component.relationship.relation,
                effect_kind=payload.operation.effect_kind,
                output_role=output_role,
                declared=context_predicate(payload.context, "declared", component.entry_id),
                cross_container=context_predicate(
                    payload.context, "cross_container", component.entry_id
                ),
                release_declared=raw_release_declared,
                disruption_target=context_predicate(
                    payload.context, "disruption_target", component.entry_id
                ),
                target_remains_identifiable=context_predicate(
                    payload.context, "target_remains_identifiable", component.entry_id
                ),
                precipitation_established=context_predicate(
                    payload.context, "precipitation_established", component.entry_id
                ),
                binding_established=context_predicate(
                    payload.context, "binding_established", component.entry_id
                ),
                field_retention_established=context_predicate(
                    payload.context, "field_retention_established", component.entry_id
                ),
                binding_preserved=context_predicate(
                    payload.context, "binding_preserved", component.entry_id
                ),
                membrane_preserved=context_predicate(
                    payload.context, "membrane_preserved", component.entry_id
                ),
                cell_integrity_preserved=context_predicate(
                    payload.context, "cell_integrity_preserved", component.entry_id
                ),
                field_preserved=context_predicate(
                    payload.context, "field_preserved", component.entry_id
                ),
                surface_preserved=context_predicate(
                    payload.context, "surface_preserved", component.entry_id
                ),
                label_has_persistent_relation=context_predicate(
                    payload.context,
                    "label_has_persistent_relation",
                    component.entry_id,
                    default=True,
                ),
                quantity_is_intact_cell_count=component.quantity.unit == "cells",
            )
            if transition is None:
                return self.unresolved(
                    provenance,
                    (
                        f"Table 3 cannot resolve component '{component.entry_id}' for "
                        f"effect '{payload.operation.effect_kind}', output '{output_role}', "
                        f"group '{classification.group.value}', relation "
                        f"'{component.relationship.relation}'"
                    ),
                )
            next_association_target = resolve_transition_association_target(
                payload.context,
                component,
                transition.next_relation.value,
                output_part_id=payload.operation.output_roles[0].part_id,
            )
            if (
                transition.next_relation.value != "free"
                and next_association_target is None
            ):
                return self.unresolved(
                    provenance,
                    (
                        f"Table 3 did not receive an association target for component "
                        f"'{component.entry_id}' next relation "
                        f"'{transition.next_relation.value}'"
                    ),
                )
            transitions.append(
                RelationshipTransition(
                    component_entry_id=component.entry_id,
                    next_relation=transition.next_relation.value,
                    next_label=transition.next_label,
                    next_association_target=next_association_target,
                    retire_quantity=transition.retire_quantity,
                )
            )

        decision = StateTransitionDecision(
            transitions=tuple(transitions),
            decision_source="provider",
            provenance=provenance,
        )
        return ModelResult.resolved(proposal=decision, provenance=provenance)

    def unresolved(
        self,
        provenance: ProviderProvenance,
        message: str,
    ) -> ModelResult:
        return ModelResult.not_applicable(
            provenance=provenance,
            diagnostics=(
                ModelDiagnostic(
                    code="MATERIAL_RULEBOOK_UNRESOLVED",
                    message=message,
                    severity="warning",
                ),
            ),
        )


def context_predicate(
    context: Mapping[str, object],
    name: str,
    component_entry_id: str,
    *,
    default: bool = False,
) -> bool:
    value = context.get(name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        component_value = value.get(component_entry_id, default)
        return component_value if isinstance(component_value, bool) else default
    return default


def context_association_target(
    context: Mapping[str, object],
    component_entry_id: str,
) -> AssociationTarget | None:
    value = context.get("association_target")
    if (
        isinstance(value, Mapping)
        and not {"kind", "id"}.issubset(value)
    ):
        value = value.get(component_entry_id)
    if isinstance(value, AssociationTarget):
        return value
    if not isinstance(value, Mapping):
        return None
    raw_kind = value.get("kind")
    raw_id = value.get("id")
    try:
        kind = AssociationTargetKind(str(raw_kind))
    except ValueError:
        return None
    if not isinstance(raw_id, str) or not raw_id:
        return None
    return AssociationTarget(kind=kind, id=raw_id)


def resolve_transition_association_target(
    context: Mapping[str, object],
    component: ComponentSnapshot,
    next_relation: str,
    *,
    output_part_id: str | None = None,
) -> AssociationTarget | None:
    if next_relation == "free":
        return None
    contextual = context_association_target(context, component.entry_id)
    if contextual is not None:
        return contextual
    current = component.relationship.association_target
    if current is not None and component.relationship.relation == next_relation:
        return current
    associated_with = component.relationship.associated_with
    if not isinstance(associated_with, str) or not associated_with:
        if (
            next_relation not in {"bead_bound", "membrane_bound", "cell_bound"}
            and isinstance(output_part_id, str)
            and output_part_id
        ):
            return AssociationTarget(
                kind=AssociationTargetKind.CONTAINER,
                id=output_part_id,
            )
        return None
    target_kind = (
        AssociationTargetKind.COMPONENT_ENTRY
        if next_relation in {"bead_bound", "membrane_bound", "cell_bound"}
        else AssociationTargetKind.CONTAINER
    )
    return AssociationTarget(kind=target_kind, id=associated_with)
