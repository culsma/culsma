"""Ordered fraction access shares the scoped separation contract."""
import pytest

from test_separation_scope import execute, SAMPLE
from test_kernel_runtime import _build_plan_from_source, _container_by_label
from culsma.driver.stub import StubDriver
from culsma.runtime.executor import run
from culsma.runtime.replay import replay_events

DENSITY = 'density_gradient_program(axis=density,order=top_to_bottom,bins=3)'
CHROMATOGRAPHY = 'chromatography_program(axis=retention_time,order=early_to_late,bins=3)'
READ = 'w << [s.contents[2]:10uL];'


def scoped(body, program=DENSITY, sample='s'):
    return f'with frac(sample={sample},program={program}) {{' + body + '}'


def material(result):
    state = result.state.artifacts['material_state']
    assert replay_events(result.events).artifacts['material_state'] == state
    return state


@pytest.mark.parametrize('program', [DENSITY, CHROMATOGRAPHY])
def test_fractionation_executes_once_and_preserves_ordered_access(program):
    plan, result = execute(scoped(READ + READ, program))
    assert result.ok, result.diagnostics
    assert [s.op for s in plan.plans[0].steps].count('frac') == 1
    state = material(result)
    assert _container_by_label(state['containers'], 'waste')['volume_uL'] == 20
    record = next(iter(state['contents_states'].values()))
    assert list(record['slot_contract']) == ['0', '1', '2']
    assert record['invalid_reason'] == 'separation_scope_ended'


@pytest.mark.parametrize('suffix', [READ, 'with env(thermal=4C) {' + READ + '}'])
def test_exit_expires_fraction_view_even_in_equivalent_environment(suffix):
    _, result = execute('with env(thermal=4C) {' + scoped(READ) + suffix + '}')
    assert not result.ok
    assert any(d.code == 'MAT_CONTENTS_STATE_NOT_INDEXED' for d in result.diagnostics)
    material(result)


def test_inner_environment_does_not_close_fractionation_context():
    plan, result = execute('with env(thermal=4C,duration=2min) {' + scoped(
        'with env(thermal=4C,duration=1min) {hold(s);}' + READ) + '}')
    assert result.ok, result.diagnostics
    steps = plan.plans[0].steps
    entry = next(s for s in steps if s.op == 'frac')
    transfer = next(s for s in steps if s.op == 'Mutation')
    assert entry.gate['env'] == transfer.gate['env']
    assert entry.gate['env_targets'] == transfer.gate['env_targets']
    material(result)


@pytest.mark.parametrize('loop', ['repeat 2', 'repeat tick in schedule(start=1,end=2,step=1)'])
def test_fractionation_scopes_compose_with_static_and_runtime_loops(loop):
    for body in [scoped(loop + ' {' + READ + '}'), loop + ' {' + scoped(READ) + '}']:
        _, result = execute(body)
        assert result.ok, result.diagnostics
        assert _container_by_label(material(result)['containers'], 'waste')['volume_uL'] == 20


def test_schedule_substitution_preserves_fractionation_operator():
    _, result = execute('repeat bins in schedule(start=2,end=3,step=1) {' + scoped(
        'w << [s.contents[0]:10uL];', DENSITY.replace('bins=3', 'bins=bins')) + '}')
    assert result.ok, result.diagnostics
    assert _container_by_label(material(result)['containers'], 'waste')['volume_uL'] == 20


@pytest.mark.parametrize('control', ['break;', 'continue;', 'w << [s.contents[99]];'])
def test_early_exit_closes_fraction_access_and_replays(control):
    _, result = execute('repeat 2 {' + scoped(control + READ) + '}')
    assert all(not r['valid'] for r in material(result)['contents_states'].values())


@pytest.mark.parametrize('inner,ok', [
    ('with sep(sample=w,program=centrifuge_program(drive=1000g)) {}', True),
    ('with sep(sample=s,program=centrifuge_program(drive=1000g)) {}', False),
    (scoped('', sample='s'), False),
    ('frac(sample=s,program=' + DENSITY + ');', True),
])
def test_nested_contexts_share_source_ownership(inner, ok):
    _, result = execute(scoped(READ + inner + READ))
    assert result.ok is ok, result.diagnostics
    assert all(not r['valid'] for r in material(result)['contents_states'].values())
    if not ok:
        assert any(d.code == 'MAT_CONTENTS_STATE_NOT_INDEXED' for d in result.diagnostics)


def test_fraction_scope_does_not_supply_magnetic_retention():
    _, result = execute(scoped('sep(sample=s,program=magnetic_program(duration=1min));w << [s.contents[1]:10uL];'))
    assert not result.ok
    assert any(d.code == 'MAT_CONTENTS_STATE_PRESERVATION_NOT_SATISFIED' for d in result.diagnostics)


def test_agitation_invalidates_fraction_view_inside_block():
    _, result = execute(scoped('agit(sample=s,mode=AgitationMode.VORTEX,duration=1s);' + READ))
    assert not result.ok
    assert any(d.code == 'MAT_CONTENTS_STATE_NOT_INDEXED' for d in result.diagnostics)


def test_protocol_expansion_and_program_alias_preserve_fractionation():
    source = '''protocol Collect(sample, output) {
      let p = density_gradient_program(axis=density,order=top_to_bottom,bins=3);
      with frac(sample=sample,program=p) {output << [sample.contents[2]:10uL];}
    }
    ''' + SAMPLE + 'Collect(sample=s,output=w);Collect(sample=s,output=w);'
    plan = _build_plan_from_source(source)
    result = run(plan, StubDriver())
    assert result.ok, result.diagnostics
    assert _container_by_label(material(result)['containers'], 'waste')['volume_uL'] == 20


def test_scoped_fractionation_rejects_separation_program_family():
    with pytest.raises(AssertionError):
        execute(scoped('', 'centrifuge_program(drive=1000g)'))


def test_invalid_bin_count_keeps_standalone_diagnostics():
    program = DENSITY.replace('bins=3', 'bins=0')
    _, legacy = execute('frac(sample=s,program=' + program + ');')
    _, result = execute(scoped('', program))
    assert not result.ok
    assert [d.code for d in result.diagnostics] == [d.code for d in legacy.diagnostics]


@pytest.mark.parametrize('program', [DENSITY, CHROMATOGRAPHY])
def test_legacy_standalone_and_group_fractionation_remain_available(program):
    for body in [
        'with env(thermal=4C) {frac(sample=s,program=' + program + ');}' + READ,
        'let g=frac(sample=s,program=' + program + ');w << [g[2]:10uL];',
    ]:
        _, result = execute(body)
        assert result.ok, result.diagnostics
        assert _container_by_label(material(result)['containers'], 'waste')['volume_uL'] == 10


def test_fractionation_suspension_preserves_access_until_body_finishes():
    from culsma.runtime.state import init_state

    class AwaitingDevice(Exception):
        pass

    class SuspendCollection(StubDriver):
        def execute(self, step):
            if step.op == 'Mutation':
                raise AwaitingDevice()
            return super().execute(step)

    plan = _build_plan_from_source('protocol T {' + SAMPLE + scoped(READ) + '}')
    state = init_state(plan)
    with pytest.raises(AwaitingDevice):
        run(plan, SuspendCollection(), state)
    record = next(iter(state.artifacts['material_state']['contents_states'].values()))
    assert record['valid']
    assert _container_by_label(state.artifacts['material_state']['containers'], 'waste')['volume_uL'] == 0


def test_collected_containers_remain_usable_after_fraction_scope_exit():
    _, result = execute(scoped(READ) + 's << [w:5uL];')
    assert result.ok, result.diagnostics
    assert _container_by_label(material(result)['containers'], 'waste')['volume_uL'] == 5
