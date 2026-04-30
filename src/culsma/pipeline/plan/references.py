"""Protocol-reference expansion helpers for plan lowering."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import (
    IRArg,
    IRConditional,
    IRInclude,
    IRProtocol,
    IRRepeat,
    IRWithConstraint,
    IRWithEnv,
)
from culsma.pipeline.plan_nodes import PlanStep

from .context import PlanLoweringContext
from .gates import merge_gate
from .serialization import DEFAULT_PLAN_EXPRESSION_SERIALIZER, PlanExpressionSerializer


class PlanReferenceResolver:
    def __init__(self, *, serializer: PlanExpressionSerializer = DEFAULT_PLAN_EXPRESSION_SERIALIZER) -> None:
        self.serializer = serializer

    def collect_referenced_protocol_names(self, statements: list[Any]) -> list[str]:
        names: list[str] = []
        for stmt in statements:
            if isinstance(stmt, IRInclude):
                names.append(stmt.name)
            elif isinstance(stmt, IRWithEnv):
                names.extend(self.collect_referenced_protocol_names(stmt.statements))
            elif isinstance(stmt, IRWithConstraint):
                names.extend(self.collect_referenced_protocol_names(stmt.statements))
            elif isinstance(stmt, IRRepeat):
                names.extend(self.collect_referenced_protocol_names(stmt.statements))
            elif isinstance(stmt, IRConditional):
                names.extend(self.collect_referenced_protocol_names(stmt.then_statements))
                names.extend(self.collect_referenced_protocol_names(stmt.else_statements))
        return names

    def bind_protocol_params(
        self,
        *,
        target_protocol: IRProtocol,
        call_args: list[IRArg],
        caller_env: dict[str, Any],
        call_span,
        call_node_id: str,
        entry_mode: bool = False,
        entry_arg_values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[Diagnostic]]:
        diagnostics: list[Diagnostic] = []
        param_by_name = {param.name: param for param in target_protocol.params}
        bound: dict[str, Any] = {}

        if entry_mode:
            for name, value in (entry_arg_values or {}).items():
                if name not in param_by_name:
                    diagnostics.append(
                        Diagnostic(
                            code="PLAN_CALL_ARG_UNKNOWN",
                            message=f"Unknown argument '{name}' for protocol '{target_protocol.name}'",
                            span=call_span,
                            node_id=call_node_id,
                        )
                    )
                    continue
                bound[name] = value
        else:
            seen_arg_names: set[str] = set()
            for arg in call_args:
                if arg.name in seen_arg_names:
                    diagnostics.append(
                        Diagnostic(
                            code="PLAN_CALL_ARG_DUPLICATE",
                            message=f"Duplicate argument '{arg.name}' for protocol '{target_protocol.name}'",
                            span=arg.span,
                            node_id=call_node_id,
                        )
                    )
                    continue
                seen_arg_names.add(arg.name)
                if arg.name not in param_by_name:
                    diagnostics.append(
                        Diagnostic(
                            code="PLAN_CALL_ARG_UNKNOWN",
                            message=f"Unknown argument '{arg.name}' for protocol '{target_protocol.name}'",
                            span=arg.span,
                            node_id=call_node_id,
                        )
                    )
                    continue
                bound[arg.name] = self.serializer.serialize_expr(arg.value, caller_env)

        local_env: dict[str, Any] = {}
        for param in target_protocol.params:
            if param.name in bound:
                local_env[param.name] = bound[param.name]
                continue
            if param.default is not None:
                default_value = self.serializer.serialize_expr(param.default, local_env)
                if self.serializer.contains_unresolved_identifier(default_value):
                    diagnostics.append(
                        Diagnostic(
                            code="PLAN_CALL_ARG_DEFAULT_EVAL_FAILED",
                            message=f"Default value for parameter '{param.name}' of protocol '{target_protocol.name}' is not resolvable",
                            span=param.span,
                            node_id=call_node_id,
                        )
                    )
                    continue
                local_env[param.name] = default_value
                continue
            diagnostics.append(
                Diagnostic(
                    code="PLAN_ENTRY_PARAM_MISSING" if entry_mode else "PLAN_CALL_ARG_MISSING",
                    message=(
                        f"Missing required parameter '{param.name}' for entry protocol '{target_protocol.name}'"
                        if entry_mode
                        else f"Missing required argument '{param.name}' for protocol '{target_protocol.name}'"
                    ),
                    span=call_span,
                    node_id=call_node_id,
                )
            )
        return local_env, diagnostics

    def expand_reference_steps(
        self,
        *,
        ref_name: str,
        ref_stmt_id: str,
        ref_args: list[IRArg],
        ctx: PlanLoweringContext,
        span,
        caller_protocol_name: str | None = None,
        call_path: list[str] | None = None,
    ) -> list[PlanStep]:
        ref_protocol = ctx.protocols_by_name.get(ref_name)
        if ref_protocol is None:
            ctx.emit_diagnostic(
                Diagnostic(
                    code="PLAN_UNKNOWN_REFERENCE",
                    message=f"Referenced protocol '{ref_name}' not found",
                    span=span,
                    node_id=ref_stmt_id,
                )
            )
            return []

        if ref_name in ctx.caller_stack:
            ctx.emit_diagnostic(
                Diagnostic(
                    code="PLAN_REFERENCE_CYCLE",
                    message=f"Reference cycle detected: {' -> '.join(ctx.caller_stack + [ref_name])}",
                    span=span,
                    node_id=ref_stmt_id,
                )
            )
            return []

        local_env, bind_diags = self.bind_protocol_params(
            target_protocol=ref_protocol,
            call_args=ref_args,
            caller_env=ctx.local_env,
            call_span=span,
            call_node_id=ref_stmt_id,
        )
        ctx.extend_diagnostics(bind_diags)
        if ctx.statement_lowerer is None:
            return []

        child_ctx = ctx.derive(
            local_env=local_env,
            protected_names={param.name for param in ref_protocol.params},
            protocol_name=caller_protocol_name or ref_name,
            caller_stack=ctx.caller_stack + [ref_name],
            gate_base=merge_gate(
                ctx.gate_base,
                protocol_name=caller_protocol_name or ref_name,
                ref_meta={
                    "ref_protocol": ref_name,
                    "ref_call_id": ref_stmt_id,
                    "call_path": ">".join(call_path or [ref_stmt_id]),
                },
            ),
            step_id_prefix=f"{ref_stmt_id}::",
            call_path=call_path or [ref_stmt_id],
        )
        return ctx.statement_lowerer.lower_list(ref_protocol.statements, child_ctx)


DEFAULT_PLAN_REFERENCE_RESOLVER = PlanReferenceResolver()
