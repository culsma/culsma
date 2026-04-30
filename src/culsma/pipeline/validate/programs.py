"""Concrete program kind and owner semantic contracts."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.common.source import Span
from culsma.pipeline.ir_nodes import IRArg, IRCall
from culsma.pipeline.program_registry import (
    get_program_spec,
    is_known_program_kind,
    is_legacy_generic_program,
)

from .resolution import ExprResolver


class ProgramContractValidator:
    @staticmethod
    def validate_program_call(
        call: IRCall,
        *,
        literal_bindings: dict[str, Any],
        node_id: str | None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        spec = get_program_spec(call.name)
        if spec is None:
            return diagnostics

        arg_names = [arg.name for arg in call.args]
        arg_name_set = set(arg_names)
        allowed_fields = {field.name for field in spec.fields}

        for missing in sorted(set(spec.required_fields) - arg_name_set):
            diagnostics.append(
                Diagnostic(
                    code="SEM_MISSING_REQUIRED_ARG",
                    message=f"Missing required arg '{missing}' in program '{call.name}'",
                    span=call.span,
                    node_id=node_id,
                )
            )

        for arg in call.args:
            if arg.name not in allowed_fields:
                diagnostics.append(
                    Diagnostic(
                        code="SEM_UNKNOWN_ARG",
                        message=f"Unknown arg '{arg.name}' in program '{call.name}'",
                        span=arg.span or call.span,
                        node_id=node_id,
                    )
                )

        seen: set[str] = set()
        duplicates: list[str] = []
        for name in arg_names:
            if name in seen and name not in duplicates:
                duplicates.append(name)
            seen.add(name)

        for dup in duplicates:
            dup_span = next((arg.span for arg in call.args if arg.name == dup), call.span)
            diagnostics.append(
                Diagnostic(
                    code="SEM_DUPLICATE_ARG",
                    message=f"Duplicate arg '{dup}' in program '{call.name}'",
                    span=dup_span or call.span,
                    node_id=node_id,
                )
            )

        field_specs = {field.name: field for field in spec.fields}
        for arg in call.args:
            field_spec = field_specs.get(arg.name)
            if field_spec is None or field_spec.enum_values is None:
                continue
            value = ExprResolver.to_text_token(arg.value, literal_bindings)
            if value is None or value not in set(field_spec.enum_values):
                diagnostics.append(
                    Diagnostic(
                        code="SEM_INVALID_PROGRAM_ARG_VALUE",
                        message=(
                            f"Program arg '{arg.name}' in '{call.name}' must be one of: "
                            + ", ".join(field_spec.enum_values)
                        ),
                        span=arg.span or call.span,
                        node_id=node_id,
                    )
                )
        return diagnostics

    @staticmethod
    def validate_owner_program_arg(
        *,
        owner: str,
        call: IRCall,
        literal_bindings: dict[str, Any],
        expr_bindings: dict[str, Any],
        node_id: str | None,
    ) -> list[Diagnostic]:
        program_arg = _find_arg_by_name(call.args, "program")
        if program_arg is None:
            return []
        return ProgramContractValidator.validate_attached_program(
            owner=owner,
            program_expr=program_arg.value,
            node_id=node_id,
            span=program_arg.span or call.span,
            expr_bindings=expr_bindings,
            literal_bindings=literal_bindings,
        )

    @staticmethod
    def validate_attached_program(
        *,
        owner: str,
        program_expr: Any,
        node_id: str | None,
        span: Span | None,
        expr_bindings: dict[str, Any],
        literal_bindings: dict[str, Any],
        source_style: str | None = None,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        program_call = ExprResolver.resolve_call_expr(program_expr, expr_bindings)
        if program_call is None:
            diagnostics.append(
                Diagnostic(
                    code="SEM_PROGRAM_KIND_INVALID",
                    message=f"{owner} requires 'program' to resolve to a concrete *_program(...) call",
                    span=span,
                    node_id=node_id,
                )
            )
            return diagnostics

        if is_legacy_generic_program(program_call.name):
            diagnostics.append(
                Diagnostic(
                    code="SEM_LEGACY_PROGRAM_FORM_FORBIDDEN",
                    message=f"Legacy generic program '{program_call.name}' is forbidden; use a concrete *_program(...) constructor",
                    span=program_call.span or span,
                    node_id=node_id,
                )
            )
            return diagnostics

        spec = get_program_spec(program_call.name)
        if spec is None:
            diagnostics.append(
                Diagnostic(
                    code="SEM_PROGRAM_KIND_INVALID",
                    message=f"Unknown concrete program kind '{program_call.name}'",
                    span=program_call.span or span,
                    node_id=node_id,
                )
            )
            return diagnostics

        if owner not in spec.owners:
            diagnostics.append(
                Diagnostic(
                    code="SEM_PROGRAM_OWNER_MISMATCH",
                    message=f"Program '{program_call.name}' is not valid for owner '{owner}'",
                    span=program_call.span or span,
                    node_id=node_id,
                )
            )
            return diagnostics

        if owner == "mutation_stmt" and source_style is not None:
            allowed_styles = set(spec.allowed_source_styles or ())
            if source_style not in allowed_styles:
                diagnostics.append(
                    Diagnostic(
                        code="SEM_MUTATION_PROGRAM_SOURCE_SHAPE_CONFLICT",
                        message=f"Program '{program_call.name}' is not valid for mutation source style '{source_style}'",
                        span=program_call.span or span,
                        node_id=node_id,
                    )
                )
        return diagnostics


def is_program_kind(name: str) -> bool:
    return is_known_program_kind(name)


def is_legacy_program_kind(name: str) -> bool:
    return is_legacy_generic_program(name)


def _find_arg_by_name(args: list[IRArg], name: str) -> IRArg | None:
    for arg in args:
        if arg.name == name:
            return arg
    return None
