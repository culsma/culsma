"""Repeat-control lowering helpers for statement compile."""

from __future__ import annotations

from typing import TYPE_CHECKING

from culsma.parser.ast_nodes import (
    Arg,
    BooleanLiteral,
    CallExpr,
    Expression,
    Identifier,
    IndexExpr,
    MemberExpr,
    Quantity,
    RepeatStatement,
)
from culsma.pipeline.ir_nodes import IRRepeat, IRStatement

if TYPE_CHECKING:
    from .statements import StatementLoweringContext


class RepeatControlLowerer:
    def lower_repeat(
        self,
        stmt: RepeatStatement,
        lowering_ctx: StatementLoweringContext,
    ) -> list[IRStatement]:
        if stmt.binding is not None:
            return self.lower_binding_repeat(stmt, lowering_ctx)
        return self.lower_count_repeat(stmt, lowering_ctx)

    def lower_binding_repeat(
        self,
        stmt: RepeatStatement,
        lowering_ctx: StatementLoweringContext,
    ) -> list[IRStatement]:
        iterable_values = lowering_ctx.schedule_evaluator.resolve_repeat_iterable_values(
            stmt.iterable,
            ctx=lowering_ctx.ctx,
        )
        if iterable_values is not None:
            return self.lower_iterable_values(stmt, lowering_ctx, iterable_values)

        resolved_iterable = lowering_ctx.schedule_evaluator.resolve_bound_expr(stmt.iterable, ctx=lowering_ctx.ctx)
        runtime_iterable_surface = isinstance(
            resolved_iterable,
            (Identifier, CallExpr, MemberExpr, IndexExpr),
        )
        if runtime_iterable_surface and not (
            isinstance(resolved_iterable, CallExpr) and resolved_iterable.name == "schedule"
        ):
            compiled_body = lowering_ctx.statement_compiler.compile_list(
                stmt.statements,
                ctx=lowering_ctx.ctx.derive(
                    scope_id=f"{lowering_ctx.stmt_id}.b",
                    const_env=lowering_ctx.ctx.const_env,
                    let_bindings=dict(lowering_ctx.ctx.let_bindings),
                    local_names=set(lowering_ctx.ctx.local_names) | {stmt.binding},
                ),
            )
            return [
                IRRepeat(
                    id=lowering_ctx.stmt_id,
                    binding=stmt.binding,
                    iterable=lowering_ctx.expr_compiler.compile(stmt.iterable),
                    statements=compiled_body,
                    span=stmt.span,
                )
            ]

        schedule_mode = lowering_ctx.schedule_evaluator.resolve_schedule_mode(stmt.iterable, ctx=lowering_ctx.ctx)
        if schedule_mode == "continuous":
            try:
                return self.lower_continuous_schedule(stmt, lowering_ctx)
            except ValueError:
                if lowering_ctx.static_control_classifier.can_defer_continuous_schedule(
                    stmt.iterable,
                    ctx=lowering_ctx.ctx,
                ):
                    return self.lower_deferred_static_repeat(
                        stmt,
                        lowering_ctx,
                        stmt.iterable,
                        env_time_boundary_deferred=True,
                    )
                raise
        try:
            points = lowering_ctx.schedule_evaluator.eval_schedule_points(stmt.iterable, ctx=lowering_ctx.ctx)
        except ValueError:
            if lowering_ctx.static_control_classifier.can_defer_discrete_schedule(stmt.iterable, ctx=lowering_ctx.ctx):
                return self.lower_deferred_static_repeat(stmt, lowering_ctx, stmt.iterable)
            raise
        return self.lower_iterable_values(stmt, lowering_ctx, points)

    def lower_iterable_values(
        self,
        stmt: RepeatStatement,
        lowering_ctx: StatementLoweringContext,
        iterable_values: list[Expression],
    ) -> list[IRStatement]:
        expanded: list[IRStatement] = []
        loop_const_env = dict(lowering_ctx.ctx.const_env)
        loop_let_bindings = dict(lowering_ctx.ctx.let_bindings)
        loop_local_names = set(lowering_ctx.ctx.local_names)
        for iteration_index, point in enumerate(iterable_values):
            substituted_statements = [
                lowering_ctx.schedule_evaluator.substitute_statement(nested_stmt, stmt.binding, point)
                for nested_stmt in stmt.statements
            ]
            nested_const_env = dict(loop_const_env)
            nested_let_bindings = dict(loop_let_bindings)
            nested_local_names = set(loop_local_names)
            nested_let_bindings[stmt.binding] = point
            runtime_control = any(
                lowering_ctx.schedule_evaluator.statement_requires_runtime_control(
                    nested_stmt,
                    ctx=lowering_ctx.ctx.derive(const_env=nested_const_env),
                )
                for nested_stmt in substituted_statements
            )
            nested_stmt_index = 0
            stop_all_iterations = False
            for nested_stmt in substituted_statements:
                nested_ctx = lowering_ctx.ctx.derive(
                    scope_id=f"{lowering_ctx.stmt_id}.i{iteration_index}" if runtime_control else lowering_ctx.ctx.scope_id,
                    const_env=nested_const_env,
                    let_bindings=nested_let_bindings,
                    local_names=nested_local_names | {stmt.binding},
                )
                compiled_nested = lowering_ctx.statement_compiler.compile(
                    nested_stmt,
                    ctx=nested_ctx,
                    stmt_index=nested_stmt_index if runtime_control else lowering_ctx.stmt_index + len(expanded),
                )
                expanded.extend(compiled_nested)
                nested_stmt_index += len(compiled_nested)
                if not runtime_control:
                    control_action = lowering_ctx.schedule_evaluator.static_control_action(compiled_nested)
                    if control_action == "continue":
                        break
                    if control_action == "break":
                        stop_all_iterations = True
                        break
            nested_let_bindings.pop(stmt.binding, None)
            nested_const_env.pop(stmt.binding, None)
            loop_const_env = nested_const_env
            loop_let_bindings = nested_let_bindings
            loop_local_names = nested_local_names
            if stop_all_iterations:
                break
        return expanded

    def lower_continuous_schedule(
        self,
        stmt: RepeatStatement,
        lowering_ctx: StatementLoweringContext,
    ) -> list[IRStatement]:
        window_boundary = lowering_ctx.schedule_evaluator.eval_continuous_schedule_boundary(
            stmt.iterable,
            ctx=lowering_ctx.ctx,
        )
        substituted_statements = list(stmt.statements)
        nested_const_env = dict(lowering_ctx.ctx.const_env)
        nested_let_bindings = dict(lowering_ctx.ctx.let_bindings)
        nested_local_names = set(lowering_ctx.ctx.local_names)
        runtime_control = any(
            lowering_ctx.schedule_evaluator.statement_requires_runtime_control(
                nested_stmt,
                ctx=lowering_ctx.ctx.derive(const_env=nested_const_env),
            )
            for nested_stmt in substituted_statements
        )
        expanded: list[IRStatement] = []
        nested_stmt_index = 0
        for nested_stmt in substituted_statements:
            compiled_nested = lowering_ctx.statement_compiler.compile(
                nested_stmt,
                ctx=lowering_ctx.ctx.derive(
                    scope_id=f"{lowering_ctx.stmt_id}.i0",
                    const_env=nested_const_env,
                    let_bindings=nested_let_bindings,
                    local_names=nested_local_names,
                    env_time_boundary=window_boundary,
                ),
                stmt_index=nested_stmt_index,
            )
            expanded.extend(compiled_nested)
            nested_stmt_index += len(compiled_nested)
            if not runtime_control:
                control_action = lowering_ctx.schedule_evaluator.static_control_action(compiled_nested)
                if control_action in {"continue", "break"}:
                    break
        return expanded

    def lower_count_repeat(
        self,
        stmt: RepeatStatement,
        lowering_ctx: StatementLoweringContext,
    ) -> list[IRStatement]:
        try:
            iterations = lowering_ctx.schedule_evaluator.eval_repeat_count(stmt.times, ctx=lowering_ctx.ctx)
        except ValueError:
            if lowering_ctx.static_control_classifier.can_defer_repeat_count(stmt.times, ctx=lowering_ctx.ctx):
                return self.lower_deferred_static_repeat(
                    stmt,
                    lowering_ctx,
                    self.count_repeat_schedule_expr(stmt),
                    binding=f"__repeat_index_{lowering_ctx.stmt_id.replace('.', '_')}",
                )
            raise
        expanded: list[IRStatement] = []
        runtime_control = any(
            lowering_ctx.schedule_evaluator.statement_requires_runtime_control(nested_stmt, ctx=lowering_ctx.ctx)
            for nested_stmt in stmt.statements
        )
        for iteration_index in range(iterations):
            nested_stmt_index = 0
            stop_all_iterations = False
            for nested_stmt in stmt.statements:
                compiled_nested = lowering_ctx.statement_compiler.compile(
                    nested_stmt,
                    ctx=lowering_ctx.ctx.derive(
                        scope_id=f"{lowering_ctx.stmt_id}.i{iteration_index}"
                        if runtime_control
                        else lowering_ctx.ctx.scope_id,
                    ),
                    stmt_index=nested_stmt_index if runtime_control else lowering_ctx.stmt_index + len(expanded),
                )
                expanded.extend(compiled_nested)
                nested_stmt_index += len(compiled_nested)
                if not runtime_control:
                    control_action = lowering_ctx.schedule_evaluator.static_control_action(compiled_nested)
                    if control_action == "continue":
                        break
                    if control_action == "break":
                        stop_all_iterations = True
                        break
            if stop_all_iterations:
                break
        return expanded

    def lower_deferred_static_repeat(
        self,
        stmt: RepeatStatement,
        lowering_ctx: StatementLoweringContext,
        iterable: Expression | None,
        *,
        binding: str | None = None,
        env_time_boundary_deferred: bool = False,
    ) -> list[IRStatement]:
        if iterable is None:
            raise ValueError("repeat binding form requires iterable expression")
        loop_binding = binding if binding is not None else stmt.binding
        if loop_binding is None:
            raise ValueError("repeat binding form requires loop binding")
        compiled_body = lowering_ctx.statement_compiler.compile_list(
            stmt.statements,
            ctx=lowering_ctx.ctx.derive(
                scope_id=f"{lowering_ctx.stmt_id}.b",
                const_env=lowering_ctx.ctx.const_env,
                let_bindings=dict(lowering_ctx.ctx.let_bindings),
                local_names=set(lowering_ctx.ctx.local_names) | {loop_binding},
                env_time_boundary_deferred=env_time_boundary_deferred,
            ),
        )
        return [
            IRRepeat(
                id=lowering_ctx.stmt_id,
                binding=loop_binding,
                iterable=lowering_ctx.expr_compiler.compile(iterable),
                statements=compiled_body,
                span=stmt.span,
            )
        ]

    def count_repeat_schedule_expr(self, stmt: RepeatStatement) -> CallExpr:
        if stmt.times is None:
            raise ValueError("repeat count requires count expression")
        return CallExpr(
            name="schedule",
            args=[
                Arg(name="start", value=Quantity(value=1.0, unit=None, span=stmt.times.span), span=stmt.times.span),
                Arg(name="end", value=stmt.times, span=stmt.times.span),
                Arg(name="step", value=Quantity(value=1.0, unit=None, span=stmt.times.span), span=stmt.times.span),
                Arg(name="__repeat_count", value=BooleanLiteral(value=True, span=stmt.times.span), span=stmt.times.span),
            ],
            span=stmt.times.span,
        )
