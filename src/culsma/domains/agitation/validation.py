"""Agitation-specific IR validation and source diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet, Any, Callable

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.external_inputs import (
    ExternalInputIssue,
    ExternalInputStatus,
    external_parameter_resolution,
)
from culsma.pipeline.ir_nodes import IRArg, IRIdentifier, IRQuantity, IRStep

from .contracts import (
    AGITATION_MODE,
    AgitationMode,
    ShakeMotionRule,
    conflicting_arguments,
    validate_centrifuge_quantity,
    validate_rotation_quantity,
)


AGIT_MODES = frozenset(AGITATION_MODE.wire_values)


@dataclass(frozen=True)
class AgitationContractValidator:
    """Validate one agitation step against its source-level mode contract."""

    step: IRStep
    bindings: dict[str, Any]
    defined_names: AbstractSet[str] = frozenset()

    def validate(self) -> list[Diagnostic]:
        if self.step.name != 'agit':
            return []
        mode_arg = self.find_argument('mode')
        if mode_arg is None:
            return []

        resolution = external_parameter_resolution(
            'agit', 'mode', mode_arg.value,
            bindings=self.bindings, defined_names=self.defined_names,
        )
        if resolution.status is ExternalInputStatus.DEFERRED or resolution.issue in {
            ExternalInputIssue.WRONG_TYPE, ExternalInputIssue.CYCLIC_BINDING,
        }:
            return []
        mode = resolution.value
        if mode is None or mode not in AGIT_MODES:
            return [Diagnostic(
                code='SEM_AGIT_MODE_UNKNOWN',
                message='agit(...): mode must be one of vortex, invert, flick, shake, stir, rotation, centrifuge',
                span=mode_arg.span or self.step.span,
                node_id=self.step.id,
            )]

        if mode is AgitationMode.CENTRIFUGE:
            return self.validate_centrifuge()

        diagnostics: list[Diagnostic] = []
        drive_arg = self.find_argument('drive')
        if drive_arg is not None:
            diagnostics.append(Diagnostic(
                code='SEM_AGIT_ARG_CONFLICT',
                message='drive is only allowed with mode=centrifuge',
                span=drive_arg.span or self.step.span,
                node_id=self.step.id,
            ))
        motion_arg = self.find_argument('motion')
        if motion_arg is not None:
            return diagnostics + self.validate_motion(mode, motion_arg)
        return diagnostics + self.validate_without_motion(mode)

    def validate_centrifuge(self) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        for name, code in (('drive', 'SEM_MISSING_REQUIRED_ARG'), ('duration', 'SEM_AGIT_DURATION_REQUIRED')):
            arg = self.find_argument(name)
            if arg is None:
                diagnostics.append(Diagnostic(
                    code=code, message=f'centrifuge requires {name}',
                    span=self.step.span, node_id=self.step.id,
                ))
            else:
                diagnostics.extend(self.validate_quantity_argument(arg, name, validate_centrifuge_quantity))
        for name in ('motion', 'rate', 'cycles'):
            arg = self.find_argument(name)
            if arg is not None:
                diagnostics.append(Diagnostic(
                    code='SEM_AGIT_ARG_CONFLICT', message=f'centrifuge does not accept {name}',
                    span=arg.span or self.step.span, node_id=self.step.id,
                ))
        return diagnostics

    def validate_without_motion(self, mode: AgitationMode) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        arguments = {name: self.find_argument(name) for name in ('duration', 'rate', 'cycles')}
        if mode not in {AgitationMode.INVERT, AgitationMode.FLICK, AgitationMode.ROTATION}:
            rate = arguments['rate']
            value = self.resolve_bound_value(rate.value) if rate is not None else None
            if isinstance(value, IRQuantity) and value.unit in {'Hz', 'cycle/min'}:
                diagnostics.append(Diagnostic(
                    code='SEM_AGIT_QUANTITY_INVALID',
                    message='agitation rate without motion must use rpm',
                    span=rate.span or self.step.span, node_id=self.step.id,
                ))
        if mode is AgitationMode.ROTATION:
            if arguments['duration'] is None:
                diagnostics.append(Diagnostic(
                    code='SEM_AGIT_DURATION_REQUIRED', message='rotation requires duration',
                    span=self.step.span, node_id=self.step.id,
                ))
            for name in ('duration', 'rate'):
                arg = arguments[name]
                if arg is not None:
                    diagnostics.extend(self.validate_quantity_argument(arg, name, validate_rotation_quantity))
        for name in conflicting_arguments(mode, {name for name, arg in arguments.items() if arg is not None}):
            arg = arguments[name]
            alternative = 'cycles' if name in {'duration', 'rate'} else 'duration/rate'
            diagnostics.append(Diagnostic(
                code='SEM_AGIT_ARG_CONFLICT',
                message=f'agit(mode = {mode}): {name} is not allowed; use {alternative}',
                span=arg.span or self.step.span, node_id=self.step.id,
            ))
        return diagnostics

    def validate_motion(self, mode: AgitationMode, motion_arg: IRArg) -> list[Diagnostic]:
        """Map explicit motion contract violations to source diagnostics."""
        if mode is not AgitationMode.SHAKE:
            return [Diagnostic(
                code='SEM_AGIT_ARG_CONFLICT', message='motion is only allowed with mode=shake',
                span=motion_arg.span or self.step.span, node_id=self.step.id,
            )]
        resolution = external_parameter_resolution(
            'agit', 'motion', motion_arg.value,
            bindings=self.bindings, defined_names=self.defined_names,
        )
        if resolution.status is ExternalInputStatus.DEFERRED or resolution.issue in {
            ExternalInputIssue.WRONG_TYPE, ExternalInputIssue.CYCLIC_BINDING,
        }:
            return []
        if resolution.status is not ExternalInputStatus.RESOLVED:
            return [Diagnostic(
                code='SEM_AGIT_MOTION_UNKNOWN',
                message='shake motion must be linear, orbital, rock or rotation',
                span=motion_arg.span or self.step.span, node_id=self.step.id,
            )]
        motion = resolution.value
        arguments = {arg.name: arg for arg in self.step.args}
        diagnostics = [Diagnostic(
            code={'conflict': 'SEM_AGIT_ARG_CONFLICT', 'duration': 'SEM_AGIT_DURATION_REQUIRED'}[kind],
            message=message,
            span=arguments[name].span or self.step.span,
            node_id=self.step.id,
        ) for name, kind, message in ShakeMotionRule.argument_violations(motion, set(arguments))]
        for name in ('duration', 'rate', 'cycles'):
            arg = arguments.get(name)
            if arg is not None:
                diagnostics.extend(self.validate_quantity_argument(
                    arg, name,
                    lambda field, value: ShakeMotionRule.validate_quantity(motion, field, value),
                ))
        return diagnostics

    def validate_quantity_argument(
        self,
        arg: IRArg,
        name: str,
        validate: Callable[[str, tuple[Any, Any]], None],
    ) -> list[Diagnostic]:
        value = self.resolve_bound_value(arg.value)
        if not isinstance(value, IRQuantity):
            return []
        try:
            validate(name, (value.value, value.unit))
        except ValueError as error:
            return [Diagnostic(
                code='SEM_AGIT_QUANTITY_INVALID', message=str(error),
                span=arg.span or self.step.span, node_id=self.step.id,
            )]
        return []

    def resolve_bound_value(self, value: Any) -> Any:
        seen: set[str] = set()
        while isinstance(value, IRIdentifier) and value.name in self.bindings and value.name not in seen:
            seen.add(value.name)
            value = self.bindings[value.name]
        return value

    def find_argument(self, name: str) -> IRArg | None:
        return next((arg for arg in self.step.args if arg.name == name), None)


def validate_agit_contract(
    step: IRStep,
    *,
    literal_bindings: dict[str, Any],
    expr_bindings: dict[str, Any] | None = None,
    defined_names: AbstractSet[str] = frozenset(),
) -> list[Diagnostic]:
    """Keep the pipeline's function entry point while validating one IR step."""
    return AgitationContractValidator(
        step, {**(expr_bindings or {}), **literal_bindings}, defined_names,
    ).validate()


def validate_motion(
    step: IRStep,
    mode: AgitationMode,
    motion_arg: IRArg,
    bindings: dict[str, Any],
    defined_names: AbstractSet[str],
) -> list[Diagnostic]:
    """Keep the existing direct motion-validation entry point."""
    return AgitationContractValidator(step, bindings, defined_names).validate_motion(mode, motion_arg)
