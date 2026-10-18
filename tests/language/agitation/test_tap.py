"""Tapping is a discrete method; a plate is one carrier, not a well group."""

import json
import runpy
from pathlib import Path

import pytest

from culsma.domains.agitation import AgitationMode
from culsma.domains.agitation.contracts import AgitationArgumentsRule
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.typecheck.expressions import TypecheckExpressionServices
from culsma.pipeline.ir_nodes import IRCall, IRIdentifier
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.runtime.state import init_state


class RecordingDriver(StubDriver):
    def __init__(self):
        super().__init__()
        self.actions = []

    def execute(self, step):
        self.actions.append(step)
        return super().execute(step)


def compile_source(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    return compiled, validate(compiled.ir, analysis=compiled.analysis), typecheck(compiled.ir, analysis=compiled.analysis)


def plan_source(source):
    compiled, semantic, typed = compile_source(source)
    assert semantic.ok and typed.ok, (semantic.diagnostics, typed.diagnostics)
    plan = lower_ir_to_plan(compiled.ir)
    assert not plan.diagnostics, plan.diagnostics
    return plan


def replay_plan(plan):
    payload = json.loads(json.dumps(plan.to_dict()))
    return PlanProgram(plans=[ProtocolPlan(p['protocol_id'], p['protocol_name'], steps=[
        PlanStep(s['step_id'], s['op'], s['args'], s['deps'], s['gate']) for s in p['steps']
    ]) for p in payload['plans']])


def test_plate_is_a_carrier_type_separate_from_a_group():
    services = TypecheckExpressionServices()
    bindings = {'p': IRCall('plate'), 'alias': IRIdentifier('p')}
    assert services.classify_local_expr_type(IRIdentifier('alias'), expr_bindings=bindings) == 'plate_ref'
    assert services.classify_local_expr_type(IRCall('group'), expr_bindings={}) == 'group_ref'


@pytest.mark.parametrize('spelling', ['AgitationMode.TAP', 'tap', '"tap"'])
def test_tap_preserves_mode_and_gentle_without_invented_parameters(spelling):
    driver = RecordingDriver()
    result = run(plan=plan_source(f'let s=tube(); agit(sample=s,mode={spelling}) with constraint(gentle);'), driver=driver)
    assert result.ok, result.diagnostics
    action, = [s for s in driver.actions if s.op == 'agit']
    assert action.args['mode'] is AgitationMode.TAP
    assert set(action.args) == {'sample', 'mode'}
    assert 'gentle' in json.dumps(action.gate).lower()


@pytest.mark.parametrize('argument', ['duration=1s', 'rate=60rpm', 'cycles=3', 'motion=rock', 'drive=3000g'])
def test_tap_rejects_parameters_before_dispatch(argument):
    _, semantic, _ = compile_source(f'let s=tube(); agit(sample=s,mode=tap,{argument});')
    assert 'SEM_AGIT_ARG_CONFLICT' in [d.code for d in semantic.diagnostics]
    field = argument.split('=')[0]
    with pytest.raises(ValueError):
        AgitationArgumentsRule().validate({'mode': AgitationMode.TAP}, {'mode', field})


def test_dynamic_tap_parameters_fail_before_driver():
    driver = RecordingDriver()
    plan = plan_source('''protocol T(flag=true) {
      let s=tube(); let method=AgitationMode.SHAKE;
      if flag { method=AgitationMode.TAP; }
      agit(sample=s,mode=method,duration=1s);
    }''')
    result = run(plan=plan, driver=driver)
    assert not result.ok
    assert 'RT_EXTERNAL_ENUM_INVALID' in [d.code for d in result.diagnostics]
    assert not any(s.op == 'agit' for s in driver.actions)


def test_plate_tap_is_one_action_and_preserves_each_well():
    driver = RecordingDriver()
    plan = plan_source('''
      let p=plate(label="Same",format=PlateFormat.WELL_96);
      let other=plate(label="Same",format=PlateFormat.WELL_96);
      let a=p[A1]; let b=p[A2]; let c=other[A1];
      let stock=tube(load=[content(kind=formulation,type=buffer,code="B"):100uL]);
      a << [stock:10uL]; b << [stock:20uL]; c << [stock:30uL];
      sep(sample=a[0],program=centrifuge_program(drive=3000g));
      sep(sample=b[0],program=centrifuge_program(drive=3000g));
      sep(sample=c[0],program=centrifuge_program(drive=3000g));
      agit(sample=p,mode=tap) with constraint(gentle);
    ''')
    result = run(plan=replay_plan(plan), driver=driver)
    assert result.ok, result.diagnostics
    action, = [s for s in driver.actions if s.op == 'agit']
    assert action.args['sample']['kind'] == 'plate_ref'
    material = result.state.artifacts['material_state']
    wells = {c['volume_uL']: (key, c) for key, c in material['containers'].items() if c['metadata']['kind'] == 'well'}
    assert set(wells) == {10, 20, 30}
    for volume in (10, 20):
        key, well = wells[volume]
        assert well['metadata']['plate_ref'] == action.args['sample']
        assert material['contents_states'][key]['kind'] == 'mixed'
        assert material['contents_states'][key]['valid'] is False
        assert well['components']['B'] == volume
    assert material['contents_states'][wells[30][0]]['valid'] is True


def test_plate_identity_survives_alias_protocol_and_loop():
    driver = RecordingDriver()
    plan = plan_source('''
      protocol Tap(target) { agit(sample=target,mode=tap); }
      protocol T {
        repeat i in schedule(start=1,end=2,step=1) {
          let p=plate(label="Repeated",format=PlateFormat.WELL_96);
          let w=p[A1]; let alias=p;
          Tap(target=alias);
        }
      }
      T();
    ''')
    result = run(plan=plan, driver=driver)
    assert result.ok, result.diagnostics
    actions = [s for s in driver.actions if s.op == 'agit']
    assert len(actions) == 2
    ids = [s.args['sample']['id'] for s in actions]
    assert len(set(ids)) == 2
    material = result.state.artifacts['material_state']
    assert sorted(c['metadata']['plate_ref']['id'] for c in material['containers'].values()) == sorted(ids)


@pytest.mark.parametrize('runtime_loop', [False, True])
def test_plate_instances_are_scoped_across_nested_calls_and_runtime_iterations(runtime_loop):
    loop = 'repeat i in schedule(start=1,end=count,step=1)' if runtime_loop else 'repeat i in schedule(start=1,end=2,step=1)'
    source = f'''
      protocol Inner {{ let p=plate(format="96well"); let w=p[A1]; agit(sample=p,mode=tap); }}
      protocol T(count=2) {{
        let p=plate(format="96well"); let w=p[A1];
        {loop} {{ Inner(); }}
        agit(sample=p,mode=tap);
      }}
      T();
    '''
    driver = RecordingDriver()
    result = run(plan=plan_source(source), driver=driver)
    assert result.ok, result.diagnostics
    actions = [s for s in driver.actions if s.op == 'agit']
    assert len(actions) == 3
    assert len({s.args['sample']['id'] for s in actions}) == 3
    material = result.state.artifacts['material_state']
    assert len(material['plates']) == len(material['containers']) == 3


def test_unallocated_plate_reference_fails_before_dispatch():
    plan = PlanProgram(plans=[ProtocolPlan('p', 'T', steps=[PlanStep('tap', 'agit', {
        'mode': 'tap', 'sample': {'kind': 'plate_ref', 'id': 'missing',
                                'carrier_id': 'P', 'rows': 8, 'cols': 12},
    }, [], None)])])
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert not result.ok
    assert 'MAT_BINDING_NOT_FOUND' in [d.code for d in result.diagnostics]
    assert not driver.actions


def test_tap_container_group_preserves_existing_member_semantics():
    driver = RecordingDriver()
    result = run(plan=plan_source('let a=tube(); let b=tube(); agit(sample=group([a,b]),mode=tap);'), driver=driver)
    assert result.ok, result.diagnostics
    material = result.state.artifacts['material_state']
    assert len(material['containers']) == 2
    assert not material.get('plates')


def test_failed_plate_action_keeps_prior_contents_organization():
    plan = plan_source('''
      let p=plate(format="96well"); let w=p[A1];
      sep(sample=w[0],program=centrifuge_program(drive=3000g));
      agit(sample=p,mode=tap);
    ''')
    result = run(plan=plan, driver=StubDriver(fail_ops={'agit'}))
    assert not result.ok
    material = result.state.artifacts['material_state']
    key, = material['containers']
    assert material['contents_states'][key]['valid'] is True
    assert material['contents_states'][key]['kind'] != 'mixed'


def test_runtime_stream_iterations_allocate_distinct_plate_instances():
    plan = plan_source('''protocol T {
      let cells=tube(); let events=stream(sample=cells,unit=single_cell);
      repeat cell in events {
        let p=plate(format="96well"); let w=p[A1]; agit(sample=p,mode=tap);
      }
    }''')
    state = init_state(plan)
    state.artifacts['stream_units'] = {'events': ['cell_0', 'cell_1']}
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver, state=state)
    assert result.ok, result.diagnostics
    actions = [s for s in driver.actions if s.op == 'agit']
    assert len(actions) == 2
    material = result.state.artifacts['material_state']
    for action in actions:
        reference = action.args['sample']
        assert reference['kind'] == 'plate_ref'
        wells = [c for c in material['containers'].values() if c['metadata'].get('plate_ref') == reference]
        assert len(wells) == 1
    assert len({s.args['sample']['id'] for s in actions}) == 2


@pytest.mark.parametrize('mode', ['shake', 'flick', 'centrifuge'])
def test_legacy_plate_agitation_remains_one_descriptor_action(mode):
    params = ',drive=3000g,duration=1s' if mode == 'centrifuge' else ''
    driver = RecordingDriver()
    result = run(plan_source(f'let p=plate(format="96well"); agit(sample=p,mode={mode}{params});'), driver)
    assert result.ok, result.diagnostics
    action, = [step for step in driver.actions if step.op == 'agit']
    assert action.args['sample']['kind'] == 'IRCall'
    assert action.args['sample']['name'] == 'plate'
    assert 'runtime_ref' not in action.args['sample']


def test_returned_plate_preserves_identity_through_protocol_call():
    driver = RecordingDriver()
    result = run(plan_source('''
      protocol CreatePlate {
        let p=plate(format="96well");
        agit(sample=p,mode=tap);
        return p;
      }
      let returned=CreatePlate();
      agit(sample=returned,mode=tap);
      return returned;
    '''), driver)
    assert result.ok, result.diagnostics
    first, second = [s.args['sample'] for s in driver.actions if s.op == 'agit']
    assert first == second
    assert result.state.artifacts['protocol_outputs']['entry']['value'] == first


def test_elisa_stop_tap_readout_order(tmp_path):
    path = Path(__file__).resolve().parents[3] / 'benchmarks/modules/07-sandwich-elisa/protocol.culs'
    source = path.read_text()
    start = source.index('  // COVERAGE GAP:')
    end = source.index('  // Source step S38:', start)
    source = source[:start] + '''  agit(sample=elisa_plate,mode=AgitationMode.TAP) with constraint(gentle);
  let stopped_reaction_wells=assay_wells;

''' + source[end:]
    (tmp_path / 'protocol.culs').write_text(source)
    (tmp_path / 'source.md').write_text(path.with_name('source.md').read_text())
    assessor = runpy.run_path(str(path.parents[2] / 'reproduce.py'))['assess']
    coverage = assessor(tmp_path, implementation='development', language_version='development')
    assert coverage['matched_steps'] == coverage['total_steps'] == 42
    assert not coverage['issues']
    driver = RecordingDriver()
    result = run(plan=plan_source(source), driver=driver)
    assert result.ok, result.diagnostics
    taps = [i for i, s in enumerate(driver.actions) if s.op == 'agit' and s.args['mode'] is AgitationMode.TAP]
    tap_index, = taps
    assert driver.actions[tap_index - 1].op == 'Mutation'
    assert driver.actions[tap_index + 1].op == 'img'
    material = result.state.artifacts['material_state']
    plate = driver.actions[tap_index].args['sample']
    wells = [c for c in material['containers'].values() if c['metadata'].get('plate_ref') == plate]
    assert len(wells) == 16
    assert all(c['volume_uL'] == 150 for c in wells)
