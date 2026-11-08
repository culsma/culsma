"""Source-to-runtime contracts for separation-owned contexts."""
import pytest
from test_kernel_runtime import _build_plan_from_source, _container_by_label
from culsma.driver.stub import StubDriver
from culsma.runtime.executor import run
from culsma.runtime.replay import replay_events

SAMPLE = '''let s=tube(label="sample",capacity=500uL,load=[buffer(code="B",type="buffer"):200uL]);
let w=tube(label="waste",capacity=500uL);'''
MAG = 'sample=s,program=magnetic_program(duration=2min)'
READ = 'w << [s.contents[1]:10uL];'


def execute(body, declarations=SAMPLE):
    plan = _build_plan_from_source('protocol T {' + declarations + body + '}')
    return plan, run(plan, StubDriver())


def test_with_sep_executes_once_and_preserves_without_outer_magnetic_env():
    plan, result = execute('with sep('+MAG+') {'+READ+READ+'}')
    assert result.ok, result.diagnostics
    assert sum(s.op == 'sep' for s in plan.plans[0].steps) == 1
    material = result.state.artifacts['material_state']
    assert _container_by_label(material['containers'], 'waste')['volume_uL'] == 20
    assert next(iter(material['contents_states'].values()))['invalid_reason'] == 'separation_scope_ended'
    assert replay_events(result.events).artifacts['material_state'] == material
    for step in plan.plans[0].steps:
        assert 'env' not in (step.gate or {})


@pytest.mark.parametrize('suffix', [READ, 'with env(field=magnetic_rack) {'+READ+'}'])
def test_leaving_sep_expires_even_when_outer_env_continues(suffix):
    _, result = execute('with env(thermal=4C) {with sep('+MAG+') {'+READ+'}'+suffix+'}')
    assert not result.ok
    assert any(d.code == 'MAT_CONTENTS_STATE_NOT_INDEXED' for d in result.diagnostics)


def test_inner_env_does_not_own_separation_lifetime():
    _, result = execute('with sep('+MAG+') {with env(thermal=4C,duration=1min) {hold(s);}'+READ+'}')
    assert result.ok, result.diagnostics


def test_new_scope_performs_new_separation():
    _, result = execute(('with sep('+MAG+') {'+READ+'}') * 2)
    assert result.ok, result.diagnostics


@pytest.mark.parametrize('loop', ['repeat 2', 'repeat tick in schedule(start=1,end=2,step=1)'])
def test_loop_inside_scope_preserves_and_scope_inside_loop_reexecutes(loop):
    for body in ['with sep('+MAG+') {'+loop+' {'+READ+'}}', loop+' {with sep('+MAG+') {'+READ+'}}']:
        _, result = execute(body)
        assert result.ok, result.diagnostics
        assert _container_by_label(result.state.artifacts['material_state']['containers'], 'waste')['volume_uL'] == 20


@pytest.mark.parametrize('control', ['break;', 'continue;', 'w << [s.contents[99]];'])
def test_early_exit_closes_scope_and_replays(control):
    _, result = execute('repeat 2 {with sep('+MAG+') {'+control+READ+'}}')
    material = result.state.artifacts['material_state']
    assert all(not r['valid'] for r in material['contents_states'].values())
    assert replay_events(result.events).artifacts['material_state'] == material


@pytest.mark.parametrize('program,extra,index', [
    ('centrifuge_program(drive=1000g)', '', 0),
    ('magnetic_program(duration=1min)', '', 1),
    ('filtration_program(membrane="filter",drive="pressure")', '', 0),
    ('centrifugal_filtration_program(membrane="filter",drive=1000g)', '', 0),
    ('phase_partition_program(solvent="solvent")', ',component_fates={B:{target_phase:100%,other_phase:0%}}', 0),
    ('precipitation_program(reagent="reagent")', ',component_fates={B:{precipitate:0%,supernatant:100%}}', 1),
    ('field_program(voltage=100V)', ',component_fates={B:{target_band_fraction:100%,non_target_fraction:0%}}', 0),
])
def test_separation_programs_share_context_contract(program, extra, index):
    _, result = execute('with sep(sample=s,program='+program+extra+') {w << [s.contents['+str(index)+']:10uL];}')
    assert result.ok, result.diagnostics
    assert all(not r['valid'] for r in result.state.artifacts['material_state']['contents_states'].values())


@pytest.mark.parametrize('scoped', [False, True])
@pytest.mark.parametrize('body', ['w << [s:10uL];', 'w << [s.contents[0]:10uL];'])
def test_disrupt_preserves_existing_processed_material_access(scoped, body):
    declarations = SAMPLE.replace('buffer(code="B",type="buffer")', 'content(kind=bio_cellular,type=cell_population,code="C")')
    action = 'sep(sample=s,program=disrupt_program(duration=1min))'
    source = 'with ' + action + ' {' + body + '}' if scoped else action + ';' + body
    _, result = execute(source, declarations)
    assert result.ok, result.diagnostics
    material = result.state.artifacts['material_state']
    assert _container_by_label(material['containers'], 'waste')['volume_uL'] == 10
    if 'contents[0]' in body:
        assert next(iter(material['contents_states'].values()))['valid'] is not scoped
    assert replay_events(result.events).artifacts['material_state'] == material


def test_disrupt_indexed_access_ends_with_separation_context():
    declarations = SAMPLE.replace('buffer(code="B",type="buffer")', 'content(kind=bio_cellular,type=cell_population,code="C")')
    _, result = execute('with sep(sample=s,program=disrupt_program(duration=1min)) {}w << [s.contents[0]:10uL];', declarations)
    assert not result.ok
    assert any(d.code == 'MAT_CONTENTS_STATE_NOT_INDEXED' for d in result.diagnostics)


def test_centrifuge_context_accepts_existing_env_time_boundary():
    _, result = execute('with env(thermal=4C,duration=2min) {with sep(sample=s,program=centrifuge_program(drive=1000g)) {w << [s.contents[0]:10uL];}}')
    assert result.ok, result.diagnostics


def test_plain_env_and_standalone_sep_keep_existing_behavior():
    _, result = execute('with env(thermal=4C) {sep(sample=s,program=centrifuge_program(drive=1000g));}w << [s.contents[0]:10uL];')
    assert result.ok, result.diagnostics


@pytest.mark.parametrize('magnetic_env', [True, False])
def test_refreshed_magnetic_view_requires_actual_field_provider(magnetic_env):
    body = 'sep(sample=s,program=magnetic_program(duration=1min));' + READ
    if magnetic_env:
        body = 'with env(field=magnetic_rack) {' + body + '}'
    _, result = execute('with sep(sample=s,program=centrifuge_program(drive=1000g)) {' + body + '}')
    assert result.ok is magnetic_env, result.diagnostics
    if magnetic_env:
        material = result.state.artifacts['material_state']
        assert next(iter(material['contents_states'].values()))['invalid_reason'] == 'separation_scope_ended'
        assert replay_events(result.events).artifacts['material_state'] == material
    else:
        assert any(d.code == 'MAT_CONTENTS_STATE_PRESERVATION_NOT_SATISFIED' for d in result.diagnostics)


@pytest.mark.parametrize('inner,ok', [
    ('with sep(sample=w,program=centrifuge_program(drive=1000g)) {}', True),
    ('with sep(sample=s,program=centrifuge_program(drive=1000g)) {}', False),
    ('sep(sample=s,program=magnetic_program(duration=1min));', True),
])
def test_nested_contexts_and_replacement_respect_source_ownership(inner, ok):
    _, result = execute('with sep(' + MAG + ') {' + READ + inner + READ + '}')
    assert result.ok is ok, result.diagnostics
    material = result.state.artifacts['material_state']
    assert all(not r['valid'] for r in material['contents_states'].values())
    assert replay_events(result.events).artifacts['material_state'] == material
    if not ok:
        assert any(d.code == 'MAT_CONTENTS_STATE_NOT_INDEXED' for d in result.diagnostics)
