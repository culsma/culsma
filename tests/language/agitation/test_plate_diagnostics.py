"""Plate diagnostics classify failures independently of the agitation method."""

from copy import deepcopy

import pytest

from culsma.common.source import Span
from culsma.domains.labware import PlateReference
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan.external_parameters import normalize_external_plan
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.runtime.material.compute import MaterialCompute
from culsma.runtime.state import init_state


class RecordingDriver(StubDriver):
    def __init__(self):
        super().__init__()
        self.actions = []

    def execute(self, step):
        self.actions.append(step)
        return super().execute(step)


def plan_source(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    assert semantic.ok, semantic.diagnostics
    plan = lower_ir_to_plan(compiled.ir)
    assert not plan.diagnostics, plan.diagnostics
    return plan


def plan_step(operation, args):
    return PlanProgram(plans=[ProtocolPlan('entry', 'T', steps=[
        PlanStep('action', operation, args, span=Span(1, 1, 0, 10)),
    ])])


@pytest.mark.parametrize('source', [
    'agit(sample=plate(format="96well"),mode=tap);',
    'let p=plate(format="96well"); agit(sample=p,mode=tap,drive=3000g);',
    'let s=tube(); agit(sample=s,mode=flick,duration=1s);',
    'let s=tube(); agit(sample=s,mode=tap,duration=1s);',
])
def test_source_target_and_parameter_conflicts_share_agitation_code(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    assert not semantic.ok
    assert {d.code for d in semantic.diagnostics} == {'SEM_AGIT_ARG_CONFLICT'}
    assert all(d.span is not None and d.node_id is not None for d in semantic.diagnostics)


def test_deferred_target_conflict_uses_existing_runtime_contract_code_before_dispatch():
    plan = plan_source('''protocol T(flag=true) {
      let method="shake";
      if flag {method="tap";}
      agit(sample=plate(format="96well"),mode=method);
    }''')
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert not result.ok
    conflict, = [d for d in result.diagnostics if d.code == 'RT_EXTERNAL_ENUM_INVALID']
    assert conflict.span is not None and conflict.node_id is not None
    assert 'bound allocated plate reference' in conflict.message
    assert not driver.actions


@pytest.mark.parametrize('args', [
    {'mode': 'shake', 'sample': PlateReference('p', 'P', 8, 12).to_dict()},
    {'mode': 'tap', 'duration': {'kind': 'IRQuantity', 'value': 1, 'unit': 's'}},
])
def test_plan_contract_conflicts_keep_existing_diagnostic(args):
    plan = normalize_external_plan(plan_step('agit', args))
    assert not plan.plans
    assert [d.code for d in plan.diagnostics] == ['PLAN_EXTERNAL_ENUM_INVALID']


@pytest.mark.parametrize('sample', [
    {'kind': 'IRIdentifier', 'name': 'missing'},
    PlateReference('missing', 'P', 8, 12).to_dict(),
])
def test_absent_carrier_and_container_use_binding_not_found(sample):
    plan = plan_step('agit', {'mode': 'tap', 'sample': sample})
    state = init_state(plan)
    state.artifacts['material_state'] = {'containers': {}}
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver, state=state)
    assert not result.ok
    assert 'MAT_BINDING_NOT_FOUND' in [d.code for d in result.diagnostics]
    assert 'MAT_PLATE_REF_INVALID' not in [d.code for d in result.diagnostics]
    assert not driver.actions


@pytest.mark.parametrize('operation', ['AllocContainer', 'agit'])
@pytest.mark.parametrize('case,code', [
    ('missing', 'MAT_BINDING_NOT_FOUND'),
    ('malformed', 'MAT_PLATE_REF_INVALID'),
    ('inconsistent', 'MAT_PLATE_REF_INVALID'),
])
def test_allocation_and_agitation_share_reference_diagnostic_categories(operation, case, code):
    reference = PlateReference('p', 'P', 8, 12).to_dict()
    payload = dict(reference)
    if case == 'missing':
        payload['id'] = 'missing'
    elif case == 'malformed':
        payload['rows'] = 0
    else:
        payload['label'] = 'Conflicting metadata'
    state = {'containers': {}, 'plates': {'p': reference}}
    before = deepcopy(state)
    args = ({'mode': 'tap', 'sample': payload} if operation == 'agit' else {
        'kind': 'well', 'plate_ref': payload, 'carrier_position': 'A1',
        'container_namespace': 'entry', 'container_name': 'w',
    })
    span = Span(2, 1, 11, 20)
    result = MaterialCompute().apply_step(
        step=PlanStep('action', operation, args, span=span), material_state=state,
    )
    assert not result.ok
    diagnostic, = result.diagnostics
    assert (diagnostic.code, diagnostic.span, diagnostic.node_id) == (code, span, 'action')
    assert state == before


@pytest.mark.parametrize('definition,code', [
    ({'target': None, 'value': {'kind': 'PlateDefinition', 'carrier_id': 'P', 'rows': 8, 'cols': 12}},
     'RT_LOCAL_ASSIGN_INVALID_TARGET'),
    ({'target': None, 'value': {'kind': 'IRString', 'value': 'X'}}, 'RT_LOCAL_ASSIGN_INVALID_TARGET'),
    ({'target': 'p', 'value': {'kind': 'PlateDefinition', 'carrier_id': 'P', 'rows': 0, 'cols': 12}},
     'RT_LOCAL_ASSIGN_UNRESOLVED'),
    ({'target': 'p', 'value': {'kind': 'IRIdentifier', 'name': 'missing'}}, 'RT_LOCAL_ASSIGN_UNRESOLVED'),
])
def test_plate_and_other_local_declarations_share_assignment_diagnostics(definition, code):
    driver = RecordingDriver()
    result = run(plan=plan_step('assign_local', definition), driver=driver)
    assert not result.ok
    assert code in [d.code for d in result.diagnostics]
    assert not result.state.artifacts.get('material_state', {}).get('plates')
    assert not driver.actions
