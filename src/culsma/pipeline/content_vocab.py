"""Shared content vocabulary for validated content constructors."""

from __future__ import annotations

import re
from enum import StrEnum

from culsma.common.content_contracts import ContainerKind, ContentKind, ContentType


class ContentSpecSugar(StrEnum):
    CONTAINER = "container"
    TUBE = "tube"
    WELL = "well"
    CHAMBER = "chamber"
    SURFACE = "surface"
    CONTENT = "content"


CONTENT_KIND_WHITELIST = frozenset(kind.value for kind in ContentKind)
CONTAINER_KIND_WHITELIST = frozenset(kind.value for kind in ContainerKind)
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

STANDARD_CONTENT_TYPES_BY_KIND_ENUM: dict[ContentKind, frozenset[ContentType]] = {
    ContentKind.BIO_ENTITY: frozenset(
        {ContentType.ORGANISM, ContentType.ORGAN, ContentType.TISSUE, ContentType.OTHER_BIO_ENTITY}
    ),
    ContentKind.BIO_FLUID: frozenset(
        {
            ContentType.WHOLE_BLOOD,
            ContentType.PLASMA,
            ContentType.SERUM,
            ContentType.BUFFY_COAT,
            ContentType.URINE,
            ContentType.SALIVA,
            ContentType.LYMPH,
            ContentType.CEREBROSPINAL_FLUID,
            ContentType.TEARS,
            ContentType.SEMEN,
            ContentType.ASCITES,
            ContentType.SYNOVIAL_FLUID,
            ContentType.BRONCHOALVEOLAR_LAVAGE_FLUID,
            ContentType.OTHER_BODY_FLUID,
        }
    ),
    ContentKind.BIO_CELLULAR: frozenset(
        {
            ContentType.CELL_LINE,
            ContentType.PRIMARY_CELLS,
            ContentType.CELL_POPULATION,
            ContentType.MICROBIAL_CELLS,
            ContentType.OTHER_CELLULAR_MATERIAL,
        }
    ),
    ContentKind.BIO_SUBCELLULAR: frozenset(
        {
            ContentType.ORGANELLE,
            ContentType.MEMBRANE,
            ContentType.VESICLE,
            ContentType.CYTOSKELETAL_STRUCTURE,
            ContentType.OTHER_SUBCELLULAR_STRUCTURE,
        }
    ),
    ContentKind.BIO_MOLECULE_OR_VIRUS: frozenset(
        {
            ContentType.DNA,
            ContentType.RNA,
            ContentType.PROTEIN,
            ContentType.VIRUS,
            ContentType.OTHER_BIOMOLECULE_OR_VIRUS,
        }
    ),
    ContentKind.CHEMICAL: frozenset(
        {
            ContentType.ORGANIC_COMPOUND,
            ContentType.INORGANIC_COMPOUND,
            ContentType.SOLVENT,
            ContentType.DETERGENT,
            ContentType.DYE,
            ContentType.OTHER_CHEMICAL,
        }
    ),
    ContentKind.PARTICULATE: frozenset(
        {ContentType.BEADS, ContentType.RESIN, ContentType.PARTICLE, ContentType.OTHER_PARTICULATE}
    ),
    ContentKind.FORMULATION: frozenset(
        {
            ContentType.MEDIUM,
            ContentType.BUFFER,
            ContentType.SUPPLEMENT,
            ContentType.MASTER_MIX,
            ContentType.GRADIENT_MEDIUM,
            ContentType.OTHER_FORMULATION,
        }
    ),
}
STANDARD_CONTENT_TYPES_BY_KIND = {
    kind.value: frozenset(content_type.value for content_type in content_types)
    for kind, content_types in STANDARD_CONTENT_TYPES_BY_KIND_ENUM.items()
}
FALLBACK_CONTENT_TYPE_BY_KIND = {
    ContentKind.BIO_ENTITY.value: ContentType.OTHER_BIO_ENTITY.value,
    ContentKind.BIO_FLUID.value: ContentType.OTHER_BODY_FLUID.value,
    ContentKind.BIO_CELLULAR.value: ContentType.OTHER_CELLULAR_MATERIAL.value,
    ContentKind.BIO_SUBCELLULAR.value: ContentType.OTHER_SUBCELLULAR_STRUCTURE.value,
    ContentKind.BIO_MOLECULE_OR_VIRUS.value: ContentType.OTHER_BIOMOLECULE_OR_VIRUS.value,
    ContentKind.CHEMICAL.value: ContentType.OTHER_CHEMICAL.value,
    ContentKind.PARTICULATE.value: ContentType.OTHER_PARTICULATE.value,
    ContentKind.FORMULATION.value: ContentType.OTHER_FORMULATION.value,
}


def parse_content_kind(value: str) -> ContentKind | None:
    try:
        return ContentKind(value)
    except ValueError:
        return None


def parse_content_type(value: str) -> ContentType | None:
    try:
        return ContentType(value)
    except ValueError:
        return None


def is_standard_content_type(kind_value: str, type_value: str) -> bool:
    kind = parse_content_kind(kind_value)
    content_type = parse_content_type(type_value)
    if kind is None or content_type is None:
        return False
    return content_type in STANDARD_CONTENT_TYPES_BY_KIND_ENUM.get(kind, frozenset())


def is_allowed_content_type(kind_value: str, type_value: str) -> bool:
    return kind_value in CONTENT_KIND_WHITELIST and is_standard_content_type(kind_value, type_value)


def content_type_fallback_for_kind(kind_value: str) -> str | None:
    return FALLBACK_CONTENT_TYPE_BY_KIND.get(kind_value)


def parse_content_spec_sugar(value: str) -> ContentSpecSugar | None:
    try:
        return ContentSpecSugar(value)
    except ValueError:
        return None
