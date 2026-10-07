"""Representation-preserving binding and record projection for all value consumers.

This service resolves references, never coerces text to quantities and never
interprets domain namespaces or runtime material/data views.
"""
from __future__ import annotations

from culsma.common.quantity_arithmetic import quantity_result_unit

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Literal

from culsma.parser.ast_nodes import (
    Identifier, MemberExpr, RecordLiteral, StringLiteral, Quantity, ListLiteral,
    BooleanLiteral, BinaryOp, UnaryOp,
)
from culsma.pipeline.ir_nodes import (
    IRIdentifier, IRMember, IRRecord, IRString, IRQuantity, IRList, IRBoolean,
    IRBinary, IRUnary,
)


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
    if isinstance(expr, (Identifier, IRIdentifier)):
        name = expr.name
    elif isinstance(expr, dict) and expr.get("kind") == "IRIdentifier":
        name = expr.get("name")
    else:
        name = None
    if name is not None:
        if name in seen:
            return ExpressionResolution(ResolutionStatus.INVALID, expr, "binding_cycle", name)
        if name not in bindings:
            return ExpressionResolution(ResolutionStatus.DEFERRED, expr, detail=name)
        return resolve_expression(bindings[name], bindings, seen | {name})
    if isinstance(expr, (MemberExpr, IRMember)):
        base, member = expr.base, expr.member
    elif isinstance(expr, dict) and expr.get("kind") == "IRMember":
        base, member = expr.get("base"), expr.get("member")
    else:
        return ExpressionResolution(ResolutionStatus.RESOLVED, expr, visited=seen)
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


def quantity_expression_unit(expr: Any, bindings: Mapping[str, Any]) -> str | None:
    """Infer a validated expression's known unit using shared arithmetic rules.

    Unknown runtime values remain distinct from unitless scalars during
    inference; neither values nor dimensions are fabricated.
    """
    unknown = object()

    def infer(current: Any, seen: frozenset[Any]) -> Any:
        result = resolve_expression(current, bindings, seen)
        if result.status is not ResolutionStatus.RESOLVED:
            return unknown
        value = result.value
        if isinstance(value, (Quantity, IRQuantity)):
            return value.unit
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return None
        if isinstance(value, dict) and value.get("kind") == "IRQuantity":
            return value.get("unit")
        if isinstance(value, (UnaryOp, IRUnary)):
            return infer(value.operand, result.visited)
        if isinstance(value, dict) and value.get("kind") == "IRUnary":
            return infer(value.get("operand"), result.visited)
        if isinstance(value, (BinaryOp, IRBinary)):
            left, right, op = value.left, value.right, value.op
        elif isinstance(value, dict) and value.get("kind") == "IRBinary":
            left, right, op = value.get("left"), value.get("right"), value.get("op")
        else:
            return unknown
        if op not in {"+", "-", "*", "/"}:
            return unknown
        left_unit, right_unit = infer(left, result.visited), infer(right, result.visited)
        if left_unit is unknown or right_unit is unknown:
            return unknown
        return quantity_result_unit(op, left_unit, right_unit)

    unit = infer(expr, frozenset())
    return None if unit is unknown else unit
