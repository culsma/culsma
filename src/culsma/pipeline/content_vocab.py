"""Shared content vocabulary for validated content constructors."""

from __future__ import annotations

import re
from enum import StrEnum


class ContentKind(StrEnum):
    BIOSAMPLE = "biosample"
    REAGENT = "reagent"
    BUFFER = "buffer"
    CONTROL = "control"
    FRACTION = "fraction"
    WASTE = "waste"
    OTHER = "other"


class ContainerKind(StrEnum):
    TUBE = "tube"
    WELL = "well"
    CHAMBER = "chamber"
    SURFACE = "surface"


class ContentSpecSugar(StrEnum):
    CONTAINER = "container"
    TUBE = "tube"
    WELL = "well"
    CHAMBER = "chamber"
    SURFACE = "surface"
    CONTENT = "content"
    BLOOD = "blood"
    REAGENT = "reagent"
    BUFFER = "buffer"


class ContentType(StrEnum):
    WHOLE_BLOOD = "whole_blood"
    PLASMA = "plasma"
    SERUM = "serum"
    CELL_PELLET = "cell_pellet"
    CELL_LYSATE = "cell_lysate"
    CELL_SUSPENSION = "cell_suspension"
    DNA_SAMPLE = "dna_sample"
    SAMPLE_DNA = "sample_dna"
    DNA_SOLUTION = "dna_solution"
    DNA_LYSATE = "dna_lysate"
    DNA_STOCK = "dna_stock"
    PURIFIED_DNA = "purified_dna"
    TEMPLATE_DNA = "template_dna"
    AMPLICON = "amplicon"
    EXTRACT = "extract"
    REACTION_MIX = "reaction_mix"
    TISSUE_PIECE = "tissue_piece"
    MIXED_CELLS = "mixed_cells"
    ADHERENT_CELLS = "adherent_cells"
    PLASMID_VECTOR = "plasmid_vector"
    DNA_INSERT = "dna_insert"
    SOLUTION = "solution"
    CELL_OR_TISSUE_SAMPLE = "cell_or_tissue_sample"
    MOLECULAR_EXTRACT = "molecular_extract"
    BUFFER = "buffer"
    WATER = "water"
    DILUENT = "diluent"
    LYSIS_BUFFER = "lysis_buffer"
    WASH_BUFFER = "wash_buffer"
    TE_BUFFER = "te_buffer"
    BINDING_BUFFER = "binding_buffer"
    ELUTION_BUFFER = "elution_buffer"
    RESUSPENSION_BUFFER = "resuspension_buffer"
    ETHANOL_WASH_BUFFER = "ethanol_wash_buffer"
    COLUMN_WASH_BUFFER = "column_wash_buffer"
    COLUMN_WASH_BUFFER_1 = "column_wash_buffer_1"
    COLUMN_WASH_BUFFER_2 = "column_wash_buffer_2"
    PHOSPHATE_BUFFER = "phosphate_buffer"
    REACTION_BUFFER = "reaction_buffer"
    CULTURE_MEDIA = "culture_media"
    CULTURE_MEDIUM = "culture_medium"
    REACTION_MEDIA = "reaction_media"
    MEDIA = "media"
    DRUG_STOCK = "drug_stock"
    NUCLEIC_ACID_EXTRACTION_BUFFER = "nucleic_acid_extraction_buffer"
    MOLECULAR_EXTRACTION_BUFFER = "molecular_extraction_buffer"
    SEQUENCING_READ_BUFFER = "sequencing_read_buffer"
    TEST_BUFFER = "test_buffer"
    TAQ_POLYMERASE = "taq_polymerase"
    PRECIPITATION_REAGENT = "precipitation_reagent"
    FEED = "feed"
    NUTRIENT_FEED = "nutrient_feed"
    QPCR_MASTER_MIX = "qpcr_master_mix"
    DNA_STAIN = "dna_stain"
    ANTICOAGULANT = "anticoagulant"
    ENZYME = "enzyme"
    MAGNETIC_BEAD = "magnetic_bead"
    AGAROSE_POWDER = "agarose_powder"
    VEHICLE_CONTROL = "vehicle_control"
    POSITIVE_CONTROL_COMPOUND = "positive_control_compound"
    COMPOUND_X_LOW = "compound_x_low"
    COMPOUND_X_MID = "compound_x_mid"
    COMPOUND_X_HIGH = "compound_x_high"
    COMPOUND_X_MAX = "compound_x_max"
    DRUG_X = "drug_x"
    COMPOUND_X_STOCK = "compound_x_stock"
    STANDARD_MIX = "standard_mix"
    PLATE_STAIN = "plate_stain"
    FLUOR_QUANT_MIX = "fluor_quant_mix"
    FLUOR_ANTIBODY = "fluor_antibody"
    FRAGMENTATION_REAGENT = "fragmentation_reagent"
    ADAPTER_MIX = "adapter_mix"
    LIGATION_REAGENT = "ligation_reagent"
    CLEANUP_REAGENT = "cleanup_reagent"
    AMPLIFICATION_REAGENT = "amplification_reagent"
    IONIZATION_REAGENT = "ionization_reagent"
    POWDER = "powder"
    PELLET = "pellet"
    SUPERNATANT = "supernatant"
    RETENTATE = "retentate"
    FILTRATE = "filtrate"
    TARGET_PHASE = "target_phase"
    PRECIPITATE = "precipitate"
    WASHED_DNA_PELLET = "washed_dna_pellet"


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
    ContentSpecSugar.BLOOD.value: "DefineContent",
    ContentSpecSugar.REAGENT.value: "DefineContent",
    ContentSpecSugar.BUFFER.value: "DefineContent",
}
CONTENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
CONTENT_TYPE_CUSTOM_PREFIX = "custom_"

STANDARD_CONTENT_TYPES_BY_KIND_ENUM: dict[ContentKind, frozenset[ContentType]] = {
    ContentKind.BIOSAMPLE: frozenset(
        {
            ContentType.WHOLE_BLOOD,
            ContentType.PLASMA,
            ContentType.SERUM,
            ContentType.CELL_PELLET,
            ContentType.CELL_LYSATE,
            ContentType.CELL_SUSPENSION,
            ContentType.DNA_SAMPLE,
            ContentType.SAMPLE_DNA,
            ContentType.DNA_SOLUTION,
            ContentType.DNA_LYSATE,
            ContentType.DNA_STOCK,
            ContentType.PURIFIED_DNA,
            ContentType.TEMPLATE_DNA,
            ContentType.AMPLICON,
            ContentType.EXTRACT,
            ContentType.REACTION_MIX,
            ContentType.TISSUE_PIECE,
            ContentType.MIXED_CELLS,
            ContentType.ADHERENT_CELLS,
            ContentType.PLASMID_VECTOR,
            ContentType.DNA_INSERT,
            ContentType.SOLUTION,
            ContentType.CELL_OR_TISSUE_SAMPLE,
            ContentType.MOLECULAR_EXTRACT,
        }
    ),
    ContentKind.BUFFER: frozenset(
        {
            ContentType.BUFFER,
            ContentType.WATER,
            ContentType.DILUENT,
            ContentType.LYSIS_BUFFER,
            ContentType.WASH_BUFFER,
            ContentType.TE_BUFFER,
            ContentType.BINDING_BUFFER,
            ContentType.ELUTION_BUFFER,
            ContentType.RESUSPENSION_BUFFER,
            ContentType.ETHANOL_WASH_BUFFER,
            ContentType.COLUMN_WASH_BUFFER,
            ContentType.COLUMN_WASH_BUFFER_1,
            ContentType.COLUMN_WASH_BUFFER_2,
            ContentType.PHOSPHATE_BUFFER,
            ContentType.REACTION_BUFFER,
            ContentType.CULTURE_MEDIA,
            ContentType.CULTURE_MEDIUM,
            ContentType.REACTION_MEDIA,
            ContentType.MEDIA,
            ContentType.DRUG_STOCK,
            ContentType.NUCLEIC_ACID_EXTRACTION_BUFFER,
            ContentType.MOLECULAR_EXTRACTION_BUFFER,
            ContentType.SEQUENCING_READ_BUFFER,
            ContentType.TEST_BUFFER,
        }
    ),
    ContentKind.REAGENT: frozenset(
        {
            ContentType.TAQ_POLYMERASE,
            ContentType.PRECIPITATION_REAGENT,
            ContentType.FEED,
            ContentType.NUTRIENT_FEED,
            ContentType.QPCR_MASTER_MIX,
            ContentType.DNA_STAIN,
            ContentType.ANTICOAGULANT,
            ContentType.ENZYME,
            ContentType.MAGNETIC_BEAD,
            ContentType.AGAROSE_POWDER,
            ContentType.VEHICLE_CONTROL,
            ContentType.POSITIVE_CONTROL_COMPOUND,
            ContentType.COMPOUND_X_LOW,
            ContentType.COMPOUND_X_MID,
            ContentType.COMPOUND_X_HIGH,
            ContentType.COMPOUND_X_MAX,
            ContentType.DRUG_X,
            ContentType.COMPOUND_X_STOCK,
            ContentType.STANDARD_MIX,
            ContentType.PLATE_STAIN,
            ContentType.FLUOR_QUANT_MIX,
            ContentType.FLUOR_ANTIBODY,
            ContentType.FRAGMENTATION_REAGENT,
            ContentType.ADAPTER_MIX,
            ContentType.LIGATION_REAGENT,
            ContentType.CLEANUP_REAGENT,
            ContentType.AMPLIFICATION_REAGENT,
            ContentType.IONIZATION_REAGENT,
            ContentType.POWDER,
        }
    ),
    ContentKind.FRACTION: frozenset(
        {
            ContentType.PELLET,
            ContentType.SUPERNATANT,
            ContentType.RETENTATE,
            ContentType.FILTRATE,
            ContentType.TARGET_PHASE,
            ContentType.PRECIPITATE,
            ContentType.WASHED_DNA_PELLET,
        }
    ),
}

STANDARD_CONTENT_TYPES_BY_KIND = {
    kind.value: frozenset(content_type.value for content_type in content_types)
    for kind, content_types in STANDARD_CONTENT_TYPES_BY_KIND_ENUM.items()
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


def is_custom_content_type(type_value: str) -> bool:
    return type_value.startswith(CONTENT_TYPE_CUSTOM_PREFIX) and len(type_value) > len(CONTENT_TYPE_CUSTOM_PREFIX)


def is_allowed_content_type(kind_value: str, type_value: str) -> bool:
    return kind_value in CONTENT_KIND_WHITELIST and (is_standard_content_type(kind_value, type_value) or is_custom_content_type(type_value))


def parse_content_spec_sugar(value: str) -> ContentSpecSugar | None:
    try:
        return ContentSpecSugar(value)
    except ValueError:
        return None
