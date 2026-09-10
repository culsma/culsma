"""Source constructor vocabulary and compatibility reexports of shared contracts."""

from __future__ import annotations

import re
from enum import StrEnum

from culsma.common.content_contracts import (
    CONTENT_KIND_WHITELIST,
    CONTAINER_KIND_WHITELIST,
    FALLBACK_CONTENT_TYPE_BY_KIND,
    STANDARD_CONTENT_TYPES_BY_KIND,
    STANDARD_CONTENT_TYPES_BY_KIND_ENUM,
    ContainerKind,
    ContentKind,
    ContentType,
    content_type_fallback_for_kind,
    is_allowed_content_type,
    is_standard_content_type,
    parse_content_kind,
    parse_content_type,
)


class ContentSpecSugar(StrEnum):
    CONTAINER = "container"
    TUBE = "tube"
    WELL = "well"
    CHAMBER = "chamber"
    SURFACE = "surface"
    CONTENT = "content"


CONTENT_SPEC_SUGARS = frozenset(sugar.value for sugar in ContentSpecSugar)
CONTENT_SPEC_SUGAR_TO_CANONICAL = {
    ContentSpecSugar.CONTAINER.value: "AllocContainer",
    ContentSpecSugar.TUBE.value: "AllocContainer",
    ContentSpecSugar.WELL.value: "AllocContainer",
    ContentSpecSugar.CHAMBER.value: "AllocContainer",
    ContentSpecSugar.SURFACE.value: "AllocContainer",
    ContentSpecSugar.CONTENT.value: "DefineContent",
}
CONTENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def parse_content_spec_sugar(value: str) -> ContentSpecSugar | None:
    try:
        return ContentSpecSugar(value)
    except ValueError:
        return None
