"""Continuous rotation through source, binding, planning and driver dispatch."""

import pytest

from culsma.domains.agitation import AgitationMode
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.external_boundary import DEFAULT_EXTERNAL_PARAMETER_NORMALIZER
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run


class RecordingDriver(StubDriver):
    def __init__(self):
        super().__init__()
        self.agitations = []

    def execute(self, step):
        if step.op == 'agit':
            self.agitations.append(step)
        return super().execute(step)


def compile_source(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    typed = typecheck(compiled.ir, analysis=compiled.analysis)
    return compiled, semantic, typed


@pytest.mark.parametrize('mode', ['AgitationMode.ROTATION', 'rotation', '"rotation"'])
@pytest.mark.parametrize('rate', ['', ', rate=20rpm'])
def test_rotation_source_forms_preserve_driver_arguments(mode, rate):
    compiled, semantic, typed = compile_source(f'''
let sample = tube(label="Sample", capacity=1mL);
with env(thermal=4C) {{
  agit(sample=sample, mode={mode}, duration=2h{rate});
}}
''')
    assert semantic.ok and typed.ok
    plan = lower_ir_to_plan(compiled.ir)
    assert not plan.diagnostics
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert result.ok, result.diagnostics
    assert len(driver.agitations) == 1
    args = driver.agitations[0].args
    assert args['mode'] is AgitationMode.ROTATION
    assert args['duration']['value'] == 2 and args['duration']['unit'] == 'h'
    assert ('rate' in args) == bool(rate)
    if rate:
        assert (args['rate']['value'], args['rate']['unit']) == (20, 'rpm')


@pytest.mark.parametrize('args,codes', [
    ('', ['SEM_AGIT_DURATION_REQUIRED']),
    (', cycles=3', ['SEM_AGIT_DURATION_REQUIRED', 'SEM_AGIT_ARG_CONFLICT']),
    (', duration=0s', ['SEM_AGIT_QUANTITY_INVALID']),
    (', duration=2mL', ['SEM_AGIT_QUANTITY_INVALID']),
    (', duration=2h, cycles=3', ['SEM_AGIT_ARG_CONFLICT']),
    (', duration=2h, rate=0rpm', ['SEM_AGIT_QUANTITY_INVALID']),
    (', duration=2h, rate=2mL', ['SEM_AGIT_QUANTITY_INVALID']),
])
def test_rotation_invalid_literals_report_owned_diagnostics(args, codes):
    _, semantic, _ = compile_source(f'''
let sample=tube(label="Sample",capacity=1mL);
with env(thermal=4C,duration=2h) {{
  agit(sample=sample,mode=rotation{args});
}}
''')
    assert not semantic.ok
    assert [diagnostic.code for diagnostic in semantic.diagnostics] == codes


@pytest.mark.parametrize('args,name', [
    (', duration=-1s', 'duration'),
    (', duration=2h, rate=-1rpm', 'rate'),
])
def test_rotation_negative_expressions_fail_before_dispatch(args, name):
    compiled, semantic, typed = compile_source(f'''
let sample=tube(label="Sample",capacity=1mL);
agit(sample=sample,mode=rotation{args});
''')
    assert semantic.ok and typed.ok
    plan = lower_ir_to_plan(compiled.ir)
    assert not plan.diagnostics
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert not result.ok
    assert not driver.agitations
    assert [(d.code, d.message) for d in result.diagnostics] == [
        ('RT_EXTERNAL_ENUM_INVALID', f'rotation {name} must be finite and positive'),
        ('RT_ABORTED_AFTER_FAILURE', 'Runtime aborted after first failed step (fail-fast mode)'),
    ]


def test_rotation_protocol_alias_and_group_preserve_materials():
    compiled, semantic, typed = compile_source('''
protocol Rotate(samples, time, speed, mode=AgitationMode.ROTATION) {
  let selected=mode;
  agit(sample=samples,mode=selected,duration=time,rate=speed);
}
let a=tube(label="A",load=[content(kind=formulation,type=buffer,code="B"):100uL]);
let b=tube(label="B",load=[content(kind=formulation,type=buffer,code="B"):200uL]);
Rotate(samples=group([a,b]),time=10min,speed=20rpm);
''')
    assert semantic.ok and typed.ok
    plan = lower_ir_to_plan(compiled.ir)
    assert not plan.diagnostics
    driver = RecordingDriver()
    result = run(plan=plan,driver=driver)
    assert result.ok, result.diagnostics
    assert all(s.args['mode'] is AgitationMode.ROTATION for s in driver.agitations)
    assert driver.agitations
    containers=result.state.artifacts['material_state']['containers']
    assert sorted(c['volume_uL'] for c in containers.values()) == [100,200]


@pytest.mark.parametrize('value', [0, -1, float('inf'), float('nan')])
def test_rotation_bound_quantity_rejected_at_plan_and_runtime_boundary(value):
    args={'mode':AgitationMode.ROTATION,'duration':{'kind':'IRQuantity','value':value,'unit':'s'}}
    for normalize in (DEFAULT_EXTERNAL_PARAMETER_NORMALIZER.normalize_plan_arguments,
                      DEFAULT_EXTERNAL_PARAMETER_NORMALIZER.normalize_runtime_arguments):
        with pytest.raises(ValueError,match='finite and positive'):
            normalize('agit',args)


def test_rotation_dynamic_duration_checked_before_driver():
    compiled, semantic, typed = compile_source('''
protocol T(flag=true) {
  let sample=tube(label="Sample",capacity=1mL);
  let time=1s;
  if flag { time=-1s; }
  agit(sample=sample,mode=rotation,duration=time);
}
''')
    assert semantic.ok and typed.ok
    plan=lower_ir_to_plan(compiled.ir)
    assert not plan.diagnostics
    driver=RecordingDriver()
    result=run(plan=plan,driver=driver)
    assert not result.ok
    assert not driver.agitations


def test_unresolved_rotation_duration_is_deferred_only_until_runtime():
    args = {'mode': AgitationMode.ROTATION,
            'duration': {'kind': 'IRIdentifier', 'name': 'missing', 'bound': True}}
    DEFAULT_EXTERNAL_PARAMETER_NORMALIZER.normalize_plan_arguments('agit', args)
    with pytest.raises(ValueError, match='unit-bearing quantity'):
        DEFAULT_EXTERNAL_PARAMETER_NORMALIZER.normalize_runtime_arguments('agit', args)


def test_rotation_invalidates_separated_contents_without_changing_amounts():
    compiled, semantic, typed = compile_source('''
let sample=tube(label="Sample",load=[
  content(kind=particulate,type=beads,code="BEADS",attrs={bead_property:magnetic}):20uL,
  content(kind=formulation,type=buffer,code="BUFFER"):180uL
]);
sep(sample=sample,program=magnetic_program(duration=5min));
agit(sample=sample,mode=rotation,duration=1min);
''')
    assert semantic.ok and typed.ok
    result = run(plan=lower_ir_to_plan(compiled.ir), driver=StubDriver())
    assert result.ok, result.diagnostics
    material = result.state.artifacts['material_state']
    sample_id = next(key for key, value in material['containers'].items() if value.get('metadata', {}).get('label') == 'Sample')
    assert material['containers'][sample_id]['volume_uL'] == 200
    state = material['contents_states'][sample_id]
    assert state['kind'] == 'mixed' and state['valid'] is False
    assert state['invalid_reason'] == 'explicit_mixing'
