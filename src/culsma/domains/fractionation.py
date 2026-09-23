"""Closed density-gradient vocabulary; chromatography extensions are separate."""
from enum import StrEnum
from .contracts import EnumParameter


class DensityGradientAxis(StrEnum):
    DENSITY = "density"


class DensityGradientOrder(StrEnum):
    TOP_TO_BOTTOM = "top_to_bottom"
    BOTTOM_TO_TOP = "bottom_to_top"


DENSITY_GRADIENT_AXIS = EnumParameter(DensityGradientAxis)
DENSITY_GRADIENT_ORDER = EnumParameter(DensityGradientOrder)
