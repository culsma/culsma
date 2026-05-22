"""Expression-level semantic validation contracts."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import (
    IRBinary,
    IRCall,
    IRGroup,
    IRIndex,
    IRList,
    IRMember,
    IRPair,
    IRPlateSelector,
    IRRecord,
    IRUnary,
)

from .constructors import ConstructorValidator
from .context import _GroupBinding
from .groups import GroupIndexValidator
from .programs import ProgramContractValidator, is_legacy_program_kind, is_program_kind

PROGRAM_OWNER_FAMILY = {"sep", "frac", "img", "ecp", "phy"}


def validate_expr_contracts(
    expr: Any,
    *,
    literal_bindings: dict[str, Any],
    expr_bindings: dict[str, Any],
    group_bindings: dict[str, _GroupBinding],
    node_id: str | None,
    content_whitelist_mode: str = "strict",
    content_type_policy: str = "required",
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    if isinstance(expr, IRIndex):
        diagnostics.extend(
            GroupIndexValidator.validate_index(
                expr,
                literal_bindings=literal_bindings,
                expr_bindings=expr_bindings,
                group_bindings=group_bindings,
                node_id=node_id,
            )
        )
        diagnostics.extend(
            validate_expr_contracts(
                expr.base,
                literal_bindings=literal_bindings,
                expr_bindings=expr_bindings,
                group_bindings=group_bindings,
                node_id=node_id,
                content_whitelist_mode=content_whitelist_mode,
                content_type_policy=content_type_policy,
            )
        )
        diagnostics.extend(
            validate_expr_contracts(
                expr.index,
                literal_bindings=literal_bindings,
                expr_bindings=expr_bindings,
                group_bindings=group_bindings,
                node_id=node_id,
                content_whitelist_mode=content_whitelist_mode,
                content_type_policy=content_type_policy,
            )
        )
        return diagnostics

    if isinstance(expr, IRCall):
        if is_legacy_program_kind(expr.name):
            diagnostics.append(
                Diagnostic(
                    code="SEM_LEGACY_PROGRAM_FORM_FORBIDDEN",
                    message=f"Legacy generic program '{expr.name}' is forbidden; use a concrete *_program(...) constructor",
                    span=expr.span,
                    node_id=node_id,
                )
            )
        elif is_program_kind(expr.name):
            diagnostics.extend(
                ProgramContractValidator.validate_program_call(
                    expr,
                    literal_bindings=literal_bindings,
                    node_id=node_id,
                )
            )
        elif expr.name.endswith("_program") and expr.name != "thermal_program":
            diagnostics.append(
                Diagnostic(
                    code="SEM_PROGRAM_KIND_INVALID",
                    message=f"Unknown concrete program kind '{expr.name}'",
                    span=expr.span,
                    node_id=node_id,
                )
            )
        if expr.name in PROGRAM_OWNER_FAMILY:
            diagnostics.extend(
                ProgramContractValidator.validate_owner_program_arg(
                    owner=expr.name,
                    call=expr,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                    node_id=node_id,
                )
            )
        if expr.name == "AllocContainer":
            diagnostics.extend(
                ConstructorValidator.validate_alloc_container_call(
                    expr,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                    node_id=node_id,
                    content_whitelist_mode=content_whitelist_mode,
                    content_type_policy=content_type_policy,
                )
            )
        if expr.name == "DefineContent":
            diagnostics.extend(
                ConstructorValidator.validate_define_content_call(
                    expr,
                    literal_bindings=literal_bindings,
                    node_id=node_id,
                    content_whitelist_mode=content_whitelist_mode,
                    content_type_policy=content_type_policy,
                )
            )
        for arg in expr.args:
            diagnostics.extend(
                validate_expr_contracts(
                    arg.value,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                    group_bindings=group_bindings,
                    node_id=node_id,
                    content_whitelist_mode=content_whitelist_mode,
                    content_type_policy=content_type_policy,
                )
            )
        return diagnostics

    if isinstance(expr, IRGroup):
        for item in expr.elements:
            diagnostics.extend(
                validate_expr_contracts(
                    item,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                    group_bindings=group_bindings,
                    node_id=node_id,
                    content_whitelist_mode=content_whitelist_mode,
                    content_type_policy=content_type_policy,
                )
            )
        return diagnostics

    if isinstance(expr, IRPlateSelector):
        return diagnostics

    if isinstance(expr, IRList):
        for item in expr.elements:
            diagnostics.extend(
                validate_expr_contracts(
                    item,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                    group_bindings=group_bindings,
                    node_id=node_id,
                    content_whitelist_mode=content_whitelist_mode,
                    content_type_policy=content_type_policy,
                )
            )
        return diagnostics

    if isinstance(expr, IRRecord):
        for value in expr.entries.values():
            diagnostics.extend(
                validate_expr_contracts(
                    value,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                    group_bindings=group_bindings,
                    node_id=node_id,
                    content_whitelist_mode=content_whitelist_mode,
                    content_type_policy=content_type_policy,
                )
            )
        return diagnostics

    if isinstance(expr, IRPair):
        diagnostics.extend(
            validate_expr_contracts(
                expr.left,
                literal_bindings=literal_bindings,
                expr_bindings=expr_bindings,
                group_bindings=group_bindings,
                node_id=node_id,
                content_whitelist_mode=content_whitelist_mode,
                content_type_policy=content_type_policy,
            )
        )
        diagnostics.extend(
            validate_expr_contracts(
                expr.right,
                literal_bindings=literal_bindings,
                expr_bindings=expr_bindings,
                group_bindings=group_bindings,
                node_id=node_id,
                content_whitelist_mode=content_whitelist_mode,
                content_type_policy=content_type_policy,
            )
        )
        return diagnostics

    if isinstance(expr, IRMember):
        return validate_expr_contracts(
            expr.base,
            literal_bindings=literal_bindings,
            expr_bindings=expr_bindings,
            group_bindings=group_bindings,
            node_id=node_id,
            content_whitelist_mode=content_whitelist_mode,
            content_type_policy=content_type_policy,
        )

    if isinstance(expr, IRUnary):
        return validate_expr_contracts(
            expr.operand,
            literal_bindings=literal_bindings,
            expr_bindings=expr_bindings,
            group_bindings=group_bindings,
            node_id=node_id,
            content_whitelist_mode=content_whitelist_mode,
            content_type_policy=content_type_policy,
        )

    if isinstance(expr, IRBinary):
        diagnostics.extend(
            validate_expr_contracts(
                expr.left,
                literal_bindings=literal_bindings,
                expr_bindings=expr_bindings,
                group_bindings=group_bindings,
                node_id=node_id,
                content_whitelist_mode=content_whitelist_mode,
                content_type_policy=content_type_policy,
            )
        )
        diagnostics.extend(
            validate_expr_contracts(
                expr.right,
                literal_bindings=literal_bindings,
                expr_bindings=expr_bindings,
                group_bindings=group_bindings,
                node_id=node_id,
                content_whitelist_mode=content_whitelist_mode,
                content_type_policy=content_type_policy,
            )
        )
    return diagnostics
