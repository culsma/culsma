"""Read configuration descriptors without executing their owning operations."""
from __future__ import annotations

from culsma.common.value_contracts import UNRESOLVED_VALUE, VALUE_CONTRACTS
from culsma.pipeline.program_registry import get_program_spec
from culsma.pipeline.plan.static_eval import PlanStaticEvaluator
from culsma.pipeline.external_boundary import DEFAULT_EXTERNAL_PARAMETER_NORMALIZER
from culsma.runtime.value_adapters.contracts import AdaptedValue


class ConfigurationValueAdapter:
    type_ids = ('configuration.program', 'configuration.schedule')

    def read(self, type_id, value, state, resolver):
        if not isinstance(value, dict) or value.get('kind') != 'IRCall':
            return UNRESOLVED_VALUE
        name = value.get('name')
        contract = VALUE_CONTRACTS.resolve_call(name)
        args = value.get('args', [])
        if contract is None or contract.type_id != type_id or not contract.accepts(args):
            return UNRESOLVED_VALUE
        spec = get_program_spec(name) if type_id == 'configuration.program' else None
        if type_id == 'configuration.program' and spec is None:
            return UNRESOLVED_VALUE
        normalized = DEFAULT_EXTERNAL_PARAMETER_NORMALIZER.normalize_plan_arguments(
            name, {arg['name']: arg['value'] for arg in args})
        result = {'kind': name}
        for key, argument in normalized.items():
            item = resolver.read_value(argument, state)
            if item is UNRESOLVED_VALUE:
                return item
            result[key] = item
        if spec is not None and (any(key not in {f.name for f in spec.fields} for key in result if key != 'kind')
                or any(key not in result for key in spec.required_fields)
                or any(sum(key in result for key in group) != 1 for group in spec.required_one_of)):
            return UNRESOLVED_VALUE
        if type_id == 'configuration.schedule':
            # Validate mode through the existing owner without expanding the schedule.
            mode = PlanStaticEvaluator().schedule_mode(value)
            if mode not in {'discrete', 'continuous'}:
                return UNRESOLVED_VALUE
        return AdaptedValue(type_id, result)

    def describe(self, value):
        return dict(value)
