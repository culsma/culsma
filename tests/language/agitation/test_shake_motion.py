"""Explicit shake trajectories from source through dispatch and plan replay."""
import json

import pytest

from culsma.domains.agitation import AgitationMode, ShakeMotion
from culsma.domains.agitation.contracts import ShakeMotionRule
from culsma.driver.stub import StubDriver
from culsma.driver.human import HumanDriver
from culsma.driver.robot import RobotDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.external_boundary import DEFAULT_EXTERNAL_PARAMETER_NORMALIZER as normalizer
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan_nodes import PlanProgram, ProtocolPlan, PlanStep
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run


class RecordingDriver(StubDriver):
    def __init__(self):
        super().__init__()
        self.actions = []

    def execute(self, step):
        if step.op == 'agit':
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


@pytest.mark.parametrize('motion,args', [
    ('LINEAR', 'duration=1min, rate=2Hz'),
    ('LINEAR', 'duration=1min, rate=120cycle/min'),
    ('ORBITAL', 'duration=1min, rate=200rpm'),
    ('ROCK', 'cycles=3'),
    ('ROCK', 'duration=5min, rate=20cycle/min'),
    ('ROCK', 'cycles=3, rate=1Hz'),
    ('ROTATION', 'duration=2h, rate=20rpm'),
])
@pytest.mark.parametrize('spelling', ['enum', 'bare', 'string'])
def test_motion_preserves_identity_and_parameters_to_driver(motion, args, spelling):
    token = {'enum': f'ShakeMotion.{motion}', 'bare': motion.lower(), 'string': f'"{motion.lower()}"'}[spelling]
    plan = plan_source(f'let sample=tube(label="S"); agit(sample=sample,mode=AgitationMode.SHAKE,motion={token},{args});')
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert result.ok, result.diagnostics
    assert len(driver.actions) == 1
    delivered = driver.actions[0].args
    assert delivered['mode'] is AgitationMode.SHAKE
    assert delivered['motion'] is ShakeMotion[motion]
    assert ('cycles' in delivered) == ('cycles=' in args)
    assert ('rate' in delivered) == ('rate=' in args)


@pytest.mark.parametrize('args,code', [
    ('mode=stir,motion=rock,duration=1s', 'SEM_AGIT_ARG_CONFLICT'),
    ('mode=rotation,motion=rotation,duration=1s', 'SEM_AGIT_ARG_CONFLICT'),
    ('mode=shake,motion=swirl,duration=1s', 'SEM_AGIT_MOTION_UNKNOWN'),
    ('mode=shake,motion=linear', 'SEM_AGIT_DURATION_REQUIRED'),
    ('mode=shake,motion=orbital,cycles=3', 'SEM_AGIT_ARG_CONFLICT'),
    ('mode=shake,motion=rock', 'SEM_AGIT_DURATION_REQUIRED'),
    ('mode=shake,motion=rock,duration=1s,cycles=3', 'SEM_AGIT_ARG_CONFLICT'),
    ('mode=shake,motion=rock,cycles=0', 'SEM_AGIT_QUANTITY_INVALID'),
    ('mode=shake,motion=rock,cycles=1.5', 'SEM_AGIT_QUANTITY_INVALID'),
    ('mode=shake,motion=rock,cycles=3s', 'SEM_AGIT_QUANTITY_INVALID'),
    ('mode=shake,motion=rock,duration=1s,rate=20rpm', 'SEM_AGIT_QUANTITY_INVALID'),
    ('mode=shake,motion=orbital,duration=1s,rate=2Hz', 'SEM_AGIT_QUANTITY_INVALID'),
    ('mode=shake,motion=rotation,duration=0s', 'SEM_AGIT_QUANTITY_INVALID'),
    ('mode=shake,duration=1s,rate=2Hz', 'SEM_AGIT_QUANTITY_INVALID'),
])
def test_motion_source_rejects_invalid_combinations(args, code):
    _, semantic, _ = compile_source(f'let s=tube(label="S"); agit(sample=s,{args});')
    assert code in [d.code for d in semantic.diagnostics]


def test_motion_rejects_foreign_enum_identity():
    _, semantic, typed = compile_source('let s=tube(label="S"); agit(sample=s,mode=shake,motion=AgitationMode.ROTATION,duration=1s);')
    assert not (semantic.ok and typed.ok)


def test_generic_shake_does_not_invent_motion():
    driver = RecordingDriver()
    result = run(plan=plan_source('let s=tube(label="S"); agit(sample=s,mode=shake,duration=1s);'), driver=driver)
    assert result.ok
    assert 'motion' not in driver.actions[0].args


def test_motion_protocol_alias_group_and_json_replay():
    plan = plan_source('''
protocol Mix(samples, movement, count) {
 let selected=movement;
 agit(sample=samples,mode=shake,motion=selected,cycles=count);
}
let a=tube(label="A",load=[content(kind=formulation,type=buffer,code="B"):100uL]);
let b=tube(label="B",load=[content(kind=formulation,type=buffer,code="B"):200uL]);
Mix(samples=group([a,b]),movement=ShakeMotion.ROCK,count=3);
''')
    payload = json.loads(json.dumps(plan.to_dict()))
    loaded = PlanProgram(plans=[ProtocolPlan(p['protocol_id'], p['protocol_name'], steps=[
        PlanStep(s['step_id'], s['op'], s['args'], s['deps'], s['gate']) for s in p['steps']
    ]) for p in payload['plans']])
    driver = RecordingDriver()
    result = run(plan=loaded, driver=driver)
    assert result.ok, result.diagnostics
    assert driver.actions and all(s.args['motion'] is ShakeMotion.ROCK for s in driver.actions)
    containers = result.state.artifacts['material_state']['containers']
    assert sorted(c['volume_uL'] for c in containers.values()) == [100, 200]


@pytest.mark.parametrize('change', ['movement=ShakeMotion.ORBITAL;', 'count=0;'])
def test_dynamic_motion_or_count_is_checked_before_action(change):
    plan = plan_source(f'''
protocol T(flag=true) {{
 let sample=tube(label="S");
 let movement=ShakeMotion.ROCK;
 let count=3;
 if flag {{ {change} }}
 agit(sample=sample,mode=shake,motion=movement,cycles=count);
}}
''')
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert not result.ok
    assert not driver.actions
    assert 'RT_EXTERNAL_ENUM_INVALID' in [d.code for d in result.diagnostics]


@pytest.mark.parametrize('value', [True, 0, -1, 1.5, float('nan'), float('inf'), (3, 's')])
def test_rock_count_rule_uses_real_values(value):
    with pytest.raises(ValueError):
        ShakeMotionRule.validate_quantity(ShakeMotion.ROCK, 'cycles', value)


def test_motion_is_deferred_at_plan_boundary_but_required_at_runtime():
    args = {'mode': AgitationMode.SHAKE,
            'motion': {'kind': 'IRIdentifier', 'name': 'missing', 'bound': True},
            'duration': {'kind': 'IRQuantity', 'value': 1, 'unit': 's'}}
    normalizer.normalize_plan_arguments('agit', args)
    with pytest.raises(ValueError, match='Unresolved enum'):
        normalizer.normalize_runtime_arguments('agit', args)


@pytest.mark.parametrize('driver_type', [HumanDriver, RobotDriver])
def test_motion_reaches_real_driver_projection(driver_type):
    recorder = RecordingDriver()
    result = run(plan=plan_source('let s=tube(label="S"); agit(sample=s,mode=shake,motion=rock,cycles=3);'), driver=recorder)
    assert result.ok
    projection = driver_type().execute(recorder.actions[0])
    assert projection.ok
    args = projection.payload['projection']['semantic_args']
    assert args['mode'] == 'shake' and args['motion'] == 'rock'
    assert 'cycles' in args


def test_frequency_expression_keeps_units_and_value():
    plan = plan_source("""
let s=tube(label="S");
let frequency=60cycle/min + 1Hz;
agit(sample=s,mode=shake,motion=linear,duration=1s,rate=frequency);
""")
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert result.ok, result.diagnostics
    rate = driver.actions[0].args['rate']
    assert rate['unit'] == 'cycle/min' and rate['value'] == pytest.approx(120)


@pytest.mark.parametrize('motion', list(ShakeMotion))
def test_motion_does_not_invent_a_rate(motion):
    plan = plan_source(f'let s=tube(label="S"); agit(sample=s,mode=shake,motion=ShakeMotion.{motion.name},duration=1s);')
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert result.ok, result.diagnostics
    assert 'rate' not in driver.actions[0].args
