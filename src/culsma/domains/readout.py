"""Readout quantities and operation-specific membership contracts."""
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from .contracts import EnumParameter


class ReadoutQuantity(StrEnum):
    UV_ABSORBANCE = "uv_absorbance"
    FLUORESCENCE = "fluorescence"
    COLORIMETRIC = "colorimetric"
    PH = "ph"
    CONDUCTIVITY = "conductivity"
    DISSOLVED_OXYGEN = "dissolved_oxygen"
    ORP = "orp"
    TEMPERATURE = "temperature"
    PRESSURE = "pressure"
    FLOW_RATE = "flow_rate"
    MASS = "mass"
    VOLUME = "volume"
    HUMIDITY = "humidity"
    CURRENT = "current"
    CUSTOMIZED = "customized"


READOUT_QUANTITIES = MappingProxyType({
    "img": EnumParameter(ReadoutQuantity, frozenset({
        ReadoutQuantity.UV_ABSORBANCE, ReadoutQuantity.FLUORESCENCE,
        ReadoutQuantity.COLORIMETRIC, ReadoutQuantity.CUSTOMIZED,
    })),
    "ecp": EnumParameter(ReadoutQuantity, frozenset({
        ReadoutQuantity.PH, ReadoutQuantity.CONDUCTIVITY, ReadoutQuantity.DISSOLVED_OXYGEN,
        ReadoutQuantity.ORP, ReadoutQuantity.CUSTOMIZED,
    })),
    "phy": EnumParameter(ReadoutQuantity, frozenset({
        ReadoutQuantity.TEMPERATURE, ReadoutQuantity.PRESSURE, ReadoutQuantity.FLOW_RATE,
        ReadoutQuantity.MASS, ReadoutQuantity.VOLUME, ReadoutQuantity.HUMIDITY,
        ReadoutQuantity.CURRENT, ReadoutQuantity.CUSTOMIZED,
    })),
})


def validate_readout_quantity(operation: str, quantity: ReadoutQuantity, *, has_schema: bool) -> ReadoutQuantity:
    value = READOUT_QUANTITIES[operation].validate(quantity)
    if value is ReadoutQuantity.CUSTOMIZED and not has_schema:
        raise ValueError("Customized readout requires schema_ref")
    return value


@dataclass(frozen=True)
class ReadoutQuantityRule:
    operation: str
    parameters = frozenset({'quantity'})

    def validate(self, values, present):
        validate_readout_quantity(self.operation, values['quantity'], has_schema='schema_ref' in present)
