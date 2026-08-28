"""Runtime executor for PlanProgram."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.driver.base import Driver
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.scientific_model import (
    ScientificModelResolver,
    create_default_scientific_model_resolver,
)
from culsma.runtime.event_log import EventLog, RuntimeEvent
from culsma.runtime.finalize import RuntimeFinalizer
from culsma.runtime.gates import GateEvaluator
from culsma.runtime.material.accounting import MaterialAccountingRecorder
from culsma.runtime.material.compute import MaterialCompute
from culsma.runtime.observation import ObservationRecorder
from culsma.runtime.protocol_outputs import ProtocolOutputRecorder
from culsma.runtime.references import RefReuseDecider
from culsma.runtime.session import RuntimeSession
from culsma.runtime.state import RuntimeState, init_state
from culsma.runtime.steps import RuntimeStepDispatcher
from culsma.runtime.values import RuntimeValueResolver


@dataclass(frozen=True)
class RunResult:
    state: RuntimeState
    events: list[RuntimeEvent] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    user_result: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        if any(d.severity == "error" for d in self.diagnostics):
            return False
        if any(status == "failed" for status in self.state.step_status.values()):
            return False
        return True


def run(
    plan: PlanProgram,
    driver: Driver,
    state: RuntimeState | None = None,
    max_scheduler_rounds: int | None = None,
    on_error: str = "abort",
    scientific_model: ScientificModelResolver | None = None,
) -> RunResult:
    """Execute plan with deterministic scheduling."""
    runtime_state = state or init_state(plan)
    initial_material_state = None
    material_state = runtime_state.artifacts.get("material_state")
    if isinstance(material_state, dict):
        initial_material_state = deepcopy(material_state)
    diagnostics = list(plan.diagnostics)
    executor = RuntimeExecutor(
        max_scheduler_rounds=max_scheduler_rounds,
        on_error=on_error,
    )
    selected_scientific_model = (
        scientific_model
        if scientific_model is not None
        else create_default_scientific_model_resolver()
    )
    return executor.execute(
        plan=plan,
        driver=driver,
        runtime_state=runtime_state,
        diagnostics=diagnostics,
        initial_material_state=initial_material_state,
        scientific_model=selected_scientific_model,
    )


class RuntimeExecutor:
    def __init__(self, *, max_scheduler_rounds: int | None = None, on_error: str = "abort") -> None:
        self.max_scheduler_rounds = max_scheduler_rounds
        self.on_error = on_error

    def execute(
        self,
        *,
        plan: PlanProgram,
        driver: Driver,
        runtime_state: RuntimeState,
        diagnostics: list[Diagnostic],
        initial_material_state: dict[str, Any] | None,
        scientific_model: ScientificModelResolver,
    ) -> RunResult:
        log = EventLog()
        steps = [step for protocol in plan.plans for step in protocol.steps]
        for step in steps:
            runtime_state.step_status.setdefault(step.step_id, "pending")
        step_by_id = {step.step_id: step for step in steps}
        step_layers = _compute_step_layers(steps)
        ordered_steps = sorted(steps, key=lambda s: (step_layers.get(s.step_id, 0), s.step_id))
        step_index_by_id = {step.step_id: idx for idx, step in enumerate(ordered_steps)}
        protocol_plan_by_last_step_id = {
            protocol.steps[-1].step_id: protocol
            for protocol in plan.plans
            if protocol.steps
        }

        gate_evaluator = GateEvaluator()
        ref_reuse_decider = RefReuseDecider()
        value_resolver = RuntimeValueResolver()
        observation_recorder = ObservationRecorder()
        protocol_output_recorder = ProtocolOutputRecorder()
        material_accounting_recorder = MaterialAccountingRecorder()
        material_accounting = material_accounting_recorder.initialize(initial_material_state)
        finalizer = RuntimeFinalizer()
        ref_groups = ref_reuse_decider.build_groups(steps)
        ref_groups_by_first = {group.first_step_id: group for group in ref_groups.values()}
        ref_cache = ref_reuse_decider.ensure_cache(runtime_state)
        material_compute = MaterialCompute(scientific_model=scientific_model)

        session = RuntimeSession(
            plan=plan,
            driver=driver,
            state=runtime_state,
            diagnostics=diagnostics,
            event_log=log,
            step_by_id=step_by_id,
            ordered_steps=ordered_steps,
            step_index_by_id=step_index_by_id,
            protocol_plan_by_last_step_id=protocol_plan_by_last_step_id,
            ref_groups=ref_groups,
            ref_groups_by_first=ref_groups_by_first,
            ref_cache=ref_cache,
            material_compute=material_compute,
            initial_material_state=initial_material_state,
            on_error=self.on_error,
            fail_fast=self.on_error != "continue",
            gate_evaluator=gate_evaluator,
            ref_reuse_decider=ref_reuse_decider,
            value_resolver=value_resolver,
            observation_recorder=observation_recorder,
            protocol_output_recorder=protocol_output_recorder,
            material_accounting_recorder=material_accounting_recorder,
            material_accounting=material_accounting,
            finalizer=finalizer,
        )
        dispatcher = RuntimeStepDispatcher()
        max_rounds = self.max_scheduler_rounds if self.max_scheduler_rounds is not None else max(1, len(steps) * 2 + 4)
        scheduler_round = 0
        aborted_due_to_error = False
        made_progress = True

        while made_progress and not aborted_due_to_error:
            scheduler_round += 1
            if scheduler_round > max_rounds:
                session.emit_diagnostic(
                    Diagnostic(
                        code="RT_SCHEDULER_GUARD_LIMIT",
                        message=f"Scheduler stopped after exceeding max rounds ({max_rounds})",
                        span=plan.span,
                        node_id=None,
                    )
                )
                break

            made_progress = False
            for step in ordered_steps:
                status = runtime_state.step_status.get(step.step_id)
                if status != "pending":
                    continue
                if not _deps_satisfied(step, runtime_state):
                    continue
                aborted_step = dispatcher.dispatch(step, session)
                made_progress = True
                if aborted_step:
                    aborted_due_to_error = True
                    break

        finalizer.finalize(session, aborted_due_to_error=aborted_due_to_error)
        events = list(log.events)
        result = RunResult(state=runtime_state, events=events, diagnostics=session.diagnostics)
        user_result = finalizer.build_report(session, ok=result.ok).to_dict()
        return RunResult(
            state=runtime_state,
            events=events,
            diagnostics=session.diagnostics,
            user_result=user_result,
        )


def _deps_satisfied(step: PlanStep, state: RuntimeState) -> bool:
    return all(_step_satisfies_dependency(dep, state) for dep in step.deps)


def _step_satisfies_dependency(step_id: str, state: RuntimeState) -> bool:
    status = state.step_status.get(step_id)
    if status == "completed":
        return True
    if status != "skipped":
        return False
    skip_reasons = state.artifacts.get("skip_reasons", {})
    if not isinstance(skip_reasons, dict):
        return False
    return skip_reasons.get(step_id) in {"runtime_condition_false", "runtime_continue", "runtime_break"}


def _compute_step_layers(steps: list[PlanStep]) -> dict[str, int]:
    step_by_id = {step.step_id: step for step in steps}
    memo: dict[str, int] = {}
    visiting: set[str] = set()

    def dfs(step_id: str) -> int:
        if step_id in memo:
            return memo[step_id]
        if step_id in visiting:
            return 0
        visiting.add(step_id)
        step = step_by_id.get(step_id)
        if step is None or not step.deps:
            layer = 0
        else:
            layer = 1 + max((dfs(dep) for dep in step.deps), default=0)
        visiting.remove(step_id)
        memo[step_id] = layer
        return layer

    for step in steps:
        dfs(step.step_id)
    return memo
