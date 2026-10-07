"""Representation-preserving binding and record projection for all value consumers.

This service resolves references, never coerces text to quantities and never
interprets domain namespaces or runtime material/data views.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Literal

from culsma.common.quantity_arithmetic import quantity_result_unit
from culsma.parser.ast_nodes import (
    Identifier, MemberExpr, RecordLiteral, StringLiteral, Quantity, ListLiteral,
    BooleanLiteral, BinaryOp, UnaryOp,
)
from culsma.pipeline.ir_nodes import (
    IRIdentifier, IRMember, IRRecord, IRString, IRQuantity, IRList, IRBoolean,
    IRBinary, IRUnary,
)


# Adapt AST, IR and serialized IR to the same structural fields. Semantic
# decisions stay in the resolver; adding a representation needs one table row.
_EXPRESSION_SHAPES = {
    "IRIdentifier": ("identifier", ("name",)),
    "IRMember": ("member", ("base", "member")),
    "IRQuantity": ("quantity", ("unit",)),
    "IRUnary": ("unary", ("operand",)),
    "IRBinary": ("binary", ("left", "right", "op")),
}
_NODE_SHAPES = {
    node_type: _EXPRESSION_SHAPES[tag]
    for tag, node_types in (
        ("IRIdentifier", (Identifier, IRIdentifier)),
        ("IRMember", (MemberExpr, IRMember)),
        ("IRQuantity", (Quantity, IRQuantity)),
        ("IRUnary", (UnaryOp, IRUnary)),
        ("IRBinary", (BinaryOp, IRBinary)),
    )
    for node_type in node_types
}


def _expression_parts(expr: Any) -> tuple[str | None, tuple[Any, ...]]:
    if isinstance(expr, dict):
        tag = expr.get("kind")
        shape = _EXPRESSION_SHAPES.get(tag) if isinstance(tag, str) else None
        if shape is None:
            return None, ()
        kind, fields = shape
        return kind, tuple(expr.get(field) for field in fields)
    shape = _NODE_SHAPES.get(type(expr))
    if shape is None:
        shape = next((_NODE_SHAPES[cls] for cls in type(expr).__mro__[1:] if cls in _NODE_SHAPES), None)
    if shape is None:
        return None, ()
    kind, fields = shape
    return kind, tuple(getattr(expr, field) for field in fields)


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    DEFERRED = "deferred"
    INVALID = "invalid"


@dataclass(frozen=True)
class ExpressionResolution:
    """Preserve the expression representation and per-call traversal history.

    Deferred values may contain partially resolved references. Consumers with
    domain namespace knowledge can finish resolving those references.
    """

    status: ResolutionStatus
    value: Any
    issue: Literal["missing_field", "non_record", "binding_cycle"] | None = None
    detail: str = ""
    visited: frozenset[Any] = frozenset()


def project_record_member(base: Any, member: str) -> ExpressionResolution:
    """Project a field without discarding its expression, unit or enum identity."""
    kind = base.get("kind") if isinstance(base, dict) else None
    serialized_expression = isinstance(kind, str) and (
        kind.startswith("IR")
        or kind in {"ContentEnum", "ExternalEnum", "DomainEnum", "ChromatographyEnum"}
    )
    if isinstance(base, (IRRecord, RecordLiteral)):
        entries = base.entries
    elif isinstance(base, dict) and not serialized_expression:
        entries = base
    else:
        entries = None
    if entries is not None:
        if member not in entries:
            return ExpressionResolution(ResolutionStatus.INVALID, base, "missing_field", member)
        return ExpressionResolution(ResolutionStatus.RESOLVED, entries[member])
    if kind in ("IRString", "IRQuantity", "IRBoolean", "IRList") or isinstance(base, (
        IRString, StringLiteral, IRQuantity, Quantity, IRList, ListLiteral,
        IRBoolean, BooleanLiteral, str, int, float, bool, list, tuple,
    )):
        return ExpressionResolution(ResolutionStatus.INVALID, base, "non_record", member)
    # Domain objects and unknown formal parameters retain their own semantics.
    return ExpressionResolution(ResolutionStatus.DEFERRED, base)


def resolve_expression(
    expr: Any, bindings: Mapping[str, Any], seen: frozenset[Any] = frozenset(),
) -> ExpressionResolution:
    """Resolve aliases and arbitrarily nested record fields with cycle protection."""
    kind, parts = _expression_parts(expr)
    name = parts[0] if kind == "identifier" else None
    if name is not None:
        if name in seen:
            return ExpressionResolution(ResolutionStatus.INVALID, expr, "binding_cycle", name)
        if name not in bindings:
            return ExpressionResolution(ResolutionStatus.DEFERRED, expr, detail=name)
        return resolve_expression(bindings[name], bindings, seen | {name})
    if kind != "member":
        return ExpressionResolution(ResolutionStatus.RESOLVED, expr, visited=seen)
    base, member = parts
    resolved = resolve_expression(base, bindings, seen)
    if resolved.status is not ResolutionStatus.RESOLVED:
        return ExpressionResolution(resolved.status, expr, resolved.issue, resolved.detail)
    selected = project_record_member(resolved.value, member)
    if selected.status is not ResolutionStatus.RESOLVED:
        return ExpressionResolution(selected.status, expr, selected.issue, selected.detail)
    # Keep base alias traversal separate from field-value traversal: two sibling
    # fields may legitimately refer to the same record. Track projection cycles.
    marker = (id(resolved.value), member)
    if marker in seen:
        return ExpressionResolution(ResolutionStatus.INVALID, expr, "binding_cycle", member)
    return resolve_expression(selected.value, bindings, seen | {marker})


# Distinguish an unknown unit from a known unitless scalar without call-local
# captured state. Traversal history and bindings remain explicit parameters.
UNKNOWN_UNIT = object()


def infer_quantity_unit(
    expr: Any, bindings: Mapping[str, Any], seen: frozenset[Any] = frozenset(),
) -> Any:
    """Return the known unit, unitless None, or the unknown-unit sentinel."""
    result = resolve_expression(expr, bindings, seen)
    if result.status is not ResolutionStatus.RESOLVED:
        return UNKNOWN_UNIT
    value = result.value
    kind, parts = _expression_parts(value)
    if kind == "quantity":
        return parts[0]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return None
    if kind == "unary":
        return infer_quantity_unit(parts[0], bindings, result.visited)
    if kind != "binary":
        return UNKNOWN_UNIT
    left, right, op = parts
    if op not in {"+", "-", "*", "/"}:
        return UNKNOWN_UNIT
    left_unit = infer_quantity_unit(left, bindings, result.visited)
    right_unit = infer_quantity_unit(right, bindings, result.visited)
    if left_unit is UNKNOWN_UNIT or right_unit is UNKNOWN_UNIT:
        return UNKNOWN_UNIT
    return quantity_result_unit(op, left_unit, right_unit)


def quantity_expression_unit(expr: Any, bindings: Mapping[str, Any]) -> str | None:
    """Infer a validated expression's unit; defer unknown values and cycles."""
    unit = infer_quantity_unit(expr, bindings)
    return None if unit is UNKNOWN_UNIT else unit
