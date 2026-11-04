"""Failed material steps must not publish their staged effects.

A scalar Mutation can stage several sources before a later source fails. That
staged prefix is distinct from completed scalar members of a MutationGroup.
"""

from copy import deepcopy
import json

import pytest

from culsma.driver.base import DriverCapabilityResult
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, PlanStepTree, ProtocolPlan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.runtime.material.compute import MaterialCompute
from culsma.runtime.replay import replay_events
from culsma.runtime.state import init_state


BUFFER = 'content(kind=formulation,type=buffer,code="BUFFER")'
PREFIX = f'''
let a=tube(label="A",capacity=100uL,load=[{BUFFER}:50uL]);
let b=tube(label="B",capacity=100uL,load=[{BUFFER}:10uL]);
let target=tube(label="Target",capacity=30uL,load=[{BUFFER}:5uL]);
let sink=tube(label="Sink",capacity=100uL);
'''


def compile_source(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    for result in (validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True),
                   typecheck(compiled.ir, analysis=compiled.analysis)):
        assert result.ok, [d.to_dict() for d in result.diagnostics]
    plan = lower_ir_to_plan(compiled.ir, analysis=compiled.analysis)
    assert not plan.diagnostics, [d.to_dict() for d in plan.diagnostics]
    return plan


def ident(name):
    return {'kind': 'IRIdentifier', 'name': name}


def aliquot(name, value):
    return {'kind': 'IRPair', 'left': ident(name),
            'right': {'kind': 'IRQuantity', 'value': value, 'unit': 'uL'}}


def mutation(step_id, sources, *, target='target', deps=()):
    return PlanStep(step_id, 'Mutation', {'target': ident(target), 'sources': sources}, list(deps))


def plan_for(*steps):
    return PlanProgram(plans=[ProtocolPlan('failure-tests', 'FailureTests', steps=list(steps))])


def independent_step():
    return PlanStep('independent', 'print', {'value': {'kind': 'IRString', 'value': 'continued'}})


class RecordingDriver(StubDriver):
    def __init__(self, *, reject=False, reject_step_id='failure', **kwargs):
        super().__init__(**kwargs)
        self.reject = reject
        self.reject_step_id = reject_step_id
        self.checked = []
        self.executed = []

    def check(self, step):
        self.checked.append(step.step_id)
        if self.reject and step.step_id == self.reject_step_id:
            return DriverCapabilityResult(ok=False, code='TEST_UNSUPPORTED')
        return super().check(step)

    def execute(self, step):
        self.executed.append(step.step_id)
        return super().execute(step)


@pytest.fixture
def material_state():
    result = run(compile_source(PREFIX), StubDriver())
    assert result.ok, result.diagnostics
    return result.state.artifacts['material_state']


FAILURES = [
    ('shortage', aliquot('b', 20), 'MAT_INSUFFICIENT_VOLUME'),
    ('overflow', aliquot('a', 30), 'MAT_CONTAINER_OVERFLOW'),
    ('missing-source', aliquot('missing', 1), 'MAT_BINDING_NOT_FOUND'),
]


@pytest.mark.parametrize('failure_name,source,code', FAILURES, ids=[f[0] for f in FAILURES])
@pytest.mark.parametrize('ordinal', [0, 1, 2])
@pytest.mark.parametrize('on_error', ['abort', 'continue'])
def test_rejected_source_does_not_commit_any_of_the_scalar_step(
    material_state, failure_name, source, code, ordinal, on_error, capsys,
):
    failure = mutation('failure', [aliquot('a', 1)] * ordinal + [source])
    dependent = mutation('dependent', [aliquot('a', 1)], target='sink', deps=['failure'])
    independent = independent_step()
    plan = plan_for(failure, dependent, independent)
    state = init_state(plan)
    state.artifacts['material_state'] = deepcopy(material_state)
    state.artifacts['local_bindings']['config'] = {'amount': 1}
    before = deepcopy(state.artifacts)
    driver = RecordingDriver()

    # MaterialCompute is a preview API: even a failed multi-source preview must
    # leave its caller's input untouched, including aliases and detailed entries.
    preview = MaterialCompute().apply_step(failure, material_state)
    assert not preview.ok
    assert code in {d.code for d in preview.diagnostics}
    assert material_state == before['material_state']

    result = run(plan, driver, state=state, on_error=on_error)
    assert not result.ok
    assert {code, 'RT_MATERIAL_ERROR'} <= {d.code for d in result.diagnostics}
    assert result.state.artifacts['material_state'] == before['material_state']
    assert result.state.artifacts['local_bindings'] == before['local_bindings']
    assert result.material_accounting.movements == []
    assert result.material_accounting.consumed_allocations == {}
    assert result.state.step_status == {
        'failure': 'failed', 'dependent': 'skipped',
        'independent': 'skipped' if on_error == 'abort' else 'completed',
    }
    assert driver.checked == driver.executed == []
    assert capsys.readouterr().out == ('' if on_error == 'abort' else 'continued\n')
    terminal = [e for e in result.events if e.step_id == 'failure' and e.kind != 'STEP_STARTED']
    assert [e.kind for e in terminal] == ['STEP_FAILED']
    assert terminal[0].payload['reason'] == 'material_compute_error'
    assert 'material_state_snapshot' not in terminal[0].payload
    assert not any(e.kind == 'BINDING_OVERWRITTEN' for e in result.events)


@pytest.mark.parametrize('stage,reason,diagnostic', [
    ('capability', 'driver_requirement_unsupported', 'RT_DRIVER_REQUIREMENT_UNSUPPORTED'),
    ('driver-fatal', 'driver_error', 'RT_DRIVER_ERROR'),
    ('driver-nonfatal', 'driver_error', 'RT_DRIVER_ERROR'),
])
@pytest.mark.parametrize('on_error', ['abort', 'continue'])
def test_successful_preflight_is_discarded_when_driver_rejects(
    material_state, stage, reason, diagnostic, on_error, capsys,
):
    failure = mutation('failure', [aliquot('a', 2), aliquot('b', 3)])
    independent = independent_step()
    plan = plan_for(failure, independent)
    state = init_state(plan)
    state.artifacts['material_state'] = deepcopy(material_state)
    before = deepcopy(material_state)
    driver = RecordingDriver(
        reject=stage == 'capability',
        fail_ops={'Mutation'} if stage == 'driver-fatal' else set(),
        non_fatal_fail_ops={'Mutation'} if stage == 'driver-nonfatal' else set(),
    )
    preview = MaterialCompute().apply_step(failure, material_state)
    assert preview.ok, preview.diagnostics
    assert preview.material_state != before

    result = run(plan, driver, state=state, on_error=on_error)
    assert not result.ok
    assert diagnostic in {d.code for d in result.diagnostics}
    assert result.state.artifacts['material_state'] == before
    assert result.material_accounting.movements == []
    assert result.material_accounting.consumed_allocations == {}
    independent_runs = on_error == 'continue' or stage == 'driver-nonfatal'
    assert result.state.step_status['independent'] == ('completed' if independent_runs else 'skipped')
    assert capsys.readouterr().out == ('continued\n' if independent_runs else '')
    assert ('failure' in driver.executed) == (stage != 'capability')
    failed = next(e for e in result.events if e.step_id == 'failure' and e.kind == 'STEP_FAILED')
    assert failed.payload['reason'] == reason
    assert not any(e.step_id == 'failure' and e.kind == 'STEP_COMPLETED' for e in result.events)


@pytest.mark.parametrize('sources,code', [
    ('a:1uL,b:20uL', 'MAT_INSUFFICIENT_VOLUME'),
    ('a:1uL,a:30uL', 'MAT_CONTAINER_OVERFLOW'),
])
@pytest.mark.parametrize('on_error', ['abort', 'continue'])
def test_source_failure_events_replay_only_committed_material(sources, code, on_error):
    # The successful statement is committed; the next statement's staged first
    # source must not leak into state, accounting, or the saved event snapshots.
    prefix = PREFIX + 'sink << [a:2uL];'
    expected = run(compile_source(prefix), StubDriver())
    result = run(compile_source(prefix + f'target << [{sources}];'), StubDriver(), on_error=on_error)
    assert expected.ok and not result.ok
    assert code in {d.code for d in result.diagnostics}
    assert result.state.artifacts['material_state'] == expected.state.artifacts['material_state']
    assert result.material_accounting == expected.material_accounting
    replayed = replay_events(json.loads(json.dumps([e.to_dict() for e in result.events])))
    assert replayed.step_status == result.state.step_status
    assert replayed.artifacts['material_state'] == result.state.artifacts['material_state']


@pytest.mark.parametrize('stage', ['capability', 'driver-fatal', 'driver-nonfatal'])
def test_failed_separation_does_not_publish_output_bindings_or_partition_state(stage):
    source = PREFIX + '''
      let parts=sep(sample=a,
        program=centrifuge_program(drive=300g,keep_source=supernatant),
        component_fates={BUFFER:{pellet:0%,supernatant:100%}});
    '''
    plan = compile_source(source)
    separation = next(s for p in plan.plans for s in p.steps if s.op == 'sep')
    expected = run(compile_source(PREFIX), StubDriver())
    successful = run(plan, StubDriver())
    assert expected.ok and successful.ok
    before = expected.state.artifacts['material_state']
    committed = successful.state.artifacts['material_state']
    assert committed != before
    assert 'parts' in committed['indexed_bindings']

    driver = RecordingDriver(
        reject=stage == 'capability', reject_step_id=separation.step_id,
        fail_ops={'sep'} if stage == 'driver-fatal' else set(),
        non_fatal_fail_ops={'sep'} if stage == 'driver-nonfatal' else set(),
    )
    result = run(plan, driver)
    assert not result.ok
    assert result.state.artifacts['material_state'] == before
    assert result.material_accounting == expected.material_accounting
    assert result.state.step_status[separation.step_id] == 'failed'
    assert (separation.step_id in driver.executed) == (stage != 'capability')
    assert not any(e.kind == 'BINDING_OVERWRITTEN' for e in result.events)
    assert not any(e.kind == 'STEP_COMPLETED' and e.step_id == separation.step_id for e in result.events)
    replayed = replay_events(json.loads(json.dumps([e.to_dict() for e in result.events])))
    assert replayed.artifacts['material_state'] == before


@pytest.mark.parametrize('on_error', ['abort', 'continue'])
def test_group_failure_retains_successful_members_without_leaking_failed_preview(on_error):
    prefix = f'let stock=tube(label="Stock",capacity=100uL,load=[{BUFFER}:50uL]);' \
             'let assay=plate(label="Assay",format="96well",capacity=20uL);'
    plan = compile_source(prefix + 'assay[A1:A3] << [series(stock,[5uL,30uL,5uL])];')
    result = run(plan, RecordingDriver(), on_error=on_error)
    assert not result.ok
    group = next(s for p in plan.plans for s in p.steps if s.op == 'MutationGroup')
    first, failed, last = PlanStepTree.children(group)
    assert [result.state.step_status[s.step_id] for s in (first, failed, last)] == [
        'completed', 'failed', 'skipped',
    ]
    containers = result.state.artifacts['material_state']['containers']
    stock = next(c for c in containers.values() if c['metadata'].get('label') == 'Stock')
    assert stock['volume_uL'] == pytest.approx(45)
    assert sum(c['volume_uL'] for c in containers.values()) == pytest.approx(50)
    assert [m.step_id for m in result.material_accounting.movements] == [first.step_id]
    replayed = replay_events(json.loads(json.dumps([e.to_dict() for e in result.events])))
    assert replayed.step_status == result.state.step_status
    assert replayed.artifacts['material_state'] == result.state.artifacts['material_state']
