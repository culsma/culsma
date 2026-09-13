"""Unknown mass with conserved symbolic shares, never a numeric zero surrogate."""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Any


def is_unknown(quantity: Any) -> bool:
    return isinstance(quantity, dict) and quantity.get("status") == "unknown"


def unknown_mass(origin: str) -> dict[str, Any]:
    return {"status": "unknown", "dimension": "mass", "unit": "mg", "value": None,
            "cross_axis_projection": False, "shares": {origin: 1.0}}


def validate_unknown(quantity: dict[str, Any]) -> None:
    shares = quantity.get("shares")
    if (quantity.get("dimension") != "mass" or quantity.get("unit") != "mg"
        or quantity.get("value") is not None or quantity.get("cross_axis_projection") is not False
        or not isinstance(shares, dict) or not shares):
        raise ValueError("Unknown mass requires a null value and nonempty symbolic shares")
    for origin, fraction in shares.items():
        if (not isinstance(origin, str) or not origin or isinstance(fraction, bool)
            or not isinstance(fraction, (int, float)) or not isfinite(fraction) or fraction <= 0):
            raise ValueError("Unknown mass shares must be positive finite fractions")


def scale_unknown(quantity: dict[str, Any], ratio: float) -> dict[str, Any]:
    result = deepcopy(quantity)
    if ratio == 0:
        result.pop("status", None)
        result.pop("shares", None)
        result["value"] = 0.0
    else:
        result["shares"] = {key: value * ratio for key, value in quantity["shares"].items()}
    return result


def merge_unknown(left: dict[str, Any], right: dict[str, Any]) -> None:
    if is_unknown(left) and not is_unknown(right) and right.get("value") == 0:
        return
    if is_unknown(right) and not is_unknown(left) and left.get("value") == 0:
        left.clear()
        left.update(deepcopy(right))
        return
    if not is_unknown(left) or not is_unknown(right):
        raise ValueError("Cannot combine known and unknown quantities in this prototype")
    for key, fraction in right["shares"].items():
        left["shares"][key] = left["shares"].get(key, 0.0) + fraction


def container_has_unknown(container: dict[str, Any], dimension: str = "mass") -> bool:
    return any(is_unknown(q) and q.get("dimension") == dimension
               for q in container.get("component_quantities", {}).values())
