"""Optional native group driver boundary conformance, without a device."""
from dataclasses import replace
import pytest
from culsma.driver.stub import StubDriver
from culsma.driver.base import DriverResult
from culsma.driver.groups import GroupDriverResult
from culsma.runtime.executor import run
from culsma.runtime.state import init_state
from test_group_execution import compile_program, PREFIX


class NativeTestDriver(StubDriver):
    supports_group_execution = True

    def __init__(self, state=None, invalid=False):
        super().__init__()
        self.groups = []
        self.state = state
        self.invalid = invalid
        self.formal_volumes_at_handoff = []

    def execute(self, step):
        assert step.op != 'Mutation', 'Native path must not call the external scalar execute'
        return super().execute(step)

    def execute_group(self, group):
        self.groups.append(group)
        if self.state is not None:
            containers=self.state.artifacts['material_state']['containers'].values()
            self.formal_volumes_at_handoff.append(next(c['volume_uL'] for c in containers if c['metadata'].get('label')=='Stock'))
        identities=tuple(m.driver_step.step_id for m in group.members)
        results=tuple(DriverResult(True,'DRV_OK',{'step_id':identity,'op':'Mutation'}) for identity in identities)
        return GroupDriverResult(identities[:-1] if self.invalid else identities, results)


def test_runtime_hands_group_once_without_scalar_external_calls():
    _,plan=compile_program(PREFIX+'assay[A1:H1] << [stock:20uL];')
    state=init_state(plan);driver=NativeTestDriver(state)
    result=run(plan,driver,state)
    assert result.ok, result.diagnostics
    assert len(driver.groups)==1 and len(driver.groups[0].members)==8
    assert driver.formal_volumes_at_handoff==[1000]
    assert driver.groups[0].members[-1].material_result.material_state!=driver.groups[0].members[0].before_material_state


def test_native_and_scalar_semantics_match():
    _,plan=compile_program(PREFIX+'assay[A1:H1] << [stock:20uL];')
    native=run(plan,NativeTestDriver())
    scalar=run(plan,StubDriver())
    assert native.ok and scalar.ok
    assert native.state.to_dict()==scalar.state.to_dict()
    assert native.events==scalar.events
    assert native.material_accounting==scalar.material_accounting


def test_preparation_error_preserves_scalar_prefix():
    _,plan=compile_program(PREFIX+'assay[A1:A3] << [series(stock,[20uL,300uL,10uL])];')
    driver=NativeTestDriver()
    native=run(plan,driver);scalar=run(plan,StubDriver())
    assert not native.ok and native.state.to_dict()==scalar.state.to_dict()
    assert [d.code for d in native.diagnostics]==[d.code for d in scalar.diagnostics]
    assert len(driver.groups)==1 and len(driver.groups[0].members)==1
    assert len(driver.groups[0].source_member_ids)==3


def test_invalid_results_never_commit_formal_state():
    _,plan=compile_program(PREFIX+'assay[A1:A2] << [stock:20uL];')
    driver=NativeTestDriver(invalid=True)
    result=run(plan,driver)
    assert not result.ok and any(d.code=='RT_GROUP_RESULT_INVALID' for d in result.diagnostics)
    assert next(c['volume_uL'] for c in result.state.artifacts['material_state']['containers'].values() if c['metadata'].get('label')=='Stock')==1000


def test_native_protocol_loop_and_constraints_share_reference_semantics():
    source=f'protocol Dose(stock,wells) {{ wells << [stock:20uL] with constraint(gentle); }} {PREFIX} let wells=assay[A1:A2]; repeat 2 {{ Dose(stock=stock,wells=wells); }}'
    _,plan=compile_program(source)
    driver=NativeTestDriver()
    native=run(plan,driver);scalar=run(plan,StubDriver())
    assert native.ok and scalar.ok
    assert native.state.to_dict()==scalar.state.to_dict()
    assert native.events==scalar.events
    assert len(driver.groups)==2
