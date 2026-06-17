"""Material compute orchestration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.conservation import (
    CONSERVATION_OPS,
    state_totals,
    totals_conserved,
)
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.refs import initialize_bindings, inventory_check_enabled
from culsma.runtime.material.result import MaterialUpdateResult
from culsma.runtime.material.state import MaterialStateManager


class MaterialCompute:
    def __init__(self, state_manager: MaterialStateManager | None = None) -> None:
        self.state_manager = state_manager or MaterialStateManager()

    def apply_step(self, step: PlanStep, material_state: dict[str, Any]) -> MaterialUpdateResult:
        """Apply deterministic material update for one runtime step."""
        state = deepcopy(material_state)
        state.setdefault("containers", {})
        initialize_bindings(state)
        before_totals = state_totals(state)

        change_plan = self.state_manager.plan_material_state_change(step=step, state=state)
        if change_plan is not None:
            result = self.state_manager.apply_change(change_plan, state)
        else:
            result = MaterialUpdateResult(material_state=state, diagnostics=[], delta={})

        if result.ok and step.op in CONSERVATION_OPS and inventory_check_enabled(state):
            after_totals = state_totals(result.material_state)
            if not totals_conserved(before_totals, after_totals):
                return diagnostic_result(
                    step=step,
                    state=result.material_state,
                    code="MAT_CONSERVATION_VIOLATION",
                    message=f"Conservation check failed for op '{step.op}'",
                )

        return result


def apply_step(step: PlanStep, material_state: dict[str, Any]) -> MaterialUpdateResult:
    return MaterialCompute().apply_step(step, material_state)
