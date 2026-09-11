"""Source-origin diagnostics and shared nested-content argument contracts."""

import pytest

from culsma.cli import execute_pipeline
from culsma.common.diagnostics import Diagnostic
from culsma.common.source import Span
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.ir_nodes import IRArg, IRCall, IRString
from culsma.pipeline.operation_specs import BUILTIN_OPERATION_SPECS
from culsma.pipeline.validate import validate
from culsma.pipeline.validate.operations import OperationContractValidator, call_contract_for_name
from culsma.pipeline.validate.validator import deduplicate_diagnostics


def validate_source(source):
    frontend = resolve_program(parse(source), include_bundled_stdlib=False)
    compiled = compile_ast(frontend.prepared_program)
    return validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)


def test_shared_argument_names_check_reports_unknown_and_duplicate_once():
    call = IRCall('DefineContent', [IRArg('role', IRString('wash')),
                                  IRArg('type', IRString('medium')),
                                  IRArg('type', IRString('buffer')),
                                  IRArg('type', IRString('medium'))])
    required, allowed = call_contract_for_name(call.name, operations=BUILTIN_OPERATION_SPECS)
    assert required == {'kind'}
    diagnostics = OperationContractValidator.validate_argument_names(call, node_id='test', allowed_args=allowed)
    assert [d.code for d in diagnostics] == ['SEM_UNKNOWN_ARG', 'SEM_DUPLICATE_ARG']
    full = OperationContractValidator.validate_call(call, node_id='test', operations=BUILTIN_OPERATION_SPECS)
    assert [d.code for d in full] == ['SEM_MISSING_REQUIRED_ARG', 'SEM_UNKNOWN_ARG', 'SEM_DUPLICATE_ARG']
    assert call_contract_for_name('not_builtin', operations=BUILTIN_OPERATION_SPECS) == (None, None)


@pytest.mark.parametrize('declaration', [
    'let x=tube(load=[content(kind=formulation,type=medium,role=culture):1uL]);',
    'let items=[content(kind=formulation,type=medium,role=culture):1uL]; let x=tube(load=items);',
    'let c=content(kind=formulation,type=medium,role=culture);',
])
def test_nested_content_names_are_checked_through_expression_paths(declaration):
    result = validate_source(f'protocol T {{ {declaration} }} T();')
    assert not result.ok
    assert len([d for d in result.diagnostics if d.code == 'SEM_UNKNOWN_ARG']) == 1


def test_invalid_parameter_names_do_not_normalize_an_arbitrary_duplicate_value():
    result = validate_source('''protocol T {
      let x=tube(load=[content(kind=chemical,kind=formulation,type=medium):1uL]);
    } T();''')
    assert [d.code for d in result.diagnostics] == ['SEM_DUPLICATE_ARG']


@pytest.mark.parametrize(('args', 'code'), [
    ('type=medium', 'SEM_MISSING_CONTENT_KIND'),
    ('kind=formulation', 'SEM_INVALID_CONTENT_TYPE_FORMAT'),
])
def test_content_required_value_diagnostics_keep_their_owner(args, code):
    result = validate_source(f'protocol T {{ let x=tube(load=[content({args}):1uL]); }} T();')
    assert [d.code for d in result.diagnostics] == [code]


def test_one_source_warning_is_not_multiplied_by_multiple_expansions(tmp_path):
    entry = tmp_path / 'main.culs'
    entry.write_text('''protocol T {
      let x=tube(load=[content(kind=buffer,type=wash_buffer,code="M"):1uL]);
    } T(); T();''')
    bundle = execute_pipeline([entry])
    assert bundle['output']['ok']
    assert [d['code'] for d in bundle['validate']] == ['SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED']
    assert len(bundle['run']['state']['artifacts']['material_state']['containers']) == 2


def test_identical_coordinates_in_different_files_keep_both_diagnostics(tmp_path):
    library_source = 'protocol T { let x=tube(load=[content(kind=buffer,type=wash_buffer):1uL]); }'
    for name in ('A', 'B'):
        (tmp_path / f'{name}.culs').write_text(library_source.replace('protocol T', f'protocol {name}'))
    entry = tmp_path / 'main.culs'
    entry.write_text('import A; import B; A.A(); B.B();')
    bundle = execute_pipeline([entry], library_roots=[tmp_path])
    assert bundle['output']['ok']
    warnings = bundle['validate']
    assert [d['code'] for d in warnings] == ['SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED'] * 2
    assert warnings[0]['span'] == warnings[1]['span']
    assert warnings[0]['node_id'] != warnings[1]['node_id']


def test_source_deduplication_preserves_distinct_origins_and_messages():
    origin = Span(1, 1, 0, 10)
    equal_coordinates = Span(1, 1, 0, 10)
    first = Diagnostic('SEM_TEST', 'same', origin, 'warning', 'entry.s0')
    duplicate = Diagnostic('SEM_TEST', 'same', origin, 'warning', 'p0.s0')
    other_file = Diagnostic('SEM_TEST', 'same', equal_coordinates, 'warning', 'p1.s0')
    other_message = Diagnostic('SEM_TEST', 'different bound value', origin, 'warning', 'entry.s1')
    other_severity = Diagnostic('SEM_TEST', 'same', origin, 'error', 'entry.s0')
    other_code = Diagnostic('SEM_OTHER', 'same', origin, 'warning', 'entry.s0')
    expected = [first, other_file, other_message, other_severity, other_code]
    assert deduplicate_diagnostics([first, duplicate, *expected[1:]]) == expected


def test_diagnostics_without_source_keep_distinct_nodes():
    first = Diagnostic('SEM_TEST', 'same', None, node_id='a')
    other = Diagnostic('SEM_TEST', 'same', None, node_id='b')
    assert deduplicate_diagnostics([first, first, other]) == [first, other]


def test_diagnostics_without_any_origin_are_not_merged_by_message():
    first = Diagnostic('SEM_TEST', 'same', None)
    other = Diagnostic('SEM_TEST', 'same', None)
    assert len(deduplicate_diagnostics([first, first, other])) == 2


def test_different_bound_values_at_one_source_keep_distinct_warnings():
    result = validate_source('''protocol T(t) {
      let x=tube(load=[content(kind=formulation,type=t):1uL]);
    } T(t="lab_one"); T(t="lab_two");''')
    assert result.ok
    warnings = result.diagnostics
    assert [d.code for d in warnings] == ['SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED'] * 2
    assert 'lab_one' in warnings[0].message
    assert 'lab_two' in warnings[1].message
