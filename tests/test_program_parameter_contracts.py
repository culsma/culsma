"""Registered call contracts work without operation-name branches."""
from dataclasses import replace

import pytest

from culsma.common.enum_parameters import CallParameterContract
from culsma.enum_services import CALL_PARAMETER_CONTRACTS, PARAMETER_CONTRACTS
from culsma.domains.fractionation import ChromatographyAxis, ChromatographyOrder
from culsma.pipeline.external_boundary import ExternalParameterNormalizer
from culsma.pipeline.program_registry import PROGRAM_REGISTRY
from culsma.pipeline.validate.programs import ProgramContractValidator
from culsma.pipeline.ir_nodes import IRArg, IRCall, IRIdentifier, IRMember
from test_chromatography_extensions import installed_registry


def member(namespace, value):
    return IRMember(IRIdentifier(namespace), value)


def test_program_spec_and_flattened_fields_share_contract_identity():
    contract = CALL_PARAMETER_CONTRACTS['chromatography_program']
    assert PROGRAM_REGISTRY['chromatography_program'].parameter_contract is contract
    for name, field in contract.fields.items():
        assert PARAMETER_CONTRACTS[('chromatography_program', name)] is field


def test_renamed_program_runs_registered_semantic_rules(monkeypatch):
    original = PROGRAM_REGISTRY['chromatography_program']
    monkeypatch.setitem(PROGRAM_REGISTRY, 'registered_test_program',
                        replace(original, kind='registered_test_program'))
    with installed_registry().activate():
        call = IRCall('registered_test_program', [
            IRArg('axis', member('LabAxis', 'ELUTION_VOLUME')),
            IRArg('order', member('ChromatographyOrder', 'EARLY_TO_LATE')),
            IRArg('bins', IRIdentifier('n')),
        ])
        diagnostics = ProgramContractValidator.validate_program_call(
            call, literal_bindings={}, node_id='test', defined_names={'n'})
        assert [d.code for d in diagnostics] == ['SEM_INVALID_PROGRAM_ARG_VALUE']
        assert 'selected axis' in diagnostics[0].message


def test_renamed_program_runs_same_rules_at_plan_and_runtime_boundaries():
    contract = CALL_PARAMETER_CONTRACTS['chromatography_program']
    normalizer = ExternalParameterNormalizer(call_contracts={'registered_test_program': contract})
    from test_chromatography_extensions import LabAxis, LabOrder
    with installed_registry().activate():
        for method in (normalizer.normalize_plan_arguments, normalizer.normalize_runtime_arguments):
            with pytest.raises(ValueError, match='selected axis'):
                method('registered_test_program', {
                    'axis': LabAxis.ELUTION_VOLUME, 'order': ChromatographyOrder.EARLY_TO_LATE})
            assert method('registered_test_program', {
                'axis': LabAxis.ELUTION_VOLUME, 'order': LabOrder.SMALL_TO_LARGE})


def test_deferred_dependency_does_not_skip_other_known_invalid_fields():
    contract = CALL_PARAMETER_CONTRACTS['chromatography_program']
    normalizer = ExternalParameterNormalizer(call_contracts={'other': contract})
    deferred = {'kind': 'IRIdentifier', 'name': 'axis', 'bound': True}
    result = normalizer.normalize_plan_arguments('other', {
        'axis': deferred, 'order': ChromatographyOrder.EARLY_TO_LATE})
    assert result['axis'] == deferred
    with pytest.raises(TypeError):
        normalizer.normalize_plan_arguments('other', {'axis': deferred, 'order': 42})
    with pytest.raises(ValueError, match='Unresolved'):
        normalizer.normalize_runtime_arguments('other', {
            'axis': deferred, 'order': ChromatographyOrder.EARLY_TO_LATE})


def test_rule_dependencies_and_call_field_tables_cannot_diverge():
    contract = CALL_PARAMETER_CONTRACTS['chromatography_program']
    with pytest.raises(ValueError, match='dependencies'):
        CallParameterContract({'axis': contract.fields['axis']}, contract.rules)
    with pytest.raises(ValueError, match='match'):
        ExternalParameterNormalizer(contracts={}, call_contracts={'other': contract})
    with pytest.raises(TypeError):
        contract.fields['extra'] = contract.fields['axis']
