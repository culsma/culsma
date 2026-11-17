"""The core owns commits and reports even when an external package owns devices."""
from contextlib import contextmanager
from pathlib import Path
import pytest
from culsma.cli import execute_pipeline
from culsma.driver.base import DriverCapabilityResult, DriverResult


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'input.culs'
    path.write_text('let sample = well(label="sample", capacity=2mL);')
    return path


def test_factory_receives_plan_state_and_closes(source):
    calls = []

    @contextmanager
    def factory(plan, state):
        assert plan.plans[0].steps[0].op == 'AllocContainer'
        assert state.artifacts['material_state']['containers'] == {}

        class Driver:
            def check(self, step):
                return DriverCapabilityResult(True, 'OK')

            def execute(self, step):
                assert not state.artifacts['material_state']['containers']
                calls.append(step.step_id)
                return DriverResult(True, 'CUSTOM')

        try:
            yield Driver()
        finally:
            calls.append('closed')

    result = execute_pipeline([source], driver_factory=factory)
    assert result['summary']['runtime_ok']
    assert calls == ['entry.s0::alloc', 'closed']
    assert len(result['run']['state']['artifacts']['material_state']['containers']) == 1


def test_failed_device_does_not_commit_material(source):
    @contextmanager
    def factory(plan, state):
        class Driver:
            def check(self, step):
                return DriverCapabilityResult(True, 'OK')

            def execute(self, step):
                return DriverResult(False, 'DEVICE_UNKNOWN', {'message': 'device did not confirm', 'error_severity': 'fatal'})
        yield Driver()

    result = execute_pipeline([source], driver_factory=factory)
    assert not result['summary']['runtime_ok']
    assert result['run']['state']['artifacts']['material_state']['containers'] == {}
    failure = next(e for e in result['run']['events'] if e['kind'] == 'STEP_FAILED')
    assert failure['payload']['driver_payload']['message'] == 'device did not confirm'


def test_stub_fail_option_cannot_leak_into_plugin(source):
    with pytest.raises(ValueError, match='RUN_DRIVER_FAIL_OPS_UNSUPPORTED'):
        execute_pipeline([source], fail_ops={'Mutation'}, driver_factory=lambda *args: None)
