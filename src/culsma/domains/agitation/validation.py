"""Agitation-specific IR validation and source diagnostics."""

from __future__ import annotations

from typing import AbstractSet, Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRArg, IRStep
from culsma.pipeline.external_inputs import external_parameter_resolution, ExternalInputStatus, ExternalInputIssue
from .contracts import AGITATION_MODE, AgitationMode, ShakeMotionRule, conflicting_arguments, validate_rotation_quantity
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

    motion_arg = _find_arg(step, 'motion')
    if motion_arg is not None:
        return validate_motion(step, mode_value, motion_arg,
                                {**(expr_bindings or {}), **literal_bindings}, defined_names)

    arguments = {name: _find_arg(step, name) for name in ("duration", "rate", "cycles")}
    if mode_value not in {AgitationMode.INVERT, AgitationMode.FLICK, AgitationMode.ROTATION}:
        rate = arguments['rate']
        value = rate.value if rate is not None else None
        bindings = {**(expr_bindings or {}), **literal_bindings}
        seen = set()
        while isinstance(value, IRIdentifier) and value.name in bindings and value.name not in seen:
            seen.add(value.name)
            value = bindings[value.name]
        if isinstance(value, IRQuantity) and value.unit in {'Hz', 'cycle/min'}:
            diagnostics.append(Diagnostic(code='SEM_AGIT_QUANTITY_INVALID',
                message='agitation rate without motion must use rpm',
                span=rate.span or step.span, node_id=step.id))
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


def validate_motion(
    step: IRStep,
    mode: AgitationMode,
    motion_arg: IRArg,
    bindings: dict[str, Any],
    defined_names: AbstractSet[str],
) -> list[Diagnostic]:
    """Validate an explicit motion argument after resolving the agitation mode.

    Translate motion contract violations into source diagnostics. Deferred
    inputs and enum type/binding errors remain owned by their pipeline stages.
    """
    if mode is not AgitationMode.SHAKE:
        return [Diagnostic(code='SEM_AGIT_ARG_CONFLICT',
                           message='motion is only allowed with mode=shake',
                           span=motion_arg.span or step.span, node_id=step.id)]
    resolution = external_parameter_resolution('agit', 'motion', motion_arg.value,
        bindings=bindings, defined_names=defined_names)
    if resolution.status is ExternalInputStatus.DEFERRED or resolution.issue in {
        ExternalInputIssue.WRONG_TYPE, ExternalInputIssue.CYCLIC_BINDING,
    }:
        return []
    if resolution.status is not ExternalInputStatus.RESOLVED:
        return [Diagnostic(code='SEM_AGIT_MOTION_UNKNOWN',
                           message='shake motion must be linear, orbital, rock or rotation',
                           span=motion_arg.span or step.span, node_id=step.id)]
    motion = resolution.value
    arguments = {arg.name: arg for arg in step.args}
    diagnostics = [Diagnostic(code={'conflict': 'SEM_AGIT_ARG_CONFLICT', 'duration': 'SEM_AGIT_DURATION_REQUIRED'}[kind], message=message,
                             span=arguments[name].span or step.span, node_id=step.id)
                   for name, kind, message in ShakeMotionRule.argument_violations(motion, set(arguments))]
    for name in ('duration', 'rate', 'cycles'):
        arg = arguments.get(name)
        if arg is None:
            continue
        value = arg.value
        seen = set()
        while isinstance(value, IRIdentifier) and value.name in bindings and value.name not in seen:
            seen.add(value.name)
            value = bindings[value.name]
        if isinstance(value, IRQuantity):
            try:
                ShakeMotionRule.validate_quantity(motion, name, (value.value, value.unit))
            except ValueError as error:
                diagnostics.append(Diagnostic(code='SEM_AGIT_QUANTITY_INVALID', message=str(error),
                                              span=arg.span or step.span, node_id=step.id))
    return diagnostics
