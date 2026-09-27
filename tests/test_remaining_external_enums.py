"""User-facing filtration drives and data kinds, from source through replay."""
import json
import pytest

from culsma.domains.data import DataKindBase, DataKind, DATA_KINDS, STANDARD_DATA_KINDS
from culsma.domains.separation import FiltrationDriveBase, FiltrationDrive, FILTRATION_DRIVES, STANDARD_FILTRATION_DRIVES
from culsma.enum_services import SOURCE_TYPE_NAMES
from culsma.parser import parse
from culsma.frontend.resolver import resolve_program
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.validate import validate
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan_nodes import PlanProgram, ProtocolPlan, PlanStep
from culsma.pipeline.external_boundary import ExternalEnumCodec
from culsma.runtime.executor import run
from culsma.driver.stub import StubDriver


class LabDrive(FiltrationDriveBase):
    PULSE = 'lab_pulse'


class LabDataKind(DataKindBase):
    QC = 'lab_qc'


def source_for(operation, value, *, params='', prefix=''):
    call = f'filtration_program(membrane="silica", drive={value})' if operation == 'filtration_program' else f'{operation}(kind={value})'
    tail = 'let sample=tube(); let split=sep(sample=sample,program=value);' if operation == 'filtration_program' else ''
    return f'protocol T{params} {{ {prefix} let value={call}; {tail} }}'


def compile_source(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    typed = typecheck(compiled.ir, analysis=compiled.analysis)
    return compiled, semantic, typed


def checked_plan(source, **kwargs):
    compiled, semantic, typed = compile_source(source)
    assert semantic.ok, semantic.diagnostics
    assert typed.ok, typed.diagnostics
    plan = lower_ir_to_plan(compiled.ir, **kwargs)
    assert not plan.diagnostics, plan.diagnostics
    return plan


def replay(plan):
    payload = json.loads(json.dumps(plan.to_dict()))['plans'][0]
    return PlanProgram(plans=[ProtocolPlan(payload['protocol_id'], payload['protocol_name'], steps=[
        PlanStep(s['step_id'], s['op'], s['args'], s['deps'], s['gate']) for s in payload['steps']])])


@pytest.mark.parametrize('operation,value,wire', [
    ('filtration_program', 'FiltrationDrive.PRESSURE', 'pressure'),
    ('filtration_program', 'pressure', 'pressure'),
    ('filtration_program', '"aspiration"', 'aspiration'),
    ('filtration_program', 'FiltrationDrive.CELL_LIFTER', 'cell_lifter'),
    ('data_ref', 'DataKind.SEQUENCE_READ', 'sequence_read'),
    ('data_ref', 'sequence_read', 'sequence_read'),
    ('data_ref', '"observation"', 'observation'),
    ('data_group_ref', 'DataKind.SORT_RECORD', 'sort_record'),
])
def test_standard_and_compatible_source(operation, value, wire):
    plan = checked_plan(source_for(operation, value))
    assert 'DomainEnum' in json.dumps(plan.to_dict())
    result = run(plan=replay(plan), driver=StubDriver())
    assert result.ok, result.diagnostics
    if operation != 'filtration_program':
        reference = result.state.artifacts['local_bindings']['value']
        assert reference['data_kind'] == wire
        assert 'data_kind_type' not in reference
        assert reference['result'] == {}
    json.dumps(result.user_result)


@pytest.mark.parametrize('operation', ['filtration_program', 'data_ref', 'data_group_ref'])
@pytest.mark.parametrize('value', ['historical_label', '"historical_label"'])
def test_unknown_old_text_remains_compatible(operation, value):
    result = run(plan=checked_plan(source_for(operation, value)), driver=StubDriver())
    assert result.ok, result.diagnostics
    if operation != 'filtration_program':
        reference = result.state.artifacts['local_bindings']['value']
        assert reference['data_kind'] == 'historical_label'
        assert 'data_kind_type' not in reference


@pytest.mark.parametrize('operation,value,code', [
    ('filtration_program', 'DataKind.OBSERVATION', 'TYPE_EXTERNAL_ENUM_MISMATCH'),
    ('filtration_program', 'FiltrationDrive.TYPO', 'SEM_INVALID_PROGRAM_ARG_VALUE'),
    ('data_ref', 'FiltrationDrive.PRESSURE', 'TYPE_EXTERNAL_ENUM_MISMATCH'),
    ('data_group_ref', 'DataKind.TYPO', 'SEM_INVALID_EXTERNAL_PARAMETER'),
    ('data_ref', '42', 'TYPE_EXTERNAL_ENUM_MISMATCH'),
    ('data_ref', 'NotInstalled.QC', 'SEM_INVALID_EXTERNAL_PARAMETER'),
])
def test_source_rejects_wrong_types_and_unknown_members(operation, value, code):
    _, semantic, typed = compile_source(source_for(operation, value))
    assert code in [d.code for d in semantic.diagnostics + typed.diagnostics]


@pytest.mark.parametrize('operation,standard,extension,base_registry', [
    ('filtration_program', 'FiltrationDrive.PRESSURE', LabDrive.PULSE, STANDARD_FILTRATION_DRIVES),
    ('data_ref', 'DataKind.OBSERVATION', LabDataKind.QC, STANDARD_DATA_KINDS),
    ('data_group_ref', 'DataKind.OBSERVATION', LabDataKind.QC, STANDARD_DATA_KINDS),
])
@pytest.mark.parametrize('form', ['direct', 'alias', 'default', 'branch', 'override'])
def test_extension_source_binding_and_serialized_replay(operation, standard, extension, base_registry, form):
    registry = base_registry.with_type(type(extension), f'example.{base_registry.wire_domain}')
    with registry.activate():
        member = f'{type(extension).__name__}.{extension.name}'
        value, params, prefix, entry = member, '', '', {}
        if form == 'alias':
            value, prefix = 'chosen', f'let chosen={member};'
        elif form == 'default':
            value, params = 'chosen', f'(chosen={member})'
        elif form == 'branch':
            value, params, prefix = 'chosen', '(flag=true)', f'let chosen={standard}; if flag {{ chosen={member}; }}'
        elif form == 'override':
            value, params = 'chosen', f'(chosen={standard})'
            entry = {'entry_args_by_protocol': {'T': {'chosen': extension}}}
        plan = checked_plan(source_for(operation, value, params=params, prefix=prefix), **entry)
        loaded = replay(plan)
        result = run(plan=loaded, driver=StubDriver())
        assert result.ok, result.diagnostics
        if operation != 'filtration_program':
            reference = result.state.artifacts['local_bindings']['value']
            assert reference['data_kind'] == extension.value
            assert reference['data_kind_type'] == registry.encode(extension)
        json.dumps(result.user_result)
    assert type(extension).__name__ not in SOURCE_TYPE_NAMES
    result = run(plan=loaded, driver=StubDriver())
    assert not result.ok
    expected_code = 'RT_LOCAL_ASSIGN_UNRESOLVED' if form == 'branch' else 'RT_EXTERNAL_ENUM_INVALID'
    assert expected_code in [d.code for d in result.diagnostics]


@pytest.mark.parametrize('operation,standard,wrong', [
    ('filtration_program', 'FiltrationDrive.PRESSURE', DataKind.OBSERVATION),
    ('data_ref', 'DataKind.OBSERVATION', FiltrationDrive.PRESSURE),
    ('data_group_ref', 'DataKind.OBSERVATION', FiltrationDrive.PRESSURE),
])
def test_wrong_entry_values_rejected_after_binding(operation, standard, wrong):
    compiled, _, _ = compile_source(source_for(operation, 'chosen', params=f'(chosen={standard})'))
    plan = lower_ir_to_plan(compiled.ir, entry_args_by_protocol={'T': {'chosen': wrong}})
    assert not plan.plans
    assert 'PLAN_EXTERNAL_ENUM_INVALID' in [d.code for d in plan.diagnostics]


@pytest.mark.parametrize('contract,standard,extension', [
    (FILTRATION_DRIVES, FiltrationDrive.PRESSURE, LabDrive),
    (DATA_KINDS, DataKind.OBSERVATION, LabDataKind),
])
def test_extension_registry_rejects_collisions_and_codec_requires_installed_identity(contract, standard, extension):
    collision = contract.enum_type('Collision', {'SAME': standard.value})
    with pytest.raises(ValueError):
        contract.registry.with_type(collision, 'example.collision')
    foreign = DataKind if contract is FILTRATION_DRIVES else FiltrationDrive
    with pytest.raises(TypeError):
        contract.registry.with_type(foreign, 'example.foreign')
    registry = contract.registry.with_type(extension, 'example.extension')
    with registry.activate():
        codec = ExternalEnumCodec()
        member = next(iter(extension))
        payload = json.loads(json.dumps(codec.encode(member)))
        assert codec.decode(payload) is member
        payload['version'] = 2
        with pytest.raises(ValueError):
            codec.decode(payload)
    assert contract.current is contract.registry


@pytest.mark.parametrize('drive,expected', [
    (FiltrationDrive.ASPIRATION, True), (' ASPIRATION ', True),
    (FiltrationDrive.PRESSURE, False), (LabDrive.PULSE, False),
    (FiltrationDriveBase('Lookalike', {'VALUE': ' ASPIRATION '}).VALUE, False),
])
def test_filtration_extensions_do_not_inherit_standard_material_handling(drive, expected):
    from culsma.runtime.material.separation_fate import SeparationOperationContract
    program = {'kind': 'IRCall', 'name': 'filtration_program', 'args': [
        {'kind': 'IRArg', 'name': 'membrane', 'value': 'adherent_cell_surface'},
        {'kind': 'IRArg', 'name': 'drive', 'value': drive},
    ]}
    assert SeparationOperationContract.is_surface_aspiration(program) is expected
