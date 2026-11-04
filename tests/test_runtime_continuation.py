"""Continuation at committed step boundaries, using real serialized artifacts."""

from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.runtime.replay import replay_events
from culsma.runtime.state import RuntimeState, init_state
from culsma.runtime.steps import RuntimeStepDispatcher


class RecordingDriver(StubDriver):
    def __init__(self):
        super().__init__(op_payloads={'img': {'result': {'signal': 12}}})
        self.calls = []

    def execute(self, step):
        self.calls.append(step.step_id)
        return super().execute(step)


def compile_source(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    for result in (validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True),
                   typecheck(compiled.ir, analysis=compiled.analysis)):
        assert result.ok, result.diagnostics
    plan = lower_ir_to_plan(compiled.ir, analysis=compiled.analysis)
    assert not plan.diagnostics, plan.diagnostics
    assert len(plan.plans) == 1
    return plan


PREFIX = '''
let stock=tube(label="Stock",capacity=200uL,load=[
  content(kind=formulation,type=buffer,code="BUFFER"):100uL]);
let target=tube(label="Target",capacity=200uL);
'''


SCENARIOS = {
    'transfer': PREFIX + 'target << [stock:10uL]; target << [stock:20uL]; return target;',
    'local': PREFIX + 'let amount=2uL; amount=amount*3; target << [stock:amount]; return target;',
    'readout': PREFIX + '''let obs=img(sample=stock,quantity=fluorescence);
      if obs.result.signal > 10 { target << [stock:10uL]; }
      else { target << [stock:20uL]; } return target;''',
    'partition': PREFIX + '''let parts=sep(sample=stock,
      program=centrifuge_program(drive=300g),
      component_fates={BUFFER:{pellet:25%,supernatant:75%}});
      target << [parts[0]]; target << [parts[1]:10uL]; return target;''',
}


@pytest.mark.parametrize('scenario', SCENARIOS)
def test_full_state_checkpoint_matches_uninterrupted_execution_at_every_boundary(scenario):
    plan = compile_source(SCENARIOS[scenario])
    complete_driver = RecordingDriver()
    complete = run(plan, complete_driver)
    assert complete.ok, complete.diagnostics
    steps = plan.plans[0].steps
    class CheckpointReached(Exception):
        pass

    dispatch = RuntimeStepDispatcher.dispatch
    for cut in range(1, len(steps) + 1):
        prefix_driver = RecordingDriver()
        state = init_state(plan)
        calls = 0

        def stop_at_boundary(self, step, session):
            nonlocal calls
            result = dispatch(self, step, session)
            calls += 1
            if calls == cut:
                raise CheckpointReached()
            return result

        # Interrupt the actual full plan after dispatch has recorded a terminal
        # step, before finalization; no synthetic prefix return is captured.
        with patch.object(RuntimeStepDispatcher, 'dispatch', stop_at_boundary):
            with pytest.raises(CheckpointReached):
                run(plan, prefix_driver, state=state)
        checkpoint = json.loads(json.dumps(state.to_dict()))
        resumed_driver = RecordingDriver()
        resumed = run(plan, resumed_driver, state=RuntimeState(**deepcopy(checkpoint)))
        assert resumed.ok, (scenario, cut, resumed.diagnostics)
        assert prefix_driver.calls + resumed_driver.calls == complete_driver.calls, (scenario, cut)
        assert resumed.state.step_status == complete.state.step_status
        for key in ('material_state', 'local_bindings', 'data_objects', 'data_bindings', 'protocol_outputs'):
            assert resumed.state.artifacts.get(key, {}) == complete.state.artifacts.get(key, {}), (scenario, cut, key)
        completed_ids = {s for s, status in checkpoint['step_status'].items() if status == 'completed'}
        assert all(e.step_id not in completed_ids for e in resumed.events)
        assert all(m.step_id not in completed_ids for m in resumed.material_accounting.movements)
        # Continuing an already completed saved execution is idempotent.
        again_driver = RecordingDriver()
        again = run(plan, again_driver, state=RuntimeState(**json.loads(json.dumps(resumed.state.to_dict()))))
        assert again.ok and not again_driver.calls and not again.events
        assert not again.material_accounting.movements
        assert again.state.artifacts['material_state'] == complete.state.artifacts['material_state']


@pytest.mark.parametrize('scenario', ['transfer', 'partition'])
def test_material_event_replay_can_continue_without_duplicate_transfers(scenario):
    plan = compile_source(SCENARIOS[scenario])
    driver = RecordingDriver()
    complete = run(plan, driver)
    assert complete.ok, complete.diagnostics
    events = json.loads(json.dumps([e.to_dict() for e in complete.events]))
    for index, event in enumerate(events):
        if event['kind'] != 'STEP_COMPLETED' or 'material_state_snapshot' not in event['payload']:
            continue
        replayed = replay_events(events[:index + 1])
        completed_ids = {s for s, status in replayed.step_status.items() if status == 'completed'}
        resumed_driver = RecordingDriver()
        resumed = run(plan, resumed_driver, state=replayed)
        assert resumed.ok, (event['step_id'], resumed.diagnostics)
        assert resumed_driver.calls == [s for s in driver.calls if s not in completed_ids]
        assert resumed.state.artifacts['material_state'] == complete.state.artifacts['material_state']
        assert all(m.step_id not in completed_ids for m in resumed.material_accounting.movements)


def test_replayed_control_skip_keeps_downstream_dependency_satisfied(capsys):
    plan = compile_source(PREFIX + '''
      let obs=img(sample=stock,quantity=fluorescence);
      if obs.result.signal < 10 { print("hidden"); }
      print("after");
    ''')
    complete = run(plan, RecordingDriver())
    assert complete.ok, complete.diagnostics
    assert capsys.readouterr().out == 'after\n'
    events = json.loads(json.dumps([e.to_dict() for e in complete.events]))
    index = next(i for i, e in enumerate(events) if e['kind'] == 'STEP_SKIPPED')
    resumed = run(plan, RecordingDriver(), state=replay_events(events[:index + 1]))
    assert resumed.ok, resumed.diagnostics
    assert resumed.state.step_status == complete.state.step_status
    assert capsys.readouterr().out == 'after\n'


def test_replay_material_snapshot_is_independent_of_event_input_and_other_replays():
    complete = run(compile_source(PREFIX), RecordingDriver())
    events = json.loads(json.dumps([e.to_dict() for e in complete.events]))
    original = deepcopy(events)
    first, second = replay_events(events), replay_events(events)
    first.artifacts['material_state']['bindings']['new'] = 'caller-owned'
    assert events == original
    assert 'new' not in second.artifacts['material_state']['bindings']


@pytest.mark.parametrize('reason,continues', [
    ('runtime_condition_false', True), ('runtime_continue', True), ('runtime_break', True),
    ('unsatisfied_dependency', False), ('aborted_after_failure', False),
])
def test_replay_preserves_control_skip_vs_failure_skip(reason, continues, capsys):
    plan = PlanProgram(plans=[ProtocolPlan('p', 'P', steps=[
        PlanStep('prior', 'print', {'value': {'kind': 'IRString', 'value': 'prior'}}),
        PlanStep('next', 'print', {'value': {'kind': 'IRString', 'value': 'next'}}, ['prior']),
    ])])
    state = replay_events([{'seq': 1, 'kind': 'STEP_SKIPPED', 'step_id': 'prior', 'payload': {'reason': reason}}])
    result = run(plan, RecordingDriver(), state=state)
    assert result.ok == continues
    assert result.state.step_status['next'] == ('completed' if continues else 'skipped')
    assert capsys.readouterr().out == ('next\n' if continues else '')


@pytest.mark.parametrize('scenario', ['transfer', 'partition'])
def test_inflight_step_is_not_reexecuted_or_reported_as_success(scenario):
    plan = compile_source(SCENARIOS[scenario])
    complete = run(plan, RecordingDriver())
    events = json.loads(json.dumps([e.to_dict() for e in complete.events]))
    last_started = max(i for i, e in enumerate(events) if e['kind'] == 'STEP_STARTED')
    inflight = events[last_started]['step_id']
    state = replay_events(events[:last_started + 1])
    before = deepcopy(state.artifacts['material_state'])
    driver = RecordingDriver()
    result = run(plan, driver, state=state)
    assert not driver.calls
    assert result.state.step_status[inflight] == 'running'
    assert result.state.artifacts['material_state'] == before
    assert not result.ok
    assert result.user_result['execution']['ok'] is False
