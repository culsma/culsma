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
