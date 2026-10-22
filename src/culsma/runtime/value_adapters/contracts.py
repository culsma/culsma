"""Interfaces for trusted semantic values, separate from ordinary record fields."""
from __future__ import annotations

from typing import Any, Protocol


class AdaptedValue(dict):
    """A display value with identity established by a semantic reader, not a record key."""
    def __init__(self, type_id: str, value: dict[str, Any]) -> None:
        super().__init__(value)
        self.type_id = type_id


class QuantityDisplayValue(dict):
    """Quantity identity assigned by the value codec, never inferred from record keys."""


class ValueAdapter(Protocol):
    def read(self, type_id: str, value: Any, state: Any, resolver: Any) -> Any: ...
    def describe(self, value: AdaptedValue) -> Any: ...
