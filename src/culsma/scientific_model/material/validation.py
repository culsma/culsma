"""Kernel-side validation for untrusted material provider results."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ..contracts import ModelRequest, ModelResult, ModelStatus
from .contracts import (
    AUTHOR_SETTABLE_MATERIAL_RELATIONS,
    COMPONENT_BOUND_MATERIAL_RELATIONS,
    MATERIAL_SEPARATION_FATE,
    MATERIAL_STATE_TRANSITION,
    AssociationTarget,
    AssociationTargetKind,
    MaterialRelation,
    MaterialModelPayload,
    SeparationDecision,
    StateTransitionDecision,
)


@dataclass(frozen=True)
class MaterialValidationIssue:
    code: str
    message: str


@dataclass(frozen=True)
class MaterialValidationResult:
    issues: tuple[MaterialValidationIssue, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.issues


def validate_material_result(
    request: ModelRequest,
    result: ModelResult,
    *,
    fraction_tolerance: float = 1e-9,
) -> MaterialValidationResult:
    if result.status is not ModelStatus.RESOLVED:
        return MaterialValidationResult()
    if not isinstance(request.payload, MaterialModelPayload):
        return MaterialValidationResult(
            issues=(
                MaterialValidationIssue(
                    code="MATERIAL_MODEL_REQUEST_INVALID",
                    message="material scientific-model request requires MaterialModelPayload",
                ),
            )
        )
    if request.capability == MATERIAL_SEPARATION_FATE:
        if not isinstance(result.proposal, SeparationDecision):
            return proposal_type_issue("SeparationDecision")
        provenance_validation = validate_decision_provenance(result.proposal, result)
        if not provenance_validation.valid:
            return provenance_validation
        return validate_separation_decision(
            request.payload,
            result.proposal,
            fraction_tolerance=fraction_tolerance,
        )
    if request.capability == MATERIAL_STATE_TRANSITION:
        if not isinstance(result.proposal, StateTransitionDecision):
            return proposal_type_issue("StateTransitionDecision")
        provenance_validation = validate_decision_provenance(result.proposal, result)
        if not provenance_validation.valid:
            return provenance_validation
        return validate_state_transition_decision(request.payload, result.proposal)
    return MaterialValidationResult(
        issues=(
            MaterialValidationIssue(
                code="MATERIAL_MODEL_CAPABILITY_UNKNOWN",
                message=f"unsupported material capability '{request.capability}'",
            ),
        )
    )


def proposal_type_issue(expected: str) -> MaterialValidationResult:
    return MaterialValidationResult(
        issues=(
            MaterialValidationIssue(
                code="MATERIAL_MODEL_PROPOSAL_TYPE_INVALID",
                message=f"resolved provider proposal must be {expected}",
            ),
        )
    )


def validate_decision_provenance(
    decision: SeparationDecision | StateTransitionDecision,
    result: ModelResult,
) -> MaterialValidationResult:
    """Require the typed decision to repeat the validated result provenance exactly."""

    if decision.provenance == result.provenance:
        return MaterialValidationResult()
    return MaterialValidationResult(
        issues=(
            MaterialValidationIssue(
                code="MATERIAL_MODEL_PROVENANCE_MISMATCH",
                message=(
                    "material decision provenance must match the selected provider "
                    "provenance in ModelResult"
                ),
            ),
        )
    )


def validate_separation_decision(
    payload: MaterialModelPayload,
    decision: SeparationDecision,
    *,
    fraction_tolerance: float,
) -> MaterialValidationResult:
    issues: list[MaterialValidationIssue] = []
    component_ids = {component.entry_id for component in payload.components}
    output_ids = {output.part_id for output in payload.operation.output_roles}
    seen_components: set[str] = set()

    for fate in decision.component_fates:
        if fate.component_entry_id not in component_ids:
            issues.append(
                MaterialValidationIssue(
                    code="MATERIAL_MODEL_COMPONENT_UNKNOWN",
                    message=f"proposal references unknown component '{fate.component_entry_id}'",
                )
            )
        if fate.component_entry_id in seen_components:
            issues.append(
                MaterialValidationIssue(
                    code="MATERIAL_MODEL_COMPONENT_DUPLICATE",
                    message=f"proposal repeats component '{fate.component_entry_id}'",
                )
            )
        seen_components.add(fate.component_entry_id)

        proposed_outputs = set(fate.fractions)
        if proposed_outputs != output_ids:
            issues.append(
                MaterialValidationIssue(
                    code="MATERIAL_MODEL_OUTPUT_SET_INVALID",
                    message=(
                        f"component '{fate.component_entry_id}' outputs {sorted(proposed_outputs)!r}; "
                        f"expected {sorted(output_ids)!r}"
                    ),
                )
            )

        values = tuple(fate.fractions.values())
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(float(value))
            or float(value) < 0.0
            or float(value) > 1.0
            for value in values
        ):
            issues.append(
                MaterialValidationIssue(
                    code="MATERIAL_MODEL_FRACTION_INVALID",
                    message=f"component '{fate.component_entry_id}' has an invalid fraction",
                )
            )
        elif abs(sum(float(value) for value in values) - 1.0) > fraction_tolerance:
            issues.append(
                MaterialValidationIssue(
                    code="MATERIAL_MODEL_FRACTION_TOTAL_INVALID",
                    message=f"component '{fate.component_entry_id}' fractions do not sum to one",
                )
            )

    missing = sorted(component_ids - seen_components)
    if missing:
        issues.append(
            MaterialValidationIssue(
                code="MATERIAL_MODEL_COMPONENT_MISSING",
                message=f"proposal omits components {missing!r}",
            )
        )
    return MaterialValidationResult(issues=tuple(issues))


def validate_state_transition_decision(
    payload: MaterialModelPayload,
    decision: StateTransitionDecision,
) -> MaterialValidationResult:
    issues: list[MaterialValidationIssue] = []
    components_by_id = {component.entry_id: component for component in payload.components}
    component_ids = set(components_by_id)
    seen_components: set[str] = set()
    for transition in decision.transitions:
        if transition.component_entry_id not in component_ids:
            issues.append(
                MaterialValidationIssue(
                    code="MATERIAL_MODEL_COMPONENT_UNKNOWN",
                    message=(
                        f"transition references unknown component "
                        f"'{transition.component_entry_id}'"
                    ),
                )
            )
        if transition.component_entry_id in seen_components:
            issues.append(
                MaterialValidationIssue(
                    code="MATERIAL_MODEL_COMPONENT_DUPLICATE",
                    message=f"transition repeats component '{transition.component_entry_id}'",
                )
            )
        seen_components.add(transition.component_entry_id)
        if (
            not isinstance(transition.next_relation, MaterialRelation)
            or transition.next_relation not in AUTHOR_SETTABLE_MATERIAL_RELATIONS
        ):
            issues.append(
                MaterialValidationIssue(
                    code="MATERIAL_MODEL_RELATION_INVALID",
                    message=(
                        f"component '{transition.component_entry_id}' has invalid next relation "
                        f"'{transition.next_relation}'"
                    ),
                )
            )
            continue
        target = transition.next_association_target
        if target is not None and (
            not isinstance(target, AssociationTarget)
            or not isinstance(target.kind, AssociationTargetKind)
            or not isinstance(target.id, str)
            or not target.id
        ):
            issues.append(
                MaterialValidationIssue(
                    code="MATERIAL_MODEL_ASSOCIATION_TARGET_INVALID",
                    message=(
                        f"component '{transition.component_entry_id}' has an invalid "
                        "next association target"
                    ),
                )
            )
            continue
        if transition.next_relation == MaterialRelation.FREE and target is not None:
            issues.append(
                MaterialValidationIssue(
                    code="MATERIAL_MODEL_ASSOCIATION_TARGET_FORBIDDEN",
                    message=(
                        f"free component '{transition.component_entry_id}' cannot "
                        "have a next association target"
                    ),
                )
            )
            continue
        component = components_by_id.get(transition.component_entry_id)
        if transition.next_relation in COMPONENT_BOUND_MATERIAL_RELATIONS:
            current_target_exists = bool(
                component is not None
                and (
                    component.relationship.association_target is not None
                    or component.relationship.associated_with is not None
                )
            )
            if target is None and not (
                component is not None
                and component.relationship.relation == transition.next_relation
                and current_target_exists
            ):
                issues.append(
                    MaterialValidationIssue(
                        code="MATERIAL_MODEL_ASSOCIATION_TARGET_MISSING",
                        message=(
                            f"component '{transition.component_entry_id}' requires a "
                            "component-entry association target"
                        ),
                    )
                )
            elif target is not None and target.kind is not AssociationTargetKind.COMPONENT_ENTRY:
                issues.append(
                    MaterialValidationIssue(
                        code="MATERIAL_MODEL_ASSOCIATION_TARGET_KIND_INVALID",
                        message=(
                            f"component '{transition.component_entry_id}' requires a "
                            "component-entry association target"
                        ),
                    )
                )
        elif transition.next_relation != MaterialRelation.FREE and target is not None:
            if target.kind is not AssociationTargetKind.CONTAINER:
                issues.append(
                    MaterialValidationIssue(
                        code="MATERIAL_MODEL_ASSOCIATION_TARGET_KIND_INVALID",
                        message=(
                            f"component '{transition.component_entry_id}' requires a "
                            "container association target"
                        ),
                    )
                )

    missing = sorted(component_ids - seen_components)
    if missing:
        issues.append(
            MaterialValidationIssue(
                code="MATERIAL_MODEL_COMPONENT_MISSING",
                message=f"transition proposal omits components {missing!r}",
            )
        )
    return MaterialValidationResult(issues=tuple(issues))
