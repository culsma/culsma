"""Shared diagnostic model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from culsma.common.source import Span


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    span: Span | None
    severity: str = "error"
    node_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "node_id": self.node_id,
        }
        if self.span is not None:
            payload["span"] = {
                "line": self.span.line,
                "col": self.span.col,
                "start": self.span.start,
                "end": self.span.end,
            }
        else:
            payload["span"] = None
        return payload
