"""Device-independent environment quantities shared by checking and execution."""

from enum import Enum

from culsma.common.quantity_arithmetic import QuantityDimension, UNIT_TO_DIMENSION, require_finite_number


class EnvironmentKey(Enum):
    """Internal ENV condition identity. Values name canonical wire fields."""

    THERMAL = "thermal"
    FIELD = "field"
    DURATION = "duration"
    CO2 = "co2"
    O2 = "o2"
    HUMIDITY = "humidity"


SOURCE_ENVIRONMENT_KEYS = {
    key.value: key for key in EnvironmentKey if key is not EnvironmentKey.HUMIDITY
}
SOURCE_ENVIRONMENT_KEYS["rh"] = EnvironmentKey.HUMIDITY
ENVIRONMENT_MODIFIERS = frozenset({EnvironmentKey.CO2, EnvironmentKey.O2, EnvironmentKey.HUMIDITY})
ENVIRONMENT_DIMENSIONS = {
    EnvironmentKey.THERMAL: QuantityDimension.TEMPERATURE,
    EnvironmentKey.DURATION: QuantityDimension.TIME,
    EnvironmentKey.CO2: QuantityDimension.PERCENT,
    EnvironmentKey.O2: QuantityDimension.PERCENT,
    EnvironmentKey.HUMIDITY: QuantityDimension.PERCENT,
}


class EnvironmentValueError(ValueError):
    """An explicit scientific condition violates the environment contract."""

    def __init__(self, message, *, reason="range"):
        super().__init__(message)
        self.reason = reason


def validate_environment_quantity(key: EnvironmentKey, number, unit, *, source_name: str | None = None):
    """Validate a resolved scalar; preserve its value and declared unit."""
    name = source_name if source_name is not None else key.value
    dimension = ENVIRONMENT_DIMENSIONS[key]
    try:
        number = require_finite_number(number)
    except ValueError as error:
        raise EnvironmentValueError(f"env {name}: {error}", reason="value") from error
    if not isinstance(unit, str) or UNIT_TO_DIMENSION.get(unit) is not dimension:
        raise EnvironmentValueError(
            f"env {name} requires a {dimension} quantity", reason="dimension")
    if key is EnvironmentKey.THERMAL:
        valid = number >= (0 if unit == "K" else -273.15)
        bounds = "at or above absolute zero (-273.15C / 0K)"
    elif key is EnvironmentKey.DURATION:
        valid = number > 0
        bounds = "strictly positive"
    else:
        valid = 0 <= number <= 100
        bounds = "between 0% and 100% inclusive"
    if not valid:
        raise EnvironmentValueError(f"env {name} must be {bounds}")


def validate_environment_gas_total(percentages):
    co2 = percentages.get(EnvironmentKey.CO2)
    o2 = percentages.get(EnvironmentKey.O2)
    if co2 is not None and o2 is not None and co2 + o2 > 100:
        raise EnvironmentValueError("env co2 + o2 must not exceed 100%", reason="gas_total")
