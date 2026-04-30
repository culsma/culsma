"""Runtime state models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from culsma.pipeline.plan_nodes import PlanProgram


@dataclass
class RuntimeState:
    step_status: dict[str, str] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    locks: dict[str, str] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_status": dict(self.step_status),
            "artifacts": dict(self.artifacts),
            "locks": dict(self.locks),
            "history": list(self.history),
        }


def init_state(plan: PlanProgram) -> RuntimeState:
    state = RuntimeState()
    for protocol_plan in plan.plans:
        for step in protocol_plan.steps:
            state.step_status[step.step_id] = "pending"
    data_objects: dict[str, Any] = {}
    data_bindings: dict[str, Any] = {}
    data_groups: dict[str, Any] = {}
    data_group_bindings: dict[str, Any] = {}
    data_group_indexed_bindings: dict[str, Any] = {}
    raw_data: dict[str, Any] = {}
    data_exports: dict[str, Any] = {}
    state.artifacts.setdefault("data_objects", data_objects)
    state.artifacts.setdefault("data_bindings", data_bindings)
    state.artifacts.setdefault("data_groups", data_groups)
    state.artifacts.setdefault("data_group_bindings", data_group_bindings)
    state.artifacts.setdefault("data_group_indexed_bindings", data_group_indexed_bindings)
    state.artifacts.setdefault("raw_data", raw_data)
    state.artifacts.setdefault("data_exports", data_exports)
    state.artifacts.setdefault("protocol_outputs", {})
    state.artifacts.setdefault("local_bindings", {})
    state.artifacts.setdefault("skip_reasons", {})
    return state
