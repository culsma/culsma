"""Runtime gate evaluation helpers."""

from __future__ import annotations

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.session import RuntimeSession
from culsma.runtime.state import RuntimeState
from culsma.runtime.values import UNRESOLVED


class GateEvaluator:
    def evaluate(self, step: PlanStep, state: RuntimeState, *, session: RuntimeSession | None = None) -> str:
        if not isinstance(step.gate, dict):
            return "run"
        raw_conditions = step.gate.get("runtime_conditions")
        if not isinstance(raw_conditions, list) or not raw_conditions:
            return "run"
        resolver = session.value_resolver if session is not None else None
        if resolver is None:
            return "error"
        for item in raw_conditions:
            if not isinstance(item, dict):
                return "error"
            value = resolver.eval_expr(item.get("expr"), state)
            if value is UNRESOLVED:
                return "error"
            passed = bool(value)
            if bool(item.get("negate")):
                passed = not passed
            if not passed:
                return "skip"
        return "run"
