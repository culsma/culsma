"""Static boundary for N-output author-declared fractionation fates."""

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.common.source import Span
from culsma.domains.material_allocation import allocation_ratio, validate_allocation_ratios
from culsma.pipeline.expression_resolution import resolve_expression, ResolutionStatus
from culsma.pipeline.ir_nodes import IRArg, IRCall, IRList, IRQuantity, IRRecord
from .resolution import ExprResolver


def validate_fraction_fates_contract(
    args: list[IRArg], *, expr_bindings: dict[str, Any], node_id: str | None,
    span: Span | None, defined_names: set[str] | frozenset[str] = frozenset(),
) -> list[Diagnostic]:
    fate_arg = next((arg for arg in args if arg.name == "component_fates"), None)
    if fate_arg is None:
        return []
    result = resolve_expression(fate_arg.value, expr_bindings)
    if result.status is ResolutionStatus.DEFERRED and result.detail in defined_names:
        return []
    rules = result.value
    if not isinstance(rules, IRRecord):
        return [Diagnostic(code="SEM_FRACTION_FATE_RULE_SHAPE_INVALID",
                           message="frac component_fates must map source content identities to ordered ratio lists",
                           span=fate_arg.span or span, node_id=node_id)]
    program_arg = next((arg for arg in args if arg.name == "program"), None)
    program = ExprResolver.resolve_call_expr(program_arg.value, expr_bindings) if program_arg else None
    bins_arg = next((arg for arg in program.args if arg.name == "bins"), None) if isinstance(program, IRCall) else None
    bins_value = ExprResolver.resolve_bound_expr(bins_arg.value, expr_bindings) if bins_arg else None
    bins = (int(bins_value.value) if isinstance(bins_value, IRQuantity)
            and bins_value.unit is None and bins_value.value > 0
            and float(bins_value.value).is_integer() else None)
    diagnostics = []
    for content_id, raw in rules.entries.items():
        resolved = resolve_expression(raw, expr_bindings)
        if resolved.status is ResolutionStatus.DEFERRED and resolved.detail in defined_names:
            continue
        values = resolved.value
        error = "SHAPE_INVALID"
        if isinstance(values, IRList):
            ratios = []
            deferred = False
            for item in values.elements:
                value = resolve_expression(item, expr_bindings)
                if value.status is ResolutionStatus.DEFERRED and value.detail in defined_names:
                    deferred = True
                ratios.append(allocation_ratio(value.value.value, value.value.unit)
                              if isinstance(value.value, IRQuantity) else None)
            # Expanded protocol/schedule calls and Runtime check deferred values.
            if deferred:
                error = "SHAPE_INVALID" if bins is not None and len(ratios) != bins else None
            else:
                error = validate_allocation_ratios(tuple(ratios), bins if bins is not None else len(ratios))
        if error:
            diagnostics.append(Diagnostic(
                code=f"SEM_FRACTION_FATE_RULE_{error}",
                message=f"Fraction fate for '{content_id}' requires one ratio per bin, each in 0..1 or 0%..100%, totaling 100%",
                span=getattr(raw, "span", None) or fate_arg.span or span, node_id=node_id,
            ))
    return diagnostics
