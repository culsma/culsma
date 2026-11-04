"""Failure and skip events reconstruct the same statuses after JSON storage."""

import json

import pytest

from culsma.driver.stub import StubDriver
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.runtime.event_log import RuntimeEvent
from culsma.runtime.executor import run
from culsma.runtime.replay import replay_events


@pytest.mark.parametrize('serialized', [False, True], ids=['events', 'json'])
def test_replay_retains_failure_reasons_and_last_material_snapshot(serialized):
    before = {'containers': {'sample': {'volume_uL': 10}}}
    after = {'containers': {'sample': {'volume_uL': 5}}}
    events = [
        RuntimeEvent(1, 'STEP_STARTED', 'load'),
        RuntimeEvent(2, 'STEP_COMPLETED', 'load', {'driver_code': 'DRV_OK', 'material_state_snapshot': before}),
        RuntimeEvent(3, 'STEP_STARTED', 'transfer'),
        RuntimeEvent(4, 'STEP_COMPLETED', 'transfer', {'material_state_snapshot': after}),
        RuntimeEvent(5, 'STEP_COMPLETED', 'print', {}),
        RuntimeEvent(6, 'STEP_FAILED', 'read', {'driver_code': 'DRV_FAILED', 'reason': 'driver_failure'}),
        RuntimeEvent(7, 'STEP_FAILED', 'dependent', {'reason': 'unsatisfied_dependency'}),
        RuntimeEvent(8, 'STEP_SKIPPED', 'branch', {'reason': 'runtime_condition_false'}),
        RuntimeEvent(9, 'REF_DECISION', 'cached', {'ref_decision': 'rerun'}),
    ]
    raw = json.loads(json.dumps([event.to_dict() for event in events])) if serialized else events
    state = replay_events(raw)
    assert state.step_status == {
        'load': 'completed', 'transfer': 'completed', 'print': 'completed',
        'read': 'failed', 'dependent': 'skipped', 'branch': 'skipped',
    }
    assert state.artifacts['material_state'] == after
    assert state.history[-3:] == [
        {'step_id': 'read', 'status': 'failed', 'driver_code': 'DRV_FAILED', 'reason': 'driver_failure'},
        {'step_id': 'dependent', 'status': 'skipped', 'driver_code': None, 'reason': 'unsatisfied_dependency'},
        {'step_id': 'branch', 'status': 'skipped', 'reason': 'runtime_condition_false'},
    ]


@pytest.mark.parametrize('on_error', ['abort', 'continue'])
def test_replay_matches_real_driver_failure_and_dependency_skips(on_error):
    plan = PlanProgram(plans=[ProtocolPlan('p', 'P', steps=[
        PlanStep('first', 'img', {'quantity': 'fluorescence'}),
        PlanStep('dependent', 'phy', {'quantity': 'temperature'}, ['first']),
        PlanStep('independent', 'phy', {'quantity': 'temperature'}),
    ])])
    result = run(plan, StubDriver(fail_ops={'img'}), on_error=on_error)
    assert not result.ok
    events = json.loads(json.dumps([event.to_dict() for event in result.events]))
    replayed = replay_events(events)
    assert replayed.step_status == result.state.step_status
    assert replayed.step_status['first'] == 'failed'
    assert replayed.step_status['dependent'] == 'skipped'
    assert replayed.step_status['independent'] == ('skipped' if on_error == 'abort' else 'completed')


def test_empty_replay_returns_independent_states():
    first = replay_events([])
    first.step_status['old'] = 'failed'
    first.artifacts['material_state'] = {'containers': {}}
    second = replay_events([])
    assert second.step_status == {}
    assert second.history == []
    assert second.artifacts == {}
