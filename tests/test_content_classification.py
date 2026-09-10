"""Validated classification contract: actual enums, exact pairs, legacy separation."""

from dataclasses import FrozenInstanceError, asdict, replace
from enum import StrEnum
import json

import pytest

from culsma.common.content_contracts import (
    ContentClassification, ContentKind, ContentType,
    STANDARD_CONTENT_TYPES_BY_KIND_ENUM, parse_content_classification,
    parse_content_kind, parse_content_type,
)
from culsma.pipeline import content_vocab
from culsma.pipeline.compat.content_taxonomy import (
    LEGACY_TYPE_ALIASES, NormalizedContentClassification, normalize_content_classification,
)


def test_classification_requires_real_enum_members_and_is_immutable():
    classification = ContentClassification(ContentKind.FORMULATION, ContentType.MEDIUM)
    classification.validate()
    assert classification.kind is ContentKind.FORMULATION
    assert classification.type is ContentType.MEDIUM
    with pytest.raises(FrozenInstanceError):
        classification.kind = ContentKind.CHEMICAL
    with pytest.raises(ValueError):
        replace(classification, kind=ContentKind.CHEMICAL)
    assert classification.to_dict() == {'kind': 'formulation', 'type': 'medium'}
    assert all(type(value) is str for value in classification.to_dict().values())
    assert json.loads(json.dumps(classification.to_dict())) == classification.to_dict()


@pytest.mark.parametrize(('kind', 'content_type', 'error'), [
    ('formulation', ContentType.MEDIUM, TypeError),
    (ContentKind.FORMULATION, 'medium', TypeError),
    (ContentType.MEDIUM, ContentType.MEDIUM, TypeError),
    (ContentKind.FORMULATION, ContentKind.FORMULATION, TypeError),
    (ContentKind.CHEMICAL, ContentType.MEDIUM, ValueError),
    (None, ContentType.MEDIUM, TypeError),
])
def test_direct_construction_cannot_bypass_validation(kind, content_type, error):
    with pytest.raises(error):
        ContentClassification(kind, content_type)


@pytest.mark.parametrize(('kind', 'content_type'), [
    ('formulation', 'medium'), (ContentKind.FORMULATION, ContentType.MEDIUM),
    ('formulation', ContentType.MEDIUM), (ContentKind.FORMULATION, 'medium'),
])
def test_canonical_token_boundary_creates_actual_enums(kind, content_type):
    classification = parse_content_classification(kind, content_type)
    assert classification.kind is ContentKind.FORMULATION
    assert classification.type is ContentType.MEDIUM


@pytest.mark.parametrize(('kind', 'content_type'), [
    ('FORMULATION', 'medium'), ('formulation', 'MEDIUM'), ('formulaton', 'medium'),
    ('chemical', 'medium'), ('biosample', 'dna_stock'), ('formulation', 'custom_mix'),
    ('formulation', None), ([], 'medium'), ('formulation', {}),
])
def test_canonical_boundary_does_not_apply_legacy_fallback(kind, content_type):
    assert parse_content_classification(kind, content_type) is None


def test_equal_string_foreign_enums_do_not_lose_family_identity():
    class Other(StrEnum):
        KIND = 'formulation'
        TYPE = 'medium'
    assert parse_content_kind(Other.KIND) is None
    assert parse_content_type(Other.TYPE) is None
    assert parse_content_classification(Other.KIND, Other.TYPE) is None
    with pytest.raises(TypeError):
        ContentClassification(Other.KIND, Other.TYPE)


def test_pair_matrix_is_complete_and_rejects_every_cross_family_pair():
    assert set(STANDARD_CONTENT_TYPES_BY_KIND_ENUM) == set(ContentKind)
    assigned_types = [t for types in STANDARD_CONTENT_TYPES_BY_KIND_ENUM.values() for t in types]
    assert len(assigned_types) == len(set(assigned_types)) == len(ContentType)
    assert set(assigned_types) == set(ContentType)
    for kind in ContentKind:
        for content_type in ContentType:
            classification = parse_content_classification(kind, content_type)
            if content_type in STANDARD_CONTENT_TYPES_BY_KIND_ENUM[kind]:
                assert classification.kind is kind
                assert classification.type is content_type
            else:
                assert classification is None
    with pytest.raises(TypeError):
        STANDARD_CONTENT_TYPES_BY_KIND_ENUM[ContentKind.CHEMICAL] = frozenset({ContentType.MEDIUM})


def test_old_vocabulary_paths_reexport_shared_contracts():
    from culsma.common import content_contracts
    for name in (
        'ContentKind', 'ContentType', 'ContainerKind', 'STANDARD_CONTENT_TYPES_BY_KIND_ENUM',
        'STANDARD_CONTENT_TYPES_BY_KIND', 'CONTENT_KIND_WHITELIST', 'CONTAINER_KIND_WHITELIST',
        'FALLBACK_CONTENT_TYPE_BY_KIND', 'parse_content_kind', 'parse_content_type',
        'is_standard_content_type', 'is_allowed_content_type', 'content_type_fallback_for_kind',
    ):
        assert getattr(content_vocab, name) is getattr(content_contracts, name)


def test_every_legacy_alias_can_promote_without_losing_metadata():
    for kind, content_type in LEGACY_TYPE_ALIASES:
        normalized = normalize_content_classification(kind, content_type)
        before = asdict(normalized)
        classification = normalized.classification
        assert isinstance(classification, ContentClassification), (kind, content_type)
        assert classification.to_dict() == {'kind': normalized.kind, 'type': normalized.type}
        assert asdict(normalized) == before
        assert 'classification' not in asdict(normalized)
    normalized = normalize_content_classification('biosample', 'dna_stock')
    assert normalized.classification.kind is ContentKind.BIO_MOLECULE_OR_VIRUS
    assert normalized.attrs == {'state': 'stock'}
    assert normalized.original_kind == 'biosample'
    assert normalized.original_type == 'dna_stock'
    assert normalized.changed


def test_unknown_history_is_preserved_but_is_not_validated_classification():
    normalized = normalize_content_classification('unknown_kind', 'unknown_type')
    assert normalized.classification is None
    assert normalized.kind == 'unknown_kind'
    assert normalized.type == 'unknown_type'
    assert NormalizedContentClassification('chemical', 'medium').classification is None


def test_legacy_fallback_and_strict_classification_are_separate():
    assert parse_content_classification('chemical', 'medium') is None
    normalized = normalize_content_classification('chemical', 'medium')
    assert normalized.classification == ContentClassification(ContentKind.CHEMICAL, ContentType.OTHER_CHEMICAL)
    assert normalized.attrs == {'original_type': 'medium'}
