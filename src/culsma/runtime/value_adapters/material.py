"""Read current material references, target views and existing sensing predicates."""
from __future__ import annotations

from copy import deepcopy
from culsma.common.value_contracts import UNRESOLVED_VALUE, VALUE_CONTRACTS
from culsma.pipeline.container_views import classify_container_target_view
from culsma.runtime.material.component_entries import normalize_component_entries, component_entry_has_quantity
from culsma.runtime.value_adapters.contracts import AdaptedValue


class MaterialValueAdapter:
    type_ids = ('material.reference', 'material.container', 'material.group', 'material.entry',
                'material.target_view', 'material.predicate')

    def read(self, type_id, value, state, resolver):
        if type_id == 'material.reference':
            material = state.artifacts.get('material_state', {})
            group = resolver.material_group_payload(material, value)
            if group is not None:
                return self.read('material.group', group, state, resolver)
            container = resolver.material_value_payload(material, value)
            return self.read_container(container, state, resolver) if container is not None else UNRESOLVED_VALUE
        if type_id == 'material.container':
            return self.read_container(value, state, resolver)
        if type_id == 'material.group':
            members = [self.read_container(item, state, resolver) for item in value.get('members', [])]
            if any(item is UNRESOLVED_VALUE for item in members):
                return UNRESOLVED_VALUE
            return AdaptedValue(type_id, {**value, 'members': members})
        if type_id == 'material.target_view':
            view = classify_container_target_view(value)
            if view is None:
                return UNRESOLVED_VALUE
            container = resolver.read_value(view.root, state)
            if not isinstance(container, AdaptedValue) or container.type_id != 'material.container':
                return UNRESOLVED_VALUE
            result = {'kind': 'container_target_view', 'container_id': container['id'], 'view': view.kind}
            if view.facet is not None:
                result['facet'] = view.facet
            return AdaptedValue(type_id, result)
        contract = VALUE_CONTRACTS.resolve_call(value.get('name'))
        args = value.get('args', [])
        if contract is None or contract.type_id != type_id or not contract.accepts(args):
            return UNRESOLVED_VALUE
        if type_id == 'material.predicate':
            return resolver.read_detection(value, state)
        args = {arg['name']: arg['value'] for arg in args}
        receiver = args['self']
        if (not isinstance(receiver, dict) or receiver.get('kind') != 'IRMember'
                or receiver.get('member') != contract.receiver_member):
            return UNRESOLVED_VALUE
        container = resolver.read_value(receiver['base'], state)
        key = resolver.read_value(args['arg0'], state)
        if not isinstance(container, AdaptedValue) or container.type_id != 'material.container' or not isinstance(key, str):
            return UNRESOLVED_VALUE
        entries = [entry for entry in container['component_entries'] if entry.get('entry_id') == key]
        return AdaptedValue(type_id, entries[0]) if len(entries) == 1 else UNRESOLVED_VALUE

    def read_container(self, value, state, resolver):
        container_id = value.get('id')
        material = state.artifacts.get('material_state', {})
        raw = material.get('containers', {}).get(container_id) if isinstance(container_id, str) else None
        if not isinstance(raw, dict):
            return UNRESOLVED_VALUE
        payload = resolver.container_ref_payload(material, container_id)
        payload['component_entries'] = [entry for entry in normalize_component_entries(
            deepcopy(raw), state=material, container_id=container_id) if component_entry_has_quantity(entry)]
        return AdaptedValue('material.container', resolver.protocol_output_serialize(payload))

    def describe(self, value):
        return dict(value)
