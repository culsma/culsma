"""Emit robot backend projections as structured command payloads."""

from __future__ import annotations

from culsma.driver.framework.models import DriverProjection


class RobotBackendEmitter:
    def emit(self, projection: DriverProjection) -> dict[str, object]:
        return {
            "command": {
                "label": projection.label,
                "summary": projection.summary,
                "details": list(projection.details),
                "category": projection.category,
            },
            "binding": dict(projection.binding),
            "projection": dict(projection.payload),
        }
