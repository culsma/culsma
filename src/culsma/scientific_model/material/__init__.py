"""Built-in material scientific-model contracts and provider."""

from .builtin import (
    BUILTIN_MATERIAL_RULEBOOK_PROVIDER_ID,
    BuiltinMaterialRulebookProvider,
)
from .classification import CalculationGroup
from .contracts import (
    MATERIAL_CONTRACT_VERSION,
    MATERIAL_SEPARATION_FATE,
    MATERIAL_STATE_TRANSITION,
    ComponentFate,
    ComponentSnapshot,
    MaterialDecision,
    MaterialModelPayload,
    OperationSnapshot,
    OutputRoleSnapshot,
    QuantitySnapshot,
    RelationshipSnapshot,
    RelationshipTransition,
    SeparationDecision,
    StateTransitionDecision,
)
from .coordinator import CoordinatedDecision, CoordinationStatus, SepEffectCoordinator
from .rulebook import RulebookOutcome
from .validation import (
    MaterialValidationIssue,
    MaterialValidationResult,
    validate_material_result,
)

__all__ = [
    "BUILTIN_MATERIAL_RULEBOOK_PROVIDER_ID",
    "MATERIAL_CONTRACT_VERSION",
    "MATERIAL_SEPARATION_FATE",
    "MATERIAL_STATE_TRANSITION",
    "BuiltinMaterialRulebookProvider",
    "CalculationGroup",
    "ComponentFate",
    "ComponentSnapshot",
    "CoordinatedDecision",
    "CoordinationStatus",
    "MaterialDecision",
    "MaterialModelPayload",
    "MaterialValidationIssue",
    "MaterialValidationResult",
    "OperationSnapshot",
    "OutputRoleSnapshot",
    "QuantitySnapshot",
    "RelationshipSnapshot",
    "RelationshipTransition",
    "RulebookOutcome",
    "SepEffectCoordinator",
    "SeparationDecision",
    "StateTransitionDecision",
    "validate_material_result",
]
