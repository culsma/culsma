"""Direct contracts for removable source and historical taxonomy compatibility."""

from __future__ import annotations

import pytest

from culsma.parser.ast_nodes import Arg, StringLiteral
from culsma.pipeline.compat.content_syntax import (
    format_content_suggestion,
    lower_legacy_content_callable,
    normalization_diagnostics,
    resolve_string_binding,
    resolve_type_token,
)
from culsma.pipeline.compat.content_taxonomy import (
    classification_attrs,
    is_custom_content_type,
    is_legacy_content_kind,
    normalize_content_classification,
)
from culsma.pipeline.compile.callable import inject_default_argument, lower_callable
from culsma.pipeline.content_vocab import is_allowed_content_type
from culsma.pipeline.ir_nodes import IRArg, IRIdentifier, IRQuantity, IRString


@pytest.mark.parametrize(
    ('value', 'bindings', 'expected'),
    [
        (IRString('medium'), {}, 'medium'),
        (IRIdentifier('t'), {'t': 'medium'}, 'medium'),
        (IRIdentifier('medium'), {}, None),
        (IRIdentifier('t'), {'t': 3}, None),
        (IRQuantity(3, None), {}, None),
    ],
)
def test_resolve_string_binding(value, bindings, expected):
    assert resolve_string_binding(value, bindings) == expected


@pytest.mark.parametrize(
    ('value', 'bindings', 'expected'),
    [
        (None, {}, None),
        (IRString('medium'), {}, 'medium'),
        (IRIdentifier('medium'), {}, 'medium'),
        (IRIdentifier('t'), {'t': 'medium'}, 'medium'),
        (IRIdentifier('t'), {}, 't'),
        # Characterize the existing type behavior; stricter typed bindings are wave two.
        (IRIdentifier('t'), {'t': 3}, 't'),
        (IRQuantity(3, None), {}, None),
    ],
)
def test_resolve_type_token_preserves_existing_behavior(value, bindings, expected):
    arg = IRArg(name='type', value=value) if value is not None else None
    assert resolve_type_token(arg, bindings) == expected


@pytest.mark.parametrize(
    ('kind', 'content_type', 'target_kind', 'target_type', 'attrs'),
    [
        ('formulation', 'medium', 'formulation', 'medium', {}),
        ('biosample', 'dna_stock', 'bio_molecule_or_virus', 'dna', {'state': 'stock'}),
        ('buffer', 'column_wash_buffer_2', 'formulation', 'buffer', {'role': 'wash', 'kit_step': '2'}),
        ('formulation', 'wash_buffer', 'formulation', 'buffer', {'role': 'wash'}),
        ('chemical', 'medium', 'chemical', 'other_chemical', {'original_type': 'medium'}),
        ('formulation', 'custom_mix', 'formulation', 'other_formulation', {'original_type': 'custom_mix'}),
        ('blood', 'custom_mix', 'bio_fluid', 'whole_blood', {}),
        ('biosample', 'custom_mix', 'bio_molecule_or_virus', 'other_biomolecule_or_virus', {'original_type': 'custom_mix'}),
        ('buffer', 'custom_mix', 'formulation', 'buffer', {'original_type': 'custom_mix'}),
        ('reagent', 'custom_mix', 'chemical', 'other_chemical', {'original_type': 'custom_mix'}),
        ('control', 'custom_mix', 'chemical', 'other_chemical', {'workflow_role': 'control', 'original_type': 'custom_mix'}),
        ('waste', 'custom_mix', 'formulation', 'other_formulation', {'disposition': 'waste', 'original_type': 'custom_mix'}),
        ('fraction', 'custom_mix', 'bio_fluid', 'other_body_fluid', {'workflow_role': 'fraction', 'original_type': 'custom_mix'}),
        ('other', 'custom_mix', 'other', 'custom_mix', {}),
        ('formulaton', 'medium', 'formulaton', 'medium', {}),
        ('FORMULATION', 'MEDIUM', 'formulation', 'medium', {}),
    ],
)
def test_historical_normalization(kind, content_type, target_kind, target_type, attrs):
    normalized = normalize_content_classification(kind, content_type)
    assert (normalized.kind, normalized.type, normalized.attrs) == (target_kind, target_type, attrs)
    assert (normalized.original_kind, normalized.original_type) == (kind.lower(), content_type.lower())
    assert normalized.changed == ((target_kind, target_type) != (kind.lower(), content_type.lower()))


def test_normalization_does_not_share_mutable_metadata_between_calls():
    first = normalize_content_classification('biosample', 'dna_stock')
    first.attrs['state'] = 'modified'
    assert normalize_content_classification('biosample', 'dna_stock').attrs == {'state': 'stock'}


@pytest.mark.parametrize('compat_mode', [False, True])
def test_source_compat_mode_does_not_change_historical_conversion(compat_mode):
    diagnostics = normalization_diagnostics(
        kind_value='biosample', type_value='dna_stock', span=None, node_id='n1', compat_mode=compat_mode,
    )
    assert len(diagnostics) == int(compat_mode)
    if compat_mode:
        assert diagnostics[0].code == 'SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED'
        assert diagnostics[0].severity == 'warning'
        assert diagnostics[0].node_id == 'n1'
        assert 'bio_molecule_or_virus' in diagnostics[0].message
    normalized = normalize_content_classification('biosample', 'dna_stock')
    assert (normalized.kind, normalized.type) == ('bio_molecule_or_virus', 'dna')


@pytest.mark.parametrize('kind', ['formulaton', 'formulation'])
def test_no_compatibility_warning_for_unknown_or_already_canonical_kind(kind):
    assert normalization_diagnostics(
        kind_value=kind, type_value='medium', span=None, node_id=None, compat_mode=True,
    ) == []


def test_format_content_suggestion():
    assert format_content_suggestion('formulation', 'medium', {}) == 'content(kind="formulation", type="medium")'
    assert format_content_suggestion('formulation', 'buffer', {'state': 'stock', 'role': 'wash'}) == (
        'content(kind="formulation", type="buffer", attrs={role: "wash", state: "stock"})'
    )


@pytest.mark.parametrize(
    ('name', 'expected'),
    [('blood', {'kind': 'blood', 'type': 'whole_blood'}), ('reagent', {'kind': 'reagent'}),
     ('buffer', {'kind': 'buffer', 'type': 'buffer'})],
)
def test_legacy_constructor_defaults(name, expected):
    args = [Arg(name='code', value=StringLiteral(value='TEST'))]
    operation, lowered = lower_legacy_content_callable(name, args, None)
    assert operation == 'DefineContent'
    assert {arg.name: arg.value.value for arg in lowered} == {'code': 'TEST', **expected}
    assert len(args) == 1
    assert lower_callable(name, args, None) == (operation, lowered)


@pytest.mark.parametrize('name', ['blood', 'reagent', 'buffer'])
def test_legacy_constructor_preserves_explicit_arguments(name):
    args = [Arg(name='kind', value=StringLiteral(value='chemical')), Arg(name='type', value=StringLiteral(value='solvent'))]
    assert lower_legacy_content_callable(name, args, None) == ('DefineContent', args)


@pytest.mark.parametrize('explicit_kind', [None, 'surface'])
def test_standard_constructor_defaults_preserve_explicit_arguments(explicit_kind):
    args = [Arg(name='kind', value=StringLiteral(value=explicit_kind))] if explicit_kind else []
    inject_default_argument(args, 'kind', StringLiteral(value='tube'), None)
    assert len(args) == 1
    assert args[0].value.value == (explicit_kind or 'tube')


@pytest.mark.parametrize('name', ['tube', 'well', 'chamber', 'surface', 'content', 'other_operation'])
def test_standard_callable_does_not_depend_on_legacy_expansion(name):
    assert lower_legacy_content_callable(name, [], None) is None
    operation, args = lower_callable(name, [], None)
    if name in {'tube', 'well', 'chamber', 'surface'}:
        assert operation == 'AllocContainer'
        assert {arg.name: arg.value.value for arg in args} == (
            {'kind': name, 'carrier_kind': 'plate'} if name == 'well' else {'kind': name}
        )
    else:
        assert operation == ('DefineContent' if name == 'content' else name)
        assert args == []


def test_legacy_helpers_do_not_extend_canonical_vocabulary():
    assert classification_attrs(role='wash', state='') == {'role': 'wash'}
    assert is_legacy_content_kind('biosample')
    assert not is_legacy_content_kind('formulation')
    assert is_custom_content_type('custom_lab_mix')
    assert not is_custom_content_type('custom_')
    assert not is_custom_content_type('medium')
    assert not is_allowed_content_type('biosample', 'dna_stock')
    assert not is_allowed_content_type('formulation', 'custom_lab_mix')
    assert is_allowed_content_type('formulation', 'medium')
