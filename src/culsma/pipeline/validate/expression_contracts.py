"""Expression-level semantic validation contracts."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.container_views import classify_container_target_view, container_view_path_error, container_view_root
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
    IRSourcePartitionRef,
    IRUnary,
)

from .constructors import ConstructorValidator
from .context import _GroupBinding
from .groups import GroupIndexValidator
from .programs import ProgramContractValidator, is_legacy_program_kind, is_program_kind
from .resolution import ExprResolver

PROGRAM_OWNER_FAMILY = {"sep", "frac"}


def validate_expr_contracts(
    expr: Any,
    *,
    literal_bindings: dict[str, Any],
    expr_bindings: dict[str, Any],
    group_bindings: dict[str, _GroupBinding],
    node_id: str | None,
    content_whitelist_mode: str = "strict",
    content_type_policy: str = "required",
    allow_source_partition: bool = False,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    if isinstance(expr, IRIndex):
        if _is_container_contents_index(expr):
            if not allow_source_partition:
                diagnostics.append(
                    Diagnostic(
                        code="SEM_CONTAINER_CONTENTS_INDEX_CONTEXT_INVALID",
                        message="container.contents[i] is only valid as a mutation source item",
                        span=expr.span,
                        node_id=node_id,
                    )
                )
            index_value, reason = ExprResolver.resolve_static_index_value(
                expr.index,
                literal_bindings=literal_bindings,
                expr_bindings=expr_bindings,
            )
            if reason == "not_static":
                diagnostics.append(
                    Diagnostic(
                        code="SEM_INDEX_NOT_STATIC_INTEGER",
                        message="container.contents index must be a compile-time decidable non-negative integer",
                        span=expr.index.span or expr.span,
                        node_id=node_id,
                    )
                )
            elif reason == "not_nonnegative_integer":
                diagnostics.append(
                    Diagnostic(
                        code="SEM_INDEX_NOT_NONNEGATIVE_INTEGER",
                        message="container.contents index must be a non-negative integer",
                        span=expr.index.span or expr.span,
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
            if index_value is None:
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

    if isinstance(expr, IRSourcePartitionRef):
        if not allow_source_partition:
            diagnostics.append(
                Diagnostic(
                    code="SEM_SOURCE_PARTITION_CONTEXT_INVALID",
                    message="source.partition(program)[i] is only valid as a mutation source item",
                    span=expr.span,
                    node_id=node_id,
                )
            )
            return diagnostics
        diagnostics.extend(
            validate_source_partition_contract(
                expr,
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
        error = container_view_path_error(expr)
        if error is not None:
            diagnostics.append(
                Diagnostic(
                    code="SEM_CONTAINER_TARGET_VIEW_INVALID",
                    message=error,
                    span=expr.span,
                    node_id=node_id,
                )
            )
        root = container_view_root(expr)
        return diagnostics + validate_expr_contracts(
            root if root is not None else expr.base,
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


def _is_container_contents_index(expr: IRIndex) -> bool:
    view = classify_container_target_view(expr.base)
    return view is not None and view.kind == "contents"


def validate_source_partition_contract(
    expr: IRSourcePartitionRef,
    *,
    literal_bindings: dict[str, Any],
    expr_bindings: dict[str, Any],
    group_bindings: dict[str, _GroupBinding],
    node_id: str | None,
    content_whitelist_mode: str,
    content_type_policy: str,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(
        validate_expr_contracts(
            expr.source,
            literal_bindings=literal_bindings,
            expr_bindings=expr_bindings,
            group_bindings=group_bindings,
            node_id=node_id,
            content_whitelist_mode=content_whitelist_mode,
            content_type_policy=content_type_policy,
        )
    )
    diagnostics.extend(
        ProgramContractValidator.validate_attached_program(
            owner="partition",
            program_expr=expr.program,
            node_id=node_id,
            span=expr.program.span or expr.span,
            expr_bindings=expr_bindings,
            literal_bindings=literal_bindings,
        )
    )
    program_call = ExprResolver.resolve_call_expr(expr.program, expr_bindings)
    if program_call is not None:
        diagnostics.extend(
            ProgramContractValidator.validate_program_call(
                program_call,
                literal_bindings=literal_bindings,
                node_id=node_id,
            )
        )
    index_value, reason = ExprResolver.resolve_static_index_value(
        expr.index,
        literal_bindings=literal_bindings,
        expr_bindings=expr_bindings,
    )
    if reason == "not_static":
        diagnostics.append(
            Diagnostic(
                code="SEM_INDEX_NOT_STATIC_INTEGER",
                message="source partition index must be a compile-time decidable non-negative integer",
                span=expr.index.span or expr.span,
                node_id=node_id,
            )
        )
    elif reason == "not_nonnegative_integer":
        diagnostics.append(
            Diagnostic(
                code="SEM_INDEX_NOT_NONNEGATIVE_INTEGER",
                message="source partition index must be a non-negative integer",
                span=expr.index.span or expr.span,
                node_id=node_id,
            )
        )
    elif index_value is not None and index_value not in {0, 1}:
        diagnostics.append(
            Diagnostic(
                code="SEM_INDEX_OUT_OF_RANGE",
                message="source partition only supports indices 0 and 1",
                span=expr.index.span or expr.span,
                node_id=node_id,
            )
        )
    return diagnostics
