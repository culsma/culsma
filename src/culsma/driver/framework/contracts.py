"""Explicit extension contracts for driver framework components."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import DriverProjection, MappingRecord


@dataclass(frozen=True)
class DriverContext:
    driver_kind: str
    runtime_context: dict[str, Any] = field(default_factory=dict)


class BindingResolver(Protocol):
    def bind(self, record: MappingRecord, context: DriverContext | None = None) -> dict[str, Any]:
        ...


class Translator(Protocol):
    def translate(self, record: MappingRecord, binding: dict[str, Any]) -> DriverProjection:
        ...


class BackendEmitter(Protocol):
    def emit(self, projection: DriverProjection) -> dict[str, Any]:
        ...


class ReceiptNormalizer(Protocol):
    def normalize(self, *, base_payload: dict[str, Any], emitted_payload: dict[str, Any]) -> dict[str, Any]:
        ...
