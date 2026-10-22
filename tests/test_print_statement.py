"""Source-to-runtime conformance for read-only program output."""

import copy
import json
import sys
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from culsma.cli import execute_pipeline, main
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run as execute_runtime
from culsma.runtime.output import format_print_value
from culsma.runtime.replay import replay_events
from culsma.runtime.state import RuntimeState


SAMPLE = '''let sample=tube(label="Sample",capacity=200uL,load=[
  content(kind=chemical,type=solvent,code="WATER"):100uL]);'''


class RecordingDriver(StubDriver):
    def __init__(self):
        super().__init__()
        self.actions = []

    def execute(self, step):
        self.actions.append(step.op)
        return super().execute(step)


def compile_source(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    typed = typecheck(compiled.ir, analysis=compiled.analysis)
    return compiled, semantic, typed


def plan_source(source):
    compiled, semantic, typed = compile_source(source)
    assert semantic.ok and typed.ok, (semantic.diagnostics, typed.diagnostics)
    plan = lower_ir_to_plan(compiled.ir, analysis=compiled.analysis)
    assert not plan.diagnostics, plan.diagnostics
    return plan


def run(*args, **kwargs):
    """Observe formatter inputs in tests while retaining real console writes."""
    printed = []

    def render(value, **kwargs):
        text = format_print_value(value, **kwargs)
        printed.append(copy.deepcopy(value))
        return text

    with patch('culsma.runtime.steps.format_print_value', side_effect=render):
        result = execute_runtime(*args, **kwargs)
    return SimpleNamespace(state=result.state, events=result.events,
        diagnostics=result.diagnostics, ok=result.ok, printed=printed)


def values(result):
    return result.printed


def test_print_order_and_driver_isolation():
    source = SAMPLE + '''
      let target=tube(capacity=200uL);
      print(sample.contents.volume);
      print(sample);
      target << [sample:10uL];
      print(sample.contents.volume);
      print(sample);
      return sample;
    '''
    driver = RecordingDriver()
    result = run(plan_source(source), driver)
    assert result.ok, result.diagnostics
    before, first, after, second = values(result)
    assert (before['value'], after['value']) == (100, 90)
    assert (first['volume_uL'], second['volume_uL']) == (100, 90)
    assert first['component_entries'][0]['quantity']['value'] == 100
    assert second['component_entries'][0]['quantity']['value'] == 90
    assert 'print' not in driver.actions
    plain_driver = RecordingDriver()
    plain = run(plan_source(SAMPLE + '''let target=tube(capacity=200uL);
      target << [sample:10uL]; return sample;'''), plain_driver)
    assert plain.ok and plain_driver.actions == driver.actions
    print_ids = {step.step_id for protocol in plan_source(source).plans
                 for step in protocol.steps if step.op == 'print'}
    events = [e for e in result.events if e.step_id in print_ids and e.kind == 'STEP_COMPLETED']
    assert len(events) == 4
    assert all('driver_code' not in e.payload and 'print_output' not in e.payload for e in events)
    assert 'print_outputs' not in result.state.artifacts


def test_values_and_current_local_bindings():
    result = run(plan_source('''
      let n=2; print(n); n=3; print(n);
      print(["hello", true, n*2, 10uL*0.6]);
      print({name:"run", reading:n});
      print({kind:"label", value:n});
      print(ContentKind.CHEMICAL);
    '''), RecordingDriver())
    assert result.ok, result.diagnostics
    assert values(result)[:2] == [2, 3]
    assert values(result)[2] == ['hello', True, 6, {'kind':'IRQuantity','value':6,'unit':'uL'}]
    assert values(result)[3] == {'name':'run','reading':3}
    assert values(result)[4] == {'kind':'label','value':3}
    assert values(result)[5]['kind'] == 'ContentEnum'


@pytest.mark.parametrize('source,code', [
    ('print();', 'SEM_PRINT_ARGUMENTS'),
    ('print(1,2);', 'SEM_PRINT_ARGUMENTS'),
    ('print(value=1);', 'SEM_PRINT_ARGUMENTS'),
    ('print(arg0=1);', 'SEM_PRINT_ARGUMENTS'),
    ('print(tube());', 'SEM_PRINT_EXPRESSION'),
    ('print([1,tube()]);', 'SEM_PRINT_EXPRESSION'),
    ('print(missing);', 'SEM_UNBOUND_NAME_REFERENCE'),
    ('print(1+missing);', 'SEM_UNBOUND_NAME_REFERENCE'),
])
def test_invalid_print_contracts(source, code):
    _, semantic, _ = compile_source(source)
    assert code in [d.code for d in semantic.diagnostics]


def test_protocol_named_print_keeps_precedence():
    source = '''protocol print(value=1) { let n=value+1; return n; }
      protocol Main { print(4); } Main();'''
    plan = plan_source(source)
    assert all(s.op != 'print' for p in plan.plans for s in p.steps)
    result = run(plan, StubDriver())
    assert result.ok and not values(result)


def test_skip_loop_and_failure_outputs():
    result = run(plan_source('''
      protocol Main(flag=false) {
        if flag { print("hidden"); }
        repeat 3 { print("loop"); }
        print("done");
      }
    '''), StubDriver())
    assert result.ok, result.diagnostics
    assert values(result) == ['loop', 'loop', 'loop', 'done']
    broken = PlanProgram(plans=[ProtocolPlan('p','P',steps=[
        PlanStep('a','print',{'value':{'kind':'IRString','value':'kept'}},[],None),
        PlanStep('b','print',{'value':{'kind':'IRIdentifier','name':'absent'}},['a'],None),
    ])])
    failure = run(broken, StubDriver())
    assert not failure.ok and values(failure) == ['kept']
    assert failure.diagnostics[0].code == 'RT_PRINT_VALUE_UNRESOLVED'


def test_replay_and_continuation(capsys):
    plan = plan_source('print("first"); print(2uL);')
    result = run(plan, StubDriver())
    assert capsys.readouterr().out == 'first\n2 uL\n'
    replay = replay_events(json.loads(json.dumps([e.to_dict() for e in result.events])))
    assert capsys.readouterr().out == ''
    assert 'print_outputs' not in replay.artifacts
    continued = run(plan, StubDriver(), state=replay)
    assert continued.ok and values(continued) == []
    assert capsys.readouterr().out == ''


def test_cli_modes_keep_console_separate(tmp_path, monkeypatch, capsys):
    path=tmp_path/'example.culs'
    path.write_text('print("hello"); print(2uL); return 7;')
    bundle=execute_pipeline([path])
    assert bundle['output']['ok']
    assert capsys.readouterr().out == 'hello\n2 uL\n'
    assert 'prints' not in bundle['output'] and 'prints' not in bundle['results']
    for mode in ('terminal', '--json', '--output', '--results'):
        output=tmp_path/'output.json'
        args=['culsma',str(path)]
        if mode=='--json': args += [mode]
        elif mode!='terminal': args += [mode,str(output)]
        monkeypatch.setattr(sys,'argv',args)
        main()
        captured=capsys.readouterr()
        if mode=='terminal':
            assert captured.out.startswith('hello\n2 uL\n')
            assert captured.out.count('hello') == 1
            assert 'print:' not in captured.out
        else:
            payload=json.loads(captured.out if mode=='--json' else output.read_text())
            assert 'prints' not in payload
            assert 'culsma_print_value_v1' not in json.dumps(payload)
            console = captured.err if mode=='--json' else captured.out
            assert console == 'hello\n2 uL\n'



@pytest.mark.parametrize('expr,code', [
    ({'kind':'IRCall','name':'markers','args':[]}, 'RT_PRINT_VALUE_UNRESOLVED'),
    ({'kind':'IRQuantity','value':float('nan'),'unit':None}, 'RT_PRINT_VALUE_INVALID'),
])
def test_external_plans_reject_effectful_or_invalid_values(expr,code):
    state=RuntimeState()
    plan=PlanProgram(plans=[ProtocolPlan('p','P',steps=[PlanStep('a','print',{'value':expr},[],None)])])
    result=run(plan, StubDriver(),state=state)
    assert not result.ok and result.diagnostics[0].code==code
    assert all(key not in state.artifacts for key in ('data_objects','streams','print_outputs'))


@pytest.mark.parametrize('expression,code', [
    ('1uL+1s', 'TYPE_DIMENSION_MISMATCH'),
    ('[1, 2/0]', 'TYPE_QUANTITY_DIVISION_BY_ZERO'),
])
def test_print_arithmetic_errors_are_decided_before_execution(expression, code):
    _, _, typed = compile_source(f'print({expression});')
    assert code in [d.code for d in typed.diagnostics]


def test_print_does_not_supply_environment_duration_or_target():
    with pytest.raises(ValueError, match='could not infer env target'):
        compile_source(SAMPLE+'with env(thermal=4C) { print(sample); }')
    _, semantic, _ = compile_source(SAMPLE+'with env(thermal=4C) { hold(sample); print(sample); }')
    assert 'SEM_ENV_DURATION_REQUIRED' in [d.code for d in semantic.diagnostics]
    result=run(plan_source(SAMPLE+'''with env(thermal=4C,duration=1s) {
      hold(sample); print(sample.contents.volume);
    }'''), StubDriver())
    assert result.ok and values(result)[0]['value']==100


def test_data_and_material_views_reflect_current_values():
    result=run(plan_source(SAMPLE+'''
      let d=data_ref(kind=qc);
      d.result.value=1; print(d.result);
      d.result.value=2; print(d.result);
      print(sample.materials); print(sample.materials[0]);
    '''), StubDriver())
    assert result.ok, result.diagnostics
    first, second, entries, selected=values(result)
    assert first=={'value':1} and second=={'value':2}
    assert entries[0]==selected
    assert selected['entry_id']=='WATER'


def test_live_material_order_matches_selection_without_mutation():
    prepared=run(plan_source(SAMPLE), StubDriver())
    material=prepared.state.artifacts['material_state']
    raw=next(iter(material['containers'].values()))
    from culsma.runtime.material.component_entries import normalize_component_entries
    entry=normalize_component_entries(raw, state=material)[0]
    zero=copy.deepcopy(entry)
    zero.update(entry_id='zero',content_ref='EMPTY',amount=0,quantity={'dimension':'volume','unit':'uL','value':0})
    other=copy.deepcopy(entry)
    other['entry_id']='same-code-new-entry'
    other['relation']='pellet'
    raw['component_entries']=[zero,entry,other]
    before=copy.deepcopy(material)
    state=RuntimeState(artifacts={'material_state':material})
    plan=PlanProgram(plans=[ProtocolPlan('p','P',steps=[PlanStep('p0','print',{
        'value':{'kind':'IRMember','base':{'kind':'IRIdentifier','name':'sample'},'member':'materials'}
    },[],None)])])
    result=run(plan,StubDriver(),state=state)
    assert result.ok, result.diagnostics
    assert [e['entry_id'] for e in values(result)[0]]==['WATER','same-code-new-entry']
    assert material==before


def test_print_first_in_reused_reference_does_not_execute_again():
    steps=[]
    for index,prefix in enumerate(['first','second']):
        steps.append(PlanStep(prefix,'print',{'value':{'kind':'IRString','value':'body'}},
            [] if index==0 else ['first'],{'ref_meta':{
                'ref_protocol':'P','ref_call_id':prefix,'call_path':'shared'}}))
    result=run(PlanProgram(plans=[ProtocolPlan('p','P',steps=steps)]),StubDriver())
    assert result.ok, result.diagnostics
    assert values(result)==['body']
    assert [e.payload['ref_decision'] for e in result.events if e.kind=='REF_DECISION']==['rerun','reuse']


def test_legacy_material_projection_does_not_initialize_ledger_entries():
    prepared=run(plan_source(SAMPLE), StubDriver())
    material=prepared.state.artifacts['material_state']
    for container in material['containers'].values():
        container.pop('component_entries', None)
    before=copy.deepcopy(material)
    state=RuntimeState(artifacts={'material_state':material})
    step=PlanStep('p0','print',{'value':{'kind':'IRIdentifier','name':'sample'}},[],None)
    result=run(PlanProgram(plans=[ProtocolPlan('p','P',steps=[step])]),StubDriver(),state=state)
    assert result.ok and values(result)[0]['component_entries']
    assert material==before


def test_container_groups_keep_current_member_projections():
    result=run(plan_source(SAMPLE+'''
      let other=tube(capacity=200uL);
      let samples=group([sample,other]);
      print(samples); print(samples[0].materials);
    '''),StubDriver())
    assert result.ok, result.diagnostics
    group, entries=values(result)
    assert group['member_count']==2
    assert group['members'][0]['component_entries']==entries
    assert group['members'][1]['component_entries']==[]


@pytest.mark.parametrize('source', [
    'let x=print(value=1);',
    'return print(value=1);',
    'let x=[print(value=1)];',
])
def test_builtin_print_is_statement_only(source):
    _, semantic, _ = compile_source(source)
    assert 'SEM_PRINT_EXPRESSION' in [d.code for d in semantic.diagnostics]


@pytest.mark.parametrize('kind', ['container_ref', 'container_group_ref', 'IRQuantity'])
def test_record_kind_fields_are_preserved_on_console(kind, tmp_path, capsys):
    from culsma.cli import format_terminal_result
    path=tmp_path/'record.culs'
    path.write_text(f'print({{kind:"{kind}", extra:17}});')
    bundle=execute_pipeline([path])
    assert bundle['output']['ok']
    assert capsys.readouterr().out == repr({'kind':kind,'extra':17}) + '\n'
    assert 'extra' not in format_terminal_result(bundle)
    assert 'prints' not in bundle['output']


def test_data_record_kind_is_not_an_output_type_tag():
    result=run(plan_source('''let d=data_ref(kind=qc);
      d.result.kind="container_ref"; d.result.extra=17; print(d.result);
    '''),StubDriver())
    assert result.ok and values(result)==[{'kind':'container_ref','extra':17}]


def test_reading_stored_expression_does_not_run_constructor():
    expression={'kind':'IRCall','name':'markers','args':[]}
    state=RuntimeState(artifacts={'local_bindings':{'x':expression}})
    before=copy.deepcopy(state.artifacts)
    step=PlanStep('a','print',{'value':{'kind':'IRIdentifier','name':'x'}},[],None)
    result=run(PlanProgram(plans=[ProtocolPlan('p','P',steps=[step])]),StubDriver(),state=state)
    assert not result.ok
    assert result.diagnostics[0].code=='RT_PRINT_VALUE_UNRESOLVED'
    assert 'print_outputs' not in state.artifacts
    assert state.artifacts['local_bindings']==before['local_bindings']


def test_malformed_reference_fails_with_diagnostic():
    from culsma.runtime.value_adapters import AdaptedValue
    state=RuntimeState(artifacts={'local_bindings':{'x':AdaptedValue('material.container', {'kind':'container_ref'})}})
    step=PlanStep('a','print',{'value':{'kind':'IRIdentifier','name':'x'}},[],None)
    result=run(PlanProgram(plans=[ProtocolPlan('p','P',steps=[step])]),StubDriver(),state=state)
    assert not result.ok and result.diagnostics[0].code=='RT_PRINT_VALUE_UNRESOLVED'


def test_partial_checkpoint_prints_only_new_statements():
    plan=plan_source('print("first");print("second");')
    prefix=copy.deepcopy(plan)
    prefix.plans[0]=replace(prefix.plans[0],steps=prefix.plans[0].steps[:1])
    checkpoint=run(prefix,StubDriver())
    assert checkpoint.ok and values(checkpoint)==['first']
    result=run(plan,StubDriver(),state=checkpoint.state)
    assert result.ok and values(result)==['second']
    assert not any('print_output' in e.payload for e in result.events)


def test_break_continue_and_mutable_loop_values():
    result=run(plan_source('''let n=0; repeat 4 {
      n=n+1; if n==2 {continue;} print(n); if n==3 {break;}
    }'''),StubDriver())
    assert result.ok and values(result)==[1,3]


def test_print_keeps_unknown_material_quantity():
    from culsma.runtime.material.unknown_quantity import unknown_mass
    prepared=run(plan_source(SAMPLE),StubDriver())
    material=prepared.state.artifacts['material_state']
    raw=next(iter(material['containers'].values()))
    unknown=unknown_mass('origin')
    raw['component_entries']=[{'entry_id':'unknown','content_ref':'UNKNOWN',
        'relation':'free','amount':None,'quantity':unknown}]
    before=copy.deepcopy(material)
    state=RuntimeState(artifacts={'material_state':material})
    expr={'kind':'IRMember','base':{'kind':'IRIdentifier','name':'sample'},'member':'materials'}
    step=PlanStep('a','print',{'value':expr},[],None)
    result=run(PlanProgram(plans=[ProtocolPlan('p','P',steps=[step])]),StubDriver(),state=state)
    assert result.ok and values(result)[0][0]['quantity']==unknown
    assert material==before


def test_batch_output_isolates_each_program(tmp_path, monkeypatch, capsys):
    first=tmp_path/'first.culs';first.write_text('print("first");')
    second=tmp_path/'second.culs';second.write_text('print("second");')
    monkeypatch.setattr(sys,'argv',['culsma',str(first),str(second),'--json'])
    main()
    captured = capsys.readouterr()
    output=json.loads(captured.out)
    assert captured.err == 'first\nsecond\n'
    assert all('prints' not in item['output'] for item in output['runs'])


def test_terminal_print_does_not_truncate_nested_values(tmp_path, capsys):
    path=tmp_path/'many.culs'
    path.write_text('''let d=data_ref(kind=qc);
      d.result.last_field="last-field";
      print({kind:"data_group_ref",items:[1,2,3,4,5],extra:"last-item"});
      print(d);
    ''')
    bundle=execute_pipeline([path])
    assert bundle['output']['ok']
    text=capsys.readouterr().out
    assert 'last-item' in text and 'last-field' in text
    assert '[1, 2, 3, 4, 5]' in text


def test_code_shaped_record_operands_are_compared_without_execution(monkeypatch):
    import culsma.runtime.values as runtime_values
    def unexpected_call(*args, **kwargs):
        raise AssertionError("A record must not execute as an expression")
    monkeypatch.setattr(runtime_values, '_eval_runtime_call', unexpected_call)
    result=run(plan_source('''print({kind:"IRCall",name:"markers",args:[]} ==
      {kind:"IRCall",name:"markers",args:[]});'''),StubDriver())
    assert result.ok and values(result)==[True]


def test_read_only_arithmetic_keeps_quantity_fields():
    result=run(plan_source('''let d=data_ref(kind=qc);d.result.v=2uL;
      print(d.result.v*2);print(-d.result.v);'''),StubDriver())
    assert result.ok, result.diagnostics
    assert [v['value'] for v in values(result)]==[4,-2]


@pytest.mark.parametrize('argument', ['', 'arg0=7'])
def test_user_protocol_print_can_return_a_value(argument):
    result=run(plan_source(f'''protocol print(arg0=7) {{return arg0;}}
      let result=print({argument}); return result;'''),StubDriver())
    assert result.ok, result.diagnostics
    assert result.state.artifacts['protocol_outputs']['entry']['value']==7
    assert not values(result)


def test_continue_on_error_retains_independent_later_prints():
    steps=[
        PlanStep('a','print',{'value':{'kind':'IRString','value':'first'}},[],None),
        PlanStep('b','print',{'value':{'kind':'IRIdentifier','name':'missing'}},[],None),
        PlanStep('c','print',{'value':{'kind':'IRString','value':'later'}},[],None),
    ]
    result=run(PlanProgram(plans=[ProtocolPlan('p','P',steps=steps)]),StubDriver(),on_error='continue')
    assert not result.ok and values(result)==['first','later']
    assert result.state.step_status=={'a':'completed','b':'failed','c':'completed'}


def test_mutable_data_list_is_read_at_each_print():
    result=run(plan_source('''let d=data_ref(kind=qc); d.result.items=[1];
      print(d.result.items);d.result.items.append(2);print(d.result.items);'''),StubDriver())
    assert result.ok and values(result)==[[1],[1,2]]


@pytest.mark.parametrize('mode', ['--json','--output','--results'])
def test_cli_failure_preserves_console_output(mode, tmp_path, monkeypatch, capsys):
    path=tmp_path/'failure.culs'
    path.write_text(SAMPLE+'''let target=tube(); print("before-failure");
      target << [sample:1uL]; print("not-executed");''')
    destination=tmp_path/'result.json'
    args=['culsma',str(path),'--fail-op','Mutation',mode]
    if mode!='--json': args.append(str(destination))
    monkeypatch.setattr(sys,'argv',args)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code==1
    captured=capsys.readouterr()
    payload=json.loads(captured.out if mode=='--json' else destination.read_text())
    assert 'prints' not in payload
    console = captured.err if mode=='--json' else captured.out
    assert 'before-failure\n' in console
    assert 'not-executed' not in console


def test_volume_read_does_not_add_bindings_to_legacy_ledger():
    from culsma.runtime.values import RuntimeValueResolver
    material={'containers':{'sample':{'volume_uL':10,'mass_mg':0,'components':{}}}}
    state=RuntimeState(artifacts={'material_state':material})
    before=copy.deepcopy(material)
    expr={'kind':'IRMember','base':{'kind':'IRMember',
        'base':{'kind':'IRIdentifier','name':'sample'},'member':'contents'},'member':'volume'}
    assert RuntimeValueResolver().read_value(expr,state)==(10,'uL')
    assert material==before


@pytest.mark.parametrize('unsupported', ['cycle','object'])
def test_invalid_values_fail_before_console_output(unsupported):
    value={} if unsupported=='cycle' else object()
    if unsupported=='cycle': value['self']=value
    state=RuntimeState(artifacts={'local_bindings':{'x':value}})
    step=PlanStep('a','print',{'value':{'kind':'IRIdentifier','name':'x'}},[],None)
    result=run(PlanProgram(plans=[ProtocolPlan('p','P',steps=[step])]),StubDriver(),state=state)
    assert not result.ok and result.diagnostics[0].code=='RT_PRINT_VALUE_INVALID'
    assert not values(result)
    assert not any('print_output' in e.payload for e in result.events)


def test_existing_stream_and_plate_are_read_without_driver_actions():
    source='''let sample=tube();let panel=markers(["CD3"]);
      let events=stream(sample=sample,unit=single_cell,panel=panel);
      let carrier=plate(rows=8,cols=12,label="P");'''
    driver=RecordingDriver()
    result=run(plan_source(source+'print(events);print(carrier);'),driver)
    baseline_driver=RecordingDriver()
    baseline=run(plan_source(source),baseline_driver)
    assert result.ok and baseline.ok
    assert [v['kind'] for v in values(result)]==['unit_stream_ref','plate_ref']
    assert driver.actions==baseline_driver.actions
    assert result.state.artifacts['local_bindings']==baseline.state.artifacts['local_bindings']


def test_console_output_is_immediate_and_flushed():
    from io import StringIO
    from contextlib import redirect_stdout

    class Console(StringIO):
        def __init__(self):
            super().__init__()
            self.flushes = 0

        def flush(self):
            self.flushes += 1
            super().flush()

    console = Console()

    class InspectingDriver(RecordingDriver):
        def execute(self, step):
            if step.op == 'Mutation':
                assert console.getvalue() == 'before\n'
                assert console.flushes >= 1
            return super().execute(step)

    source = SAMPLE + 'let target=tube(); print("before"); target << [sample:1uL]; print("after");'
    with redirect_stdout(console):
        result = execute_runtime(plan_source(source), InspectingDriver())
    assert result.ok
    assert console.getvalue() == 'before\nafter\n'
    assert console.flushes == 2


def test_console_values_are_absent_from_saved_artifacts(tmp_path, monkeypatch, capsys):
    from culsma.cli import write_run_artifacts
    path=tmp_path/'print.culs'
    path.write_text('let n=1; print(n); n=2; print(n); return n;')
    bundle=execute_pipeline([path])
    assert capsys.readouterr().out == '1\n2\n'
    write_run_artifacts(bundle, tmp_path/'artifacts')
    for path in (tmp_path/'artifacts').glob('*.json'):
        text = path.read_text()
        assert 'print_outputs' not in text and 'print_output"' not in text
        assert 'culsma_print_value_v1' not in text and '"prints"' not in text
    assert bundle['output']['returns']['entry']['value'] == 2
