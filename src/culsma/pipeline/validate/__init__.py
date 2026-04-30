"""Semantic validation package."""

from .context import ValidationResult
from .groups import GroupIndexValidator
from .validator import validate

_classify_group_binding = GroupIndexValidator.classify_binding

__all__ = [
    "ValidationResult",
    "_classify_group_binding",
    "validate",
]
