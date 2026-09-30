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
    SHAKE = "shake"
    STIR = "stir"
    ROTATION = "rotation"


AGITATION_MODE = EnumParameter(AgitationMode)


def conflicting_arguments(mode: AgitationMode, present: set[str]) -> tuple[str, ...]:
    """Return conflicting parameter names in stable diagnostic order."""
    value = AGITATION_MODE.validate(mode)
    forbidden = ("duration", "rate") if value in {AgitationMode.INVERT, AgitationMode.FLICK} else ("cycles",)
    return tuple(name for name in forbidden if name in present)


def validate_agitation_arguments(mode: AgitationMode, *, has_duration: bool, has_rate: bool, has_cycles: bool) -> AgitationMode:
    """Check mode-dependent arguments after the actual mode has been bound."""
    value = AGITATION_MODE.validate(mode)
    if value is AgitationMode.ROTATION and not has_duration:
        raise ValueError("rotation requires duration")
    present = {name for name, enabled in (
        ("duration", has_duration), ("rate", has_rate), ("cycles", has_cycles)
    ) if enabled}
    conflicts = conflicting_arguments(value, present)
    if conflicts:
        if conflicts[0] in {"duration", "rate"}:
            raise ValueError('invert/flick forbid duration and rate; use cycles')
        raise ValueError('cycles is only allowed for invert/flick')
    return value


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
        validate_agitation_arguments(values['mode'], has_duration='duration' in present,
                                    has_rate='rate' in present, has_cycles='cycles' in present)
        if values['mode'] is AgitationMode.ROTATION:
            for name in ('duration', 'rate'):
                if name in values:
                    validate_rotation_quantity(name, values[name])


CALL_PARAMETER_CONTRACTS = MappingProxyType({'agit': CallParameterContract({'mode': AGITATION_MODE}, (AgitationArgumentsRule(),))})
