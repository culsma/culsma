"""Standard plate geometry and capacity defaults."""

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from culsma.common.enum_parameters import EnumParameter
from culsma.common.enum_parameters import CallParameterContract


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


@dataclass(frozen=True)
class PlateReference:
    """One physical carrier instance; display identifiers do not define identity."""

    id: str
    carrier_id: str | None
    rows: int | None
    cols: int | None
    label: str | None = None

    def __post_init__(self):
        if type(self.id) is not str or not self.id or self.carrier_id is not None and type(self.carrier_id) is not str:
            raise ValueError('Plate reference requires instance identity and optional carrier text')
        if self.label is not None and type(self.label) is not str:
            raise ValueError('Plate label must be text')
        if self.rows is not None or self.cols is not None:
            PlateGeometry(self.rows, self.cols)

    def to_dict(self):
        return {'kind': 'plate_ref', 'id': self.id, 'carrier_id': self.carrier_id,
                'rows': self.rows, 'cols': self.cols, 'label': self.label}

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or value.get('kind') != 'plate_ref':
            raise ValueError('Expected a plate reference')
        return cls(value.get('id'), value.get('carrier_id'), value.get('rows'),
                   value.get('cols'), value.get('label'))


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



CALL_PARAMETER_CONTRACTS = MappingProxyType({'plate': CallParameterContract({'format': PLATE_FORMAT})})
