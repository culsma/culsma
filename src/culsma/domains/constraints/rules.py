"""Pure constraint rules shared by source and execution adapters."""
from collections.abc import Iterable

from .checks import COLD_CHAIN_MAX_C, ColdChainRule, ConstraintContext, ConstraintViolation
from .contracts import ConstraintRequirementBase, REQUIREMENT_REGISTRY


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
    def context_violations(
        requirements: Iterable[ConstraintRequirementBase | str],
        contexts: Iterable[ConstraintContext],
    ) -> list[ConstraintViolation]:
        """Select checks from each rule object, then validate supplied facts.

        Contexts may be lazy: do not resolve facts when no selected rule needs them.
        Unknown requirements are diagnosed by applicability_violations.
        """
        checks = []
        for requirement in dict.fromkeys(requirements):
            spec = REQUIREMENT_REGISTRY.get(requirement)
            if spec is not None:
                checks.extend(spec.context_checks)
        if not checks:
            return []
        violations = []
        for context in contexts:
            for check in checks:
                violation = check(context)
                if violation is not None:
                    violations.append(violation)
        return violations

    @staticmethod
    def cold_chain_violation(temperature):
        """Compatibility entry for callers checking a single temperature."""
        return ColdChainRule.validate(ConstraintContext(thermal=temperature))
