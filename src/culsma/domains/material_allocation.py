"""Shared ratio contracts for authored separation and fractionation allocations."""

from math import isfinite


def allocation_ratio(value: object, unit: object = None) -> float | None:
    """Decode a finite dimensionless fraction; physical quantities are not ratios."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if unit not in (None, "%", "pct"):
        return None
    ratio = float(value) / (100.0 if unit is not None else 1.0)
    return ratio if isfinite(ratio) else None


def validate_allocation_ratios(ratios: tuple[float | None, ...], output_count: int) -> str | None:
    """Return the failed contract, or None for a complete conserved allocation."""
    if len(ratios) != output_count:
        return "SHAPE_INVALID"
    if any(value is None or isinstance(value, bool) or not isfinite(value) or not 0 <= value <= 1 for value in ratios):
        return "VALUE_INVALID"
    if abs(sum(ratios) - 1.0) > 1e-9:
        return "TOTAL_INVALID"
    return None
