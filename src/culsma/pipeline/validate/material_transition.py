"""Semantic contract for author-supplied material relationship transitions."""

from __future__ import annotations

from typing import Any, Mapping

from culsma.common.diagnostics import Diagnostic
from culsma.common.source import Span
from culsma.pipeline.container_views import resolve_materials_index
from culsma.pipeline.ir_nodes import IRArg, IRCall, IRIdentifier, IRList, IRString

from .resolution import ExprResolver


def validate_material_transitions_contract(
    args: list[IRArg],
    *,
    expr_bindings: dict[str, Any],
    output_contract: Mapping[str, str] | None,
    node_id: str | None,
    span: Span | None,
) -> list[Diagnostic]:
    transition_arg = next((arg for arg in args if arg.name == "transitions"), None)
    if transition_arg is None:
        return []

    rules = ExprResolver.resolve_bound_expr(transition_arg.value, expr_bindings)
    if not isinstance(rules, IRList):
        return [
            _issue(
                "SEM_MATERIAL_TRANSITIONS_SHAPE_INVALID",
                "sep transitions must be a list",
                transition_arg.span or span,
                node_id,
            )
        ]

    sample_arg = next((arg for arg in args if arg.name == "sample"), None)
    sample_name = _identifier_name(sample_arg.value) if sample_arg is not None else None
    output_aliases = _output_aliases(output_contract)
    diagnostics: list[Diagnostic] = []
    for rule in rules.elements:
        if not isinstance(rule, IRCall) or rule.name != "transition":
            diagnostics.append(
                _issue(
                    "SEM_MATERIAL_TRANSITION_SHAPE_INVALID",
                    "each transitions item must be transition(subject = ..., output = ..., to = ...)",
                    getattr(rule, "span", None) or transition_arg.span or span,
                    node_id,
                )
            )
            continue

        named = {arg.name: arg for arg in rule.args}
        names = [arg.name for arg in rule.args]
        if set(names) != {"subject", "output", "to"} or len(names) != 3:
            diagnostics.append(
                _issue(
                    "SEM_MATERIAL_TRANSITION_ARGS_INVALID",
                    "transition requires exactly subject, output, and to",
                    rule.span or transition_arg.span or span,
                    node_id,
                )
            )
            continue

        selector = resolve_materials_index(
            named["subject"].value,
            expr_bindings=expr_bindings,
        )
        if selector is None:
            diagnostics.append(
                _issue(
                    "SEM_MATERIAL_SELECTOR_INVALID",
                    "transition subject must be sample.materials[index]",
                    named["subject"].span or rule.span or span,
                    node_id,
                )
            )
        else:
            selector_sample = _identifier_name(selector.container)
            if sample_name is None or selector_sample != sample_name:
                diagnostics.append(
                    _issue(
                        "SEM_MATERIAL_SELECTOR_CONTAINER_MISMATCH",
                        "transition subject container must be the same binding as sep sample",
                        named["subject"].span or rule.span or span,
                        node_id,
                    )
                )

        output_expr = named["output"].value
        output_name = output_expr.name if isinstance(output_expr, IRIdentifier) else None
        if (
            isinstance(output_expr, IRString)
            or output_name is None
            or output_name in expr_bindings
        ):
            diagnostics.append(
                _issue(
                    "SEM_MATERIAL_TRANSITION_OUTPUT_INVALID",
                    "transition output must be a declared output enum identifier",
                    named["output"].span or rule.span or span,
                    node_id,
                )
            )
        elif output_contract is not None and output_name not in output_aliases:
            diagnostics.append(
                _issue(
                    "SEM_MATERIAL_TRANSITION_OUTPUT_INVALID",
                    f"transition output '{output_name}' is not declared by the separation program",
                    named["output"].span or rule.span or span,
                    node_id,
                )
            )

        target_expr = named["to"].value
        if (
            not isinstance(target_expr, IRIdentifier)
            or target_expr.name != "free"
            or target_expr.name in expr_bindings
        ):
            diagnostics.append(
                _issue(
                    "SEM_MATERIAL_TRANSITION_TARGET_INVALID",
                    "transition to must be the MaterialRelation enum identifier free",
                    named["to"].span or rule.span or span,
                    node_id,
                )
            )
    return diagnostics


def _output_aliases(output_contract: Mapping[str, str] | None) -> set[str]:
    if output_contract is None:
        return set()
    return set(output_contract) | set(output_contract.values())


def _identifier_name(expr: Any) -> str | None:
    return expr.name if isinstance(expr, IRIdentifier) else None


def _issue(
    code: str,
    message: str,
    span: Span | None,
    node_id: str | None,
) -> Diagnostic:
    return Diagnostic(code=code, message=message, span=span, node_id=node_id)
