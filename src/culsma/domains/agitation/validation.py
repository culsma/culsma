"""Agitation-specific IR validation and source diagnostics."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRStep
from culsma.pipeline.external_inputs import external_parameter_resolution, ExternalInputStatus, ExternalInputIssue
from .contracts import AGITATION_MODE, AgitationMode, conflicting_arguments, validate_rotation_quantity
from culsma.pipeline.ir_nodes import IRQuantity, IRIdentifier

AGIT_MODES = frozenset(AGITATION_MODE.wire_values)


def validate_agit_contract(step: IRStep, *, literal_bindings: dict[str, Any], expr_bindings=None, defined_names=frozenset()) -> list[Diagnostic]:
    if step.name != "agit":
        return []

    diagnostics: list[Diagnostic] = []
    mode_arg = _find_arg(step, "mode")
    if mode_arg is None:
        return diagnostics

    resolution = external_parameter_resolution('agit', 'mode', mode_arg.value,
        bindings={**(expr_bindings or {}), **literal_bindings}, defined_names=defined_names)
    if resolution.status is ExternalInputStatus.DEFERRED or resolution.issue in {ExternalInputIssue.WRONG_TYPE, ExternalInputIssue.CYCLIC_BINDING}:
        return []
    mode_value = resolution.value
    if mode_value is None or mode_value not in AGIT_MODES:
        diagnostics.append(
            Diagnostic(
                code="SEM_AGIT_MODE_UNKNOWN",
                message="agit(...): mode must be one of vortex, invert, flick, shake, stir, rotation",
                span=mode_arg.span or step.span,
                node_id=step.id,
            )
        )
        return diagnostics

    arguments = {name: _find_arg(step, name) for name in ("duration", "rate", "cycles")}
    if mode_value is AgitationMode.ROTATION:
        if arguments["duration"] is None:
            diagnostics.append(Diagnostic(
                code="SEM_AGIT_DURATION_REQUIRED", message="rotation requires duration",
                span=step.span, node_id=step.id,
            ))
        bindings = {**(expr_bindings or {}), **literal_bindings}
        for name in ("duration", "rate"):
            arg = arguments[name]
            if arg is None:
                continue
            value = arg.value
            seen = set()
            while isinstance(value, IRIdentifier) and value.name in bindings and value.name not in seen:
                seen.add(value.name)
                value = bindings[value.name]
            if isinstance(value, IRQuantity):
                try:
                    validate_rotation_quantity(name, (value.value, value.unit))
                except ValueError as error:
                    diagnostics.append(Diagnostic(
                        code="SEM_AGIT_QUANTITY_INVALID", message=str(error),
                        span=arg.span or step.span, node_id=step.id,
                    ))
    for name in conflicting_arguments(mode_value, {name for name, arg in arguments.items() if arg is not None}):
        arg = arguments[name]
        alternative = "cycles" if name in {"duration", "rate"} else "duration/rate"
        diagnostics.append(
            Diagnostic(
                code="SEM_AGIT_ARG_CONFLICT",
                message=f"agit(mode = {mode_value}): {name} is not allowed; use {alternative}",
                span=arg.span or step.span,
                node_id=step.id,
            )
        )
    return diagnostics


def _find_arg(step: IRStep, name: str):
    return next((arg for arg in step.args if arg.name == name), None)
