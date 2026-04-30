"""Name binding and surface-read diagnostics for semantic validation."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.common.source import Span
from culsma.pipeline.ir_nodes import (
    IRCall,
    IRGroup,
    IRIdentifier,
    IRIndex,
    IRLet,
    IRMember,
    IRMutation,
    IRPair,
    IRPlateSelector,
    IRStep,
    IRString,
    IRWithEnv,
)

from .resolution import ExprResolver

_READOUT_FAMILY = {"img", "ecp", "phy"}
_SAMPLE_CALL_FAMILY = {"sep", "frac", "img", "ecp", "phy"}


class BindingValidator:
    @staticmethod
    def validate_unbound_name_references_for_expr(
        expr: Any,
        *,
        defined_names: set[str],
        literal_bindings: dict[str, Any],
        expr_bindings: dict[str, Any],
        strict_mode: bool,
        span: Span | None,
        node_id: str | None,
    ) -> list[Diagnostic]:
        resolved = ExprResolver.resolve_bound_expr(expr, expr_bindings)
        if isinstance(resolved, IRCall):
            reads = _surface_reads_from_current_call(
                resolved,
                literal_bindings=literal_bindings,
                expr_bindings=expr_bindings,
            )
        else:
            reads = _surface_reads_from_container_expr(
                resolved,
                literal_bindings=literal_bindings,
                expr_bindings=expr_bindings,
            )
        return _validate_unbound_name_references_from_reads(
            reads,
            defined_names=defined_names,
            strict_mode=strict_mode,
            node_id=node_id,
            default_span=span,
        )

    @staticmethod
    def validate_unbound_name_references_for_step(
        step: IRStep,
        *,
        defined_names: set[str],
        literal_bindings: dict[str, Any],
        expr_bindings: dict[str, Any],
        strict_mode: bool,
    ) -> list[Diagnostic]:
        if step.name not in _READOUT_FAMILY and step.name != "agit":
            return []
        reads: dict[str, Span | None] = {}
        sample_arg = _find_arg(step, "sample")
        if sample_arg is not None:
            reads.update(
                _surface_reads_from_container_expr(
                    sample_arg.value,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                )
            )
        return _validate_unbound_name_references_from_reads(
            reads,
            defined_names=defined_names,
            strict_mode=strict_mode,
            node_id=step.id,
            default_span=step.span,
        )

    @staticmethod
    def validate_unbound_name_references_for_mutation(
        stmt: IRMutation,
        *,
        defined_names: set[str],
        literal_bindings: dict[str, Any],
        expr_bindings: dict[str, Any],
        strict_mode: bool,
    ) -> list[Diagnostic]:
        reads: dict[str, Span | None] = {}
        if stmt.target is not None:
            reads.update(
                _surface_reads_from_container_expr(
                    stmt.target,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                )
            )
        for source in stmt.sources:
            source_expr = source.left if isinstance(source, IRPair) else source
            reads.update(
                _surface_reads_from_container_expr(
                    source_expr,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                )
            )
        return _validate_unbound_name_references_from_reads(
            reads,
            defined_names=defined_names,
            strict_mode=strict_mode,
            node_id=stmt.id,
            default_span=stmt.span,
        )

    @staticmethod
    def validate_unbound_name_references_for_with_env(
        stmt: IRWithEnv,
        *,
        defined_names: set[str],
        literal_bindings: dict[str, Any],
        expr_bindings: dict[str, Any],
        strict_mode: bool,
    ) -> list[Diagnostic]:
        reads: dict[str, Span | None] = {}
        for target in stmt.targets:
            reads.update(
                _surface_reads_from_container_expr(
                    target,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                )
            )
        return _validate_unbound_name_references_from_reads(
            reads,
            defined_names=defined_names,
            strict_mode=strict_mode,
            node_id=stmt.id,
            default_span=stmt.span,
        )

    @staticmethod
    def assign_target_root_name(expr: Any) -> str | None:
        current = expr
        while isinstance(current, IRMember):
            current = current.base
        if isinstance(current, IRIdentifier):
            return current.name
        return None

    @staticmethod
    def resolve_let_value(stmt: IRLet, literal_bindings: dict[str, Any]) -> str | list[str] | float | None:
        value = stmt.value
        if value is None:
            return None
        resolved_str = ExprResolver.to_string(value, literal_bindings)
        if resolved_str is not None:
            return resolved_str
        resolved_num = ExprResolver.to_number(value, literal_bindings)
        if resolved_num is not None:
            return resolved_num
        return ExprResolver.to_string_list(value, literal_bindings)

    @staticmethod
    def let_defines_runtime_name(stmt: IRLet, *, expr_bindings: dict[str, Any]) -> bool:
        if stmt.value is None:
            return False
        resolved = ExprResolver.resolve_bound_expr(stmt.value, expr_bindings)
        if isinstance(resolved, (IRIdentifier, IRString, IRPlateSelector, IRIndex)):
            return True
        return isinstance(resolved, IRCall) and resolved.name in {
            "AllocContainer",
            "stream",
            "markers",
            "data_schema",
            "data_ref",
            "data_group_ref",
        }


def _surface_reads_from_container_expr(
    expr: Any,
    *,
    literal_bindings: dict[str, Any],
    expr_bindings: dict[str, Any],
) -> dict[str, Span | None]:
    refs: dict[str, Span | None] = {}
    resolved = ExprResolver.resolve_bound_expr(expr, expr_bindings)
    if isinstance(resolved, IRGroup):
        for item in resolved.elements:
            refs.update(
                _surface_reads_from_container_expr(
                    item,
                    literal_bindings=literal_bindings,
                    expr_bindings=expr_bindings,
                )
            )
        return refs
    if isinstance(resolved, IRPlateSelector):
        value = ExprResolver.to_name_ref(resolved.base, literal_bindings)
        if value is not None:
            refs[value] = resolved.base.span or resolved.span
        return refs
    value = ExprResolver.to_name_ref(resolved, literal_bindings)
    if value is not None:
        refs[value] = resolved.span
    return refs


def _surface_reads_from_current_call(
    call: IRCall,
    *,
    literal_bindings: dict[str, Any],
    expr_bindings: dict[str, Any],
) -> dict[str, Span | None]:
    if call.name not in _SAMPLE_CALL_FAMILY:
        return {}
    sample_arg = _find_arg_by_name(call.args, "sample")
    if sample_arg is None:
        return {}
    return _surface_reads_from_container_expr(
        sample_arg.value,
        literal_bindings=literal_bindings,
        expr_bindings=expr_bindings,
    )


def _validate_unbound_name_references_from_reads(
    reads: dict[str, Span | None],
    *,
    defined_names: set[str],
    strict_mode: bool,
    node_id: str | None,
    default_span: Span | None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if not strict_mode:
        return diagnostics
    for name, span in reads.items():
        if name in defined_names:
            continue
        diagnostics.append(
            Diagnostic(
                code="SEM_UNBOUND_NAME_REFERENCE",
                message=f"Name '{name}' is used before any binding is established",
                span=span or default_span,
                node_id=node_id,
            )
        )
    return diagnostics


def _find_arg(step: IRStep, name: str):
    for arg in step.args:
        if arg.name == name:
            return arg
    return None


def _find_arg_by_name(args, name: str):
    for arg in args:
        if arg.name == name:
            return arg
    return None
