"""Standard plate geometry and capacity defaults."""
from dataclasses import dataclass
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


def parse_well_position(position: str) -> tuple[int, int]:
    """Parse a positive A1-style coordinate, independent of a plate layout."""
    index = 0
    while index < len(position) and 'A' <= position[index] <= 'Z':
        index += 1
    if index == 0 or index == len(position) or not position[index:].isdigit():
        raise ValueError(f"Invalid well position '{position}'")
    row = 0
    for char in position[:index]:
        row = row * 26 + ord(char) - ord('A') + 1
    col = int(position[index:])
    if col < 1:
        raise ValueError(f"Invalid well position '{position}'")
    return row, col


def row_index_to_label(index: int) -> str:
    if type(index) is not int or index < 1:
        raise ValueError('Row index must be a positive integer')
    parts = []
    while index:
        index, remainder = divmod(index - 1, 26)
        parts.append(chr(ord('A') + remainder))
    return ''.join(reversed(parts))


def selector_positions(regions: list[tuple[str, str | None]]) -> list[str]:
    """Enumerate logical coordinates in source region / row-major order.

    This does not validate geometry or materialize containers. Bounds depend
    on the actual layout and are checked only after parameter binding.
    """
    positions = []
    seen = set()
    for start, end in regions:
        first_row, first_col = parse_well_position(start)
        last_row, last_col = parse_well_position(end or start)
        for row in range(min(first_row, last_row), max(first_row, last_row) + 1):
            for col in range(min(first_col, last_col), max(first_col, last_col) + 1):
                position = f'{row_index_to_label(row)}{col}'
                if position in seen:
                    raise ValueError(f"Duplicate well '{position}' is not allowed in plate selector")
                positions.append(position)
                seen.add(position)
    return positions


@dataclass(frozen=True)
class PlateGeometry:
    rows: int
    cols: int

    def __post_init__(self):
        if type(self.rows) is not int or type(self.cols) is not int or self.rows < 1 or self.cols < 1:
            raise ValueError('Plate rows and cols must be positive integers')

    def validate_position(self, position: str) -> None:
        row, col = parse_well_position(position)
        if row > self.rows or col > self.cols:
            raise ValueError(
                f"plate selector '{position}' exceeds plate bounds ({self.rows} rows, {self.cols} cols)"
            )


def validate_plate_position(position: str, *, rows: int, cols: int) -> None:
    """Compatibility entry point; geometry owns the bounds rule."""
    PlateGeometry(rows, cols).validate_position(position)
