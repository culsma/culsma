"""`with env(...)` semantic contracts."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRArg, IRCall, IRQuantity, IRWithEnv

from .resolution import ExprResolver


class EnvContractValidator:
    @staticmethod
    def validate_with_env(
        stmt: IRWithEnv,
        *,
        literal_bindings: dict[str, Any],
        expr_bindings: dict[str, Any],
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        allowed_arg_names = {"thermal", "field", "co2", "rh", "duration"}
        seen_arg_names: set[str] = set()
        duplicate_arg_names: list[str] = []
        for arg in stmt.env_args:
            if arg.name not in allowed_arg_names:
                diagnostics.append(
                    Diagnostic(
                        code="SEM_UNKNOWN_ARG",
                        message=f"Unknown arg '{arg.name}' in with env(...)",
                        span=arg.span or stmt.span,
                        node_id=stmt.id,
                    )
                )
            if arg.name in seen_arg_names and arg.name not in duplicate_arg_names:
                duplicate_arg_names.append(arg.name)
            seen_arg_names.add(arg.name)
        for name in duplicate_arg_names:
            dup_span = next((arg.span for arg in stmt.env_args if arg.name == name), stmt.span)
            diagnostics.append(
                Diagnostic(
                    code="SEM_DUPLICATE_ARG",
                    message=f"Duplicate arg '{name}' in with env(...)",
                    span=dup_span or stmt.span,
                    node_id=stmt.id,
                )
            )
        if diagnostics:
            return diagnostics
        if not stmt.targets:
            diagnostics.append(
                Diagnostic(
                    code="SEM_ENV_TARGET_REQUIRED",
                    message="with env(...): at least one inferred target is required",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            )
        if not stmt.statements and not getattr(stmt, "explicit_hold", False):
            diagnostics.append(
                Diagnostic(
                    code="SEM_ENV_BODY_REQUIRED",
                    message="with env(...): at least one statement is required; use explicit hold(sample = ...) for pure env hold",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            )
        thermal_arg = _find_arg_by_name(stmt.env_args, "thermal")
        field_arg = _find_arg_by_name(stmt.env_args, "field")
        co2_arg = _find_arg_by_name(stmt.env_args, "co2")
        rh_arg = _find_arg_by_name(stmt.env_args, "rh")
        duration_arg = _find_arg_by_name(stmt.env_args, "duration")
        if thermal_arg is None and field_arg is None:
            if duration_arg is not None:
                diagnostics.append(
                    Diagnostic(
                        code="SEM_ENV_DURATION_WITHOUT_THERMAL",
                        message="with env(...): duration requires thermal",
                        span=duration_arg.span or stmt.span,
                        node_id=stmt.id,
                    )
                )
                return diagnostics
            diagnostics.append(
                Diagnostic(
                    code="SEM_ENV_THERMAL_REQUIRED",
                    message="with env(...): at least one environment dimension is required",
                    span=stmt.span,
                    node_id=stmt.id,
                )
            )
            return diagnostics

        if thermal_arg is None and (co2_arg is not None or rh_arg is not None):
            conflict_arg = co2_arg or rh_arg
            diagnostics.append(
                Diagnostic(
                    code="SEM_ENV_ARG_CONFLICT",
                    message="with env(...): co2/rh require thermal",
                    span=(conflict_arg.span if conflict_arg is not None else stmt.span) or stmt.span,
                    node_id=stmt.id,
                )
            )

        if thermal_arg is None:
            if duration_arg is not None:
                diagnostics.append(
                    Diagnostic(
                        code="SEM_ENV_DURATION_WITHOUT_THERMAL",
                        message="with env(...): duration requires thermal",
                        span=duration_arg.span or stmt.span,
                        node_id=stmt.id,
                    )
                )
            return diagnostics

        thermal_value = ExprResolver.resolve_bound_expr(thermal_arg.value, expr_bindings)
        thermal_program = isinstance(thermal_value, IRCall) and thermal_value.name == "thermal_program"
        scalar_thermal = isinstance(thermal_value, IRQuantity) or (
            isinstance(thermal_arg.value, IRQuantity) and not thermal_program
        )

        if thermal_program and (co2_arg is not None or rh_arg is not None):
            conflict_arg = co2_arg or rh_arg
            diagnostics.append(
                Diagnostic(
                    code="SEM_ENV_ARG_CONFLICT",
                    message="with env(...): co2/rh are forbidden when thermal uses thermal_program(...)",
                    span=(conflict_arg.span if conflict_arg is not None else stmt.span) or stmt.span,
                    node_id=stmt.id,
                )
            )

        if thermal_program and duration_arg is not None:
            diagnostics.append(
                Diagnostic(
                    code="SEM_ENV_DURATION_FORBIDDEN_WITH_THERMAL_PROGRAM",
                    message="with env(...): outer duration is forbidden when thermal uses thermal_program(...)",
                    span=duration_arg.span or stmt.span,
                    node_id=stmt.id,
                )
            )
        if scalar_thermal and duration_arg is None:
            diagnostics.append(
                Diagnostic(
                    code="SEM_ENV_DURATION_REQUIRED",
                    message="with env(...): scalar thermal requires explicit duration",
                    span=thermal_arg.span or stmt.span,
                    node_id=stmt.id,
                )
            )
        return diagnostics


def _find_arg_by_name(args: list[IRArg], name: str) -> IRArg | None:
    for arg in args:
        if arg.name == name:
            return arg
    return None
