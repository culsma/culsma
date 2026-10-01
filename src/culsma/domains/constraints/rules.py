"""Pure constraint rules shared by source and execution adapters."""
from dataclasses import dataclass
from culsma.common.quantity_arithmetic import require_finite_number
from .contracts import REQUIREMENT_REGISTRY

COLD_CHAIN_MAX_C = 8.0


@dataclass(frozen=True)
class ConstraintViolation:
    kind: str
    message: str


class ConstraintRules:
    """Pure semantic checks with no stage or execution dependencies."""

    @staticmethod
    def applicability_violations(family, requirements):
        if family is None:
            return []
        violations = []
        for name in dict.fromkeys(requirements):
            spec = REQUIREMENT_REGISTRY.get(name)
            if spec is None:
                violations.append(ConstraintViolation("unknown", f"Unknown requirement '{name}' in constraint(...)"))
            elif family not in spec.allowed_on:
                violations.append(ConstraintViolation("family", f"Requirement '{name}' is not allowed on action family '{family}'"))
        return violations

    @staticmethod
    def combination_violations(requirements):
        names = tuple(dict.fromkeys(requirements))
        violations = []
        for name in names:
            spec = REQUIREMENT_REGISTRY.get(name)
            if spec is not None:
                for conflict in sorted(spec.conflicts):
                    if conflict in names:
                        violations.append(ConstraintViolation("conflict", f"Requirement '{name}' conflicts with '{conflict}'"))
        if 'customized' in names and len(names) > 1:
            violations.append(ConstraintViolation("customized", "constraint(customized, ...): customized must not be mixed with standard requirements"))
        return violations

    @staticmethod
    def cold_chain_violation(temperature):
        """Check an explicitly resolved (value, unit); absence is handled by adapters."""
        if not isinstance(temperature, tuple) or len(temperature) != 2:
            return ConstraintViolation("unresolved", "Cold-chain thermal value must resolve to a temperature quantity")
        value, unit = temperature
        try:
            number = require_finite_number(value)
        except ValueError:
            return ConstraintViolation("unresolved", "Cold-chain thermal value must be finite")
        if unit not in {'C', 'K'}:
            return ConstraintViolation("unresolved", "Cold-chain thermal value must use temperature units")
        celsius = number - 273.15 if unit == 'K' else number
        if celsius > COLD_CHAIN_MAX_C:
            return ConstraintViolation("environment", f"Requirement 'cold_chain' conflicts with env thermal {value}{unit}")
        return None
