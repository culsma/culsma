"""Runtime adapter invoked once by the shared action entry, before effects."""
from culsma.common.diagnostics import Diagnostic
from .contracts import CONSTRAINT_REQUIREMENTS
from .rules import ConstraintRules

# Control, declarations and internal bookkeeping are not physical actions.
_ACTION_FAMILIES = {name: name for name in ('agit', 'sep', 'frac', 'img', 'ecp', 'phy', 'env_hold')}
_ACTION_FAMILIES['Mutation'] = 'mutation'


class RuntimeConstraintValidator:
    """Validate active constraints at the shared runtime action boundary."""

    def validate(self, step, evaluate):
        family = _ACTION_FAMILIES.get(step.op)
        if family is None:
            return []
        gate = step.gate or {}
        constraint = gate.get('constraint', {})
        requirements = list(constraint.get('requirements', ()))
        for wire, payload in constraint.get('requirement_types', {}).items():
            member = CONSTRAINT_REQUIREMENTS.current.decode(payload)
            if member.value != wire or wire not in requirements:
                return [self._diagnostic(step, 'RT_CONSTRAINT_INVALID', 'Requirement identity does not match its gate')]
            requirements = [member if name == wire else name for name in requirements]
        violations = ConstraintRules.applicability_violations(family, requirements) + ConstraintRules.combination_violations(requirements)
        if 'cold_chain' in requirements:
            # Check each explicit scoped thermal setting, matching source validation.
            # No thermal setting means a qualitative driver requirement, not an
            # inferred temperature. Unknown explicit values must resolve before use.
            layers = gate.get('env_layers')
            environments = [layer.get('env', {}) for layer in layers] if isinstance(layers, list) else [gate.get('env', {})]
            for env in environments:
                if 'thermal' in env:
                    violation = ConstraintRules.cold_chain_violation(evaluate(env['thermal']))
                    if violation is not None:
                        violations.append(violation)
        return [self._diagnostic(step, 'RT_CONSTRAINT_ENV_CONFLICT' if v.kind == 'environment' else 'RT_CONSTRAINT_INVALID', v.message)
                for v in violations]

    @staticmethod
    def _diagnostic(step, code, message):
        return Diagnostic(code=code, message=message, span=step.span, node_id=step.step_id)
