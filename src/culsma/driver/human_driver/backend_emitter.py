"""Emit human backend projections as structured payloads."""

from __future__ import annotations

from culsma.driver.framework.models import DriverProjection
from .run_sheet import projection_to_packet


class HumanBackendEmitter:
    def emit(self, projection: DriverProjection) -> dict[str, object]:
        return {
            "instruction": {
                "title": projection.label,
                "summary": projection.summary,
                "details": list(projection.details),
                "category": projection.category,
            },
            "binding": dict(projection.binding),
            "projection": dict(projection.payload),
            "instruction_packet": projection_to_packet(projection),
        }
