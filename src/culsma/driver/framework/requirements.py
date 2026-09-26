"""Require explicit driver support for declared requirement extensions."""
from culsma.domains.constraints import CONSTRAINT_REQUIREMENTS


class RequirementCapability:
    @staticmethod
    def require_support(gate, driver):
        constraint = (gate or {}).get('constraint', {})
        identities = constraint.get('requirement_types', {})
        for wire, payload in identities.items():
            member = CONSTRAINT_REQUIREMENTS.current.decode(payload)
            if member.value != wire or wire not in constraint.get('requirements', []):
                raise ValueError('Requirement identity does not match its gate')
            identity = (payload['id'], payload['version'])
            if identity not in getattr(driver, 'supported_requirement_types', frozenset()):
                raise ValueError(f'Driver does not support requirement type {identity}')
