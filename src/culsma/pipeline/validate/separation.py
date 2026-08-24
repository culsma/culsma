"""Semantic validation for author-defined per-content separation fates."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.common.source import Span
from culsma.pipeline.ir_nodes import IRArg, IRCall, IRQuantity, IRRecord
from culsma.pipeline.program_registry import get_separation_slot_contract

from .resolution import ExprResolver

_RATIO_EPSILON = 1e-9


def validate_component_fates_contract(
    args: list[IRArg],
    *,
    expr_bindings: dict[str, Any],
    node_id: str | None,
    span: Span | None,
) -> list[Diagnostic]:
    fate_arg = next((arg for arg in args if arg.name == "component_fates"), None)
    if fate_arg is None:
        return []

    program_arg = next((arg for arg in args if arg.name == "program"), None)
    program = (
        ExprResolver.resolve_call_expr(program_arg.value, expr_bindings)
        if program_arg is not None
        else None
    )
    if not isinstance(program, IRCall):
        return [
            _diagnostic(
                "SEM_SEPARATION_FATE_PROGRAM_UNRESOLVED",
                "component_fates requires a statically resolved separation program",
                fate_arg.span or span,
                node_id,
            )
        ]

    slot_contract = get_separation_slot_contract(program.name)
    if slot_contract is None:
        return []  # The attached-program validator owns unknown/incompatible programs.

    rules = ExprResolver.resolve_bound_expr(fate_arg.value, expr_bindings)
    if not isinstance(rules, IRRecord):
        return [
            _diagnostic(
                "SEM_SEPARATION_FATE_RULE_SHAPE_INVALID",
                "sep component_fates must be a record keyed by content id",
                fate_arg.span or span,
                node_id,
            )
        ]

    aliases = {slot: slot for slot in slot_contract}
    aliases.update({name: slot for slot, name in slot_contract.items()})
    expected_slots = set(slot_contract)
    diagnostics: list[Diagnostic] = []
    for component_id, raw_fate in rules.entries.items():
        fate = raw_fate
        if not isinstance(fate, IRRecord):
            diagnostics.append(
                _diagnostic(
                    "SEM_SEPARATION_FATE_RULE_SHAPE_INVALID",
                    f"component_fates entry '{component_id}' must be a record of output ratios",
                    getattr(raw_fate, "span", None) or fate_arg.span or span,
                    node_id,
                )
            )
            continue

        slot_values: dict[str, float] = {}
        invalid = False
        for output_name, raw_value in fate.entries.items():
            slot = aliases.get(output_name)
            if slot is None:
                diagnostics.append(
                    _diagnostic(
                        "SEM_SEPARATION_FATE_RULE_SLOT_INVALID",
                        (
                            f"component_fates entry '{component_id}' uses unknown output "
                            f"'{output_name}'; expected {', '.join(sorted(aliases))}"
                        ),
                        getattr(raw_value, "span", None) or fate.span or fate_arg.span or span,
                        node_id,
                    )
                )
                invalid = True
                continue
            ratio = _static_ratio(raw_value, expr_bindings)
            if ratio is None or ratio < 0.0 or ratio > 1.0:
                diagnostics.append(
                    _diagnostic(
                        "SEM_SEPARATION_FATE_RULE_VALUE_INVALID",
                        (
                            f"component_fates ratio for '{component_id}.{output_name}' "
                            "must be a unitless value from 0 to 1 or a percentage "
                            "from 0% to 100%"
                        ),
                        getattr(raw_value, "span", None) or fate.span or fate_arg.span or span,
                        node_id,
                    )
                )
                invalid = True
                continue
            if slot in slot_values:
                diagnostics.append(
                    _diagnostic(
                        "SEM_SEPARATION_FATE_RULE_SLOT_INVALID",
                        f"component_fates entry '{component_id}' declares output slot {slot} more than once",
                        getattr(raw_value, "span", None) or fate.span or fate_arg.span or span,
                        node_id,
                    )
                )
                invalid = True
                continue
            slot_values[slot] = ratio

        if expected_slots - set(slot_values):
            diagnostics.append(
                _diagnostic(
                    "SEM_SEPARATION_FATE_RULE_SHAPE_INVALID",
                    f"component_fates entry '{component_id}' must declare both separation outputs",
                    fate.span or fate_arg.span or span,
                    node_id,
                )
            )
            invalid = True
        if not invalid and abs(sum(slot_values.values()) - 1.0) > _RATIO_EPSILON:
            diagnostics.append(
                _diagnostic(
                    "SEM_SEPARATION_FATE_RULE_TOTAL_INVALID",
                    f"component_fates ratios for '{component_id}' must sum to 1 (100%)",
                    fate.span or fate_arg.span or span,
                    node_id,
                )
            )
    return diagnostics


def _static_ratio(value: Any, expr_bindings: dict[str, Any]) -> float | None:
    del expr_bindings
    if not isinstance(value, IRQuantity):
        return None
    if value.unit is None:
        return float(value.value)
    if value.unit in {"%", "pct"}:
        return float(value.value) / 100.0
    return None


def _diagnostic(code: str, message: str, span: Span | None, node_id: str | None) -> Diagnostic:
    return Diagnostic(code=code, message=message, span=span, node_id=node_id)
