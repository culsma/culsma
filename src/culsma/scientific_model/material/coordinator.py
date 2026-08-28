"""Author-precedence coordinator for material scientific decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..contracts import ModelRequest, ModelResult, ModelStatus, ScientificModelResolver
from .contracts import MaterialDecision
from .validation import MaterialValidationIssue, validate_material_result


class CoordinationStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class CoordinatedDecision:
    status: CoordinationStatus
    decision: MaterialDecision | None
    source: str
    model_result: ModelResult | None = None
    validation_issues: tuple[MaterialValidationIssue, ...] = ()


@dataclass(frozen=True)
class SepEffectCoordinator:
    resolver: ScientificModelResolver

    def resolve(
        self,
        request: ModelRequest,
        *,
        validated_author_decision: MaterialDecision | None = None,
    ) -> CoordinatedDecision:
        if validated_author_decision is not None:
            return CoordinatedDecision(
                status=CoordinationStatus.RESOLVED,
                decision=validated_author_decision,
                source="author",
            )

        result = self.resolver.resolve(request)
        if result.status is ModelStatus.NOT_APPLICABLE:
            return CoordinatedDecision(
                status=CoordinationStatus.UNRESOLVED,
                decision=None,
                source="provider",
                model_result=result,
            )
        if result.status is ModelStatus.FAILED:
            return CoordinatedDecision(
                status=CoordinationStatus.FAILED,
                decision=None,
                source="provider",
                model_result=result,
            )

        validation = validate_material_result(request, result)
        if not validation.valid:
            return CoordinatedDecision(
                status=CoordinationStatus.REJECTED,
                decision=None,
                source="provider",
                model_result=result,
                validation_issues=validation.issues,
            )
        decision = result.proposal
        if not isinstance(decision, MaterialDecision):
            raise AssertionError("material result validator accepted an invalid proposal type")
        return CoordinatedDecision(
            status=CoordinationStatus.RESOLVED,
            decision=decision,
            source="provider",
            model_result=result,
        )
