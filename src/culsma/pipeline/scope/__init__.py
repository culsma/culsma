"""Pipeline-local scope semantics."""

from .analysis import ScopeAnalyzer
from .model import (
    ScopeAssignmentEffect,
    ScopeFrame,
    ScopeModel,
    ScopeResolution,
    ScopeSlot,
)
from .queries import ScopeQueryService

__all__ = [
    "ScopeAnalyzer",
    "ScopeAssignmentEffect",
    "ScopeFrame",
    "ScopeModel",
    "ScopeQueryService",
    "ScopeResolution",
    "ScopeSlot",
]
