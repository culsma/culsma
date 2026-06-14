"""Organization-state material operation implementations."""

from __future__ import annotations

from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.contents_state import mark_contents_state_mixed
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.refs import ref_display, resolve_structured_ref
from culsma.runtime.material.result import MaterialUpdateResult


def apply_agit(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    sample_arg = step.args.get("sample")
    sample_id = resolve_structured_ref(state, sample_arg, create_if_identifier=False)
    if sample_id is None:
        return diagnostic_result(
            step,
            state,
            "MAT_BINDING_NOT_FOUND",
            f"Unknown agit sample '{ref_display(sample_arg)}'",
        )
    impact = mark_contents_state_mixed(state, sample_id, step_id=step.step_id)
    return MaterialUpdateResult(
        material_state=state,
        diagnostics=[],
        delta={"op": "agit", "sample": sample_id, "contents_state_impact": impact},
    )
