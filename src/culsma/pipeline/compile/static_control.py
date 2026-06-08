"""Compile-stage classification for plan-time static control."""

from __future__ import annotations

from culsma.parser.ast_nodes import (
    BinaryOp,
    CallExpr,
    Expression,
    Identifier,
    IndexExpr,
    ListLiteral,
    MemberExpr,
    MethodCallExpr,
    PairExpr,
    RecordLiteral,
    SourcePartitionExpr,
    StringLiteral,
    UnaryOp,
    WithEnvStmt,
)

from .context import BlockContext


class StaticControlClassifier:
    def can_defer_repeat_count(self, expr: Expression | None, *, ctx: BlockContext) -> bool:
        return expr is not None and self.contains_unresolved_param_reference(expr, ctx=ctx)

    def can_defer_discrete_schedule(self, expr: Expression | None, *, ctx: BlockContext) -> bool:
        args = self.schedule_args(expr, ctx=ctx)
        if args is None or self.schedule_mode(args) != "discrete":
            return False
        if ctx.env_time_boundary_deferred and "end" not in args and "start" in args and "step" in args:
            return True
        return any(self.contains_unresolved_param_reference(value, ctx=ctx) for value in args.values())

    def can_defer_continuous_schedule(self, expr: Expression | None, *, ctx: BlockContext) -> bool:
        args = self.schedule_args(expr, ctx=ctx)
        if args is None or self.schedule_mode(args) != "continuous":
            return False
        return any(self.contains_unresolved_param_reference(value, ctx=ctx) for value in args.values())

    def can_defer_env_time_boundary(self, stmt: WithEnvStmt, *, ctx: BlockContext) -> bool:
        duration_arg = next((arg for arg in stmt.env_args if arg.name == "duration"), None)
        if duration_arg is not None:
            return self.contains_unresolved_param_reference(duration_arg.value, ctx=ctx)
        thermal_arg = next((arg for arg in stmt.env_args if arg.name == "thermal"), None)
        if thermal_arg is None:
            return False
        thermal_value = self.resolve_bound_expr(thermal_arg.value, ctx=ctx)
        if not isinstance(thermal_value, CallExpr) or thermal_value.name != "thermal_program":
            return False
        duration = next((arg for arg in thermal_value.args if arg.name == "duration"), None)
        return duration is not None and self.contains_unresolved_param_reference(duration.value, ctx=ctx)

    def schedule_args(self, expr: Expression | None, *, ctx: BlockContext) -> dict[str, Expression] | None:
        if expr is None:
            return None
        resolved = self.resolve_bound_expr(expr, ctx=ctx)
        if not isinstance(resolved, CallExpr) or resolved.name != "schedule":
            return None
        return {arg.name: self.resolve_bound_expr(arg.value, ctx=ctx) for arg in resolved.args}

    def schedule_mode(self, args: dict[str, Expression]) -> str | None:
        raw = args.get("mode")
        if raw is None:
            return "discrete"
        if isinstance(raw, Identifier) and raw.name in {"discrete", "continuous"}:
            return raw.name
        if isinstance(raw, StringLiteral) and raw.value in {"discrete", "continuous"}:
            return raw.value
        return None

    def resolve_bound_expr(self, expr: Expression, *, ctx: BlockContext) -> Expression:
        seen: set[str] = set()
        current = expr
        while isinstance(current, Identifier) and current.name in ctx.let_bindings:
            if current.name in seen:
                break
            seen.add(current.name)
            current = ctx.let_bindings[current.name]
        return current

    def contains_unresolved_param_reference(self, expr: Expression | None, *, ctx: BlockContext) -> bool:
        if expr is None:
            return False
        resolved = self.resolve_bound_expr(expr, ctx=ctx)
        if isinstance(resolved, Identifier):
            return resolved.name in ctx.param_names and resolved.name not in ctx.let_bindings
        if isinstance(resolved, BinaryOp):
            return self.contains_unresolved_param_reference(
                resolved.left,
                ctx=ctx,
            ) or self.contains_unresolved_param_reference(
                resolved.right,
                ctx=ctx,
            )
        if isinstance(resolved, UnaryOp):
            return self.contains_unresolved_param_reference(resolved.operand, ctx=ctx)
        if isinstance(resolved, ListLiteral):
            return any(self.contains_unresolved_param_reference(item, ctx=ctx) for item in resolved.elements)
        if isinstance(resolved, RecordLiteral):
            return any(self.contains_unresolved_param_reference(item, ctx=ctx) for item in resolved.entries.values())
        if isinstance(resolved, CallExpr):
            return any(self.contains_unresolved_param_reference(arg.value, ctx=ctx) for arg in resolved.args)
        if isinstance(resolved, IndexExpr):
            return self.contains_unresolved_param_reference(
                resolved.base,
                ctx=ctx,
            ) or self.contains_unresolved_param_reference(
                resolved.index,
                ctx=ctx,
            )
        if isinstance(resolved, MemberExpr):
            return self.contains_unresolved_param_reference(resolved.base, ctx=ctx)
        if isinstance(resolved, MethodCallExpr):
            return self.contains_unresolved_param_reference(
                resolved.base,
                ctx=ctx,
            ) or any(self.contains_unresolved_param_reference(arg, ctx=ctx) for arg in resolved.args)
        if isinstance(resolved, SourcePartitionExpr):
            return (
                self.contains_unresolved_param_reference(resolved.source, ctx=ctx)
                or self.contains_unresolved_param_reference(resolved.program, ctx=ctx)
                or self.contains_unresolved_param_reference(resolved.index, ctx=ctx)
            )
        if isinstance(resolved, PairExpr):
            return self.contains_unresolved_param_reference(
                resolved.left,
                ctx=ctx,
            ) or self.contains_unresolved_param_reference(
                resolved.right,
                ctx=ctx,
            )
        return False
