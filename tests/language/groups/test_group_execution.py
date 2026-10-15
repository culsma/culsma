"""GROUP-EXEC conformance: compiler keeps groups, runtime interprets members."""
from dataclasses import replace
import json
import time

import pytest

from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.ir_nodes import IRMutation, IRMutationGroup
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan.serialization import PlanExpressionSerializer
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, PlanStepTree
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run


BUFFER = 'content(kind=formulation,type=buffer,code="BUFFER")'
PREFIX = f'let stock=tube(label="Stock",capacity=2000uL,load=[{BUFFER}:1000uL]); let assay=plate(label="Assay",format="96well",capacity=200uL);'


def compile_program(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    for result in (validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True), typecheck(compiled.ir, analysis=compiled.analysis)):
        assert result.ok, [d.to_dict() for d in result.diagnostics]
    plan = lower_ir_to_plan(compiled.ir)
    assert not plan.diagnostics, [d.to_dict() for d in plan.diagnostics]
    return compiled.ir, plan


def scalar_reference(plan):
    serializer = PlanExpressionSerializer()
    return replace(plan, plans=[replace(p, steps=serializer.linearize_steps(PlanStepTree.leaves(p.steps))) for p in plan.plans])


def quantities(result):
    return {v['metadata']['label']: v.get('total_volume_uL') for v in result.state.artifacts['material_state']['containers'].values()}


def test_group_is_one_ir_and_plan_operation():
    ir, plan = compile_program(PREFIX + 'assay[A1:H1] << [stock:20uL];')
    groups = [s for s in ir.script_entry.statements if isinstance(s, IRMutationGroup)]
    assert len(groups) == 1 and len(groups[0].members) == 8
    assert not any(isinstance(s, IRMutation) for s in ir.script_entry.statements)
    roots = [s for p in plan.plans for s in p.steps if s.op == 'MutationGroup']
    assert len(roots) == 1 and len(PlanStepTree.children(roots[0])) == 8
    assert not any(s.op == 'Mutation' for p in plan.plans for s in p.steps)
    json.dumps(plan.to_dict())


def test_group_runtime_matches_explicit_scalar_program():
    _, plan = compile_program(PREFIX + 'assay[A1:H1] << [stock:20uL];')
    grouped = run(plan, StubDriver())
    scalar = run(scalar_reference(plan), StubDriver())
    assert grouped.ok and scalar.ok
    assert grouped.state.artifacts['material_state'] == scalar.state.artifacts['material_state']
    assert grouped.material_accounting == scalar.material_accounting
    assert grouped.user_result['process_summary']==scalar.user_result['process_summary']
    assert [d.code for d in grouped.diagnostics] == [d.code for d in scalar.diagnostics]
    assert all(grouped.state.step_status[m.step_id] == 'completed' for p in plan.plans for s in p.steps for m in PlanStepTree.children(s))


def test_series_and_alias_preserve_member_mapping():
    _, plan = compile_program(PREFIX + 'let chosen=assay[A1:A2]; let alias=chosen; alias << [series(stock,[20uL,30uL])];')
    result = run(plan, StubDriver())
    assert result.ok, result.diagnostics
    scalar = run(scalar_reference(plan), StubDriver())
    assert result.state.artifacts['material_state'] == scalar.state.artifacts['material_state']
    group = next(s for p in plan.plans for s in p.steps if s.op == 'MutationGroup')
    assert [m.args['sources'][0]['right']['value'] for m in PlanStepTree.children(group)] == [20,30]


@pytest.mark.parametrize('on_error', ['abort', 'continue'])
def test_member_error_preserves_completed_prefix(on_error):
    _, plan = compile_program(PREFIX + 'assay[A1:A3] << [series(stock,[20uL,300uL,10uL])];')
    grouped = run(plan, StubDriver(), on_error=on_error)
    scalar = run(scalar_reference(plan), StubDriver(), on_error=on_error)
    assert not grouped.ok and not scalar.ok
    assert grouped.state.artifacts['material_state'] == scalar.state.artifacts['material_state']
    group = next(s for p in plan.plans for s in p.steps if s.op == 'MutationGroup')
    members = PlanStepTree.children(group)
    assert grouped.state.step_status[members[0].step_id] == 'completed'
    assert grouped.state.step_status[members[1].step_id] == 'failed'
    assert grouped.state.step_status[members[2].step_id] == 'skipped'
    assert [d.code for d in grouped.diagnostics] == [d.code for d in scalar.diagnostics]


def test_protocol_condition_repeat_and_constraints():
    source = f'protocol Dose(stock,wells) {{ wells << [stock:20uL]; }} {PREFIX} let wells=assay[A1:A2]; repeat 2 {{ if true {{ Dose(stock=stock,wells=wells); }} }}'
    _, plan = compile_program(source)
    result = run(plan, StubDriver())
    scalar = run(scalar_reference(plan), StubDriver())
    assert result.ok, result.diagnostics
    assert result.state.artifacts['material_state'] == scalar.state.artifacts['material_state']
    members = [m.step_id for p in plan.plans for s in p.steps for m in PlanStepTree.children(s)]
    assert len(members) == 4 and len(set(members)) == 4


@pytest.mark.parametrize('selector,size', [('A1:H1',8),('A1:H12',96)])
def test_large_group_retains_one_envelope(selector,size,record_property):
    _, plan = compile_program(PREFIX + f'assay[{selector}] << [stock:5uL];')
    groups = [s for p in plan.plans for s in p.steps if s.op == 'MutationGroup']
    assert len(groups) == 1 and len(PlanStepTree.children(groups[0])) == size
    started = time.perf_counter()
    result = run(plan, StubDriver())
    elapsed = time.perf_counter() - started
    assert result.ok, result.diagnostics
    assert sum(result.state.step_status[m.step_id] == 'completed' for m in PlanStepTree.children(groups[0])) == size
    record_property('group_members',size)
    record_property('runtime_seconds',elapsed)


@pytest.mark.parametrize('members', [[], ['bad'], [PlanStep('same','Mutation'),PlanStep('same','Mutation')]])
def test_malformed_group_plan_is_rejected(members):
    step = PlanStep('group','MutationGroup',{'members':members})
    with pytest.raises(ValueError, match='RT_MUTATION_GROUP_INVALID'):
        PlanStepTree.children(step)


def test_group_member_constraints_are_preserved():
    _, plan = compile_program(PREFIX + 'assay[A1:A2] << [stock:20uL] with constraint(gentle);')
    group=next(s for p in plan.plans for s in p.steps if s.op=='MutationGroup')
    assert all('gentle' in m.gate['constraint']['requirements'] for m in PlanStepTree.children(group))
    assert run(plan,StubDriver()).ok
    rejected=run(plan,StubDriver(supported_requirements=set()))
    assert not rejected.ok
    assert any(d.code=='RT_DRIVER_REQUIREMENT_UNSUPPORTED' for d in rejected.diagnostics)


def test_runtime_repeat_group_members_have_distinct_instance_ids():
    from culsma.runtime.state import init_state
    _, plan=compile_program(PREFIX + 'let wells=assay[A1:A2]; let cells=tube(); let events=stream(sample=cells,unit=single_cell); repeat cell in events { wells << [stock:20uL]; }')
    state=init_state(plan)
    state.artifacts['stream_units']={'events':['cell0','cell1']}
    result=run(plan,StubDriver(),state)
    assert result.ok, result.diagnostics
    effects=[h['step_id'] for h in result.state.history if h.get('driver_code')=='DRV_OK' and '.g' in h['step_id']]
    assert len(effects)==4 and len(set(effects))==4


def test_scalar_and_single_member_selector_keep_scalar_path():
    _, plan=compile_program(PREFIX + 'let one=assay[A1]; one[0] << [stock:20uL];')
    assert not any(s.op=='MutationGroup' for p in plan.plans for s in p.steps)
    assert run(plan,StubDriver()).ok


@pytest.mark.parametrize('status', ['waiting', 'running'])
@pytest.mark.parametrize('blocked_ordinal', [0, 1])
def test_unresolved_member_state_cannot_complete_group(status,blocked_ordinal):
    from culsma.runtime.state import init_state
    _,plan=compile_program(PREFIX+'assay[A1:A2] << [stock:20uL];')
    group=next(s for p in plan.plans for s in p.steps if s.op=='MutationGroup')
    members=PlanStepTree.children(group)
    state=init_state(plan)
    state.step_status[members[blocked_ordinal].step_id]=status
    result=run(plan,StubDriver(),state)
    assert not result.ok
    assert result.state.step_status[group.step_id]=='failed'
    assert result.state.step_status[members[blocked_ordinal].step_id]==status
    assert any(d.code=='RT_MUTATION_GROUP_UNRESOLVED' for d in result.diagnostics)
    assert not any(event.kind=='STEP_STARTED' and event.step_id in {m.step_id for m in members} for event in result.events)
    containers=result.state.artifacts['material_state']['containers'].values()
    assert next(c['volume_uL'] for c in containers if c['metadata'].get('label')=='Stock')==1000
