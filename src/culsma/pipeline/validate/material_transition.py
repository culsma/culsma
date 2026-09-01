"""Semantic contract for author-supplied material relationship transitions."""

from __future__ import annotations

from typing import Any, Mapping

from culsma.common.diagnostics import Diagnostic
from culsma.common.source import Span
from culsma.pipeline.container_views import resolve_materials_index
from culsma.pipeline.ir_nodes import IRArg, IRCall, IRIdentifier, IRList, IRString
from culsma.scientific_model.material import (
    AUTHOR_SETTABLE_MATERIAL_RELATIONS,
    COMPONENT_BOUND_MATERIAL_RELATIONS,
    MaterialRelation,
)

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
                    "each transitions item must be a transition(...) call",
                    getattr(rule, "span", None) or transition_arg.span or span,
                    node_id,
                )
            )
            continue

        named = {arg.name: arg for arg in rule.args}
        names = [arg.name for arg in rule.args]
        required_names = {"subject", "output", "to"}
        allowed_names = required_names | {"associated_with"}
        if (
            not required_names.issubset(names)
            or not set(names).issubset(allowed_names)
            or len(names) != len(set(names))
        ):
            diagnostics.append(
                _issue(
                    "SEM_MATERIAL_TRANSITION_ARGS_INVALID",
                    "transition requires subject, output, and to, with optional associated_with",
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
        target_relation: MaterialRelation | None = None
        if isinstance(target_expr, IRIdentifier) and target_expr.name not in expr_bindings:
            try:
                target_relation = MaterialRelation(target_expr.name)
            except ValueError:
                target_relation = None
        if target_relation not in AUTHOR_SETTABLE_MATERIAL_RELATIONS:
            diagnostics.append(
                _issue(
                    "SEM_MATERIAL_TRANSITION_TARGET_INVALID",
                    "transition to must be an author-settable MaterialRelation enum identifier",
                    named["to"].span or rule.span or span,
                    node_id,
                )
            )

        association_arg = named.get("associated_with")
        if target_relation in COMPONENT_BOUND_MATERIAL_RELATIONS:
            if association_arg is None:
                diagnostics.append(
                    _issue(
                        "SEM_MATERIAL_TRANSITION_ASSOCIATION_REQUIRED",
                        f"transition to {target_relation.value} requires associated_with = sample.materials[index]",
                        rule.span or transition_arg.span or span,
                        node_id,
                    )
                )
        elif association_arg is not None:
            diagnostics.append(
                _issue(
                    "SEM_MATERIAL_TRANSITION_ASSOCIATION_FORBIDDEN",
                    "associated_with is only valid for component-bound target relations",
                    association_arg.span or rule.span or span,
                    node_id,
                )
            )

        if association_arg is not None:
            association_selector = resolve_materials_index(
                association_arg.value,
                expr_bindings=expr_bindings,
            )
            if association_selector is None:
                diagnostics.append(
                    _issue(
                        "SEM_MATERIAL_TRANSITION_ASSOCIATION_INVALID",
                        "associated_with must be sample.materials[index]",
                        association_arg.span or rule.span or span,
                        node_id,
                    )
                )
            else:
                association_sample = _identifier_name(association_selector.container)
                if sample_name is None or association_sample != sample_name:
                    diagnostics.append(
                        _issue(
                            "SEM_MATERIAL_SELECTOR_CONTAINER_MISMATCH",
                            "associated_with container must be the same binding as sep sample",
                            association_arg.span or rule.span or span,
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
