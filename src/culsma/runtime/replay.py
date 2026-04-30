"""Replay runtime events into reconstructed state."""

from __future__ import annotations

from typing import Any

from culsma.runtime.event_log import RuntimeEvent
from culsma.runtime.state import RuntimeState


def replay_events(events: list[RuntimeEvent] | list[dict[str, Any]]) -> RuntimeState:
    """Reconstruct runtime state from event sequence."""
    state = RuntimeState()

    for raw in events:
        event = _as_event(raw)
        step_id = event.step_id

        if event.kind == "STEP_STARTED":
            state.step_status[step_id] = "running"
            state.history.append({"step_id": step_id, "status": "running"})
            continue

        if event.kind == "STEP_COMPLETED":
            state.step_status[step_id] = "completed"
            state.history.append(
                {
                    "step_id": step_id,
                    "status": "completed",
                    "driver_code": event.payload.get("driver_code"),
                }
            )
            material_snapshot = event.payload.get("material_state_snapshot")
            if isinstance(material_snapshot, dict):
                state.artifacts["material_state"] = material_snapshot
            continue

        if event.kind == "STEP_FAILED":
            reason = event.payload.get("reason")
            status = "failed"
            if reason == "unsatisfied_dependency":
                status = "skipped"
            state.step_status[step_id] = status
            state.history.append(
                {
                    "step_id": step_id,
                    "status": status,
                    "driver_code": event.payload.get("driver_code"),
                    "reason": reason,
                }
            )
            continue

        if event.kind == "STEP_SKIPPED":
            state.step_status[step_id] = "skipped"
            state.history.append(
                {
                    "step_id": step_id,
                    "status": "skipped",
                    "reason": event.payload.get("reason"),
                }
            )
            continue

    return state


def _as_event(raw: RuntimeEvent | dict[str, Any]) -> RuntimeEvent:
    if isinstance(raw, RuntimeEvent):
        return raw
    return RuntimeEvent(
        seq=int(raw["seq"]),
        kind=str(raw["kind"]),
        step_id=str(raw["step_id"]),
        payload=dict(raw.get("payload", {})),
        span=raw.get("span"),
    )
