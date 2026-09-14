"""Floating-point boundary comparisons for continuous material quantities."""

from math import isfinite, ulp


# Allow a few representable steps for conversion, subtraction and summation.
# This is a floating-point error budget, not an experimental/pipetting tolerance.
MATERIAL_BOUNDARY_ULPS = 8


def material_amounts_close(left: float, right: float) -> bool:
    """Compare positive finite amounts at their current binary floating precision.

    No absolute floor: an empty source must never supply a positive request.
    Callers compare quantities already converted to the same canonical unit.
    """
    if not isfinite(left) or not isfinite(right) or left < 0 or right < 0:
        return False
    if left == right:
        return True
    if left == 0 or right == 0:
        return False
    return abs(left - right) <= MATERIAL_BOUNDARY_ULPS * max(ulp(left), ulp(right))


def resolve_available_amount(requested: float, available: float) -> float | None:
    """Resolve a request to actual stock; return None for a real shortage.

    A near-total request on either side of the boundary consumes all stock.
    The returned amount must drive both the movement ratio and its recorded delta.
    """
    if not isfinite(requested) or not isfinite(available) or requested < 0 or available < 0:
        return None
    if material_amounts_close(requested, available):
        return available
    return requested if requested <= available else None


def material_limit_exceeded(amount: float, limit: float) -> bool:
    """Check a physical bound without rejecting representational roundoff."""
    return amount > limit and not material_amounts_close(amount, limit)
