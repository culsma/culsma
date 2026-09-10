"""Validated content classification, independent of parser, pipeline and runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class ContentKind(StrEnum):
    BIO_ENTITY = "bio_entity"
    BIO_FLUID = "bio_fluid"
    BIO_CELLULAR = "bio_cellular"
    BIO_SUBCELLULAR = "bio_subcellular"
    BIO_MOLECULE_OR_VIRUS = "bio_molecule_or_virus"
    CHEMICAL = "chemical"
    PARTICULATE = "particulate"
    FORMULATION = "formulation"


class ContainerKind(StrEnum):
    TUBE = "tube"
    WELL = "well"
    CHAMBER = "chamber"
    SURFACE = "surface"


class ContentType(StrEnum):
    ORGANISM = "organism"
    ORGAN = "organ"
    TISSUE = "tissue"
    OTHER_BIO_ENTITY = "other_bio_entity"
    WHOLE_BLOOD = "whole_blood"
    PLASMA = "plasma"
    SERUM = "serum"
    BUFFY_COAT = "buffy_coat"
    URINE = "urine"
    SALIVA = "saliva"
    LYMPH = "lymph"
    CEREBROSPINAL_FLUID = "cerebrospinal_fluid"
    TEARS = "tears"
    SEMEN = "semen"
    ASCITES = "ascites"
    SYNOVIAL_FLUID = "synovial_fluid"
    BRONCHOALVEOLAR_LAVAGE_FLUID = "bronchoalveolar_lavage_fluid"
    OTHER_BODY_FLUID = "other_body_fluid"
    CELL_LINE = "cell_line"
    PRIMARY_CELLS = "primary_cells"
    CELL_POPULATION = "cell_population"
    MICROBIAL_CELLS = "microbial_cells"
    OTHER_CELLULAR_MATERIAL = "other_cellular_material"
    ORGANELLE = "organelle"
    MEMBRANE = "membrane"
    VESICLE = "vesicle"
    CYTOSKELETAL_STRUCTURE = "cytoskeletal_structure"
    OTHER_SUBCELLULAR_STRUCTURE = "other_subcellular_structure"
    DNA = "dna"
    RNA = "rna"
    PROTEIN = "protein"
    VIRUS = "virus"
    OTHER_BIOMOLECULE_OR_VIRUS = "other_biomolecule_or_virus"
    ORGANIC_COMPOUND = "organic_compound"
    INORGANIC_COMPOUND = "inorganic_compound"
    SOLVENT = "solvent"
    DETERGENT = "detergent"
    DYE = "dye"
    OTHER_CHEMICAL = "other_chemical"
    BEADS = "beads"
    RESIN = "resin"
    PARTICLE = "particle"
    OTHER_PARTICULATE = "other_particulate"
    MEDIUM = "medium"
    BUFFER = "buffer"
    SUPPLEMENT = "supplement"
    MASTER_MIX = "master_mix"
    GRADIENT_MEDIUM = "gradient_medium"
    OTHER_FORMULATION = "other_formulation"


CONTENT_ENUM_TYPES: dict[str, type[StrEnum]] = {
    enum_type.__name__: enum_type for enum_type in (ContentKind, ContentType, ContainerKind)
}


def resolve_content_enum_member(enum_type: type[StrEnum], member: str) -> StrEnum | None:
    """Return a declared member while preserving its enum family."""
    return enum_type.__members__.get(member)


CONTENT_KIND_WHITELIST = frozenset(kind.value for kind in ContentKind)
CONTAINER_KIND_WHITELIST = frozenset(kind.value for kind in ContainerKind)

STANDARD_CONTENT_TYPES_BY_KIND_ENUM: Mapping[ContentKind, frozenset[ContentType]] = MappingProxyType({
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
})
STANDARD_CONTENT_TYPES_BY_KIND = MappingProxyType({
    kind.value: frozenset(content_type.value for content_type in content_types)
    for kind, content_types in STANDARD_CONTENT_TYPES_BY_KIND_ENUM.items()
})
FALLBACK_CONTENT_TYPE_BY_KIND = MappingProxyType({
    ContentKind.BIO_ENTITY.value: ContentType.OTHER_BIO_ENTITY.value,
    ContentKind.BIO_FLUID.value: ContentType.OTHER_BODY_FLUID.value,
    ContentKind.BIO_CELLULAR.value: ContentType.OTHER_CELLULAR_MATERIAL.value,
    ContentKind.BIO_SUBCELLULAR.value: ContentType.OTHER_SUBCELLULAR_STRUCTURE.value,
    ContentKind.BIO_MOLECULE_OR_VIRUS.value: ContentType.OTHER_BIOMOLECULE_OR_VIRUS.value,
    ContentKind.CHEMICAL.value: ContentType.OTHER_CHEMICAL.value,
    ContentKind.PARTICULATE.value: ContentType.OTHER_PARTICULATE.value,
    ContentKind.FORMULATION.value: ContentType.OTHER_FORMULATION.value,
})


@dataclass(frozen=True)
class ContentClassification:
    """A validated pair; source spellings and compatibility metadata live outside it."""

    kind: ContentKind
    type: ContentType

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Enforce real enum families and the canonical pair, including direct construction."""
        if self.kind.__class__ is not ContentKind or self.type.__class__ is not ContentType:
            raise TypeError("ContentClassification requires ContentKind and ContentType members")
        if self.type not in STANDARD_CONTENT_TYPES_BY_KIND_ENUM[self.kind]:
            raise ValueError(f"Unsupported content classification '{self.kind.value}/{self.type.value}'")

    def to_dict(self) -> dict[str, str]:
        """Serialize canonical values explicitly at a data boundary."""
        return {"kind": self.kind.value, "type": self.type.value}


def parse_content_kind(value: str | ContentKind) -> ContentKind | None:
    if type(value) not in (str, ContentKind):
        return None
    try:
        return ContentKind(value)
    except ValueError:
        return None


def parse_content_type(value: str | ContentType) -> ContentType | None:
    if type(value) not in (str, ContentType):
        return None
    try:
        return ContentType(value)
    except ValueError:
        return None


def parse_content_classification(
    kind_value: str | ContentKind, type_value: str | ContentType,
) -> ContentClassification | None:
    """Promote exact canonical tokens or members; never normalize or apply fallback."""
    kind = parse_content_kind(kind_value)
    content_type = parse_content_type(type_value)
    if kind is None or content_type is None:
        return None
    try:
        return ContentClassification(kind, content_type)
    except ValueError:
        return None


def is_standard_content_type(kind_value: str, type_value: str) -> bool:
    return parse_content_classification(kind_value, type_value) is not None


def is_allowed_content_type(kind_value: str, type_value: str) -> bool:
    return is_standard_content_type(kind_value, type_value)


def content_type_fallback_for_kind(kind_value: str) -> str | None:
    return FALLBACK_CONTENT_TYPE_BY_KIND.get(kind_value)
