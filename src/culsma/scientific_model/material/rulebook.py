"""Outcome vocabulary shared by built-in material Rulebook stages."""

from enum import StrEnum


class RulebookOutcome(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    KEEP_SEPARATE = "KEEP_SEPARATE"
    REJECT = "REJECT"
