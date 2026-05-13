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
    SeparationHandler,
)
from culsma.runtime.material.support import (
    MaterialUpdateResult,
    _CONSERVATION_OPS,
    _diag_result,
    _initialize_bindings,
    _inventory_check_enabled,
    _state_totals,
    _totals_conserved,
)


class MaterialOpDispatcher:
    def __init__(self, handlers: tuple[MaterialOpHandler, ...] | None = None) -> None:
        self.handlers = handlers or (
            ContainerContentHandler(),
            MutationHandler(),
            SeparationHandler(),
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
        _initialize_bindings(state)
        before_totals = _state_totals(state)

        result = self.dispatcher.handler_for(step.op).apply(step, state)

        if result.ok and step.op in _CONSERVATION_OPS and _inventory_check_enabled(state):
            after_totals = _state_totals(result.material_state)
            if not _totals_conserved(before_totals, after_totals):
                return _diag_result(
                    step=step,
                    state=result.material_state,
                    code="MAT_CONSERVATION_VIOLATION",
                    message=f"Conservation check failed for op '{step.op}'",
                )

        return result


def apply_step(step: PlanStep, material_state: dict[str, Any]) -> MaterialUpdateResult:
    return MaterialCompute().apply_step(step, material_state)
