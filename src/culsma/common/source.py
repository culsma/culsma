"""Shared source-location types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """Source position range in the original input text."""

    line: int
    col: int
    start: int
    end: int
