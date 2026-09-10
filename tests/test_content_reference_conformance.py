"""CNT-ENUM-01..07: independently authored reference versus executable behavior."""

import json

import pytest

from conformance.content_contract import SNAPSHOT, PILOT_DIAGNOSTICS, implementation_errors, validate_snapshot
from culsma.common.content_contracts import ContentKind, ContentType, STANDARD_CONTENT_TYPES_BY_KIND_ENUM
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan_nodes import PlanStep
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.runtime.material.container_content import apply_alloc_container, apply_define_content
from culsma.runtime.replay import replay_events

REFERENCE = json.loads(SNAPSHOT.read_text())
CONTRACT = REFERENCE['contract']


def compile_source(source, mode='strict', entry_args=None):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis, content_whitelist_mode=mode)
    typed = typecheck(compiled.ir, analysis=compiled.analysis)
    plan = lower_ir_to_plan(compiled.ir, entry_args_by_protocol=entry_args)
    return semantic, typed, plan


def execute_source(source):
    semantic, typed, plan = compile_source(source)
    assert semantic.ok and typed.ok and not plan.diagnostics, [d.to_dict() for d in [*semantic.diagnostics,*typed.diagnostics,*plan.diagnostics]]
    result = run(plan=plan, driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    events = json.loads(json.dumps([event.to_dict() for event in result.events]))
    replayed = replay_events(events)
    assert replayed.step_status == result.state.step_status
    assert replayed.artifacts['material_state'] == result.state.artifacts['material_state']
    return result


def test_reference_snapshot_is_self_consistent():
    validate_snapshot(REFERENCE)
    assert set(CONTRACT['requirements']) == {f'CNT-ENUM-0{index}' for index in range(1,8)}


def test_reference_taxonomy_matches_implementation():
    assert implementation_errors(CONTRACT) == []
    expected = {(kind, content_type) for kind, types in CONTRACT['types_by_kind'].items() for content_type in types}
    actual = {(kind.value, content_type.value) for kind, types in STANDARD_CONTENT_TYPES_BY_KIND_ENUM.items() for content_type in types}
    assert actual == expected


@pytest.mark.parametrize('case', CONTRACT['legacy_cases'], ids=lambda case: '/'.join(case['input']))
def test_reference_legacy_examples(case):
    from culsma.pipeline.compat.content_taxonomy import normalize_content_classification
    normalized = normalize_content_classification(*case['input'])
    assert [normalized.kind, normalized.type] == case['output']
    assert normalized.attrs == case['attrs']
    assert [normalized.original_kind, normalized.original_type] == case['input']
    assert normalized.classification is not None


@pytest.mark.parametrize('kind', sorted(CONTRACT['types_by_kind']))
def test_reference_per_kind_fallback(kind):
    from culsma.pipeline.compat.content_taxonomy import normalize_content_classification
    normalized = normalize_content_classification(kind, 'lab_local_unknown')
    assert normalized.type == CONTRACT['fallback_by_kind'][kind]
    assert normalized.attrs == {'original_type': 'lab_local_unknown'}


def diagnostics_for_case(code):
    source_cases = {
        'SEM_INVALID_CONTENT_KIND': ('formulaton', 'medium'),
        'SEM_INVALID_CONTENT_TYPE_VALUE': ('chemical', 'medium'),
        'SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED': ('chemical', 'medium'),
        'SEM_CONTENT_ENUM_MEMBER_INVALID': ('ContentKind.FORMULATON', 'ContentType.MEDIUM'),
        'TYPE_CONTENT_ENUM_TYPE_MISMATCH': ('ContentType.MEDIUM', 'ContentType.MEDIUM'),
        'TYPE_CONTENT_KIND_NOT_TEXT': ('3', 'medium'),
        'TYPE_CONTENT_TYPE_NOT_TEXT': ('formulation', '3'),
    }
    if code in source_cases:
        kind, content_type = source_cases[code]
        source = f'protocol T {{ let x=tube(load=[content(kind={kind},type={content_type}):1mL]); }}'
    elif code == 'SEM_SURFACE_CAPACITY_FORBIDDEN':
        source = 'protocol T { let x=surface(capacity=1mL); }'
    elif code == 'SEM_CONTENT_ENUM_BINDING_CYCLE':
        source = 'protocol T(k=t,t=k) { let x=tube(load=[content(kind=k,type=medium):1mL]); }'
    elif code == 'TYPE_CONTAINER_KIND_NOT_TEXT':
        source = 'protocol T { let x=container(kind=3); }'
    elif code.startswith('PLAN_'):
        source = ('protocol T(k) { let x=container(kind=k); }' if code == 'PLAN_CONTAINER_KIND_INVALID'
                  else 'protocol T(k) { let x=tube(load=[content(kind=k,type=medium):1mL]); }')
    elif code.startswith('MAT_'):
        if code == 'MAT_CONTENT_CLASSIFICATION_INVALID':
            step = PlanStep('bad','DefineContent',{'kind':3,'type':'medium'})
            handler = apply_define_content
        else:
            kind = 3 if code == 'MAT_CONTAINER_KIND_INVALID' else 'surface'
            step = PlanStep('bad','AllocContainer',{'kind':kind,'container_namespace':'T','container_name':'x',
                                                   'capacity':{'kind':'IRQuantity','value':1,'unit':'mL'}})
            handler = apply_alloc_container
        state = {}
        result = handler(step,state)
        assert state == {}
        return {'material':result.diagnostics}
    else:
        raise AssertionError(f'Unmapped case: {code}')
    mode = 'compat' if code == 'SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED' else 'strict'
    semantic, typed, plan = compile_source(source, mode, {'T':{'k':ContentType.MEDIUM}} if code.startswith('PLAN_') else None)
    return {'semantic':semantic.diagnostics,'type':typed.diagnostics,'plan':plan.diagnostics}


@pytest.mark.parametrize('code', sorted(PILOT_DIAGNOSTICS))
def test_reference_diagnostic_ownership(code):
    expected = CONTRACT['diagnostics'][code]
    actual = [(phase, diagnostic.severity) for phase, diagnostics in diagnostics_for_case(code).items()
              for diagnostic in diagnostics if diagnostic.code == code]
    assert actual, f'{code} was not reproduced'
    assert set(actual) == {(expected['stage'], expected['severity'])}


def test_open_metadata_survives_execution_and_replay():
    assert CONTRACT['roles_open']
    result = execute_source('''protocol T { let x=tube(load=[
      content(kind=ContentKind.FORMULATION,type=ContentType.MEDIUM,code="M",name="Custom medium",
              attrs={role:lab_specific_role, custom_key:"custom value"}):1mL]); }''')
    content = result.state.artifacts['material_state']['content_registry']['M']
    assert content['content_attrs'] == {'role':'lab_specific_role','custom_key':'custom value'}
    assert content['content_code'] == 'M'
    assert content['content_name'] == 'Custom medium'


@pytest.mark.parametrize(('kind','content_type','amount','transfer'), [
    ('formulation','medium','10uL','4uL'),
    ('bio_cellular','cell_line','100cells','40cells'),
    ('chemical','organic_compound','10mg','4mg'),
])
def test_enum_text_calculation_and_event_replay(kind,content_type,amount,transfer):
    results = []
    for form in ('bare','quoted','enum'):
        kind_expr = {'bare':kind, 'quoted':json.dumps(kind), 'enum':f'ContentKind.{kind.upper()}'}[form]
        type_expr = {'bare':content_type, 'quoted':json.dumps(content_type), 'enum':f'ContentType.{content_type.upper()}'}[form]
        result = execute_source(f'''protocol T {{
          let source=tube(capacity=5mL,load=[content(kind={kind_expr},type={type_expr},code="M"): {amount}]);
          let target=tube(capacity=5mL);
          target << [source:{transfer}];
        }}''')
        results.append(result.state.artifacts['material_state'])
    assert results[0] == results[1] == results[2]
    assert all(type(results[2]['content_registry']['M'][field]) is str for field in ('content_kind','content_type'))


def test_reference_enum_example_is_executable():
    import re
    source = re.findall(r'```culsma\n(.*?)```', REFERENCE['sources']['enums']['markdown'], re.DOTALL)
    assert len(source) == 1
    result = execute_source(source[0])
    assert result.state.artifacts['material_state']['content_registry']['DMEM_F12_COMPLETE']['content_type'] == 'medium'


@pytest.mark.parametrize('kind', sorted(CONTRACT['types_by_kind']))
def test_reference_pair_matrix_enforced_by_frontend(kind):
    all_types = {content_type for members in CONTRACT['types_by_kind'].values() for content_type in members}
    for content_type in sorted(all_types):
        valid = content_type in CONTRACT['types_by_kind'][kind]
        for explicit in (False, True):
            kind_expr = f'ContentKind.{kind.upper()}' if explicit else kind
            type_expr = f'ContentType.{content_type.upper()}' if explicit else content_type
            source = f'protocol T {{ let x=tube(load=[content(kind={kind_expr},type={type_expr}):1uL]); }}'
            semantic, typed, _ = compile_source(source)
            assert typed.ok
            assert [d.code for d in semantic.diagnostics] == ([] if valid else ['SEM_INVALID_CONTENT_TYPE_VALUE']), (kind,content_type,explicit)
