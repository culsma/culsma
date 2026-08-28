"""Closed calculation-group vocabulary for the built-in material provider."""

from enum import StrEnum


class CalculationGroup(StrEnum):
    MOBILE_PHASE = "mobile_phase"
    SEDIMENTABLE_MATERIAL = "sedimentable_material"
    CAPTURE_SUPPORT = "capture_support"
    CONTEXT_DEPENDENT_TARGET = "context_dependent_target"
    COMPOSITE_OR_UNKNOWN = "composite_or_unknown"
