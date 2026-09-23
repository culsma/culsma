"""Agitation vocabulary."""
from enum import StrEnum
from .contracts import EnumParameter


class AgitationMode(StrEnum):
    VORTEX = "vortex"
    INVERT = "invert"
    FLICK = "flick"
    SHAKE = "shake"
    STIR = "stir"


AGITATION_MODE = EnumParameter(AgitationMode)


def validate_agitation_arguments(mode: AgitationMode, *, has_duration: bool, has_rate: bool, has_cycles: bool) -> AgitationMode:
    """Check mode-dependent arguments after the actual mode has been bound."""
    value = AGITATION_MODE.validate(mode)
    if value in {AgitationMode.INVERT, AgitationMode.FLICK}:
        if has_duration or has_rate:
            raise ValueError('invert/flick forbid duration and rate; use cycles')
    elif has_cycles:
        raise ValueError('cycles is only allowed for invert/flick')
    return value
