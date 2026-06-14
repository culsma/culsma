"""Material diagnostics helpers."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.result import MaterialUpdateResult


class MaterialDiagnostics:
    @staticmethod
    def result(step: PlanStep, state: dict[str, Any], code: str, message: str) -> MaterialUpdateResult:
        return diagnostic_result(step, state, code, message)


def diagnostic_result(step: PlanStep, state: dict[str, Any], code: str, message: str) -> MaterialUpdateResult:
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[Diagnostic(code=code, message=message, span=step.span, node_id=step.step_id)],
        delta={},
    )
