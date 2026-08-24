"""Statement-level IR -> Plan lowering dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, cast

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import (
    IRArg,
    IRAssign,
    IRCall,
    IRConditional,
    IRControl,
    IRIdentifier,
    IRInclude,
    IRLet,
    IRList,
    IRMutation,
    IRPair,
    IRQuantity,
    IRRepeat,
    IRStatement,
    IRStep,
    IRWithConstraint,
    IRWithEnv,
)
from culsma.pipeline.plan_nodes import PlanStep

from .context import PlanLoweringContext
from .gates import append_constraints, append_env_layer, append_runtime_condition, merge_gate
from .references import DEFAULT_PLAN_REFERENCE_RESOLVER, PlanReferenceResolver
from .serialization import DEFAULT_PLAN_EXPRESSION_SERIALIZER, PlanExpressionSerializer
from .static_eval import PlanStaticEvaluator


_CORE_RUNTIME_CALLS = {"sep", "frac", "img", "ecp", "phy"}
_LOCAL_RUNTIME_CALLS = {"markers", "stream", "data_ref", "data_group_ref", "data_schema"}
_CONSTRUCTOR_CALLS = {"AllocContainer"}


@dataclass
class PlanStatementLoweringState:
    output: list[PlanStep] | None = None


@dataclass
class LetPlanState(PlanStatementLoweringState):
    call: IRCall | None = None


@dataclass
class ConditionalPlanState(PlanStatementLoweringState):
    static_condition: bool | None = None


class BasePlanStatementHandler:
    serializer: PlanExpressionSerializer = DEFAULT_PLAN_EXPRESSION_SERIALIZER
    reference_resolver: PlanReferenceResolver = DEFAULT_PLAN_REFERENCE_RESOLVER
    static_evaluator: PlanStaticEvaluator = PlanStaticEvaluator()

    def handle(self, stmt: IRStatement, ctx: PlanLoweringContext) -> list[PlanStep]:
        state = self.prepare(stmt, ctx)
        if state.output is not None:
            return state.output

        self.validate_pre_lowering_rules(stmt, ctx, state)
        if state.output is not None:
            return state.output

        self.update_or_derive_local_env(stmt, ctx, state)
        if state.output is not None:
            return state.output

        self.serialize_child_expressions(stmt, ctx, state)
        if state.output is not None:
            return state.output

        output = self.lower_current_or_children(stmt, ctx, state)
        self.apply_post_lowering_effects(stmt, ctx, state, output)
        return state.output if state.output is not None else output

    def prepare(self, _stmt: IRStatement, _ctx: PlanLoweringContext) -> PlanStatementLoweringState:
        return PlanStatementLoweringState()

    def validate_pre_lowering_rules(
        self,
        _stmt: IRStatement,
        _ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
    ) -> None:
        return

    def update_or_derive_local_env(
        self,
        _stmt: IRStatement,
        _ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
    ) -> None:
        return

    def serialize_child_expressions(
        self,
        _stmt: IRStatement,
        _ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
    ) -> None:
        return

    def lower_current_or_children(
        self,
        _stmt: IRStatement,
        _ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
    ) -> list[PlanStep]:
        return []

    def apply_post_lowering_effects(
        self,
        _stmt: IRStatement,
        _ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
        _output: list[PlanStep],
    ) -> None:
        return


class LetPlanHandler(BasePlanStatementHandler):
    def prepare(self, stmt: IRStatement, _ctx: PlanLoweringContext) -> PlanStatementLoweringState:
        stmt = cast(IRLet, stmt)
        state = LetPlanState()
        if (
            isinstance(stmt.value, IRCall)
            and stmt.value.name in (_CORE_RUNTIME_CALLS | _LOCAL_RUNTIME_CALLS | _CONSTRUCTOR_CALLS)
        ):
            state.call = stmt.value
        return state

    def validate_pre_lowering_rules(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        state: PlanStatementLoweringState,
    ) -> None:
        stmt = cast(IRLet, stmt)
        if stmt.name not in ctx.protected_names:
            return
        ctx.emit_diagnostic(
            Diagnostic(
                code="PLAN_CALL_PARAM_REDECLARED",
                message=f"Parameter '{stmt.name}' is redeclared by let in protocol '{ctx.protocol_name}'",
                span=stmt.span,
                node_id=stmt.id,
            )
        )
        state.output = []

    def update_or_derive_local_env(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        state: PlanStatementLoweringState,
    ) -> None:
        stmt = cast(IRLet, stmt)
        state = cast(LetPlanState, state)
        if state.call is None and stmt.value is not None:
            ctx.local_env[stmt.name] = self.serializer.serialize_expr(stmt.value, ctx.local_env)

    def lower_current_or_children(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        state: PlanStatementLoweringState,
    ) -> list[PlanStep]:
        stmt = cast(IRLet, stmt)
        state = cast(LetPlanState, state)
        if state.call is None:
            return []
        return self.lower_let_call_to_steps(stmt=stmt, call=state.call, ctx=ctx)

    def apply_post_lowering_effects(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        state: PlanStatementLoweringState,
        _output: list[PlanStep],
    ) -> None:
        stmt = cast(IRLet, stmt)
        state = cast(LetPlanState, state)
        if state.call is not None and state.call.name in _LOCAL_RUNTIME_CALLS:
            ctx.local_env[stmt.name] = {"kind": "IRIdentifier", "name": stmt.name}

    def lower_let_call_to_steps(
        self,
        *,
        stmt: IRLet,
        call: IRCall,
        ctx: PlanLoweringContext,
    ) -> list[PlanStep]:
        if call.name in _CORE_RUNTIME_CALLS:
            return [
                PlanStep(
                    step_id=f"{ctx.step_id_prefix}{stmt.id}",
                    op=call.name,
                    args={
                        **{arg.name: self.serializer.serialize_expr(arg.value, ctx.local_env) for arg in call.args},
                        "bind": stmt.name,
                    },
                    deps=[],
                    gate=merge_gate(ctx.gate_base),
                    span=stmt.span,
                )
            ]

        if call.name in _LOCAL_RUNTIME_CALLS:
            return [
                PlanStep(
                    step_id=f"{ctx.step_id_prefix}{stmt.id}",
                    op="assign_local",
                    args={
                        "target": stmt.name,
                        "value": self.serializer.serialize_expr(call, ctx.local_env),
                    },
                    deps=[],
                    gate=merge_gate(ctx.gate_base),
                    span=stmt.span,
                )
            ]

        if call.name != "AllocContainer":
            return []

        alloc_args = {
            arg.name: self.serializer.serialize_expr(arg.value, ctx.local_env)
            for arg in call.args
            if arg.name != "load"
        }
        steps = [
            PlanStep(
                step_id=f"{ctx.step_id_prefix}{stmt.id}::alloc",
                op="AllocContainer",
                args={**alloc_args, "bind": stmt.name},
                deps=[],
                gate=merge_gate(ctx.gate_base),
                span=stmt.span,
            )
        ]

        load_arg = self.serializer.find_arg_by_name(call.args, "load")
        if load_arg is None or not isinstance(load_arg.value, IRList):
            return steps

        requires_material_finalization = False
        for idx, item in enumerate(load_arg.value.elements):
            if not isinstance(item, IRPair) or not isinstance(item.left, IRCall) or item.left.name != "DefineContent":
                continue
            if isinstance(item.right, IRQuantity) and item.right.unit == "cells":
                requires_material_finalization = True
            define_step_id = f"{ctx.step_id_prefix}{stmt.id}::load{idx}::define"
            content_ref = self.serializer.load_content_ref_expr(item.left, define_step_id)
            steps.append(
                PlanStep(
                    step_id=define_step_id,
                    op="DefineContent",
                    args={arg.name: self.serializer.serialize_expr(arg.value, ctx.local_env) for arg in item.left.args},
                    deps=[],
                    gate=merge_gate(ctx.gate_base),
                    span=item.left.span,
                )
            )
            steps.append(
                PlanStep(
                    step_id=f"{ctx.step_id_prefix}{stmt.id}::load{idx}::load",
                    op="LoadContent",
                    args={
                        "container": self.serializer.serialize_expr(IRIdentifier(name=stmt.name, span=stmt.span), ctx.local_env),
                        "content": self.serializer.serialize_expr(content_ref, ctx.local_env),
                        "amount": self.serializer.serialize_expr(item.right, ctx.local_env),
                    },
                    deps=[],
                    gate=merge_gate(ctx.gate_base),
                    span=item.span,
                )
            )
        if requires_material_finalization:
            steps.append(
                PlanStep(
                    step_id=f"{ctx.step_id_prefix}{stmt.id}::finalize",
                    op="FinalizeContainerContents",
                    args={
                        "container": self.serializer.serialize_expr(
                            IRIdentifier(name=stmt.name, span=stmt.span),
                            ctx.local_env,
                        )
                    },
                    deps=[],
                    gate=merge_gate(ctx.gate_base),
                    span=stmt.span,
                )
            )
        return steps


class AssignPlanHandler(BasePlanStatementHandler):
    def lower_current_or_children(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
    ) -> list[PlanStep]:
        stmt = cast(IRAssign, stmt)
        if isinstance(stmt.target, IRIdentifier):
            return [
                PlanStep(
                    step_id=f"{ctx.step_id_prefix}{stmt.id}",
                    op="assign_local",
                    args={
                        "target": stmt.target.name,
                        "value": self.serializer.serialize_expr(stmt.value, ctx.local_env),
                    },
                    deps=[],
                    gate=merge_gate(ctx.gate_base),
                    span=stmt.span,
                )
            ]
        return [
            PlanStep(
                step_id=f"{ctx.step_id_prefix}{stmt.id}",
                op="assign_member",
                args={
                    "target": self.serializer.serialize_expr(stmt.target, ctx.local_env),
                    "value": self.serializer.serialize_expr(stmt.value, ctx.local_env),
                },
                deps=[],
                gate=merge_gate(ctx.gate_base),
                span=stmt.span,
            )
        ]

    def apply_post_lowering_effects(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
        _output: list[PlanStep],
    ) -> None:
        stmt = cast(IRAssign, stmt)
        if isinstance(stmt.target, IRIdentifier):
            ctx.local_env[stmt.target.name] = {"kind": "IRIdentifier", "name": stmt.target.name}


class IncludePlanHandler(BasePlanStatementHandler):
    def lower_current_or_children(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
    ) -> list[PlanStep]:
        stmt = cast(IRInclude, stmt)
        nested_ref_stmt_id = f"{ctx.step_id_prefix}{stmt.id}"
        return self.reference_resolver.expand_reference_steps(
            ref_name=stmt.name,
            ref_stmt_id=nested_ref_stmt_id,
            ref_args=stmt.args,
            ctx=ctx,
            span=stmt.span,
            caller_protocol_name=ctx.protocol_name,
            call_path=ctx.call_path + [nested_ref_stmt_id],
        )


class WithEnvPlanHandler(BasePlanStatementHandler):
    def lower_current_or_children(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
    ) -> list[PlanStep]:
        stmt = cast(IRWithEnv, stmt)
        env_payload = self.serializer.serialize_arg_list(stmt.env_args, ctx.local_env)
        env_targets = self.serializer.serialize_expr(stmt.targets, ctx.local_env)
        gate = append_env_layer(
            ctx.gate_base,
            env=env_payload,
            env_targets=env_targets,
        )
        if stmt.explicit_hold and not stmt.statements:
            return [
                PlanStep(
                    step_id=f"{ctx.step_id_prefix}{stmt.id}",
                    op="env_hold",
                    args={},
                    deps=[],
                    gate=gate,
                    span=stmt.span,
                )
            ]
        if ctx.statement_lowerer is None:
            return []
        child_ctx = ctx.derive(
            local_env=dict(ctx.local_env),
            gate_base=gate,
            step_id_prefix=ctx.step_id_prefix,
            call_path=ctx.call_path,
            env_time_boundary=self.static_evaluator.env_time_boundary_from_payload(env_payload),
        )
        return ctx.statement_lowerer.lower_list(stmt.statements, child_ctx)

    def apply_post_lowering_effects(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
        _output: list[PlanStep],
    ) -> None:
        stmt = cast(IRWithEnv, stmt)
        self.serializer.invalidate_local_env_names(ctx.local_env, stmt.statements)

class WithConstraintPlanHandler(BasePlanStatementHandler):
    def lower_current_or_children(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
    ) -> list[PlanStep]:
        stmt = cast(IRWithConstraint, stmt)
        if ctx.statement_lowerer is None:
            return []
        child_ctx = ctx.derive(
            local_env=dict(ctx.local_env),
            gate_base=append_constraints(
                ctx.gate_base,
                requirements=stmt.requirements,
                options=self.serializer.serialize_arg_list(stmt.options, ctx.local_env),
            ),
            step_id_prefix=ctx.step_id_prefix,
            call_path=ctx.call_path,
        )
        return ctx.statement_lowerer.lower_list(stmt.statements, child_ctx)

    def apply_post_lowering_effects(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
        _output: list[PlanStep],
    ) -> None:
        stmt = cast(IRWithConstraint, stmt)
        self.serializer.invalidate_local_env_names(ctx.local_env, stmt.statements)


class RepeatPlanHandler(BasePlanStatementHandler):
    def lower_current_or_children(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
    ) -> list[PlanStep]:
        stmt = cast(IRRepeat, stmt)
        iterable = self.serializer.serialize_expr(stmt.iterable, ctx.local_env)
        if self.static_evaluator.is_schedule_payload(iterable):
            try:
                schedule_mode = self.static_evaluator.schedule_mode(iterable)
            except ValueError as exc:
                ctx.emit_diagnostic(
                    Diagnostic(
                        code="PLAN_STATIC_REPEAT_SCHEDULE_INVALID",
                        message=f"Static repeat schedule for '{stmt.id}' is invalid after parameter binding: {exc}",
                        span=stmt.span,
                        node_id=f"{ctx.step_id_prefix}{stmt.id}",
                    )
            )
                return []
            if schedule_mode == "continuous":
                return self.lower_static_continuous_schedule(stmt=stmt, ctx=ctx, iterable=iterable)
            return self.lower_static_schedule_repeat(stmt=stmt, ctx=ctx, iterable=iterable)

        body_steps: list[PlanStep] = []
        if ctx.statement_lowerer is not None:
            child_ctx = ctx.derive(
                local_env=dict(ctx.local_env),
                gate_base=merge_gate(ctx.gate_base),
                step_id_prefix="",
                call_path=ctx.call_path,
            )
            body_steps = ctx.statement_lowerer.lower_list(stmt.statements, child_ctx)
        return [
            PlanStep(
                step_id=f"{ctx.step_id_prefix}{stmt.id}",
                op="repeat_bind",
                args={
                    "binding": stmt.binding,
                    "iterable": iterable,
                    "body_steps": self.serializer.linearize_steps(body_steps),
                },
                deps=[],
                gate=merge_gate(ctx.gate_base),
                span=stmt.span,
            )
        ]

    def apply_post_lowering_effects(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
        _output: list[PlanStep],
    ) -> None:
        stmt = cast(IRRepeat, stmt)
        self.serializer.invalidate_local_env_names(ctx.local_env, stmt.statements)

    def lower_static_schedule_repeat(
        self,
        *,
        stmt: IRRepeat,
        ctx: PlanLoweringContext,
        iterable: Any,
    ) -> list[PlanStep]:
        try:
            points = self.static_evaluator.eval_discrete_schedule_points(
                iterable,
                env_time_boundary=ctx.env_time_boundary,
            )
        except ValueError as exc:
            ctx.emit_diagnostic(
                Diagnostic(
                    code="PLAN_STATIC_REPEAT_SCHEDULE_INVALID",
                    message=f"Static repeat schedule for '{stmt.id}' is invalid after parameter binding: {exc}",
                    span=stmt.span,
                    node_id=f"{ctx.step_id_prefix}{stmt.id}",
                )
            )
            return []
        if ctx.statement_lowerer is None:
            return []

        expanded: list[PlanStep] = []
        iteration_env = dict(ctx.local_env)
        previous_binding_present = stmt.binding in iteration_env
        previous_binding = iteration_env.get(stmt.binding)
        try:
            for iteration_index, point in enumerate(points):
                iteration_env[stmt.binding] = point
                child_ctx = ctx.derive(
                    local_env=iteration_env,
                    gate_base=merge_gate(ctx.gate_base),
                    step_id_prefix=f"{ctx.step_id_prefix}{stmt.id}.i{iteration_index}.",
                    call_path=ctx.call_path,
                )
                expanded.extend(ctx.statement_lowerer.lower_list(stmt.statements, child_ctx))
        finally:
            if previous_binding_present:
                iteration_env[stmt.binding] = previous_binding
            else:
                iteration_env.pop(stmt.binding, None)
        return expanded

    def lower_static_continuous_schedule(
        self,
        *,
        stmt: IRRepeat,
        ctx: PlanLoweringContext,
        iterable: Any,
    ) -> list[PlanStep]:
        try:
            boundary = self.static_evaluator.eval_continuous_schedule_boundary(
                iterable,
                env_time_boundary=ctx.env_time_boundary,
            )
        except ValueError as exc:
            ctx.emit_diagnostic(
                Diagnostic(
                    code="PLAN_STATIC_REPEAT_SCHEDULE_INVALID",
                    message=f"Static repeat schedule for '{stmt.id}' is invalid after parameter binding: {exc}",
                    span=stmt.span,
                    node_id=f"{ctx.step_id_prefix}{stmt.id}",
                )
            )
            return []
        if ctx.statement_lowerer is None:
            return []
        child_ctx = ctx.derive(
            local_env=dict(ctx.local_env),
            gate_base=merge_gate(ctx.gate_base),
            step_id_prefix=ctx.step_id_prefix,
            call_path=ctx.call_path,
            env_time_boundary=boundary,
        )
        return ctx.statement_lowerer.lower_list(stmt.statements, child_ctx)


class ConditionalPlanHandler(BasePlanStatementHandler):
    def prepare(self, stmt: IRStatement, ctx: PlanLoweringContext) -> PlanStatementLoweringState:
        stmt = cast(IRConditional, stmt)
        state = ConditionalPlanState()
        condition_payload = self.serializer.serialize_expr(stmt.condition, ctx.local_env)
        state.static_condition = self.static_evaluator.eval_bool(condition_payload)
        return state

    def lower_current_or_children(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        state: PlanStatementLoweringState,
    ) -> list[PlanStep]:
        stmt = cast(IRConditional, stmt)
        state = cast(ConditionalPlanState, state)
        if ctx.statement_lowerer is None:
            return []
        condition_payload = self.serializer.serialize_expr(stmt.condition, ctx.local_env)
        if state.static_condition is not None:
            selected = stmt.then_statements if state.static_condition else stmt.else_statements
            return ctx.statement_lowerer.lower_list(selected, ctx)
        then_ctx = ctx.derive(
            local_env=dict(ctx.local_env),
            gate_base=append_runtime_condition(ctx.gate_base, condition_payload, negate=False),
            step_id_prefix=ctx.step_id_prefix,
            call_path=ctx.call_path,
        )
        else_ctx = ctx.derive(
            local_env=dict(ctx.local_env),
            gate_base=append_runtime_condition(ctx.gate_base, condition_payload, negate=True),
            step_id_prefix=ctx.step_id_prefix,
            call_path=ctx.call_path,
        )
        return ctx.statement_lowerer.lower_list(stmt.then_statements, then_ctx) + ctx.statement_lowerer.lower_list(
            stmt.else_statements,
            else_ctx,
        )

    def apply_post_lowering_effects(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        state: PlanStatementLoweringState,
        _output: list[PlanStep],
    ) -> None:
        stmt = cast(IRConditional, stmt)
        state = cast(ConditionalPlanState, state)
        if state.static_condition is None:
            statements = [*stmt.then_statements, *stmt.else_statements]
        else:
            statements = stmt.then_statements if state.static_condition else stmt.else_statements
        self.serializer.invalidate_local_env_names(ctx.local_env, statements)


class MutationPlanHandler(BasePlanStatementHandler):
    def lower_current_or_children(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
    ) -> list[PlanStep]:
        stmt = cast(IRMutation, stmt)
        return [
            PlanStep(
                step_id=f"{ctx.step_id_prefix}{stmt.id}",
                op="Mutation",
                args={
                    "target": self.serializer.serialize_expr(stmt.target, ctx.local_env),
                    "sources": self.serializer.serialize_expr(stmt.sources, ctx.local_env),
                },
                deps=[],
                gate=merge_gate(ctx.gate_base),
                span=stmt.span,
            )
        ]


class ControlPlanHandler(BasePlanStatementHandler):
    def lower_current_or_children(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
    ) -> list[PlanStep]:
        stmt = cast(IRControl, stmt)
        return [
            PlanStep(
                step_id=f"{ctx.step_id_prefix}{stmt.id}",
                op=f"control_{stmt.action}",
                args={},
                deps=[],
                gate=merge_gate(ctx.gate_base),
                span=stmt.span,
            )
        ]


class StepPlanHandler(BasePlanStatementHandler):
    def lower_current_or_children(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
        _state: PlanStatementLoweringState,
    ) -> list[PlanStep]:
        stmt = cast(IRStep, stmt)
        return [
            PlanStep(
                step_id=f"{ctx.step_id_prefix}{stmt.id}",
                op=stmt.name,
                args={arg.name: self.serializer.serialize_expr(arg.value, ctx.local_env) for arg in stmt.args},
                deps=[],
                gate=merge_gate(ctx.gate_base),
                span=stmt.span,
            )
        ]


_STATEMENT_HANDLERS_BY_TYPE: dict[type[object], BasePlanStatementHandler] = {
    IRLet: LetPlanHandler(),
    IRAssign: AssignPlanHandler(),
    IRInclude: IncludePlanHandler(),
    IRWithEnv: WithEnvPlanHandler(),
    IRWithConstraint: WithConstraintPlanHandler(),
    IRRepeat: RepeatPlanHandler(),
    IRConditional: ConditionalPlanHandler(),
    IRMutation: MutationPlanHandler(),
    IRControl: ControlPlanHandler(),
    IRStep: StepPlanHandler(),
}


class PlanStatementLowerer:
    def __init__(
        self,
        *,
        serializer: PlanExpressionSerializer = DEFAULT_PLAN_EXPRESSION_SERIALIZER,
        reference_resolver: PlanReferenceResolver = DEFAULT_PLAN_REFERENCE_RESOLVER,
        handlers_by_type: Mapping[type[object], BasePlanStatementHandler] | None = None,
    ) -> None:
        self.serializer = serializer
        self.reference_resolver = reference_resolver
        self.handlers_by_type = dict(handlers_by_type or _STATEMENT_HANDLERS_BY_TYPE)
        for handler in self.handlers_by_type.values():
            handler.serializer = serializer
            handler.reference_resolver = reference_resolver

    def lower_list(self, statements: list[IRStatement], ctx: PlanLoweringContext) -> list[PlanStep]:
        previous_lowerer = ctx.statement_lowerer
        previous_serializer = ctx.serializer
        previous_reference_resolver = ctx.reference_resolver
        ctx.statement_lowerer = self
        ctx.serializer = self.serializer
        ctx.reference_resolver = self.reference_resolver
        try:
            steps: list[PlanStep] = []
            for stmt in statements:
                steps.extend(self.materialize_runtime_locals_before_statement(stmt, ctx))
                steps.extend(self.lower_statement(stmt, ctx))
            return steps
        finally:
            ctx.statement_lowerer = previous_lowerer
            ctx.serializer = previous_serializer
            ctx.reference_resolver = previous_reference_resolver

    def lower_statement(self, stmt: IRStatement, ctx: PlanLoweringContext) -> list[PlanStep]:
        handler = self.handlers_by_type.get(type(stmt))
        if handler is None:
            return []
        return handler.handle(stmt, ctx)

    def materialize_runtime_locals_before_statement(
        self,
        stmt: IRStatement,
        ctx: PlanLoweringContext,
    ) -> list[PlanStep]:
        if ctx.scope_query is None:
            return []
        stmt_id = getattr(stmt, "id", "statement")
        steps: list[PlanStep] = []
        for effect in ctx.scope_query.assignment_effects(stmt_id):
            if self.assignment_can_initialize_without_previous_value(stmt, effect.name, effect.reads_before_write):
                continue
            value = ctx.local_env.get(effect.name)
            if not self.needs_runtime_local_materialization(effect.name, value):
                continue
            steps.append(
                PlanStep(
                    step_id=f"{ctx.step_id_prefix}{stmt_id}::init::{effect.name}",
                    op="assign_local",
                    args={"target": effect.name, "value": value},
                    deps=[],
                    gate=merge_gate(ctx.gate_base),
                    span=getattr(stmt, "span", None),
                )
            )
            ctx.local_env[effect.name] = {"kind": "IRIdentifier", "name": effect.name}
        return steps

    def assignment_can_initialize_without_previous_value(
        self,
        stmt: IRStatement,
        name: str,
        reads_before_write: bool,
    ) -> bool:
        return (
            isinstance(stmt, IRAssign)
            and isinstance(stmt.target, IRIdentifier)
            and stmt.target.name == name
            and not reads_before_write
        )

    def needs_runtime_local_materialization(self, name: str, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, dict) and value.get("kind") == "IRIdentifier" and value.get("name") == name:
            return False
        return True
