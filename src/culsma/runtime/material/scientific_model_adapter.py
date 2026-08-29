"""Public Runtime adapter for scientific-model separation decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from culsma.scientific_model import ModelRequest, ProviderProvenance
from culsma.scientific_model.material import (
    MATERIAL_CONTRACT_VERSION,
    MATERIAL_SEPARATION_FATE,
    MATERIAL_STATE_TRANSITION,
    ComponentSnapshot,
    CoordinationStatus,
    MaterialModelPayload,
    OperationSnapshot,
    OutputRoleSnapshot,
    QuantitySnapshot,
    RelationshipSnapshot,
    SepEffectCoordinator,
    SeparationDecision,
    StateTransitionDecision,
)

from .separation_fate import (
    ContentPhysicalState,
    ExplicitContentFate,
    SeparationOperationContract,
)


@dataclass(frozen=True)
class RuntimePartitionComponent:
    component_id: str
    amount: float
    explicit_fate: ExplicitContentFate | None
    physical_state: ContentPhysicalState


@dataclass(frozen=True)
class MaterialEffectFailure:
    code: str
    message: str


@dataclass(frozen=True)
class ResolvedOutput:
    part_id: str
    semantic_role: str


@dataclass(frozen=True)
class ResolvedComponentOutput:
    part_id: str
    semantic_role: str
    fraction: float
    next_relation: str | None
    next_label: str | None
    retire_quantity: bool
    replacement_quantity: QuantitySnapshot | None
    decision_source: str
    fate_provenance: ProviderProvenance | None
    transition_provenance: ProviderProvenance | None


@dataclass(frozen=True)
class ResolvedComponentEffect:
    source_component_id: str
    source_amount: float
    source_relation: str
    source_accessibility: str
    source_preservation: str
    outputs: tuple[ResolvedComponentOutput, ...]


@dataclass(frozen=True)
class ResolvedMaterialEffect:
    operation_id: str
    program_kind: str
    outputs: tuple[ResolvedOutput, ...]
    component_effects: tuple[ResolvedComponentEffect, ...]


class ScientificModelPartitionAdapter:
    """Translate Runtime material records to and from the public model port."""

    def __init__(self, coordinator: SepEffectCoordinator) -> None:
        self.coordinator = coordinator

    def resolve(
        self,
        *,
        state: dict[str, Any],
        source: dict[str, Any],
        source_quantities: dict[str, Any],
        components: dict[str, RuntimePartitionComponent],
        operation_contract: SeparationOperationContract,
        request_id: str,
        source_id: str | None,
    ) -> ResolvedMaterialEffect | MaterialEffectFailure:
        output_roles = tuple(
            OutputRoleSnapshot(part_id=slot, semantic_role=role)
            for slot, role in operation_contract.slot_contract.items()
        )
        resolved_outputs = tuple(
            ResolvedOutput(
                part_id=output.part_id,
                semantic_role=output.semantic_role,
            )
            for output in output_roles
        )
        provider_components = tuple(
            self.build_component_snapshot(
                state=state,
                source=source,
                source_quantities=source_quantities,
                component=component,
                source_id=source_id,
            )
            for component in components.values()
            if component.explicit_fate is None
        )
        fractions_by_component = {
            component.component_id: component.explicit_fate.ratios
            for component in components.values()
            if component.explicit_fate is not None
        }
        fate_source_by_component = {
            component.component_id: component.explicit_fate.source
            for component in components.values()
            if component.explicit_fate is not None
        }
        fate_provenance_by_component: dict[str, ProviderProvenance | None] = {
            component.component_id: None
            for component in components.values()
            if component.explicit_fate is not None
        }

        if provider_components:
            fate_request = ModelRequest(
                request_id=f"{request_id}:separation_fate",
                capability=MATERIAL_SEPARATION_FATE,
                contract_version=MATERIAL_CONTRACT_VERSION,
                payload=MaterialModelPayload(
                    operation=OperationSnapshot(
                        program_kind=operation_contract.program_kind,
                        effect_kind="separation_fate",
                        output_roles=output_roles,
                        program_args=operation_contract.program_args,
                    ),
                    components=provider_components,
                    context={
                        "filter_retains": {
                            component.entry_id: self.component_context_flag(
                                state,
                                component.content_ref,
                                "filter_retains",
                            )
                            for component in provider_components
                        },
                        "is_magnetic_support": {
                            component.entry_id: self.is_magnetic_support(
                                state,
                                component.content_ref,
                            )
                            for component in provider_components
                        },
                    },
                ),
            )
            coordinated = self.coordinator.resolve(fate_request)
            failure = self.coordination_failure(
                coordinated,
                capability=MATERIAL_SEPARATION_FATE,
            )
            if failure is not None:
                return failure
            decision = coordinated.decision
            if not isinstance(decision, SeparationDecision):
                return MaterialEffectFailure(
                    "MAT_SCIENTIFIC_MODEL_REJECTED",
                    "Separation capability did not return SeparationDecision",
                )
            for component_fate in decision.component_fates:
                fractions = component_fate.fractions
                ratio0 = float(fractions[output_roles[0].part_id])
                ratio1 = float(fractions[output_roles[1].part_id])
                component_id = component_fate.component_entry_id
                fractions_by_component[component_id] = (ratio0, ratio1)
                fate_source_by_component[component_id] = "scientific_model_provider"
                fate_provenance_by_component[component_id] = decision.provenance

        resolved_component_effects: list[ResolvedComponentEffect] = []
        for component in components.values():
            component_fractions = fractions_by_component.get(component.component_id)
            if component_fractions is None:
                return MaterialEffectFailure(
                    "MAT_SCIENTIFIC_MODEL_REJECTED",
                    f"No separation fate was produced for component '{component.component_id}'",
                )
            base_snapshot = self.build_component_snapshot(
                state=state,
                source=source,
                source_quantities=source_quantities,
                component=component,
                source_id=source_id,
            )
            resolved_component_outputs: list[ResolvedComponentOutput] = []
            for slot_index, fraction in enumerate(component_fractions):
                output = output_roles[slot_index]
                if fraction <= 0.0:
                    resolved_component_outputs.append(
                        ResolvedComponentOutput(
                            part_id=output.part_id,
                            semantic_role=output.semantic_role,
                            fraction=fraction,
                            next_relation=None,
                            next_label=None,
                            retire_quantity=False,
                            replacement_quantity=None,
                            decision_source=fate_source_by_component[component.component_id],
                            fate_provenance=fate_provenance_by_component[component.component_id],
                            transition_provenance=None,
                        )
                    )
                    continue
                projected_snapshot = ComponentSnapshot(
                    entry_id=f"{component.component_id}@{output.part_id}",
                    content_ref=base_snapshot.content_ref,
                    canonical_kind=base_snapshot.canonical_kind,
                    canonical_type=base_snapshot.canonical_type,
                    quantity=QuantitySnapshot(
                        value=base_snapshot.quantity.value * fraction,
                        unit=base_snapshot.quantity.unit,
                    ),
                    relationship=base_snapshot.relationship,
                )
                transition_request = ModelRequest(
                    request_id=(
                        f"{request_id}:state_transition:"
                        f"{component.component_id}:{output.part_id}"
                    ),
                    capability=MATERIAL_STATE_TRANSITION,
                    contract_version=MATERIAL_CONTRACT_VERSION,
                    payload=MaterialModelPayload(
                        operation=OperationSnapshot(
                            program_kind=operation_contract.program_kind,
                            effect_kind="separate",
                            output_roles=(output,),
                            program_args=operation_contract.program_args,
                        ),
                        components=(projected_snapshot,),
                        context=self.build_transition_context(
                            state=state,
                            component=component,
                            program_kind=operation_contract.program_kind,
                            output_role=output.semantic_role,
                            current_relation=base_snapshot.relationship.relation,
                        ),
                    ),
                )
                coordinated = self.coordinator.resolve(transition_request)
                failure = self.coordination_failure(
                    coordinated,
                    capability=MATERIAL_STATE_TRANSITION,
                )
                if failure is not None:
                    return failure
                decision = coordinated.decision
                if not isinstance(decision, StateTransitionDecision):
                    return MaterialEffectFailure(
                        "MAT_SCIENTIFIC_MODEL_REJECTED",
                        "State-transition capability did not return StateTransitionDecision",
                    )
                transition = decision.transitions[0]
                resolved_component_outputs.append(
                    ResolvedComponentOutput(
                        part_id=output.part_id,
                        semantic_role=output.semantic_role,
                        fraction=fraction,
                        next_relation=transition.next_relation,
                        next_label=transition.next_label,
                        retire_quantity=transition.retire_quantity,
                        replacement_quantity=transition.replacement_quantity,
                        decision_source=fate_source_by_component[component.component_id],
                        fate_provenance=fate_provenance_by_component[component.component_id],
                        transition_provenance=decision.provenance,
                    )
                )
            resolved_component_effects.append(
                ResolvedComponentEffect(
                    source_component_id=component.component_id,
                    source_amount=component.amount,
                    source_relation=base_snapshot.relationship.relation,
                    source_accessibility=(
                        "accessible"
                        if base_snapshot.relationship.relation == "free"
                        else "immobilized"
                    ),
                    source_preservation=(
                        base_snapshot.relationship.preservation or "unspecified"
                    ),
                    outputs=tuple(resolved_component_outputs),
                )
            )
        return ResolvedMaterialEffect(
            operation_id=request_id,
            program_kind=operation_contract.program_kind,
            outputs=resolved_outputs,
            component_effects=tuple(resolved_component_effects),
        )

    def build_component_snapshot(
        self,
        *,
        state: dict[str, Any],
        source: dict[str, Any],
        source_quantities: dict[str, Any],
        component: RuntimePartitionComponent,
        source_id: str | None,
    ) -> ComponentSnapshot:
        registry = state.get("content_registry")
        content = (
            registry.get(component.component_id) if isinstance(registry, dict) else None
        )
        content = content if isinstance(content, dict) else {}
        quantity = source_quantities.get(component.component_id)
        quantity = quantity if isinstance(quantity, dict) else {}
        relation = self.canonical_relation(component.physical_state.association)
        if relation == "unspecified":
            source_metadata = source.get("metadata")
            legacy_classes = (
                source_metadata.get("component_partition_classes")
                if isinstance(source_metadata, dict)
                else None
            )
            legacy_class = (
                legacy_classes.get(component.component_id)
                if isinstance(legacy_classes, dict)
                else None
            )
            relation = "pellet" if legacy_class == "retained_fraction" else "free"
        return ComponentSnapshot(
            entry_id=component.component_id,
            content_ref=component.component_id,
            canonical_kind=str(content.get("content_kind", "")),
            canonical_type=str(content.get("content_type", "")),
            quantity=QuantitySnapshot(
                value=float(quantity.get("value", component.amount)),
                unit=str(quantity.get("unit", "component_amount")),
            ),
            relationship=RelationshipSnapshot(
                relation=relation,
                associated_with=(source_id if relation != "free" else None),
                preservation=component.physical_state.preservation_state,
            ),
        )

    def build_transition_context(
        self,
        *,
        state: dict[str, Any],
        component: RuntimePartitionComponent,
        program_kind: str,
        output_role: str,
        current_relation: str,
    ) -> dict[str, bool]:
        authored_fate = component.explicit_fate is not None
        magnetic_support = self.is_magnetic_support(state, component.component_id)
        return {
            "release_declared": False,
            "precipitation_established": (
                authored_fate and output_role == "precipitate"
            ),
            "binding_established": authored_fate and output_role == "bound",
            "field_retention_established": (
                program_kind == "magnetic_program"
                and output_role == "bound"
                and magnetic_support
            ),
            "binding_preserved": current_relation == "bead_bound",
            "membrane_preserved": (
                current_relation == "membrane_bound" and output_role == "retentate"
            ),
            "cell_integrity_preserved": current_relation == "cell_bound",
            "field_preserved": (
                current_relation == "field_retained" and output_role == "bound"
            ),
        }

    def coordination_failure(
        self,
        coordinated: Any,
        *,
        capability: str,
    ) -> MaterialEffectFailure | None:
        if coordinated.status is CoordinationStatus.RESOLVED:
            return None
        code_by_status = {
            CoordinationStatus.UNRESOLVED: "MAT_SCIENTIFIC_MODEL_UNRESOLVED",
            CoordinationStatus.FAILED: "MAT_SCIENTIFIC_MODEL_FAILED",
            CoordinationStatus.REJECTED: "MAT_SCIENTIFIC_MODEL_REJECTED",
        }
        details: list[str] = []
        if coordinated.model_result is not None:
            details.extend(
                diagnostic.message
                for diagnostic in coordinated.model_result.diagnostics
            )
        details.extend(issue.message for issue in coordinated.validation_issues)
        suffix = f": {'; '.join(details)}" if details else ""
        return MaterialEffectFailure(
            code_by_status.get(
                coordinated.status,
                "MAT_SCIENTIFIC_MODEL_REJECTED",
            ),
            f"Scientific capability '{capability}' was not resolved{suffix}",
        )

    def canonical_relation(self, relation: str) -> str:
        return {
            "bead": "bead_bound",
            "membrane": "membrane_bound",
            "cell": "cell_bound",
        }.get(relation, relation)

    def is_magnetic_support(self, state: dict[str, Any], component_id: str) -> bool:
        return self.component_context_flag(
            state,
            component_id,
            "is_magnetic_support",
        ) or self.component_context_value(
            state,
            component_id,
            "bead_property",
        ) == "magnetic"

    def component_context_flag(
        self,
        state: dict[str, Any],
        component_id: str,
        name: str,
    ) -> bool:
        return self.component_context_value(state, component_id, name) is True

    def component_context_value(
        self,
        state: dict[str, Any],
        component_id: str,
        name: str,
    ) -> Any:
        registry = state.get("content_registry")
        content = registry.get(component_id) if isinstance(registry, dict) else None
        attrs = content.get("content_attrs") if isinstance(content, dict) else None
        return attrs.get(name) if isinstance(attrs, dict) else None
