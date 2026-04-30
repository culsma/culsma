"""Local expression resolution helpers for semantic validation."""

from __future__ import annotations

from typing import Any

from culsma.pipeline.ir_nodes import IRCall, IRIdentifier, IRList, IRQuantity, IRString, IRUnary


class ExprResolver:
    @staticmethod
    def resolve_bound_expr(expr: Any, expr_bindings: dict[str, Any]) -> Any:
        seen: set[str] = set()
        current = expr
        while isinstance(current, IRIdentifier) and current.name in expr_bindings and current.name not in seen:
            seen.add(current.name)
            current = expr_bindings[current.name]
        return current

    @staticmethod
    def resolve_call_expr(expr: Any, expr_bindings: dict[str, Any]) -> IRCall | None:
        resolved = ExprResolver.resolve_bound_expr(expr, expr_bindings)
        return resolved if isinstance(resolved, IRCall) else None

    @staticmethod
    def resolve_static_index_value(
        expr: Any,
        *,
        literal_bindings: dict[str, Any],
        expr_bindings: dict[str, Any],
    ) -> tuple[int | None, str | None]:
        number = ExprResolver.to_number(expr, literal_bindings)
        if number is not None:
            if number < 0 or not float(number).is_integer():
                return None, "not_nonnegative_integer"
            return int(number), None

        resolved = ExprResolver.resolve_bound_expr(expr, expr_bindings)
        if isinstance(resolved, IRQuantity):
            if resolved.unit is not None:
                return None, "not_nonnegative_integer"
            if resolved.value < 0 or not float(resolved.value).is_integer():
                return None, "not_nonnegative_integer"
            return int(resolved.value), None
        if isinstance(resolved, IRUnary) and resolved.op == "-":
            inner_number = ExprResolver.to_number(resolved, literal_bindings)
            if inner_number is None:
                return None, "not_nonnegative_integer"
            return None, "not_nonnegative_integer"
        return None, "not_static"

    @staticmethod
    def to_string(expr: Any, literal_bindings: dict[str, Any]) -> str | None:
        if isinstance(expr, IRString):
            return expr.value
        if isinstance(expr, IRIdentifier):
            bound = literal_bindings.get(expr.name)
            return bound if isinstance(bound, str) else None
        return None

    @staticmethod
    def to_text_token(expr: Any, literal_bindings: dict[str, Any]) -> str | None:
        if isinstance(expr, IRString):
            return expr.value
        if isinstance(expr, IRIdentifier):
            bound = literal_bindings.get(expr.name)
            if isinstance(bound, str):
                return bound
            return expr.name
        return None

    @staticmethod
    def to_name_ref(expr: Any, literal_bindings: dict[str, Any]) -> str | None:
        if isinstance(expr, IRString):
            return expr.value
        if isinstance(expr, IRIdentifier):
            bound = literal_bindings.get(expr.name)
            if isinstance(bound, str):
                return bound
            return expr.name
        return None

    @staticmethod
    def to_number(expr: Any, literal_bindings: dict[str, Any]) -> float | None:
        if isinstance(expr, IRQuantity) and expr.unit is None:
            return float(expr.value)
        if isinstance(expr, IRUnary) and expr.op == "-":
            inner = ExprResolver.to_number(expr.operand, literal_bindings)
            return None if inner is None else -inner
        if isinstance(expr, IRIdentifier):
            bound = literal_bindings.get(expr.name)
            if isinstance(bound, (int, float)):
                return float(bound)
        return None

    @staticmethod
    def to_string_list(expr: Any, literal_bindings: dict[str, Any]) -> list[str] | None:
        if isinstance(expr, IRList):
            values: list[str] = []
            for item in expr.elements:
                resolved = ExprResolver.to_string(item, literal_bindings)
                if resolved is None:
                    return None
                values.append(resolved)
            return values
        if isinstance(expr, IRIdentifier):
            bound = literal_bindings.get(expr.name)
            if isinstance(bound, list) and all(isinstance(v, str) for v in bound):
                return list(bound)
        return None
