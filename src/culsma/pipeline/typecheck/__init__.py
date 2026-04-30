"""Type and unit checking for Canonical IR v0.1."""

from __future__ import annotations

from typing import Mapping

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRProgram
from culsma.pipeline.operation_specs import BUILTIN_OPERATION_SPECS, OperationSpec

from .context import TypecheckContext, TypecheckResult
from .expressions import (
    TypecheckExpressionServices,
    _classify_local_expr_type,
    _coerce_quantity_like,
    _member_assignment_path,
    _resolve_bound_expr,
    _typecheck_assignment,
    _typecheck_constructor_load,
    _typecheck_content_descriptors,
    _typecheck_define_content_args,
    _typecheck_let_call,
    _typecheck_member_assignment,
    _typecheck_mutation,
    _typecheck_program_call,
    _typecheck_program_calls_in_expr,
    _typecheck_thermal_program_call,
    _typecheck_with_env,
    _validate_centrifuge_speed_quantity,
    _validate_program_quantity_field,
    _validate_quantity_dimensions,
)
from .statements import StatementTypechecker


def typecheck(
    ir: IRProgram,
    *,
    operation_specs: Mapping[str, OperationSpec] = BUILTIN_OPERATION_SPECS,
) -> TypecheckResult:
    """Check quantity dimensions against per-operation argument expectations."""
    diagnostics: list[Diagnostic] = []
    statement_typechecker = StatementTypechecker()

    for protocol in ir.protocols:
        ctx = TypecheckContext(
            operation_specs=operation_specs,
            diagnostics=diagnostics,
            expr_bindings={},
            statement_typechecker=statement_typechecker,
        )
        statement_typechecker.typecheck_list(protocol.statements, ctx)

    return TypecheckResult(ir=ir, diagnostics=diagnostics)


__all__ = [
    "StatementTypechecker",
    "TypecheckContext",
    "TypecheckExpressionServices",
    "TypecheckResult",
    "typecheck",
    "_classify_local_expr_type",
    "_coerce_quantity_like",
    "_member_assignment_path",
    "_resolve_bound_expr",
    "_typecheck_assignment",
    "_typecheck_constructor_load",
    "_typecheck_content_descriptors",
    "_typecheck_define_content_args",
    "_typecheck_let_call",
    "_typecheck_member_assignment",
    "_typecheck_mutation",
    "_typecheck_program_call",
    "_typecheck_program_calls_in_expr",
    "_typecheck_thermal_program_call",
    "_typecheck_with_env",
    "_validate_centrifuge_speed_quantity",
    "_validate_program_quantity_field",
    "_validate_quantity_dimensions",
]
