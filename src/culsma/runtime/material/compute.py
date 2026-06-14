"""Material compute orchestration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.handler import (
    ContainerContentHandler,
    MaterialOpHandler,
    MutationHandler,
    NoopMaterialOpHandler,
    OrganizationResetHandler,
    SeparationHandler,
)
from culsma.runtime.material.conservation import (
    CONSERVATION_OPS,
    state_totals,
    totals_conserved,
)
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.refs import initialize_bindings, inventory_check_enabled
from culsma.runtime.material.result import MaterialUpdateResult


class MaterialOpDispatcher:
    def __init__(self, handlers: tuple[MaterialOpHandler, ...] | None = None) -> None:
        self.handlers = handlers or (
            ContainerContentHandler(),
            MutationHandler(),
            SeparationHandler(),
            OrganizationResetHandler(),
            NoopMaterialOpHandler(),
        )

    def handler_for(self, op: str) -> MaterialOpHandler:
        for handler in self.handlers:
            if handler.handles(op):
                return handler
        return NoopMaterialOpHandler()


class MaterialCompute:
    def __init__(self, dispatcher: MaterialOpDispatcher | None = None) -> None:
        self.dispatcher = dispatcher or MaterialOpDispatcher()

    def apply_step(self, step: PlanStep, material_state: dict[str, Any]) -> MaterialUpdateResult:
        """Apply deterministic material update for one runtime step."""
        state = deepcopy(material_state)
        state.setdefault("containers", {})
        initialize_bindings(state)
        before_totals = state_totals(state)

        result = self.dispatcher.handler_for(step.op).apply(step, state)

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
