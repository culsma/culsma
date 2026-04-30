"""Lower Canonical IR to executable Plan v0.1."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRProgram
from culsma.pipeline.plan_nodes import PlanProgram, ProtocolPlan

from .context import PlanLoweringContext
from .references import DEFAULT_PLAN_REFERENCE_RESOLVER, PlanReferenceResolver
from .serialization import DEFAULT_PLAN_EXPRESSION_SERIALIZER, PlanExpressionSerializer
from .statements import BasePlanStatementHandler, PlanStatementLowerer, PlanStatementLoweringState


def lower_ir_to_plan(
    ir: IRProgram,
    *,
    entry_args_by_protocol: dict[str, dict[str, Any]] | None = None,
) -> PlanProgram:
    """Lower validated IR into protocol-scoped execution plans."""
    plans: list[ProtocolPlan] = []
    diagnostics: list[Diagnostic] = []
    protocols_by_name = {p.name: p for p in ir.protocols}
    serializer = DEFAULT_PLAN_EXPRESSION_SERIALIZER
    reference_resolver = DEFAULT_PLAN_REFERENCE_RESOLVER
    statement_lowerer = PlanStatementLowerer(
        serializer=serializer,
        reference_resolver=reference_resolver,
    )
    referenced_protocols = {
        ref_name
        for protocol in ir.protocols
        for ref_name in reference_resolver.collect_referenced_protocol_names(protocol.statements)
    }

    root_protocols = [protocol for protocol in ir.protocols if protocol.name not in referenced_protocols]
    if not root_protocols and ir.protocols:
        root_protocols = list(ir.protocols)

    for protocol in root_protocols:
        env, entry_diags = reference_resolver.bind_protocol_params(
            target_protocol=protocol,
            call_args=[],
            caller_env={},
            call_span=protocol.span,
            call_node_id=protocol.id,
            entry_mode=True,
            entry_arg_values=(entry_args_by_protocol or {}).get(protocol.name, {}),
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
            statement_lowerer=statement_lowerer,
            serializer=serializer,
            reference_resolver=reference_resolver,
            step_id_prefix="",
            call_path=[],
        )
        ordered_steps = statement_lowerer.lower_list(protocol.statements, ctx)
        steps = serializer.linearize_steps(ordered_steps)

        plans.append(
            ProtocolPlan(
                protocol_id=protocol.id,
                protocol_name=protocol.name,
                returns=list(protocol.returns),
                return_value=serializer.serialize_expr(protocol.return_value, env) if protocol.return_value is not None else None,
                return_bindings={
                    arg.name: serializer.serialize_expr(arg.value, env)
                    for arg in protocol.return_bindings
                },
                steps=steps,
                span=protocol.span,
            )
        )

    return PlanProgram(plans=plans, diagnostics=diagnostics, span=ir.span)


__all__ = [
    "BasePlanStatementHandler",
    "PlanExpressionSerializer",
    "PlanLoweringContext",
    "PlanReferenceResolver",
    "PlanStatementLowerer",
    "PlanStatementLoweringState",
    "lower_ir_to_plan",
]
