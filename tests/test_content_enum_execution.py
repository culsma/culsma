"""2C execution contracts: enum identity survives binding and JSON boundaries."""

from copy import deepcopy
import json

import pytest

from culsma.common.content_contracts import ContentKind, ContentType, ContainerKind
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan_nodes import PlanStep
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.runtime.material.container_content import apply_define_content, apply_alloc_container


def compile_plan(source, entry_args=None):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    typed = typecheck(compiled.ir, analysis=compiled.analysis)
    assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]
    return lower_ir_to_plan(compiled.ir, entry_args_by_protocol=entry_args)


def enum_payload(family, member):
    return {'kind': 'ContentEnum', 'enum': family, 'member': member}


@pytest.mark.parametrize('form', ['direct', 'alias', 'default', 'entry', 'assign'])
def test_enum_content_runs_through_all_binding_paths(form):
    params, declarations = '', ''
    kind, content_type, vessel = 'ContentKind.FORMULATION', 'ContentType.MEDIUM', 'ContainerKind.TUBE'
    entry_args = None
    if form == 'alias':
        declarations = f'let k={kind}; let t={content_type}; let c={vessel};'
        kind, content_type, vessel = 'k', 't', 'c'
    elif form == 'assign':
        declarations = 'let k=ContentKind.CHEMICAL; k=ContentKind.FORMULATION;'
        kind = 'k'
    elif form == 'default':
        params = f'(k={kind}, t={content_type}, c={vessel})'
        kind, content_type, vessel = 'k', 't', 'c'
    elif form == 'entry':
        params = '(k, t, c)'
        kind, content_type, vessel = 'k', 't', 'c'
        entry_args = {'T': {'k': ContentKind.FORMULATION, 't': ContentType.MEDIUM, 'c': ContainerKind.TUBE}}
    plan = compile_plan(f'''protocol T{params} {{ {declarations}
      let x=container(kind={vessel}, capacity=5mL,
        load=[content(kind={kind}, type={content_type}, code="M", attrs={{role:culture}}):4mL]);
    }}''', entry_args)
    assert not plan.diagnostics, [d.to_dict() for d in plan.diagnostics]
    payload = json.loads(json.dumps(plan.to_dict()))
    assert 'ContentEnum' in str(payload)
    result = run(plan=plan, driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    registry = result.state.artifacts['material_state']['content_registry']
    assert registry['M']['content_kind'] == 'formulation'
    assert registry['M']['content_type'] == 'medium'
    assert registry['M']['content_attrs'] == {'role': 'culture'}


@pytest.mark.parametrize(('k', 't'), [
    (ContentType.MEDIUM, ContentType.MEDIUM), (ContentKind.CHEMICAL, ContentType.MEDIUM),
    (23, 'medium'), ('unknown_kind', 'medium'), ('formulation', 5),
])
def test_entry_values_are_rechecked_after_binding(k, t):
    plan = compile_plan('protocol T(k,t) { let x=tube(load=[content(kind=k,type=t):1mL]); }', {'T': {'k': k, 't': t}})
    assert 'PLAN_CONTENT_CLASSIFICATION_INVALID' in [d.code for d in plan.diagnostics]
    assert not plan.plans


@pytest.mark.parametrize(('kind', 'content_type'), [
    (enum_payload('ContentKind','CHEMICAL'), enum_payload('ContentType','MEDIUM')),
    (enum_payload('ContentType','MEDIUM'), 'medium'),
    (enum_payload('ContentKind','TYPO'), 'medium'),
    (None, 'medium'), ('formulation', None), (42, 'medium'), ('unknown_kind', 'medium'),
])
def test_runtime_invalid_classification_never_mutates_registry(kind, content_type):
    state = {'content_registry': {'existing': {'content_kind':'chemical'}}, 'content_bindings': {}}
    before = deepcopy(state)
    result = apply_define_content(PlanStep('bad','DefineContent',{'kind':kind,'type':content_type,'code':'M'}), state)
    assert [d.code for d in result.diagnostics] == ['MAT_CONTENT_CLASSIFICATION_INVALID']
    assert state == before


def test_runtime_container_enum_family_and_surface_capacity_checked_before_mutation():
    for kind in (enum_payload('ContentKind','FORMULATION'), enum_payload('ContainerKind','SURFACE')):
        state = {}
        result = apply_alloc_container(PlanStep('bad','AllocContainer',{
            'kind':kind, 'capacity': {'kind':'IRQuantity','value':1,'unit':'mL'},
            'container_namespace':'T', 'container_name':'x',
        }), state)
        assert not result.ok
        assert not state


def test_runtime_legacy_normalization_keeps_history_metadata():
    state = {}
    result = apply_define_content(PlanStep('old','DefineContent',{'kind':'biosample','type':'dna_stock','code':'D'}), state)
    assert result.ok
    assert state['content_registry']['D']['content_kind'] == 'bio_molecule_or_virus'
    assert state['content_registry']['D']['content_original_kind'] == 'biosample'
    assert state['content_registry']['D']['content_attrs'] == {'state':'stock'}


def test_alias_after_runtime_assignment_keeps_captured_enum():
    plan = compile_plan('''protocol T {
      let k=ContentKind.CHEMICAL;
      k=ContentKind.FORMULATION;
      let saved=k;
      k=ContentKind.CHEMICAL;
      let x=tube(load=[content(kind=saved,type=ContentType.MEDIUM,code="M"):1mL]);
    }''')
    result=run(plan=plan, driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    assert result.state.artifacts['material_state']['content_registry']['M']['content_kind'] == 'formulation'


def test_enum_protocol_call_binding():
    plan=compile_plan('''protocol Child(k,t) {
      let x=tube(load=[content(kind=k,type=t,code="M"):1mL]);
    }
    protocol T { Child(k=ContentKind.FORMULATION,t=ContentType.MEDIUM); }
    T();
    ''')
    result=run(plan=plan, driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_runtime_dynamic_wrong_family_is_rejected():
    from culsma.pipeline.plan_nodes import PlanProgram, ProtocolPlan
    plan=PlanProgram(plans=[ProtocolPlan('T','T',steps=[
        PlanStep('assign','assign_local',{'target':'k','value':enum_payload('ContentType','MEDIUM')}),
        PlanStep('define','DefineContent',{'kind':{'kind':'IRIdentifier','name':'k'},'type':'medium','code':'M'}),
    ])])
    result=run(plan=plan,driver=StubDriver())
    assert not result.ok
    assert 'MAT_CONTENT_CLASSIFICATION_INVALID' in [d.code for d in result.diagnostics]
    assert not result.state.artifacts.get('material_state',{}).get('content_registry')


def test_enum_in_conditional_and_repeat_executes_selected_values():
    plan=compile_plan('''protocol T(flag=true) {
      let k=ContentKind.CHEMICAL;
      if flag { k=ContentKind.FORMULATION; }
      repeat tick in [1,2] {
        let x=tube(load=[content(kind=k,type=ContentType.MEDIUM,code="M"):1mL]);
      }
    }''')
    result=run(plan=plan,driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    assert len(result.state.artifacts['material_state']['containers']) == 2


def test_enum_cells_execute_with_count_preserved():
    plan=compile_plan('''protocol T {
      let x=tube(load=[content(kind=ContentKind.BIO_CELLULAR,type=ContentType.CELL_LINE,code="C"):4cells]);
    }''')
    result=run(plan=plan,driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    container=next(iter(result.state.artifacts['material_state']['containers'].values()))
    assert container['component_quantities']['C']['value'] == 4


def test_enum_plan_json_round_trip_executes_identical_material_state():
    from culsma.pipeline.plan_nodes import PlanProgram, ProtocolPlan
    plan=compile_plan('protocol T { let x=tube(load=[content(kind=ContentKind.FORMULATION,type=ContentType.MEDIUM,code="M"):1mL]); }')
    payload=json.loads(json.dumps(plan.to_dict()))
    protocol=payload['plans'][0]
    reloaded=PlanProgram(plans=[ProtocolPlan(protocol['protocol_id'],protocol['protocol_name'],steps=[
        PlanStep(step['step_id'],step['op'],step['args'],step['deps'],step['gate']) for step in protocol['steps']
    ])])
    first=run(plan=plan,driver=StubDriver())
    second=run(plan=reloaded,driver=StubDriver())
    assert first.ok and second.ok
    assert first.state.artifacts['material_state'] == second.state.artifacts['material_state']


def test_serialized_enum_identity_round_trip_and_malformed_values():
    from culsma.common.content_contracts import serialize_content_enum, parse_serialized_content_enum
    for family in (ContentKind, ContentType, ContainerKind):
        for value in family:
            assert parse_serialized_content_enum(json.loads(json.dumps(serialize_content_enum(value)))) is value
    for payload in (None, {}, {'kind':'ContentEnum','enum':[],'member':'MEDIUM'},
                    enum_payload('Unknown','MEDIUM'), enum_payload('ContentKind','TYPO')):
        assert parse_serialized_content_enum(payload) is None


def test_public_bound_contracts_preserve_enum_identity_and_legacy_provenance():
    from culsma.pipeline.content_boundary import (
        resolve_bound_content_classification, resolve_bound_container_kind, resolve_runtime_container_kind,
    )
    explicit=resolve_bound_content_classification(enum_payload('ContentKind','FORMULATION'),enum_payload('ContentType','MEDIUM'))
    assert explicit.classification.kind is ContentKind.FORMULATION
    assert explicit.normalization is None
    legacy=resolve_bound_content_classification('biosample','dna_stock')
    assert legacy.classification.type is ContentType.DNA
    assert legacy.normalization.original_type == 'dna_stock'
    assert resolve_bound_container_kind(enum_payload('ContainerKind','TUBE')) is ContainerKind.TUBE
    assert resolve_runtime_container_kind('container') == 'container'
    with pytest.raises(ValueError):
        resolve_bound_container_kind('container')


def test_bound_plan_validation_covers_repeat_body_and_preserves_other_operations():
    from culsma.pipeline.plan.content_enums import validate_bound_content_step, validate_bound_content_steps
    bad=PlanStep('bad','DefineContent',{'kind':enum_payload('ContentKind','CHEMICAL'),'type':enum_payload('ContentType','MEDIUM')})
    assert [d.code for d in validate_bound_content_steps([PlanStep('loop','repeat',{'body_steps':[bad]})])] == ['PLAN_CONTENT_CLASSIFICATION_INVALID']
    assert validate_bound_content_step(PlanStep('other','Custom',bad.args)) == []
    assert validate_bound_content_step(PlanStep('dynamic','DefineContent',{'kind':{'kind':'IRIdentifier','name':'k'},'type':'medium'})) == []


def test_runtime_enum_evaluation_preserves_family_and_rejects_unknown_members():
    from culsma.runtime.values import RuntimeValueResolver, evaluate_content_enum, UNRESOLVED
    from culsma.runtime.state import RuntimeState
    resolver=RuntimeValueResolver()
    payload=enum_payload('ContentKind','FORMULATION')
    assert evaluate_content_enum(payload) is ContentKind.FORMULATION
    assert evaluate_content_enum(enum_payload('ContentKind','TYPO')) is UNRESOLVED
    assert resolver.eval_expr(payload,RuntimeState()) is ContentKind.FORMULATION
    assert resolver.value_to_serialized(ContentKind.FORMULATION) == payload


def test_deferred_enum_retains_family_across_branch_and_alias():
    from culsma.pipeline.content_inputs import (
        ContentArgumentResolver, ContentArgumentScope, ContentResolutionStatus,
        ContentResolutionIssue, DeferredContentEnum, deferred_content_enum_bindings,
    )
    scope=ContentArgumentScope(expr_bindings={'k':ContentKind.FORMULATION})
    updates=deferred_content_enum_bindings(['k'],scope)
    assert updates['k'] == DeferredContentEnum(ContentKind)
    result=ContentArgumentResolver.resolve_argument(updates['k'],ContentKind,scope)
    assert result.status is ContentResolutionStatus.DEFERRED
    assert ContentArgumentResolver.resolve_argument(updates['k'],ContentType,scope).issue is ContentResolutionIssue.WRONG_ENUM_TYPE
    plan=compile_plan('''protocol T(flag=true) {
      let k=ContentKind.CHEMICAL;
      if flag { k=ContentKind.FORMULATION; }
      let saved=k;
      k=ContentKind.CHEMICAL;
      let x=tube(load=[content(kind=saved,type=ContentType.MEDIUM,code="M"):1mL]);
    }''')
    result=run(plan=plan,driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_wrong_enum_assignment_inside_conditional_is_typechecked():
    compiled=compile_ast(resolve_program(parse('protocol T(flag=true) { let k=ContentKind.FORMULATION; if flag { k=ContentType.MEDIUM; } }')).prepared_program)
    typed=typecheck(compiled.ir,analysis=compiled.analysis)
    assert 'TYPE_LOCAL_ASSIGN_MISMATCH' in [d.code for d in typed.diagnostics]


def test_namespace_shadowing_record_is_not_replaced_with_builtin_enum():
    plan=compile_plan('''protocol T {
      let ContentKind={FORMULATION: "chemical"};
      let x=tube(load=[content(kind=ContentKind.FORMULATION,type=ContentType.SOLVENT,code="M"):1mL]);
    }''')
    result=run(plan=plan,driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    assert result.state.artifacts['material_state']['content_registry']['M']['content_kind'] == 'chemical'


def test_scientific_classification_rules_use_shared_enum_members():
    from culsma.scientific_model.material.classification import CLASSIFICATION_RULES, classify_canonical_content, CalculationGroup
    for rule in CLASSIFICATION_RULES:
        assert rule.canonical_kind is None or type(rule.canonical_kind) is ContentKind
        assert rule.canonical_types is None or all(type(value) is ContentType for value in rule.canonical_types)
    assert classify_canonical_content('formulation','medium').group is CalculationGroup.MOBILE_PHASE
    assert classify_canonical_content('chemical','medium').group is CalculationGroup.COMPOSITE_OR_UNKNOWN
    assert classify_canonical_content('unknown','unknown').group is CalculationGroup.COMPOSITE_OR_UNKNOWN
