"""Schedule evaluation and compile-time control helpers."""

from __future__ import annotations

from culsma.parser.ast_nodes import (
    Arg,
    AssignStatement,
    BinaryOp,
    BooleanLiteral,
    BreakStmt,
    CallExpr,
    ContinueStmt,
    Expression,
    Identifier,
    IfStatement,
    IndexExpr,
    LetStatement,
    ListLiteral,
    MemberExpr,
    MethodCallExpr,
    MutationStmt,
    PairExpr,
    Quantity,
    RecordLiteral,
    RepeatStatement,
    Statement,
    StepCall,
    StringLiteral,
    UnaryOp,
    WithConstraintStmt,
    WithEnvStmt,
)
from culsma.pipeline.ir_nodes import IRControl, IRStatement

from .context import BlockContext

_TIME_UNIT_SCALE = {
    "ms": 0.001,
    "s": 1.0,
    "sec": 1.0,
    "min": 60.0,
    "hr": 3600.0,
    "h": 3600.0,
}


class ScheduleEvaluator:
    def try_eval_numeric_expr(self, expr: Expression, *, ctx: BlockContext) -> float | None:
        return _try_eval_numeric_expr(expr, ctx.const_env)

    def try_eval_bool_expr(self, expr: Expression, *, ctx: BlockContext) -> bool | None:
        return _try_eval_bool_expr(expr, ctx.const_env)

    def resolve_repeat_iterable_values(self, expr: Expression, *, ctx: BlockContext) -> list[Expression] | None:
        return _resolve_repeat_iterable_values(expr, let_bindings=ctx.let_bindings)

    def resolve_schedule_mode(self, expr: Expression, *, ctx: BlockContext) -> str | None:
        return _resolve_schedule_mode(expr, let_bindings=ctx.let_bindings)

    def eval_continuous_schedule_boundary(self, expr: Expression, *, ctx: BlockContext) -> Quantity | None:
        return _eval_continuous_schedule_boundary(
            expr,
            let_bindings=ctx.let_bindings,
            env_time_boundary=ctx.env_time_boundary,
        )

    def eval_schedule_points(self, expr: Expression, *, ctx: BlockContext) -> list[Quantity]:
        return _eval_schedule_points(
            expr,
            let_bindings=ctx.let_bindings,
            env_time_boundary=ctx.env_time_boundary,
        )

    def eval_repeat_count(self, expr: Expression, *, ctx: BlockContext) -> int:
        return _eval_repeat_count(expr, ctx.const_env)

    def statement_requires_runtime_control(self, stmt: object, *, ctx: BlockContext) -> bool:
        return _statement_requires_runtime_control(stmt, ctx.const_env)

    def static_control_action(self, statements: list[IRStatement]) -> str | None:
        return _static_control_action(statements)

    def invalidate_runtime_mutated_names(self, statements: list[object], *, ctx: BlockContext) -> None:
        _invalidate_runtime_mutated_names(
            statements,
            const_env=ctx.const_env,
            let_bindings=ctx.let_bindings,
        )

    def substitute_statement(self, stmt: Statement, binding: str, value: Expression) -> Statement:
        return _substitute_statement(stmt, binding, value)

    def resolve_bound_expr(self, expr: Expression, *, ctx: BlockContext) -> Expression:
        seen: set[str] = set()
        current = expr
        while isinstance(current, Identifier) and current.name in ctx.let_bindings:
            if current.name in seen:
                break
            seen.add(current.name)
            current = ctx.let_bindings[current.name]
        return current

    def extract_env_time_boundary(self, stmt: WithEnvStmt, *, ctx: BlockContext) -> Quantity | None:
        duration_arg = next((arg for arg in stmt.env_args if arg.name == "duration"), None)
        if duration_arg is not None:
            resolved = self.resolve_bound_expr(duration_arg.value, ctx=ctx)
            return resolved if isinstance(resolved, Quantity) and self.is_time_point(resolved) else None

        thermal_arg = next((arg for arg in stmt.env_args if arg.name == "thermal"), None)
        if thermal_arg is None:
            return None
        thermal_value = self.resolve_bound_expr(thermal_arg.value, ctx=ctx)
        if not isinstance(thermal_value, CallExpr) or thermal_value.name != "thermal_program":
            return None
        duration = next((arg for arg in thermal_value.args if arg.name == "duration"), None)
        if duration is None:
            return None
        resolved = self.resolve_bound_expr(duration.value, ctx=ctx)
        return resolved if isinstance(resolved, Quantity) and self.is_time_point(resolved) else None

    def supports_runtime_boolean_surface(self, expr: Expression) -> bool:
        if isinstance(expr, (BooleanLiteral, Identifier, MemberExpr, MethodCallExpr)):
            return True
        if not isinstance(expr, BinaryOp):
            return False
        if expr.op in {"and", "or"}:
            return self.supports_runtime_boolean_surface(expr.left) and self.supports_runtime_boolean_surface(expr.right)
        return expr.op in {"==", "!=", "<", ">", "<=", ">="}

    def is_time_point(self, point: Quantity) -> bool:
        return point.unit in _TIME_UNIT_SCALE


def _static_control_action(statements: list[IRStatement]) -> str | None:
    for stmt in statements:
        if isinstance(stmt, IRControl):
            return stmt.action
    return None


def _invalidate_runtime_mutated_names(
    statements: list[object],
    *,
    const_env: dict[str, float | bool],
    let_bindings: dict[str, Expression],
) -> None:
    for name in _assigned_names_in_statements(statements):
        const_env.pop(name, None)
        let_bindings.pop(name, None)


def _assigned_names_in_statements(statements: list[object]) -> set[str]:
    names: set[str] = set()
    for stmt in statements:
        if isinstance(stmt, AssignStatement) and isinstance(stmt.target, Identifier):
            names.add(stmt.target.name)
        elif isinstance(stmt, RepeatStatement):
            names.update(_assigned_names_in_statements(stmt.statements))
        elif isinstance(stmt, IfStatement):
            names.update(_assigned_names_in_statements(stmt.then_statements))
            names.update(_assigned_names_in_statements(stmt.else_statements))
        elif isinstance(stmt, WithEnvStmt):
            names.update(_assigned_names_in_statements(stmt.statements))
        elif isinstance(stmt, WithConstraintStmt):
            names.update(_assigned_names_in_statements(stmt.statements))
    return names


def _eval_schedule_points(
    expr: Expression | None,
    *,
    let_bindings: dict[str, Expression],
    env_time_boundary: Quantity | None,
) -> list[Expression]:
    if expr is None:
        raise ValueError("repeat binding form requires iterable expression")
    resolved = _resolve_let_bound_expr(expr, let_bindings)
    if not isinstance(resolved, CallExpr) or resolved.name != "schedule":
        raise ValueError("repeat <name> in ... requires schedule(...)")

    args = {arg.name: _resolve_let_bound_expr(arg.value, let_bindings) for arg in resolved.args}
    mode = _schedule_mode_from_args(args)
    if mode != "discrete":
        raise ValueError("schedule(mode=continuous) cannot be expanded as discrete points")
    if "duration" in args or "observe_every" in args or "control_every" in args:
        raise ValueError("discrete schedule does not allow duration, observe_every, or control_every")
    has_at = "at" in args
    has_interval_shape = any(name in args for name in {"start", "step", "end"})
    if has_at == has_interval_shape:
        raise ValueError("schedule(...) must use either start/end/step or at=[...]")

    if has_at:
        at_value = args["at"]
        if not isinstance(at_value, ListLiteral) or not at_value.elements:
            raise ValueError("schedule(at=[...]) requires non-empty list")
        points = [_resolve_schedule_point(item) for item in at_value.elements]
        _validate_schedule_point_list(points)
        if _is_time_point_list(points):
            boundary = env_time_boundary
            if boundary is not None:
                boundary_seconds = _time_quantity_to_seconds(boundary)
                max_seconds = max(_time_quantity_to_seconds(point) for point in points)
                if boundary_seconds is not None and max_seconds > boundary_seconds + 1e-9:
                    raise ValueError("env-bound time schedule exceeds enclosing env boundary")
        return points

    start = args.get("start")
    step = args.get("step")
    end = args.get("end")
    if start is None or step is None:
        raise ValueError("schedule(start=..., step=...) requires start and step")

    start_point = _resolve_schedule_point(start)
    step_point = _resolve_schedule_point(step)
    if _is_time_point(start_point):
        if not _is_time_point(step_point):
            raise ValueError("schedule start/end/step types must be consistent")
        effective_end = end
        if effective_end is None:
            if env_time_boundary is None:
                raise ValueError("time schedule without end requires enclosing env boundary")
            effective_end = env_time_boundary
        end_point = _resolve_schedule_point(effective_end)
        if not _is_time_point(end_point):
            raise ValueError("schedule start/end/step types must be consistent")
        return _expand_time_schedule_points(start_point, end_point, step_point, env_time_boundary)

    if _is_unitless_int_point(start_point):
        if not _is_unitless_int_point(step_point):
            raise ValueError("schedule start/end/step types must be consistent")
        if end is None:
            raise ValueError("count schedule requires explicit end")
        end_point = _resolve_schedule_point(end)
        if not _is_unitless_int_point(end_point):
            raise ValueError("schedule start/end/step types must be consistent")
        return _expand_count_schedule_points(start_point, end_point, step_point)

    raise ValueError("schedule(...) supports only time quantities or unitless integer points")


def _resolve_repeat_iterable_values(
    expr: Expression | None,
    *,
    let_bindings: dict[str, Expression],
) -> list[Expression] | None:
    if expr is None:
        raise ValueError("repeat binding form requires iterable expression")
    resolved = _resolve_let_bound_expr(expr, let_bindings)
    if isinstance(resolved, ListLiteral):
        return list(resolved.elements)
    return None


def _resolve_schedule_mode(
    expr: Expression | None,
    *,
    let_bindings: dict[str, Expression],
) -> str:
    if expr is None:
        raise ValueError("repeat binding form requires iterable expression")
    resolved = _resolve_let_bound_expr(expr, let_bindings)
    if not isinstance(resolved, CallExpr) or resolved.name != "schedule":
        raise ValueError("repeat <name> in ... requires schedule(...)")
    args = {arg.name: _resolve_let_bound_expr(arg.value, let_bindings) for arg in resolved.args}
    return _schedule_mode_from_args(args)


def _schedule_mode_from_args(args: dict[str, Expression]) -> str:
    raw = args.get("mode")
    if raw is None:
        return "discrete"
    if isinstance(raw, Identifier) and raw.name in {"discrete", "continuous"}:
        return raw.name
    if isinstance(raw, StringLiteral) and raw.value in {"discrete", "continuous"}:
        return raw.value
    raise ValueError("schedule mode must be discrete or continuous")


def _eval_continuous_schedule_boundary(
    expr: Expression | None,
    *,
    let_bindings: dict[str, Expression],
    env_time_boundary: Quantity | None,
) -> Quantity:
    if expr is None:
        raise ValueError("repeat binding form requires iterable expression")
    resolved = _resolve_let_bound_expr(expr, let_bindings)
    if not isinstance(resolved, CallExpr) or resolved.name != "schedule":
        raise ValueError("repeat <name> in ... requires schedule(...)")

    args = {arg.name: _resolve_let_bound_expr(arg.value, let_bindings) for arg in resolved.args}
    mode = _schedule_mode_from_args(args)
    if mode != "continuous":
        raise ValueError("continuous schedule boundary requires mode=continuous")
    if "at" in args or "step" in args:
        raise ValueError("schedule(mode=continuous) does not allow at or step")
    if "observe_every" in args:
        observe = args["observe_every"]
        if not isinstance(observe, Quantity) or not _is_time_point(observe):
            raise ValueError("schedule(mode=continuous) observe_every must be a time quantity")
    if "control_every" in args:
        control = args["control_every"]
        if not isinstance(control, Quantity) or not _is_time_point(control):
            raise ValueError("schedule(mode=continuous) control_every must be a time quantity")

    start = args.get("start")
    if not isinstance(start, Quantity) or not _is_time_point(start):
        raise ValueError("schedule(mode=continuous) requires time-valued start")

    duration = args.get("duration")
    end = args.get("end")
    if duration is None and end is None:
        raise ValueError("schedule(mode=continuous) requires end or duration")
    if duration is not None and end is not None:
        raise ValueError("schedule(mode=continuous) must not use both end and duration")

    if duration is not None:
        if not isinstance(duration, Quantity) or not _is_time_point(duration):
            raise ValueError("schedule(mode=continuous) duration must be a time quantity")
        boundary = duration
    else:
        assert end is not None
        if not isinstance(end, Quantity) or not _is_time_point(end):
            raise ValueError("schedule(mode=continuous) end must be a time quantity")
        start_seconds = _time_quantity_to_seconds(start)
        end_seconds = _time_quantity_to_seconds(end)
        if start_seconds is None or end_seconds is None:
            raise ValueError("schedule(mode=continuous) start/end must use supported time units")
        if end_seconds < start_seconds - 1e-9:
            raise ValueError("schedule(mode=continuous) end must be >= start")
        boundary = Quantity(value=_seconds_to_unit(end_seconds - start_seconds, start.unit), unit=start.unit, span=start.span)

    if env_time_boundary is not None:
        boundary_seconds = _time_quantity_to_seconds(boundary)
        outer_seconds = _time_quantity_to_seconds(env_time_boundary)
        if boundary_seconds is not None and outer_seconds is not None and boundary_seconds > outer_seconds + 1e-9:
            raise ValueError("continuous schedule window exceeds enclosing boundary")
    return boundary


def _resolve_schedule_point(expr: Expression) -> Quantity:
    if isinstance(expr, Quantity):
        return expr
    raise ValueError("schedule points must be quantity literals or let-bound quantity literals")


def _validate_schedule_point_list(points: list[Quantity]) -> None:
    first = points[0]
    if _is_time_point(first):
        if not all(_is_time_point(point) for point in points):
            raise ValueError("schedule(at=[...]) points must use consistent types")
        return
    if _is_unitless_int_point(first):
        if not all(_is_unitless_int_point(point) for point in points):
            raise ValueError("schedule(at=[...]) points must use consistent types")
        return
    raise ValueError("schedule(at=[...]) supports only time quantities or unitless integer points")


def _expand_time_schedule_points(
    start: Quantity,
    end: Quantity,
    step: Quantity,
    env_time_boundary: Quantity | None,
) -> list[Expression]:
    start_seconds = _time_quantity_to_seconds(start)
    end_seconds = _time_quantity_to_seconds(end)
    step_seconds = _time_quantity_to_seconds(step)
    if start_seconds is None or end_seconds is None or step_seconds is None:
        raise ValueError("schedule time points must use supported time units")
    if step_seconds <= 0:
        raise ValueError("schedule time step must be > 0")
    effective_end_seconds = end_seconds
    if env_time_boundary is not None:
        boundary_seconds = _time_quantity_to_seconds(env_time_boundary)
        if boundary_seconds is not None and effective_end_seconds > boundary_seconds + 1e-9:
            raise ValueError("env-bound time schedule exceeds enclosing env boundary")
    if start_seconds > effective_end_seconds + 1e-9:
        return []

    points: list[Expression] = []
    current = start_seconds
    while current <= effective_end_seconds + 1e-9:
        points.append(Quantity(value=_seconds_to_unit(current, start.unit), unit=start.unit, span=start.span))
        current += step_seconds
    return points


def _expand_count_schedule_points(start: Quantity, end: Quantity, step: Quantity) -> list[Expression]:
    start_value = int(start.value)
    end_value = int(end.value)
    step_value = int(step.value)
    if step_value <= 0:
        raise ValueError("schedule count step must be > 0")
    if start_value > end_value:
        return []
    return [Quantity(value=float(v), unit=None, span=start.span) for v in range(start_value, end_value + 1, step_value)]


def _resolve_let_bound_expr(expr: Expression, let_bindings: dict[str, Expression]) -> Expression:
    seen: set[str] = set()
    current = expr
    while isinstance(current, Identifier) and current.name in let_bindings:
        if current.name in seen:
            break
        seen.add(current.name)
        current = let_bindings[current.name]
    return current


def _substitute_statement(stmt, binding: str, value: Expression):
    if isinstance(stmt, LetStatement):
        return LetStatement(name=stmt.name, value=_substitute_expr(stmt.value, binding, value), span=stmt.span)
    if isinstance(stmt, AssignStatement):
        return AssignStatement(target=_substitute_expr(stmt.target, binding, value), value=_substitute_expr(stmt.value, binding, value), span=stmt.span)
    if isinstance(stmt, StepCall):
        return StepCall(
            name=stmt.name,
            args=[Arg(name=arg.name, value=_substitute_expr(arg.value, binding, value), span=arg.span) for arg in stmt.args],
            span=stmt.span,
        )
    if isinstance(stmt, WithEnvStmt):
        return WithEnvStmt(
            env_args=[Arg(name=arg.name, value=_substitute_expr(arg.value, binding, value), span=arg.span) for arg in stmt.env_args],
            statements=[_substitute_statement(nested, binding, value) for nested in stmt.statements],
            span=stmt.span,
        )
    if isinstance(stmt, WithConstraintStmt):
        return WithConstraintStmt(
            requirements=list(stmt.requirements),
            options=[Arg(name=arg.name, value=_substitute_expr(arg.value, binding, value), span=arg.span) for arg in stmt.options],
            statements=[_substitute_statement(nested, binding, value) for nested in stmt.statements],
            span=stmt.span,
        )
    if isinstance(stmt, MutationStmt):
        return MutationStmt(
            target=_substitute_expr(stmt.target, binding, value),
            sources=[_substitute_expr(source, binding, value) for source in stmt.sources],
            span=stmt.span,
        )
    if isinstance(stmt, RepeatStatement):
        return RepeatStatement(
            times=_substitute_expr(stmt.times, binding, value) if stmt.times is not None else None,
            binding=stmt.binding,
            iterable=_substitute_expr(stmt.iterable, binding, value) if stmt.iterable is not None else None,
            statements=[_substitute_statement(nested, binding, value) for nested in stmt.statements],
            span=stmt.span,
        )
    if isinstance(stmt, IfStatement):
        return IfStatement(
            condition=_substitute_expr(stmt.condition, binding, value),
            then_statements=[_substitute_statement(nested, binding, value) for nested in stmt.then_statements],
            else_statements=[_substitute_statement(nested, binding, value) for nested in stmt.else_statements],
            span=stmt.span,
        )
    return stmt


def _substitute_expr(expr: Expression, binding: str, value: Expression) -> Expression:
    if isinstance(expr, Identifier):
        return value if expr.name == binding else expr
    if isinstance(expr, BinaryOp):
        return BinaryOp(op=expr.op, left=_substitute_expr(expr.left, binding, value), right=_substitute_expr(expr.right, binding, value), span=expr.span)
    if isinstance(expr, UnaryOp):
        return UnaryOp(op=expr.op, operand=_substitute_expr(expr.operand, binding, value), span=expr.span)
    if isinstance(expr, ListLiteral):
        return ListLiteral(elements=[_substitute_expr(item, binding, value) for item in expr.elements], span=expr.span)
    if isinstance(expr, RecordLiteral):
        return RecordLiteral(
            entries={key: _substitute_expr(record_value, binding, value) for key, record_value in expr.entries.items()},
            span=expr.span,
        )
    if isinstance(expr, CallExpr):
        return CallExpr(
            name=expr.name,
            args=[Arg(name=arg.name, value=_substitute_expr(arg.value, binding, value), span=arg.span) for arg in expr.args],
            span=expr.span,
        )
    if isinstance(expr, IndexExpr):
        return IndexExpr(base=_substitute_expr(expr.base, binding, value), index=_substitute_expr(expr.index, binding, value), span=expr.span)
    if isinstance(expr, MemberExpr):
        return MemberExpr(base=_substitute_expr(expr.base, binding, value), member=expr.member, span=expr.span)
    if isinstance(expr, PairExpr):
        return PairExpr(left=_substitute_expr(expr.left, binding, value), right=_substitute_expr(expr.right, binding, value), span=expr.span)
    return expr


def _is_time_point(point: Quantity) -> bool:
    return point.unit in _TIME_UNIT_SCALE


def _is_unitless_int_point(point: Quantity) -> bool:
    return point.unit is None and float(point.value).is_integer()


def _is_time_point_list(points: list[Quantity]) -> bool:
    return bool(points) and _is_time_point(points[0])


def _time_quantity_to_seconds(quantity: Quantity) -> float | None:
    if quantity.unit not in _TIME_UNIT_SCALE:
        return None
    return float(quantity.value) * _TIME_UNIT_SCALE[quantity.unit]


def _seconds_to_unit(seconds: float, unit: str | None) -> float:
    if unit is None or unit not in _TIME_UNIT_SCALE:
        return seconds
    return seconds / _TIME_UNIT_SCALE[unit]


def _eval_repeat_count(expr: Expression, const_env: dict[str, float | bool]) -> int:
    value = _try_eval_numeric_expr(expr, const_env)
    if value is None:
        raise ValueError("repeat count must be a unitless numeric expression")
    if value < 0:
        raise ValueError("repeat count must be >= 0")
    if not float(value).is_integer():
        raise ValueError("repeat count must be an integer")
    return int(value)


def _statement_requires_runtime_control(stmt: object, const_env: dict[str, float | bool]) -> bool:
    if isinstance(stmt, (BreakStmt, ContinueStmt)):
        return True
    if isinstance(stmt, IfStatement):
        condition = _try_eval_bool_expr(stmt.condition, const_env)
        if condition is None:
            return True
        selected = stmt.then_statements if condition else stmt.else_statements
        return any(_statement_requires_runtime_control(nested, const_env) for nested in selected)
    if isinstance(stmt, RepeatStatement):
        return any(_statement_requires_runtime_control(nested, const_env) for nested in stmt.statements)
    if isinstance(stmt, WithEnvStmt):
        return any(_statement_requires_runtime_control(nested, const_env) for nested in stmt.statements)
    if isinstance(stmt, WithConstraintStmt):
        return any(_statement_requires_runtime_control(nested, const_env) for nested in stmt.statements)
    return False


def _try_eval_numeric_expr(expr: Expression, const_env: dict[str, float | bool]) -> float | None:
    if isinstance(expr, Quantity):
        if expr.unit is not None:
            return None
        return float(expr.value)
    if isinstance(expr, Identifier):
        value = const_env.get(expr.name)
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        return None
    if isinstance(expr, UnaryOp):
        operand = _try_eval_numeric_expr(expr.operand, const_env)
        if operand is None:
            return None
        if expr.op == "-":
            return -operand
        return None
    if isinstance(expr, BinaryOp):
        left = _try_eval_numeric_expr(expr.left, const_env)
        right = _try_eval_numeric_expr(expr.right, const_env)
        if left is None or right is None:
            return None
        if expr.op == "+":
            return left + right
        if expr.op == "-":
            return left - right
        if expr.op == "*":
            return left * right
        if expr.op == "/":
            if right == 0:
                raise ValueError("repeat count expression division by zero")
            return left / right
        return None
    return None


def _try_eval_bool_expr(expr: Expression, const_env: dict[str, float | bool]) -> bool | None:
    if isinstance(expr, BooleanLiteral):
        return bool(expr.value)
    if isinstance(expr, Identifier):
        value = const_env.get(expr.name)
        if isinstance(value, bool):
            return value
        return None
    if isinstance(expr, BinaryOp):
        if expr.op in {"and", "or"}:
            left = _try_eval_bool_expr(expr.left, const_env)
            right = _try_eval_bool_expr(expr.right, const_env)
            if left is None or right is None:
                return None
            return (left and right) if expr.op == "and" else (left or right)
        if expr.op in {"==", "!="}:
            left_qty = _try_eval_quantity_expr(expr.left)
            right_qty = _try_eval_quantity_expr(expr.right)
            if left_qty is not None and right_qty is not None:
                return (left_qty == right_qty) if expr.op == "==" else (left_qty != right_qty)
            left_bool = _try_eval_bool_expr(expr.left, const_env)
            right_bool = _try_eval_bool_expr(expr.right, const_env)
            if left_bool is not None and right_bool is not None:
                return (left_bool == right_bool) if expr.op == "==" else (left_bool != right_bool)
            left_num = _try_eval_numeric_expr(expr.left, const_env)
            right_num = _try_eval_numeric_expr(expr.right, const_env)
            if left_num is None or right_num is None:
                return None
            return (left_num == right_num) if expr.op == "==" else (left_num != right_num)
        if expr.op in {"<", ">", "<=", ">="}:
            left_qty = _try_eval_quantity_expr(expr.left)
            right_qty = _try_eval_quantity_expr(expr.right)
            if left_qty is not None and right_qty is not None:
                if expr.op == "<":
                    return left_qty < right_qty
                if expr.op == ">":
                    return left_qty > right_qty
                if expr.op == "<=":
                    return left_qty <= right_qty
                return left_qty >= right_qty
            left = _try_eval_numeric_expr(expr.left, const_env)
            right = _try_eval_numeric_expr(expr.right, const_env)
            if left is None or right is None:
                return None
            if expr.op == "<":
                return left < right
            if expr.op == ">":
                return left > right
            if expr.op == "<=":
                return left <= right
            return left >= right
    return None


def _try_eval_quantity_expr(expr: Expression) -> float | None:
    if not isinstance(expr, Quantity) or expr.unit is None:
        return None
    seconds = _time_quantity_to_seconds(expr)
    if seconds is not None:
        return seconds
    return None
