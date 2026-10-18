"""Agitation vocabulary."""

from enum import StrEnum
from culsma.common.quantity_arithmetic import UNIT_TO_DIMENSION, require_finite_number
from culsma.common.enum_parameters import EnumParameter
from types import MappingProxyType
from culsma.common.enum_parameters import CallParameterContract


class AgitationMode(StrEnum):
    VORTEX = "vortex"
    INVERT = "invert"
    FLICK = "flick"
    TAP = "tap"
    SHAKE = "shake"
    STIR = "stir"
    ROTATION = "rotation"
    CENTRIFUGE = "centrifuge"


class ShakeMotion(StrEnum):
    LINEAR = "linear"
    ORBITAL = "orbital"
    ROCK = "rock"
    ROTATION = "rotation"


AGITATION_MODE = EnumParameter(AgitationMode)
SHAKE_MOTION = EnumParameter(ShakeMotion)


def validate_agitation_target(mode: AgitationMode, target_kind: str) -> None:
    """Check the current target/method contract independently of stage syntax."""
    if target_kind == 'plate' and AGITATION_MODE.validate(mode) is not AgitationMode.TAP:
        raise ValueError('whole-plate agitation requires mode=tap')


def conflicting_arguments(mode: AgitationMode, present: set[str]) -> tuple[str, ...]:
    """Return conflicting parameter names in stable diagnostic order."""
    value = AGITATION_MODE.validate(mode)
    forbidden = (
        ("duration", "rate", "cycles") if value is AgitationMode.TAP
        else ("duration", "rate") if value in {AgitationMode.INVERT, AgitationMode.FLICK}
        else ("rate", "cycles") if value is AgitationMode.CENTRIFUGE
        else ("cycles",)
    )
    return tuple(name for name in forbidden if name in present)


def validate_agitation_arguments(mode: AgitationMode, *, has_duration: bool, has_rate: bool, has_cycles: bool) -> AgitationMode:
    """Check mode-dependent arguments after the actual mode has been bound."""
    value = AGITATION_MODE.validate(mode)
    if value in {AgitationMode.ROTATION, AgitationMode.CENTRIFUGE} and not has_duration:
        raise ValueError(f"{value} requires duration")
    present = {name for name, enabled in (
        ("duration", has_duration), ("rate", has_rate), ("cycles", has_cycles)
    ) if enabled}
    conflicts = conflicting_arguments(value, present)
    if conflicts:
        if value is AgitationMode.TAP:
            raise ValueError('tap does not accept duration, rate or cycles')
        if conflicts[0] in {"duration", "rate"}:
            raise ValueError('invert/flick forbid duration and rate; use cycles')
        raise ValueError('cycles is only allowed for invert/flick')
    return value


def validate_centrifuge_quantity(name, value):
    expected = 'time' if name == 'duration' else 'centrifugal drive'
    units = set(UNIT_TO_DIMENSION) if name == 'duration' else {'g', 'rpm'}
    if not isinstance(value, tuple) or len(value) != 2 or value[1] not in units or (
        name == 'duration' and UNIT_TO_DIMENSION.get(value[1]) != 'time'
    ):
        raise ValueError(f'centrifuge {name} must be a {expected} quantity')
    try:
        number = require_finite_number(value[0])
    except ValueError as error:
        raise ValueError(f'centrifuge {name} must be finite and positive') from error
    if number <= 0:
        raise ValueError(f'centrifuge {name} must be finite and positive')


def validate_rotation_quantity(name, value):
    """Check a shared (number, unit) value, independent of stage representation."""
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError(f"rotation {name} must be a unit-bearing quantity")
    expected = "time" if name == "duration" else "rotation_rate"
    number, unit = value
    if UNIT_TO_DIMENSION.get(unit) != expected:
        raise ValueError(f"rotation {name} must have dimension {expected}")
    try:
        number = require_finite_number(number)
    except ValueError as error:
        raise ValueError(f"rotation {name} must be finite and positive") from error
    if number <= 0:
        raise ValueError(f"rotation {name} must be finite and positive")


class AgitationArgumentsRule:
    parameters = frozenset({'mode'})

    def validate(self, values, present):
        mode = values['mode']
        sample = values.get('sample')
        if mode is AgitationMode.TAP and isinstance(sample, dict) and sample.get('kind') == 'IRCall' and sample.get('name') == 'plate':
            raise ValueError('Whole-plate agitation requires a bound allocated plate reference')
        if isinstance(sample, dict) and sample.get('kind') == 'plate_ref':
            validate_agitation_target(mode, 'plate')
        if mode is AgitationMode.CENTRIFUGE:
            if 'drive' not in present:
                raise ValueError('centrifuge requires drive')
            if 'duration' not in present:
                raise ValueError('centrifuge requires duration')
            if 'motion' in present or 'rate' in present or 'cycles' in present:
                raise ValueError('centrifuge accepts drive and duration, not motion, rate or cycles')
            for name in ('drive', 'duration'):
                value = values.get(name)
                if value is not None:
                    validate_centrifuge_quantity(name, value)
            return
        if 'drive' in present:
            raise ValueError('drive is only allowed with mode=centrifuge')
        if 'motion' in present:
            if values['mode'] is not AgitationMode.SHAKE:
                raise ValueError('motion is only allowed with mode=shake')
            return
        validate_agitation_arguments(values['mode'], has_duration='duration' in present,
                                    has_rate='rate' in present, has_cycles='cycles' in present)
        if 'rate' in values and values['mode'] not in {AgitationMode.INVERT, AgitationMode.FLICK, AgitationMode.TAP, AgitationMode.ROTATION}:
            rate = values['rate']
            if isinstance(rate, tuple) and len(rate) == 2 and rate[1] != 'rpm':
                raise ValueError('agitation rate without motion must use rpm')
        if values['mode'] is AgitationMode.ROTATION:
            for name in ('duration', 'rate'):
                if name in values:
                    validate_rotation_quantity(name, values[name])


class ShakeMotionRule:
    """Motion-owned shape and quantity rules shared by source and runtime."""

    parameters = frozenset({'mode', 'motion'})

    @staticmethod
    def argument_violations(motion, present):
        SHAKE_MOTION.validate(motion)
        if motion is ShakeMotion.ROCK:
            if 'duration' in present and 'cycles' in present:
                return [('cycles', 'conflict', 'rock accepts duration or cycles, not both')]
            if not {'duration', 'cycles'} & present:
                return [('motion', 'duration', 'rock requires duration or cycles')]
        else:
            errors = []
            if 'duration' not in present:
                errors.append(('motion', 'duration', f'{motion} requires duration'))
            if 'cycles' in present:
                errors.append(('cycles', 'conflict', f'{motion} forbids cycles; use duration'))
            return errors
        return []

    @staticmethod
    def validate_quantity(motion, name, value):
        if name == 'cycles':
            if isinstance(value, tuple) and len(value) == 2 and value[1] is None:
                value = value[0]
            number = require_finite_number(value)
            if number <= 0 or int(number) != number:
                raise ValueError('rock cycles must be a positive integer')
            return
        if not isinstance(value, tuple) or len(value) != 2:
            raise ValueError(f'{motion} {name} must be a unit-bearing quantity')
        number, unit = value
        dimension = ('time' if name == 'duration' else
                     'frequency' if motion in {ShakeMotion.LINEAR, ShakeMotion.ROCK} else 'rotation_rate')
        if not isinstance(unit, str) or UNIT_TO_DIMENSION.get(unit) != dimension:
            raise ValueError(f'{motion} {name} must have dimension {dimension}')
        try:
            number = require_finite_number(number)
        except ValueError as error:
            raise ValueError(f'{motion} {name} must be finite and positive') from error
        if number <= 0:
            raise ValueError(f'{motion} {name} must be finite and positive')

    def validate(self, values, present):
        if values['mode'] is not AgitationMode.SHAKE:
            raise ValueError('motion is only allowed with mode=shake')
        motion = SHAKE_MOTION.validate(values['motion'])
        errors = self.argument_violations(motion, present)
        if errors:
            raise ValueError(errors[0][2])
        for name in ('duration', 'rate', 'cycles'):
            if name in values:
                self.validate_quantity(motion, name, values[name])


CALL_PARAMETER_CONTRACTS = MappingProxyType({'agit': CallParameterContract(
    {'mode': AGITATION_MODE, 'motion': SHAKE_MOTION},
    (AgitationArgumentsRule(), ShakeMotionRule()),
)})
