"""Public boundary services preserve identity, deferred values and dependency ownership."""
from dataclasses import FrozenInstanceError
from enum import StrEnum

import pytest

from culsma.domains.contracts import EnumParameter
from culsma.domains.labware import PlateGeometry
from culsma.domains.agitation import AgitationMode, AGITATION_MODE
from culsma.domains.readout import ReadoutQuantity
from culsma.pipeline.external_boundary import ExternalEnumCodec, ExternalParameterNormalizer
from culsma.pipeline.external_inputs import ExternalInputStatus
from culsma.pipeline.ir_nodes import IRIdentifier, IRQuantity
from culsma.pipeline.plan.plates import PlateDescriptorResolver, ResolvedPlateDescriptor


def test_codec_registry_is_a_readonly_snapshot_and_restores_exact_identity():
    registry = {'AgitationMode': AgitationMode}
    codec = ExternalEnumCodec(registry)
    registry.clear()
    assert codec.decode(codec.encode(AgitationMode.VORTEX)) is AgitationMode.VORTEX
    with pytest.raises(TypeError):
        codec.enum_types['ReadoutQuantity'] = ReadoutQuantity
    with pytest.raises(TypeError):
        codec.encode(ReadoutQuantity.PH)


@pytest.mark.parametrize('payload', [
    {'kind': 'ExternalEnum', 'enum': 'AgitationMode', 'member': 'TYPO'},
    {'kind': 'IRString', 'enum': 'AgitationMode', 'member': 'VORTEX'},
    {'kind': 'ExternalEnum', 'enum': 'Unknown', 'member': 'VORTEX'},
    {'kind': 'ExternalEnum', 'enum': [], 'member': 1},
])
def test_codec_rejects_invalid_wire_identity(payload):
    with pytest.raises(ValueError):
        ExternalEnumCodec().decode(payload)


def test_normalizer_distinguishes_deferred_from_invalid_and_runtime_requires_final_value():
    normalizer = ExternalParameterNormalizer()
    shadowed = {'kind': 'IRIdentifier', 'name': 'vortex', 'bound': True}
    assert normalizer.resolve_member(shadowed, AGITATION_MODE).status == ExternalInputStatus.DEFERRED
    assert normalizer.normalize_plan_arguments('agit', {'mode': shadowed})['mode'] == shadowed
    with pytest.raises(ValueError):
        normalizer.normalize_runtime_arguments('agit', {'mode': shadowed})
    assert normalizer.resolve_member(ReadoutQuantity.PH, AGITATION_MODE).status == ExternalInputStatus.INVALID
    with pytest.raises(TypeError):
        normalizer.require_member(ReadoutQuantity.PH, AGITATION_MODE)


def test_normalizer_uses_injected_contracts_and_codec_for_nested_calls():
    class Choice(StrEnum):
        ONE = 'one'
    contracts = {('custom', 'choice'): EnumParameter(Choice)}
    normalizer = ExternalParameterNormalizer(contracts, ExternalEnumCodec({'Choice': Choice}))
    contracts.clear()
    payload = {'kind': 'IRCall', 'name': 'custom',
               'args': [{'name': 'choice', 'value': 'one'}]}
    planned = normalizer.normalize_plan_arguments('outer', {'program': payload})
    encoded = planned['program']['args'][0]['value']
    assert encoded == {'kind': 'ExternalEnum', 'enum': 'Choice', 'member': 'ONE'}
    runtime = normalizer.normalize_runtime_arguments('outer', planned)
    assert runtime['program']['args'][0]['value'] is Choice.ONE


@pytest.mark.parametrize('rows,cols', [(0, 1), (1, -1), (True, 2), (2.5, 2)])
def test_geometry_cannot_be_constructed_with_invalid_dimensions(rows, cols):
    with pytest.raises(ValueError):
        PlateGeometry(rows, cols)


def test_resolved_descriptor_is_immutable_and_owns_allocation_bounds():
    descriptor = ResolvedPlateDescriptor(PlateGeometry(4, 6), 'P', IRQuantity(2, 'mL'), 'Plate')
    with pytest.raises(FrozenInstanceError):
        descriptor.carrier_id = 'Other'
    with pytest.raises(ValueError, match='bounds'):
        descriptor.allocation('H12')
    fields = {arg.name: arg.value for arg in descriptor.allocation('D6').args}
    assert fields['label'].value == 'Plate_D6'
    assert fields['capacity'].value == 2
    assert fields['carrier_id'].value == 'P'


@pytest.mark.parametrize('capacity', [IRQuantity(-1, 'mL'), IRQuantity(1, 's'), IRQuantity(float('nan'), 'mL')])
def test_descriptor_constructor_enforces_capacity_invariant(capacity):
    with pytest.raises(ValueError):
        ResolvedPlateDescriptor(PlateGeometry(1, 1), 'P', capacity)


def test_resolver_does_not_retain_environment_and_snapshots_are_independent():
    resolver = PlateDescriptorResolver()
    env = {'p': {'kind': 'IRCall', 'name': 'plate',
                 'args': [{'name': 'format', 'value': '24well'}]}}
    first = resolver.resolve(IRIdentifier('p'), env)
    env['p']['args'][0]['value'] = '96well'
    second = resolver.resolve(IRIdentifier('p'), env)
    assert first.geometry == PlateGeometry(4, 6)
    assert first.capacity.value == 3.4
    assert second.geometry == PlateGeometry(8, 12)
    assert second.capacity is None
    assert not hasattr(resolver, 'env')
