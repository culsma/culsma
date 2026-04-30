"""Structured runtime event logging."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from culsma.common.source import Span


@dataclass(frozen=True)
class RuntimeEvent:
    seq: int
    kind: str
    step_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    span: Span | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventLog:
    def __init__(self) -> None:
        self._seq = 0
        self.events: list[RuntimeEvent] = []

    def emit(self, kind: str, step_id: str, payload: dict[str, Any] | None = None, span: Span | None = None) -> RuntimeEvent:
        self._seq += 1
        event = RuntimeEvent(
            seq=self._seq,
            kind=kind,
            step_id=step_id,
            payload=payload or {},
            span=span,
        )
        self.events.append(event)
        return event

