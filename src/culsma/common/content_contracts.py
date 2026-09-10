"""Shared content enums, independent of parser, pipeline and runtime."""

from __future__ import annotations

from enum import StrEnum


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
