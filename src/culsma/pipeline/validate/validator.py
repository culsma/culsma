"""Semantic validation for Canonical IR v0.1."""

from __future__ import annotations

from typing import Mapping

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.analysis import CompileAnalysis, ProtocolAnalysis
from culsma.pipeline.ir_nodes import IRBoolean, IRList, IRParam, IRProgram, IRQuantity, IRString
from culsma.pipeline.operation_specs import BUILTIN_OPERATION_SPECS, OperationSpec

from .context import ValidationResult, _GroupBinding
from .statements import StatementValidationContext, validate_statement_list_with_context


def validate(
    ir: IRProgram,
    *,
    analysis: CompileAnalysis,
    operation_specs: Mapping[str, OperationSpec] = BUILTIN_OPERATION_SPECS,
    initial_defined_names: set[str] | None = None,
    enforce_binding: bool = False,
    content_whitelist_mode: str = "compat",
    content_type_policy: str = "required",
) -> ValidationResult:
    """Validate IR against builtin operation signature rules."""
    diagnostics: list[Diagnostic] = []
    operations = operation_specs

    for protocol in ir.protocols:
        literal_bindings = literal_param_bindings(protocol.params)
        expr_bindings = {
            param.name: param.default
            for param in protocol.params
            if param.default is not None
        }
        group_bindings: dict[str, _GroupBinding] = {}
        defined_names: set[str] = set(initial_defined_names or set()) | {param.name for param in protocol.params}
        protocol_analysis = analysis.protocols.get(protocol.id, ProtocolAnalysis())
        ctx = StatementValidationContext(
            literal_bindings=literal_bindings,
            expr_bindings=expr_bindings,
            group_bindings=group_bindings,
            defined_names=defined_names,
            active_requirements=(),
            diagnostics=diagnostics,
            operations=operations,
            analysis=analysis,
            protocol_analysis=protocol_analysis,
            enforce_binding=enforce_binding,
            content_whitelist_mode=content_whitelist_mode,
            content_type_policy=content_type_policy,
        )
        validate_statement_list_with_context(protocol.statements, ctx)

    return ValidationResult(ir=ir, diagnostics=_dedupe_diagnostics(diagnostics))


def literal_param_bindings(params: list[IRParam]) -> dict[str, object]:
    bindings: dict[str, object] = {}
    for param in params:
        literal = literal_param_value(param.default)
        if literal is not None:
            bindings[param.name] = literal
    return bindings


def literal_param_value(value: object) -> object | None:
    if isinstance(value, IRString):
        return value.value
    if isinstance(value, IRBoolean):
        return value.value
    if isinstance(value, IRQuantity) and value.unit is None:
        return float(value.value)
    if isinstance(value, IRList):
        items = [literal_param_value(item) for item in value.elements]
        if all(isinstance(item, str) for item in items):
            return items
    return None


def _dedupe_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    seen: set[tuple[object, ...]] = set()
    unique: list[Diagnostic] = []
    for diagnostic in diagnostics:
        span = diagnostic.span
        span_key = None if span is None else (span.line, span.col, span.start, span.end)
        key = (
            diagnostic.code,
            diagnostic.message,
            diagnostic.severity,
            diagnostic.node_id,
            span_key,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(diagnostic)
    return unique
