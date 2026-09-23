"""Standard plate geometry and capacity defaults."""
from enum import StrEnum
from types import MappingProxyType
from .contracts import EnumParameter


class PlateFormat(StrEnum):
    WELL_6 = "6well"
    WELL_12 = "12well"
    WELL_24 = "24well"
    WELL_48 = "48well"
    WELL_96 = "96well"
    WELL_384 = "384well"


PLATE_FORMAT = EnumParameter(PlateFormat)
PLATE_DIMENSIONS = MappingProxyType({
    PlateFormat.WELL_6: (2, 3),
    PlateFormat.WELL_12: (3, 4),
    PlateFormat.WELL_24: (4, 6),
    PlateFormat.WELL_48: (6, 8),
    PlateFormat.WELL_96: (8, 12),
    PlateFormat.WELL_384: (16, 24),
})
PLATE_DEFAULT_WELL_CAPACITY = MappingProxyType({PlateFormat.WELL_24: (3.4, "mL")})


def plate_dimensions(format: PlateFormat) -> tuple[int, int]:
    return PLATE_DIMENSIONS[PLATE_FORMAT.validate(format)]


def plate_default_well_capacity(format: PlateFormat) -> tuple[float, str] | None:
    return PLATE_DEFAULT_WELL_CAPACITY.get(PLATE_FORMAT.validate(format))
