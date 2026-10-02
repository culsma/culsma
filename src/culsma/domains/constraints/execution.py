"""Runtime adapter invoked once by the shared action entry, before effects."""
from culsma.common.diagnostics import Diagnostic
from .contracts import CONSTRAINT_REQUIREMENTS
from .rules import ConstraintRules
from .checks import ConstraintContext

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
        violations.extend(ConstraintRules.context_violations(
            requirements, self._contexts(gate, evaluate)))
        return [self._diagnostic(step, 'RT_CONSTRAINT_ENV_CONFLICT' if v.kind == 'environment' else 'RT_CONSTRAINT_INVALID', v.message)
                for v in violations]

    @staticmethod
    def _contexts(gate, evaluate):
        # Yield lazily so unconstrained actions do not resolve unrelated facts.
        # Check every explicit nested setting; absence implies no temperature.
        layers = gate.get('env_layers')
        environments = [layer.get('env', {}) for layer in layers] if isinstance(layers, list) else [gate.get('env', {})]
        for env in environments:
            if 'thermal' in env:
                yield ConstraintContext(thermal=evaluate(env['thermal']))

    @staticmethod
    def _diagnostic(step, code, message):
        return Diagnostic(code=code, message=message, span=step.span, node_id=step.step_id)
