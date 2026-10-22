"""Value extension contracts and source-to-console adapter conformance."""
from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from culsma.common.value_contracts import VALUE_CONTRACTS, ReadCallContract, UNRESOLVED_VALUE
from culsma.driver.stub import StubDriver
from culsma.pipeline.program_registry import PROGRAM_REGISTRY, register_program_value_contracts
from culsma.runtime.executor import run
from culsma.runtime.output import format_print_value
from culsma.runtime.state import RuntimeState
from culsma.runtime.value_adapters import AdaptedValue, ValueAdapterRegistry, create_value_adapter_registry
from culsma.runtime.values import RuntimeValueResolver
from test_print_statement import SAMPLE, compile_source, plan_source, RecordingDriver


def test_registry_lookup_and_extension(monkeypatch, capsys):
    calls = []

    class CustomAdapter:
        def read(self, type_id, value, state, resolver):
            calls.append('read')
            return AdaptedValue(type_id, {'answer': 42})

        def describe(self, value):
            calls.append('describe')
            return f"Custom({value['answer']})"

    registry = ValueAdapterRegistry()
    adapter = CustomAdapter()
    registry.register('custom.value', adapter)
    assert registry.resolve('custom.value') is adapter
    assert registry.resolve('not.registered') is None
    assert calls == []
    with pytest.raises(ValueError, match='duplicate'):
        registry.register('custom.value', adapter)
    monkeypatch.setattr(VALUE_CONTRACTS, 'calls', dict(VALUE_CONTRACTS.calls))
    monkeypatch.setattr(VALUE_CONTRACTS, 'types', set(VALUE_CONTRACTS.types))
    VALUE_CONTRACTS.register_call('custom_value', ReadCallContract('custom.value'))
    monkeypatch.setattr('culsma.runtime.values.create_value_adapter_registry', lambda: registry)
    result = run(plan_source('let x=custom_value();print(x);'), StubDriver())
    assert result.ok, result.diagnostics
    assert capsys.readouterr().out == 'Custom(42)\n'
    assert calls == ['read', 'describe']
    assert 'prints' not in result.state.artifacts


def test_registered_programs_need_no_print_whitelist(monkeypatch, capsys):
    monkeypatch.setitem(PROGRAM_REGISTRY, 'test_program', replace(
        PROGRAM_REGISTRY['centrifuge_program'], kind='test_program'))
    monkeypatch.setattr(VALUE_CONTRACTS, 'calls', dict(VALUE_CONTRACTS.calls))
    monkeypatch.setattr(VALUE_CONTRACTS, 'types', set(VALUE_CONTRACTS.types))
    register_program_value_contracts()
    result = run(plan_source('let p=test_program(drive=300g);print(p);print(p.drive);'), StubDriver())
    assert result.ok, result.diagnostics
    assert capsys.readouterr().out == "{'kind': 'test_program', 'drive': 300 g}\n300 g\n"


@pytest.mark.parametrize('expression,expected', [
    ('centrifuge_program(drive=300g)', "'drive': 300 g"),
    ('thermal_program(from=25C,duration=1s)', "'from': 25 C"),
    ('magnetic_program(duration=1s)', "'duration': 1 s"),
    ('filtration_program(membrane="silica",drive=pressure)', 'PRESSURE'),
    ('schedule(start=1,end=3,step=1)', "'end': 3"),
    ('schedule(at=[1s,2s])', "'at': [1 s, 2 s]"),
    ('schedule(mode=ScheduleMode.CONTINUOUS,start=0s,duration=2s)', 'CONTINUOUS'),
])
def test_configuration_and_schedule_values(expression, expected, capsys):
    driver = RecordingDriver()
    result = run(plan_source(f'let config={expression};print(config);'), driver)
    assert result.ok, result.diagnostics
    assert expected in capsys.readouterr().out
    assert driver.actions == []
    direct = run(plan_source(f'print({expression});'), driver)
    assert direct.ok, direct.diagnostics
    assert expected in capsys.readouterr().out
    assert driver.actions == []


def test_target_views_and_exact_entry_selection(capsys):
    source = SAMPLE + '''
      print(sample.contents); print(sample.structure.bottom);
      let view=sample.structure.sidewall;print(view);
      let entry=sample.materials.get("WATER");print(entry.quantity);
    '''
    driver = RecordingDriver()
    result = run(plan_source(source), driver)
    assert result.ok, result.diagnostics
    text = capsys.readouterr().out
    assert "'view': 'contents'" in text and "'facet': 'bottom'" in text
    assert "'facet': 'sidewall'" in text and "'value': 100" in text
    baseline = run(plan_source(SAMPLE), RecordingDriver())
    assert result.state.artifacts['material_state'] == baseline.state.artifacts['material_state']
    assert 'print' not in driver.actions


def test_bound_read_query_keeps_binding_time(capsys):
    source = SAMPLE + '''let target=tube();
      let original=sample.materials.get("WATER");
      let original_amount=original.amount;
      target << [sample:10uL];
      print(original_amount);print(original.amount);let current=sample.materials.get("WATER");print(current.amount);
    '''
    result = run(plan_source(source), StubDriver())
    assert result.ok, result.diagnostics
    assert capsys.readouterr().out == '100\n90\n90\n'
    result = run(plan_source('let detector=surface();let ion=data_ref(kind=ion_event);'
        'let hit=detector.detects(ion);print(hit);print(detector.detects(ion));'), StubDriver())
    assert result.ok, result.diagnostics
    assert capsys.readouterr().out == 'False\nFalse\n'


@pytest.mark.parametrize('expression', ['tube()', 'data_ref(kind=qc)', 'markers(["CD3"])',
    'img(sample=sample,quantity=fluorescence)', 'sample.materials.replace({})'])
def test_effectful_calls_stay_rejected(expression):
    _, semantic, _ = compile_source(SAMPLE+f'print({expression});')
    assert 'SEM_PRINT_EXPRESSION' in [d.code for d in semantic.diagnostics]


@pytest.mark.parametrize('kind', ['material.container', 'configuration.program', 'container_ref', 'IRCall'])
def test_user_records_do_not_dispatch_by_kind(kind, capsys):
    source = f'let d=data_ref(kind=qc); d.result.kind="{kind}";d.result.answer=17;print(d.result);'
    result = run(plan_source(source), StubDriver())
    assert result.ok, result.diagnostics
    assert capsys.readouterr().out == repr({'kind':kind, 'answer':17}) + '\n'


def test_missing_adapter_does_not_fall_back_to_record_fields():
    resolver = RuntimeValueResolver(adapters=ValueAdapterRegistry())
    assert resolver.read_adapted('material.container', {}, RuntimeState()) is UNRESOLVED_VALUE
    with pytest.raises(ValueError, match='No value adapter'):
        format_print_value(AdaptedValue('unknown.type', {'answer':42}), registry=resolver.adapters)


def test_adapter_reads_do_not_initialize_legacy_material_state():
    from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
    material={'containers':{'sample':{'volume_uL':10,'mass_mg':0,'components':{}}}}
    state=RuntimeState(artifacts={'material_state':material})
    before=copy.deepcopy(material)
    value={'kind':'IRMember','base':{'kind':'IRIdentifier','name':'sample'},'member':'contents'}
    plan=PlanProgram(plans=[ProtocolPlan('p','P',steps=[PlanStep('a','print',{'value':value},[],None)])])
    result=run(plan,StubDriver(),state=state)
    assert result.ok, result.diagnostics
    assert material==before


def test_query_values_serialize_without_adapter_objects(tmp_path, capsys):
    from culsma.cli import execute_pipeline
    path=tmp_path/'query.culs';path.write_text(SAMPLE+'let entry=sample.materials.get("WATER");print(entry);return entry;')
    bundle=execute_pipeline([path])
    assert bundle['output']['ok']
    json.dumps(bundle, default=str)
    json.dumps(bundle['run'])
    assert 'WATER' in capsys.readouterr().out
    assert 'prints' not in bundle['output']


def test_assigned_and_indexed_records_keep_user_kind(capsys):
    # Plain stored records have no semantic reference identity, even with reserved-looking keys.
    resolver = RuntimeValueResolver()
    state=RuntimeState(artifacts={'local_bindings':{'r':{'kind':'container_ref','extra':17}}})
    assert resolver.read_value({'kind':'IRIdentifier','name':'r'},state)=={'kind':'container_ref','extra':17}
    record = {'kind':'container_ref','extra':17}
    state=RuntimeState(artifacts={'local_bindings':{'items':[record]}})
    expr={'kind':'IRIndex','base':{'kind':'IRIdentifier','name':'items'},
          'index':{'kind':'IRQuantity','value':0,'unit':None}}
    assert resolver.read_value(expr,state)==record


def test_quantity_shaped_record_is_not_a_quantity(capsys):
    result=run(plan_source('print({kind:"IRQuantity",value:17,unit:"uL"});print(17uL);'),StubDriver())
    assert result.ok, result.diagnostics
    assert capsys.readouterr().out == "{'kind': 'IRQuantity', 'value': 17, 'unit': 'uL'}\n17 uL\n"


def test_detection_query_binding_is_not_recomputed(capsys):
    plan=plan_source('let detector=surface();let ion=data_ref(kind=ion_event);'
        'let hit=detector.detects(ion);print(hit);print(detector.detects(ion));')
    prefix=copy.deepcopy(plan)
    prefix.plans[0]=replace(prefix.plans[0],steps=prefix.plans[0].steps[:-2])
    checkpoint=run(prefix,StubDriver())
    checkpoint.state.artifacts['detect_hits']={'detector':['ion']}
    result=run(plan,StubDriver(),state=checkpoint.state)
    assert result.ok, result.diagnostics
    assert capsys.readouterr().out=='False\nTrue\n'


def test_external_read_query_never_executes_nested_constructor(monkeypatch):
    from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
    def forbidden(*args,**kwargs):
        raise AssertionError('Read query executed a constructor')
    monkeypatch.setattr('culsma.runtime.values._eval_runtime_call',forbidden)
    call={'kind':'IRCall','name':'detects','args':[
        {'name':'self','value':{'kind':'IRCall','name':'markers','args':[]}},
        {'name':'arg0','value':{'kind':'IRString','value':'ion'}}]}
    plan=PlanProgram(plans=[ProtocolPlan('p','P',steps=[PlanStep('a','print',{'value':call},[],None)])])
    result=run(plan,StubDriver())
    assert not result.ok and result.diagnostics[0].code=='RT_PRINT_VALUE_UNRESOLVED'


def test_record_member_names_do_not_become_target_views():
    state=RuntimeState(artifacts={'local_bindings':{
        'r':{'contents':{'volume':17},'structure':{'bottom':'label'}}}})
    resolver=RuntimeValueResolver()
    root={'kind':'IRIdentifier','name':'r'}
    contents={'kind':'IRMember','base':root,'member':'contents'}
    assert resolver.read_value(contents,state)=={'volume':17}
    assert resolver.read_value({'kind':'IRMember','base':contents,'member':'volume'},state)==17
    structure={'kind':'IRMember','base':root,'member':'structure'}
    assert resolver.read_value({'kind':'IRMember','base':structure,'member':'bottom'},state)=='label'
