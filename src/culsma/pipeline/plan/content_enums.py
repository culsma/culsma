"""Explicit execution boundary until content enum runtime support is connected."""

from __future__ import annotations

from typing import Any

from culsma.common.content_contracts import CONTENT_ENUM_TYPES
from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.plan_nodes import PlanProgram


def contains_member_expression(value: Any) -> bool:
    if isinstance(value, dict):
        return value.get("kind") == "IRMember" or any(contains_member_expression(item) for item in value.values())
    return isinstance(value, list) and any(contains_member_expression(item) for item in value)


def has_unlowered_content_enum(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("kind") == "IRMember":
            base = value.get("base")
            if isinstance(base, dict) and base.get("kind") == "IRIdentifier" and base.get("name") in CONTENT_ENUM_TYPES:
                return True
        if value.get("op", value.get("name")) in {"AllocContainer", "DefineContent"}:
            args = value.get("args")
            if isinstance(args, dict):
                if any(contains_member_expression(args.get(name)) for name in ("kind", "type")):
                    return True
            elif isinstance(args, list):
                if any(isinstance(arg, dict) and arg.get("name") in {"kind", "type"}
                       and contains_member_expression(arg.get("value")) for arg in args):
                    return True
        return any(has_unlowered_content_enum(item) for item in value.values())
    return isinstance(value, list) and any(has_unlowered_content_enum(item) for item in value)


def guard_content_enum_execution(plan: PlanProgram) -> PlanProgram:
    """Never execute a partially supported enum as an empty material classification."""
    if not has_unlowered_content_enum(plan.to_dict()):
        return plan
    return PlanProgram(
        plans=[],
        diagnostics=[*plan.diagnostics, Diagnostic(
            code="PLAN_CONTENT_ENUM_EXECUTION_UNSUPPORTED",
            message="Explicit content enums currently support semantic and type checking only; "
                    "execution requires the planned enum runtime support. Use compatible text inputs for execution.",
            span=plan.span,
        )],
        span=plan.span,
    )
