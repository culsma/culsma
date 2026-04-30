"""Group binding and static group-index validation."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRArg, IRGroup, IRIdentifier, IRIndex, IRPlateSelector

from .context import _GroupBinding
from .resolution import ExprResolver


class GroupIndexValidator:
    @staticmethod
    def classify_binding(
        expr: Any,
        *,
        literal_bindings: dict[str, Any],
        expr_bindings: dict[str, Any],
    ) -> _GroupBinding | None:
        resolved = ExprResolver.resolve_bound_expr(expr, expr_bindings)
        if isinstance(resolved, (IRGroup, IRPlateSelector)):
            return _GroupBinding(kind="container_group", size=None)
        call = ExprResolver.resolve_call_expr(expr, expr_bindings)
        if call is None:
            return None
        if call.name == "sep":
            return _GroupBinding(kind="sep_container_group", size=2)
        if call.name in {"img", "ecp", "phy"}:
            sample_arg = _find_arg_by_name(call.args, "sample")
            if sample_arg is None:
                return None
            sample_expr = ExprResolver.resolve_bound_expr(sample_arg.value, expr_bindings)
            if isinstance(sample_expr, (IRGroup, IRPlateSelector)):
                return _GroupBinding(kind="data_group", size=_static_group_cardinality(sample_expr))
        if call.name == "data_group_ref":
            return _GroupBinding(kind="data_group", size=None)
        if call.name != "frac":
            return None
        program_arg = _find_arg_by_name(call.args, "program")
        program_call = ExprResolver.resolve_call_expr(program_arg.value, expr_bindings) if program_arg is not None else None
        bins: int | None = None
        if program_call is not None and program_call.name in {"density_gradient_program", "chromatography_program"}:
            bins_arg = _find_arg_by_name(program_call.args, "bins")
            if bins_arg is not None:
                bins, reason = ExprResolver.resolve_static_index_value(
                    bins_arg.value,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                )
                if reason is not None:
                    bins = None
        return _GroupBinding(kind="fraction_group", size=bins)

    @staticmethod
    def validate_index(
        expr: IRIndex,
        *,
        literal_bindings: dict[str, Any],
        expr_bindings: dict[str, Any],
        group_bindings: dict[str, _GroupBinding],
        node_id: str | None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        if not isinstance(expr.base, IRIdentifier):
            diagnostics.append(
                Diagnostic(
                    code="SEM_INVALID_GROUP_INDEX_BASE",
                    message="group index base must be a group binding identifier",
                    span=expr.base.span or expr.span,
                    node_id=node_id,
                )
            )
            return diagnostics

        binding = group_bindings.get(expr.base.name)
        if binding is None:
            diagnostics.append(
                Diagnostic(
                    code="SEM_INVALID_GROUP_INDEX_BASE",
                    message=f"Identifier '{expr.base.name}' is not a group-like binding",
                    span=expr.base.span or expr.span,
                    node_id=node_id,
                )
            )
            return diagnostics

        index_value, reason = ExprResolver.resolve_static_index_value(
            expr.index,
            literal_bindings=literal_bindings,
            expr_bindings=expr_bindings,
        )
        if reason == "not_static":
            diagnostics.append(
                Diagnostic(
                    code="SEM_INDEX_NOT_STATIC_INTEGER",
                    message="group index must be a compile-time decidable non-negative integer",
                    span=expr.index.span or expr.span,
                    node_id=node_id,
                )
            )
            return diagnostics
        if reason == "not_nonnegative_integer":
            diagnostics.append(
                Diagnostic(
                    code="SEM_INDEX_NOT_NONNEGATIVE_INTEGER",
                    message="group index must be a non-negative integer",
                    span=expr.index.span or expr.span,
                    node_id=node_id,
                )
            )
            return diagnostics
        if index_value is None:
            return diagnostics

        if binding.kind == "sep_container_group" and index_value not in {0, 1}:
            diagnostics.append(
                Diagnostic(
                    code="SEM_INDEX_OUT_OF_RANGE",
                    message="sep_container_group only supports indices 0 and 1",
                    span=expr.index.span or expr.span,
                    node_id=node_id,
                )
            )
        if binding.kind == "fraction_group" and binding.size is not None and index_value >= binding.size:
            diagnostics.append(
                Diagnostic(
                    code="SEM_INDEX_OUT_OF_RANGE",
                    message=f"fraction_group index {index_value} is out of range for bins={binding.size}",
                    span=expr.index.span or expr.span,
                    node_id=node_id,
                )
            )
        if binding.kind == "data_group" and binding.size is not None and index_value >= binding.size:
            diagnostics.append(
                Diagnostic(
                    code="SEM_INDEX_OUT_OF_RANGE",
                    message=f"data_group_ref index {index_value} is out of range for size={binding.size}",
                    span=expr.index.span or expr.span,
                    node_id=node_id,
                )
            )
        return diagnostics


def _find_arg_by_name(args: list[IRArg], name: str) -> IRArg | None:
    for arg in args:
        if arg.name == name:
            return arg
    return None


def _static_group_cardinality(expr: Any) -> int | None:
    if isinstance(expr, IRGroup):
        return len(expr.elements)
    return None
