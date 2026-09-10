"""Final content argument validation shared by plan binding and material writes."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from culsma.common.content_contracts import (
    ContainerKind, ContentClassification, ContentKind, ContentType,
    parse_content_classification, parse_serialized_content_enum,
)
from culsma.pipeline.compat.content_taxonomy import (
    NormalizedContentClassification, normalize_content_classification, legacy_runtime_container_kind,
)


@dataclass(frozen=True)
class BoundContentClassification:
    classification: ContentClassification
    normalization: NormalizedContentClassification | None = None


def read_bound_content_token(value: Any, expected_enum: type[StrEnum]) -> StrEnum | str:
    """Read a final value without confusing a string-equal enum with its family."""
    if isinstance(value, dict) and value.get('kind') == 'ContentEnum':
        value = parse_serialized_content_enum(value)
        if value is None:
            raise ValueError('Unknown or malformed content enum member')
    if isinstance(value, StrEnum):
        if type(value) is not expected_enum:
            raise ValueError(f'Expected {expected_enum.__name__}, got {type(value).__name__}')
        return value
    if isinstance(value, dict):
        if value.get('kind') == 'IRString':
            value = value.get('value')
        elif value.get('kind') == 'IRIdentifier':
            value = value.get('name')
    if type(value) is str:
        return value
    raise ValueError(f'Expected {expected_enum.__name__} or compatible text')


def resolve_bound_content_classification(kind_value: Any, type_value: Any) -> BoundContentClassification:
    kind = read_bound_content_token(kind_value, ContentKind)
    content_type = read_bound_content_token(type_value, ContentType)
    classification = parse_content_classification(kind, content_type)
    if isinstance(kind, StrEnum) or isinstance(content_type, StrEnum):
        if classification is None:
            raise ValueError(f'Unsupported explicit content classification {kind}/{content_type}')
        return BoundContentClassification(classification)
    normalized = normalize_content_classification(kind, content_type)
    classification = normalized.classification
    if classification is None:
        raise ValueError(f'Unsupported content classification {kind}/{content_type}')
    return BoundContentClassification(classification, normalized)


def resolve_bound_container_kind(value: Any) -> ContainerKind:
    token = read_bound_content_token(value, ContainerKind)
    try:
        return ContainerKind(token)
    except ValueError:
        raise ValueError(f'Unsupported container kind {token}') from None


def resolve_runtime_container_kind(value: Any) -> ContainerKind | str:
    """Historical material plans also admit the generic legacy container token."""
    token = read_bound_content_token(value, ContainerKind)
    if type(token) is str:
        legacy = legacy_runtime_container_kind(token)
        if legacy is not None:
            return legacy
    return resolve_bound_container_kind(value)
