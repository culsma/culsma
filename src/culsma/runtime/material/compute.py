"""Material compute orchestration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.scientific_model import (
    ScientificModelResolver,
    create_default_scientific_model_resolver,
)
from culsma.scientific_model.material import SepEffectCoordinator
from culsma.runtime.material.conservation import (
    CONSERVATION_OPS,
    declared_quantity_retirements,
    state_totals,
    totals_conserved_with_declared_retirements,
)
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.ledger import (
    normalize_material_state_detail_ledger,
    refresh_material_state_aggregates,
)
from culsma.runtime.material.refs import initialize_bindings
from culsma.runtime.material.movements import derive_material_movements, material_quantities_changed
from culsma.runtime.material.result import MaterialUpdateResult
from culsma.runtime.material.scientific_model_adapter import (
    ScientificModelPartitionAdapter,
)
from culsma.runtime.material.state import MaterialStateManager


class MaterialCompute:
    def __init__(
        self,
        state_manager: MaterialStateManager | None = None,
        scientific_model: ScientificModelResolver | None = None,
    ) -> None:
        self.scientific_model = (
            scientific_model
            if scientific_model is not None
            else create_default_scientific_model_resolver()
        )
        self.sep_effect_coordinator = SepEffectCoordinator(self.scientific_model)
        self.material_effect_adapter = ScientificModelPartitionAdapter(
            self.sep_effect_coordinator
        )
        self.state_manager = state_manager or MaterialStateManager(
            material_effect_adapter=self.material_effect_adapter
        )

    def apply_step(self, step: PlanStep, material_state: dict[str, Any]) -> MaterialUpdateResult:
        """Apply deterministic material update for one runtime step."""
        state = deepcopy(material_state)
        state.setdefault("containers", {})
        detail_error = normalize_material_state_detail_ledger(state)
        if detail_error is not None:
            return diagnostic_result(
                step=step,
                state=state,
                code="MAT_INVALID_COMPONENT_QUANTITY",
                message=detail_error,
            )
        initialize_bindings(state)
        before_totals = state_totals(state)
        movement_before_state = deepcopy(state)

        change_plan = self.state_manager.plan_material_state_change(step=step, state=state)
        if change_plan is not None:
            result = self.state_manager.apply_change(change_plan, state)
        else:
            result = MaterialUpdateResult(material_state=state, diagnostics=[], delta={})

        operation_result_state = deepcopy(result.material_state)
        refresh_material_state_aggregates(result.material_state)

        if result.ok and step.op in CONSERVATION_OPS:
            after_totals = state_totals(result.material_state)
            if not totals_conserved_with_declared_retirements(
                before_totals,
                after_totals,
                result.delta,
            ):
                return diagnostic_result(
                    step=step,
                    state=result.material_state,
                    code="MAT_CONSERVATION_VIOLATION",
                    message=f"Conservation check failed for op '{step.op}'",
                )

        movement_specs = derive_material_movements(
            delta=result.delta,
            before_state=movement_before_state,
            after_state=result.material_state,
        )
        if (
            result.ok
            and result.delta.get("op") not in {"LoadContent", "FinalizeContainerContents"}
            and not movement_specs
            and not declared_quantity_retirements(result.delta)
            and material_quantities_changed(
                before_state=movement_before_state,
                after_state=operation_result_state,
            )
        ):
            return diagnostic_result(
                step=step,
                state=result.material_state,
                code="MAT_MOVEMENT_CONTRACT_MISSING",
                message=(
                    f"Material operation '{step.op}' changed container quantities "
                    "without declaring source-to-destination movements"
                ),
            )
        return MaterialUpdateResult(
            material_state=result.material_state,
            diagnostics=result.diagnostics,
            delta=result.delta,
            movements=movement_specs,
        )


def apply_step(
    step: PlanStep,
    material_state: dict[str, Any],
    scientific_model: ScientificModelResolver | None = None,
) -> MaterialUpdateResult:
    return MaterialCompute(scientific_model=scientific_model).apply_step(step, material_state)
