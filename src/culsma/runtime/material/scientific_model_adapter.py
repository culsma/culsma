"""Public Runtime adapter for scientific-model material decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from culsma.scientific_model import ModelRequest, ProviderProvenance
from culsma.scientific_model.material import (
    MATERIAL_CONTRACT_VERSION,
    MATERIAL_SEPARATION_FATE,
    MATERIAL_STATE_TRANSITION,
    AssociationTarget,
    AssociationTargetKind,
    ComponentSnapshot,
    CoordinationStatus,
    MaterialEffectCoordinator,
    MaterialModelPayload,
    OperationSnapshot,
    OutputRoleSnapshot,
    QuantitySnapshot,
    RelationshipSnapshot,
    SeparationDecision,
    StateTransitionDecision,
)
from culsma.runtime.material.component_entries import ENTRY_EPSILON

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
    content_ref: str | None = None
    quantity: dict[str, Any] | None = None
    associated_with: str | None = None
    association_target_kind: str | None = None
    preservation: str | None = None
    label: str | None = None

    @property
    def entry_id(self) -> str:
        return self.component_id


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
    next_association_target: AssociationTarget | None = None


@dataclass(frozen=True)
class ResolvedComponentEffect:
    source_component_id: str
    source_amount: float
    source_relation: str
    source_accessibility: str
    source_preservation: str
    outputs: tuple[ResolvedComponentOutput, ...]
    source_content_ref: str | None = None

    @property
    def source_entry_id(self) -> str:
        return self.source_component_id


@dataclass(frozen=True)
class ResolvedMaterialEffect:
    operation_id: str
    program_kind: str
    outputs: tuple[ResolvedOutput, ...]
    component_effects: tuple[ResolvedComponentEffect, ...]


@dataclass(frozen=True)
class ResolvedComponentTransition:
    source_entry_id: str
    next_relation: str
    next_label: str | None
    provenance: ProviderProvenance | None
    next_association_target: AssociationTarget | None = None


@dataclass(frozen=True)
class ResolvedMaterialTransition:
    operation_id: str
    effect_kind: str
    component_transitions: tuple[ResolvedComponentTransition, ...]


class ScientificModelMaterialAdapter:
    """Translate Runtime material records to and from the public model port."""

    def __init__(self, coordinator: MaterialEffectCoordinator) -> None:
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
        output_ids_by_part: dict[str, str] | None = None,
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
        state_transition_only = operation_contract.effect_kind != "separation_fate"
        provider_components = (
            ()
            if state_transition_only
            else tuple(
                self.build_component_snapshot(
                    state=state,
                    source=source,
                    source_quantities=source_quantities,
                    component=component,
                    source_id=source_id,
                )
                for component in components.values()
                if component.explicit_fate is None
                and component.amount > ENTRY_EPSILON
            )
        )
        fractions_by_component = {
            component.entry_id: component.explicit_fate.ratios
            for component in components.values()
            if component.explicit_fate is not None
        }
        fate_source_by_component = {
            component.entry_id: component.explicit_fate.source
            for component in components.values()
            if component.explicit_fate is not None
        }
        fate_provenance_by_component: dict[str, ProviderProvenance | None] = {
            component.entry_id: None
            for component in components.values()
            if component.explicit_fate is not None
        }
        for component in components.values():
            if component.amount > ENTRY_EPSILON:
                continue
            fractions_by_component[component.entry_id] = (1.0, 0.0)
            fate_source_by_component[component.entry_id] = "zero_quantity_noop"
            fate_provenance_by_component[component.entry_id] = None
        if state_transition_only:
            for component in components.values():
                if component.explicit_fate is not None:
                    continue
                fractions_by_component[component.entry_id] = (1.0, 0.0)
                fate_source_by_component[component.entry_id] = (
                    "state_transition_operation_shape"
                )
                fate_provenance_by_component[component.entry_id] = None

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
                        "surface_preserved": {
                            component.entry_id: self.operation_preserves_relation(
                                operation_contract,
                                relation="container_surface",
                                output_part_id="1",
                            )
                            and component.relationship.relation == "container_surface"
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
                fate_provenance_by_component[component_id] = coordinated.provenance

        resolved_component_effects: list[ResolvedComponentEffect] = []
        for component in components.values():
            component_fractions = fractions_by_component.get(component.entry_id)
            if component_fractions is None:
                return MaterialEffectFailure(
                    "MAT_SCIENTIFIC_MODEL_REJECTED",
                    f"No separation fate was produced for component '{component.entry_id}'",
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
                if fraction <= 0.0 or component.amount <= ENTRY_EPSILON:
                    resolved_component_outputs.append(
                        ResolvedComponentOutput(
                            part_id=output.part_id,
                            semantic_role=output.semantic_role,
                            fraction=fraction,
                            next_relation=None,
                            next_label=None,
                            retire_quantity=False,
                            replacement_quantity=None,
                            decision_source=fate_source_by_component[component.entry_id],
                            fate_provenance=fate_provenance_by_component[component.entry_id],
                            transition_provenance=None,
                        )
                    )
                    continue
                projected_snapshot = ComponentSnapshot(
                    entry_id=f"{component.entry_id}@{output.part_id}",
                    content_ref=base_snapshot.content_ref,
                    canonical_kind=base_snapshot.canonical_kind,
                    canonical_type=base_snapshot.canonical_type,
                    quantity=QuantitySnapshot(
                        value=base_snapshot.quantity.value * fraction,
                        unit=base_snapshot.quantity.unit,
                    ),
                    relationship=base_snapshot.relationship,
                )
                transition_effect_kind = (
                    operation_contract.effect_kind
                    if state_transition_only and output.part_id == output_roles[0].part_id
                    else "separate"
                )
                transition_output = (
                    OutputRoleSnapshot(
                        part_id=output.part_id,
                        semantic_role="result_material",
                    )
                    if transition_effect_kind == "disrupt"
                    else output
                )
                transition_context = self.build_transition_context(
                    state=state,
                    component=component,
                    operation_contract=operation_contract,
                    output_part_id=output.part_id,
                    output_role=output.semantic_role,
                    current_relation=base_snapshot.relationship.relation,
                    model_entry_id=projected_snapshot.entry_id,
                    components=components,
                    fractions_by_component=fractions_by_component,
                    output_id=(output_ids_by_part or {}).get(
                        output.part_id,
                        output.part_id,
                    ),
                )
                transition_request = ModelRequest(
                    request_id=(
                        f"{request_id}:state_transition:"
                        f"{component.entry_id}:{output.part_id}"
                    ),
                    capability=MATERIAL_STATE_TRANSITION,
                    contract_version=MATERIAL_CONTRACT_VERSION,
                    payload=MaterialModelPayload(
                        operation=OperationSnapshot(
                            program_kind=operation_contract.program_kind,
                            effect_kind=transition_effect_kind,
                            output_roles=(transition_output,),
                            program_args=operation_contract.program_args,
                        ),
                        components=(projected_snapshot,),
                        context=transition_context,
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
                        next_association_target=self.resolved_association_target(
                            transition.next_relation,
                            transition.next_association_target,
                            transition_context,
                            projected_snapshot.entry_id,
                        ),
                        retire_quantity=transition.retire_quantity,
                        replacement_quantity=transition.replacement_quantity,
                        decision_source=fate_source_by_component[component.entry_id],
                        fate_provenance=fate_provenance_by_component[component.entry_id],
                        transition_provenance=coordinated.provenance,
                    )
                )
            resolved_component_effects.append(
                ResolvedComponentEffect(
                    source_component_id=component.entry_id,
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
                    source_content_ref=base_snapshot.content_ref,
                )
            )
        return ResolvedMaterialEffect(
            operation_id=request_id,
            program_kind=operation_contract.program_kind,
            outputs=resolved_outputs,
            component_effects=tuple(resolved_component_effects),
        )

    def resolve_movement(
        self,
        *,
        state: dict[str, Any],
        source: dict[str, Any],
        entries: tuple[dict[str, Any], ...],
        request_id: str,
        source_id: str,
        destination_id: str,
    ) -> ResolvedMaterialTransition | MaterialEffectFailure:
        """Resolve Table 3 once for every positive entry in a physical move."""

        resolved: list[ResolvedComponentTransition] = []
        source_quantities = source.get("component_quantities")
        source_quantities = (
            source_quantities if isinstance(source_quantities, dict) else {}
        )
        for entry in entries:
            entry_id = str(entry.get("entry_id", ""))
            content_ref = str(entry.get("content_ref", ""))
            quantity = entry.get("quantity")
            component = RuntimePartitionComponent(
                component_id=entry_id,
                content_ref=content_ref,
                amount=float(entry.get("amount", 0.0)),
                explicit_fate=None,
                physical_state=ContentPhysicalState(
                    association=str(entry.get("relation", "free")),
                    accessibility=(
                        "accessible"
                        if entry.get("relation", "free") == "free"
                        else "immobilized"
                    ),
                    preservation_state=str(entry.get("preservation") or "derived"),
                    source="component_entry",
                ),
                quantity=dict(quantity) if isinstance(quantity, dict) else None,
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
                label=str(entry["label"]) if isinstance(entry.get("label"), str) else None,
            )
            snapshot = self.build_component_snapshot(
                state=state,
                source=source,
                source_quantities=source_quantities,
                component=component,
                source_id=source_id,
            )
            release_declared = (
                snapshot.relationship.relation == "container_surface"
                and isinstance(quantity, dict)
                and quantity.get("dimension") == "count"
            )
            movement_target = self.movement_association_target(
                component=component,
                destination_id=destination_id,
            )
            request = ModelRequest(
                request_id=f"{request_id}:state_transition:{entry_id}",
                capability=MATERIAL_STATE_TRANSITION,
                contract_version=MATERIAL_CONTRACT_VERSION,
                payload=MaterialModelPayload(
                    operation=OperationSnapshot(
                        program_kind="material_move",
                        effect_kind="move",
                        output_roles=(
                            OutputRoleSnapshot(
                                part_id=destination_id,
                                semantic_role="destination",
                            ),
                        ),
                        program_args={},
                    ),
                    components=(snapshot,),
                    context={
                        "cross_container": True,
                        "release_declared": release_declared,
                        "binding_preserved": snapshot.relationship.relation == "bead_bound",
                        "membrane_preserved": snapshot.relationship.relation == "membrane_bound",
                        "cell_integrity_preserved": snapshot.relationship.relation == "cell_bound",
                        "field_preserved": False,
                        "label_has_persistent_relation": False,
                        "association_target": {
                            entry_id: movement_target
                        },
                    },
                ),
            )
            coordinated = self.coordinator.resolve(request)
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
                    "Movement transition did not return StateTransitionDecision",
                )
            transition = decision.transitions[0]
            resolved.append(
                ResolvedComponentTransition(
                    source_entry_id=entry_id,
                    next_relation=transition.next_relation,
                    next_label=transition.next_label,
                    provenance=coordinated.provenance,
                    next_association_target=(
                        transition.next_association_target
                        or (
                            None
                            if transition.next_relation == "free"
                            else movement_target
                        )
                    ),
                )
            )
        return ResolvedMaterialTransition(
            operation_id=request_id,
            effect_kind="move",
            component_transitions=tuple(resolved),
        )

    def transition_records(
        self,
        transition: ResolvedMaterialTransition,
    ) -> dict[str, dict[str, Any]]:
        return {
            component.source_entry_id: {
                "next_relation": component.next_relation,
                "next_label": component.next_label,
                "next_association_target": (
                    {
                        "kind": component.next_association_target.kind.value,
                        "id": component.next_association_target.id,
                    }
                    if component.next_association_target is not None
                    else None
                ),
                "provenance": provider_provenance_record(component.provenance),
                "scientific_decision": True,
            }
            for component in transition.component_transitions
        }

    def build_component_snapshot(
        self,
        *,
        state: dict[str, Any],
        source: dict[str, Any],
        source_quantities: dict[str, Any],
        component: RuntimePartitionComponent,
        source_id: str | None,
    ) -> ComponentSnapshot:
        content_ref = component.content_ref or component.entry_id
        registry = state.get("content_registry")
        content = (
            registry.get(content_ref) if isinstance(registry, dict) else None
        )
        content = content if isinstance(content, dict) else {}
        quantity = component.quantity
        if not isinstance(quantity, dict):
            quantity = source_quantities.get(content_ref)
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
                legacy_classes.get(content_ref)
                if isinstance(legacy_classes, dict)
                else None
            )
            relation = "pellet" if legacy_class == "retained_fraction" else "free"
        return ComponentSnapshot(
            entry_id=component.entry_id,
            content_ref=content_ref,
            canonical_kind=str(content.get("content_kind", "")),
            canonical_type=str(content.get("content_type", "")),
            quantity=QuantitySnapshot(
                value=float(quantity.get("value", component.amount)),
                unit=str(quantity.get("unit", "component_amount")),
            ),
            relationship=RelationshipSnapshot(
                relation=relation,
                associated_with=(
                    component.associated_with or source_id
                    if relation != "free"
                    else None
                ),
                association_target=self.component_association_target(
                    component=component,
                    relation=relation,
                    source_id=source_id,
                ),
                preservation=(
                    component.preservation
                    or component.physical_state.preservation_state
                ),
                label=component.label,
            ),
        )

    def build_transition_context(
        self,
        *,
        state: dict[str, Any],
        component: RuntimePartitionComponent,
        operation_contract: SeparationOperationContract,
        output_part_id: str,
        output_role: str,
        current_relation: str,
        model_entry_id: str,
        components: dict[str, RuntimePartitionComponent],
        fractions_by_component: dict[str, tuple[float, float]],
        output_id: str,
    ) -> dict[str, object]:
        authored_fate = component.explicit_fate is not None
        content_ref = component.content_ref or component.entry_id
        magnetic_support = self.is_magnetic_support(state, content_ref)
        association_target = self.separation_association_target(
            state=state,
            component=component,
            current_relation=current_relation,
            output_part_id=output_part_id,
            output_role=output_role,
            output_id=output_id,
            components=components,
            fractions_by_component=fractions_by_component,
        )
        return {
            "declared": operation_contract.effect_kind == "disrupt",
            "release_declared": False,
            "disruption_target": operation_contract.effect_kind == "disrupt",
            "target_remains_identifiable": self.component_context_flag(
                state,
                content_ref,
                "target_remains_identifiable",
            ),
            "precipitation_established": (
                authored_fate and output_role == "precipitate"
            ),
            "binding_established": authored_fate and output_role == "bound",
            "field_retention_established": (
                operation_contract.program_kind == "magnetic_program"
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
            "surface_preserved": (
                current_relation == "container_surface"
                and self.operation_preserves_relation(
                    operation_contract,
                    relation="container_surface",
                    output_part_id=output_part_id,
                )
            ),
            "association_target": {
                model_entry_id: association_target
            },
        }

    def component_association_target(
        self,
        *,
        component: RuntimePartitionComponent,
        relation: str,
        source_id: str | None,
    ) -> AssociationTarget | None:
        """Convert the 1.x association projection to its typed model form."""

        if relation == "free":
            return None
        target_id = component.associated_with or source_id
        if not isinstance(target_id, str) or not target_id:
            return None
        raw_kind = component.association_target_kind
        if raw_kind is None:
            raw_kind = (
                AssociationTargetKind.COMPONENT_ENTRY.value
                if relation in {"bead_bound", "membrane_bound", "cell_bound"}
                else AssociationTargetKind.CONTAINER.value
            )
        try:
            kind = AssociationTargetKind(raw_kind)
        except ValueError:
            return None
        return AssociationTarget(kind=kind, id=target_id)

    def resolved_association_target(
        self,
        next_relation: str,
        provider_target: AssociationTarget | None,
        transition_context: dict[str, object],
        model_entry_id: str,
    ) -> AssociationTarget | None:
        """Apply the 1.x provider fallback at the adapter boundary."""

        if next_relation == "free":
            return None
        if provider_target is not None:
            return provider_target
        targets = transition_context.get("association_target")
        candidate = (
            targets.get(model_entry_id)
            if isinstance(targets, dict)
            else None
        )
        return candidate if isinstance(candidate, AssociationTarget) else None

    def movement_association_target(
        self,
        *,
        component: RuntimePartitionComponent,
        destination_id: str,
    ) -> AssociationTarget:
        """Return the target candidate for one cross-container transition."""

        relation = self.canonical_relation(component.physical_state.association)
        current = self.component_association_target(
            component=component,
            relation=relation,
            source_id=None,
        )
        if relation in {"bead_bound", "membrane_bound", "cell_bound"} and current:
            return current
        return AssociationTarget(
            kind=AssociationTargetKind.CONTAINER,
            id=destination_id,
        )

    def separation_association_target(
        self,
        *,
        state: dict[str, Any],
        component: RuntimePartitionComponent,
        current_relation: str,
        output_part_id: str,
        output_role: str,
        output_id: str,
        components: dict[str, RuntimePartitionComponent],
        fractions_by_component: dict[str, tuple[float, float]],
    ) -> AssociationTarget | None:
        """Return the candidate target consumed by Table 3 for one output."""

        current = self.component_association_target(
            component=component,
            relation=current_relation,
            source_id=None,
        )
        if current_relation in {"bead_bound", "membrane_bound", "cell_bound"}:
            return current
        if (
            component.explicit_fate is not None
            and output_role == "bound"
            and not self.is_magnetic_support(
                state,
                component.content_ref or component.entry_id,
            )
        ):
            support_ids = self.projected_magnetic_support_entry_ids(
                state=state,
                output_part_id=output_part_id,
                components=components,
                fractions_by_component=fractions_by_component,
            )
            if len(support_ids) == 1:
                return AssociationTarget(
                    kind=AssociationTargetKind.COMPONENT_ENTRY,
                    id=support_ids[0],
                )
            return None
        return AssociationTarget(
            kind=AssociationTargetKind.CONTAINER,
            id=output_id,
        )

    def projected_magnetic_support_entry_ids(
        self,
        *,
        state: dict[str, Any],
        output_part_id: str,
        components: dict[str, RuntimePartitionComponent],
        fractions_by_component: dict[str, tuple[float, float]],
    ) -> tuple[str, ...]:
        """List positive magnetic-support entries projected to one output."""

        try:
            output_index = int(output_part_id)
        except ValueError:
            return ()
        support_ids: list[str] = []
        for candidate in components.values():
            if candidate.amount <= ENTRY_EPSILON:
                continue
            fractions = fractions_by_component.get(candidate.entry_id)
            if fractions is None or output_index >= len(fractions):
                continue
            if fractions[output_index] <= 0.0:
                continue
            if self.is_magnetic_support(
                state,
                candidate.content_ref or candidate.entry_id,
            ):
                support_ids.append(candidate.entry_id)
        return tuple(support_ids)

    def operation_preserves_relation(
        self,
        operation_contract: SeparationOperationContract,
        *,
        relation: str,
        output_part_id: str,
    ) -> bool:
        runtime_relation = {
            "bead_bound": "bead",
            "membrane_bound": "membrane",
            "cell_bound": "cell",
        }.get(relation, relation)
        return (
            operation_contract.preserved_association_slots.get(runtime_relation)
            == output_part_id
        )

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


# 1.x compatibility name. The adapter now covers separation and movement.
ScientificModelPartitionAdapter = ScientificModelMaterialAdapter


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
