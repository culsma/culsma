"""Deterministic arithmetic for scalar quantities, shared by checking and execution."""

from __future__ import annotations

from math import isfinite
from typing import Any

Scalar = int | float
QuantityValue = Scalar | tuple[Scalar, str]


# Multipliers within each dimension. Temperature conversion is affine and is
# deliberately excluded from implicit mixed-unit arithmetic.
UNIT_SCALES = {
    "volume": {"uL": 1, "ul": 1, "mL": 1000, "ml": 1000, "L": 1000000},
    "mass": {"ug": .001, "mg": 1, "g": 1000, "kg": 1000000},
    "time": {"ms": .001, "s": 1, "sec": 1, "min": 60, "h": 3600, "hr": 3600, "day": 86400},
    "temperature": {"C": 1, "K": 1},
    "percent": {"%": 1, "pct": 1},
    "count": {"cells": 1},
    "electric_potential": {"V": 1, "mV": .001},
    "electric_current": {"A": 1, "mA": .001, "uA": .000001},
    "rotation_rate": {"rpm": 1},
}
UNIT_TO_DIMENSION = {unit: dim for dim, units in UNIT_SCALES.items() for unit in units}


class QuantityArithmeticError(ValueError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def require_finite_number(value: Any) -> Scalar:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QuantityArithmeticError("operand", "Quantity arithmetic requires numeric operands")
    try:
        finite = isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise QuantityArithmeticError("nonfinite", "Quantity arithmetic requires finite representable values")
    return value


def quantity_parts(value: Any) -> tuple[Scalar, str | None]:
    if isinstance(value, tuple) and len(value) == 2:
        number, unit = value
        if not isinstance(unit, str) or unit not in UNIT_TO_DIMENSION:
            raise QuantityArithmeticError("unit", f"Unknown quantity unit '{unit}'")
        return require_finite_number(number), unit
    return require_finite_number(value), None


def convert_value(value: Scalar, source_unit: str, target_unit: str) -> Scalar:
    if source_unit not in UNIT_TO_DIMENSION or target_unit not in UNIT_TO_DIMENSION:
        raise QuantityArithmeticError("unit", "Unknown quantity unit")
    dimension = UNIT_TO_DIMENSION[source_unit]
    if dimension != UNIT_TO_DIMENSION[target_unit]:
        raise QuantityArithmeticError("dimension", f"Incompatible units '{source_unit}' and '{target_unit}'")
    if source_unit == target_unit:
        return require_finite_number(value)
    if dimension == "temperature":
        raise QuantityArithmeticError("dimension", "Mixed C/K arithmetic requires an explicit temperature conversion")
    scales = UNIT_SCALES[dimension]
    return require_finite_number(require_finite_number(value) * (scales[source_unit] / scales[target_unit]))


def quantity_result_unit(op: str, left_unit: str | None, right_unit: str | None) -> str | None:
    """Infer arithmetic dimensions without assuming any numeric operand value."""
    for unit in (left_unit, right_unit):
        if unit is not None and unit not in UNIT_TO_DIMENSION:
            raise QuantityArithmeticError("unit", f"Unknown quantity unit '{unit}'")
    if op in {"+", "-"}:
        if (left_unit is None) != (right_unit is None):
            raise QuantityArithmeticError("dimension", "Cannot add or subtract a scalar and a unit-bearing quantity")
    elif op == "*":
        if left_unit is not None and right_unit is not None:
            raise QuantityArithmeticError("dimension", "Multiplication producing compound units is unsupported")
        return left_unit or right_unit
    elif op == "/":
        if left_unit is None and right_unit is not None:
            raise QuantityArithmeticError("dimension", "Division producing inverse units is unsupported")
    else:
        raise QuantityArithmeticError("operand", f"Unsupported quantity operator '{op}'")
    if left_unit is not None and right_unit is not None:
        if UNIT_TO_DIMENSION[left_unit] != UNIT_TO_DIMENSION[right_unit]:
            raise QuantityArithmeticError("dimension", f"Incompatible units '{left_unit}' and '{right_unit}'")
        if UNIT_TO_DIMENSION[left_unit] == "temperature" and left_unit != right_unit:
            raise QuantityArithmeticError("dimension", "Mixed C/K arithmetic requires an explicit temperature conversion")
    return None if op == "/" and right_unit is not None else left_unit


def quantity_binary(op: str, left: Any, right: Any) -> QuantityValue:
    """Keep the quantity operand's unit; additive operations use the left unit.

    Compatible quantity ratios are scalar. Compound/inverse units are outside
    the current language quantity model. No display rounding occurs here.
    """
    lv, lu = quantity_parts(left)
    rv, ru = quantity_parts(right)
    unit = quantity_result_unit(op, lu, ru)
    if op == "/" and rv == 0:
        raise QuantityArithmeticError("zero", "Division by zero in quantity expression")
    if lu is not None and ru is not None:
        rv = convert_value(rv, ru, lu)
        if op == "/" and rv == 0:
            raise QuantityArithmeticError("nonfinite", "Quantity denominator underflowed during unit conversion")
    if op == "+":
        value = lv + rv
    elif op == "-":
        value = lv - rv
    elif op == "*":
        value = lv * rv
    else:
        value = lv / rv
    require_finite_number(value)
    return (value, unit) if unit is not None else value
