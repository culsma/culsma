"""Conditional checks over domain values, independent of source and runtime."""
from dataclasses import dataclass
from culsma.common.quantity_arithmetic import require_finite_number

COLD_CHAIN_MAX_C = 8.0


@dataclass(frozen=True)
class ConstraintViolation:
    kind: str
    message: str


@dataclass(frozen=True)
class ConstraintContext:
    """One explicit thermal setting; absent settings do not create a context."""

    thermal: object


class ColdChainRule:
    """Check an explicit temperature without inferring physical conditions."""

    @staticmethod
    def validate(context: ConstraintContext) -> ConstraintViolation | None:
        """Check an explicitly resolved (value, unit); absence is handled by adapters."""
        temperature = context.thermal
        if not isinstance(temperature, tuple) or len(temperature) != 2:
            return ConstraintViolation("unresolved", "Cold-chain thermal value must resolve to a temperature quantity")
        value, unit = temperature
        try:
            number = require_finite_number(value)
        except ValueError:
            return ConstraintViolation("unresolved", "Cold-chain thermal value must be finite")
        if not isinstance(unit, str) or unit not in {'C', 'K'}:
            return ConstraintViolation("unresolved", "Cold-chain thermal value must use temperature units")
        celsius = number - 273.15 if unit == 'K' else number
        if celsius > COLD_CHAIN_MAX_C:
            return ConstraintViolation("environment", f"Requirement 'cold_chain' conflicts with env thermal {value}{unit}")
        return None
