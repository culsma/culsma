"""Lower Canonical IR to executable Plan v0.1."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.entrypoints import EntryResolution, resolve_entry
from culsma.pipeline.analysis import CompileAnalysis
from culsma.pipeline.ir_nodes import IRProgram, IRProtocol, IRScriptEntry
from culsma.pipeline.plan_nodes import PlanProgram, ProtocolPlan
from culsma.pipeline.scope import ScopeAnalyzer, ScopeQueryService

from .context import PlanLoweringContext
from .references import DEFAULT_PLAN_REFERENCE_RESOLVER, PlanReferenceResolver
from .serialization import DEFAULT_PLAN_EXPRESSION_SERIALIZER, PlanExpressionSerializer
from .statements import BasePlanStatementHandler, PlanStatementLowerer, PlanStatementLoweringState


def lower_ir_to_plan(
    ir: IRProgram,
    *,
    analysis: CompileAnalysis | None = None,
    entry_resolution: EntryResolution | None = None,
    entry_protocol: str | None = None,
    entry_args_by_protocol: dict[str, dict[str, Any]] | None = None,
) -> PlanProgram:
    """Lower validated IR into protocol-scoped execution plans."""
    plans: list[ProtocolPlan] = []
    diagnostics: list[Diagnostic] = []
    entry_resolution = entry_resolution or resolve_entry(
        ir,
        explicit_entry=entry_protocol,
        warn_on_legacy=False,
    )
    diagnostics.extend(entry_resolution.diagnostics)
    protocols_by_name = {p.name: p for p in ir.protocols}
    scope_model = analysis.scope if analysis is not None else ScopeAnalyzer().analyze(ir)
    scope_query = ScopeQueryService.from_model(scope_model)
    serializer = DEFAULT_PLAN_EXPRESSION_SERIALIZER
    reference_resolver = DEFAULT_PLAN_REFERENCE_RESOLVER
    statement_lowerer = PlanStatementLowerer(
        serializer=serializer,
        reference_resolver=reference_resolver,
    )
    if entry_resolution.kind == "none":
        return PlanProgram(plans=[], diagnostics=diagnostics, span=ir.span)

    if entry_resolution.kind == "script":
        if ir.script_entry is None:
            diagnostics.append(
                Diagnostic(
                    code="PLAN_SCRIPT_ENTRY_NOT_FOUND",
                    message="Script entry was selected but no script entry exists",
                    span=ir.span,
                    node_id=None,
                )
            )
            return PlanProgram(plans=[], diagnostics=diagnostics, span=ir.span)
        plans.append(
            lower_script_entry_to_plan(
                ir.script_entry,
                protocols_by_name=protocols_by_name,
                diagnostics=diagnostics,
                scope_query=scope_query,
                statement_lowerer=statement_lowerer,
                serializer=serializer,
                reference_resolver=reference_resolver,
            )
        )
        return PlanProgram(plans=plans, diagnostics=diagnostics, span=ir.span)

    root_protocol = next(
        (protocol for protocol in ir.protocols if protocol.name == entry_resolution.entry_protocol),
        None,
    )
    if root_protocol is None:
        diagnostics.append(
            Diagnostic(
                code="PLAN_ENTRY_PROTOCOL_NOT_FOUND",
                message=f"Entry protocol '{entry_resolution.entry_protocol}' not found",
                span=ir.span,
                node_id=None,
            )
        )
        return PlanProgram(plans=[], diagnostics=diagnostics, span=ir.span)

    plans.append(
        lower_protocol_entry_to_plan(
            root_protocol,
            protocols_by_name=protocols_by_name,
            diagnostics=diagnostics,
            scope_query=scope_query,
            statement_lowerer=statement_lowerer,
            serializer=serializer,
            reference_resolver=reference_resolver,
            entry_args=(entry_args_by_protocol or {}).get(root_protocol.name, {}),
        )
    )

    return PlanProgram(plans=plans, diagnostics=diagnostics, span=ir.span)


def lower_script_entry_to_plan(
    script: IRScriptEntry,
    *,
    protocols_by_name: dict[str, IRProtocol],
    diagnostics: list[Diagnostic],
    scope_query: ScopeQueryService,
    statement_lowerer: PlanStatementLowerer,
    serializer: PlanExpressionSerializer,
    reference_resolver: PlanReferenceResolver,
) -> ProtocolPlan:
    env: dict[str, Any] = {}
    ctx = PlanLoweringContext(
        protocols_by_name=protocols_by_name,
        diagnostics=diagnostics,
        local_env=env,
        protected_names=set(),
        protocol_name="entry",
        caller_stack=[],
        gate_base={"entry_kind": "script", "entry_name": "entry"},
        scope_query=scope_query,
        statement_lowerer=statement_lowerer,
        serializer=serializer,
        reference_resolver=reference_resolver,
        step_id_prefix="",
        call_path=[],
    )
    ordered_steps = statement_lowerer.lower_list(script.statements, ctx)
    return ProtocolPlan(
        protocol_id=script.id,
        protocol_name="entry",
        entry_kind="script",
        output_name="entry",
        returns=list(script.returns),
        return_value=serializer.serialize_expr(script.return_value, env) if script.return_value is not None else None,
        return_bindings={
            arg.name: serializer.serialize_expr(arg.value, env)
            for arg in script.return_bindings
        },
        steps=serializer.linearize_steps(ordered_steps),
        span=script.span,
    )


def lower_protocol_entry_to_plan(
    protocol: IRProtocol,
    *,
    protocols_by_name: dict[str, IRProtocol],
    diagnostics: list[Diagnostic],
    scope_query: ScopeQueryService,
    statement_lowerer: PlanStatementLowerer,
    serializer: PlanExpressionSerializer,
    reference_resolver: PlanReferenceResolver,
    entry_args: dict[str, Any],
) -> ProtocolPlan:
    env, entry_diags = reference_resolver.bind_protocol_params(
        target_protocol=protocol,
        call_args=[],
        caller_env={},
        call_span=protocol.span,
        call_node_id=protocol.id,
        entry_mode=True,
        entry_arg_values=entry_args,
    )
    diagnostics.extend(entry_diags)
    ctx = PlanLoweringContext(
        protocols_by_name=protocols_by_name,
        diagnostics=diagnostics,
        local_env=env,
        protected_names={param.name for param in protocol.params},
        protocol_name=protocol.name,
        caller_stack=[protocol.name],
        gate_base={"protocol_name": protocol.name},
        scope_query=scope_query,
        statement_lowerer=statement_lowerer,
        serializer=serializer,
        reference_resolver=reference_resolver,
        step_id_prefix="",
        call_path=[],
    )
    ordered_steps = statement_lowerer.lower_list(protocol.statements, ctx)
    return ProtocolPlan(
        protocol_id=protocol.id,
        protocol_name=protocol.name,
        entry_kind="protocol",
        output_name=protocol.name,
        returns=list(protocol.returns),
        return_value=serializer.serialize_expr(protocol.return_value, env) if protocol.return_value is not None else None,
        return_bindings={
            arg.name: serializer.serialize_expr(arg.value, env)
            for arg in protocol.return_bindings
        },
        steps=serializer.linearize_steps(ordered_steps),
        span=protocol.span,
    )


__all__ = [
    "BasePlanStatementHandler",
    "PlanExpressionSerializer",
    "PlanLoweringContext",
    "PlanReferenceResolver",
    "PlanStatementLowerer",
    "PlanStatementLoweringState",
    "lower_protocol_entry_to_plan",
    "lower_ir_to_plan",
    "lower_script_entry_to_plan",
]
