"""Shared content vocabulary for validated content constructors."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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

LEGACY_CONTENT_KINDS = frozenset({"biosample", "reagent", "buffer", "control", "fraction", "waste", "other"})
KNOWN_CONTENT_KINDS = CONTENT_KIND_WHITELIST | LEGACY_CONTENT_KINDS


@dataclass(frozen=True)
class NormalizedContentClassification:
    kind: str
    type: str
    attrs: dict[str, str] = field(default_factory=dict)
    original_kind: str | None = None
    original_type: str | None = None

    @property
    def changed(self) -> bool:
        return (self.original_kind is not None and self.original_kind != self.kind) or (
            self.original_type is not None and self.original_type != self.type
        )


def _attrs(**values: str) -> dict[str, str]:
    return {key: value for key, value in values.items() if value}


_LEGACY_TYPE_ALIASES: dict[tuple[str, str], tuple[str, str, dict[str, str]]] = {
    ("biosample", "whole_blood"): (ContentKind.BIO_FLUID.value, ContentType.WHOLE_BLOOD.value, {}),
    ("biosample", "plasma"): (ContentKind.BIO_FLUID.value, ContentType.PLASMA.value, {}),
    ("biosample", "serum"): (ContentKind.BIO_FLUID.value, ContentType.SERUM.value, {}),
    ("biosample", "cell_pellet"): (
        ContentKind.BIO_CELLULAR.value,
        ContentType.OTHER_CELLULAR_MATERIAL.value,
        _attrs(state="pellet"),
    ),
    ("biosample", "cell_lysate"): (
        ContentKind.BIO_CELLULAR.value,
        ContentType.OTHER_CELLULAR_MATERIAL.value,
        _attrs(state="lysate"),
    ),
    ("biosample", "cell_suspension"): (
        ContentKind.BIO_CELLULAR.value,
        ContentType.OTHER_CELLULAR_MATERIAL.value,
        _attrs(state="suspension"),
    ),
    ("biosample", "mixed_cells"): (
        ContentKind.BIO_CELLULAR.value,
        ContentType.CELL_POPULATION.value,
        _attrs(state="mixed"),
    ),
    ("biosample", "adherent_cells"): (
        ContentKind.BIO_CELLULAR.value,
        ContentType.CELL_LINE.value,
        _attrs(culture_state="adherent"),
    ),
    ("biosample", "tissue_piece"): (ContentKind.BIO_ENTITY.value, ContentType.TISSUE.value, {}),
    ("biosample", "cell_or_tissue_sample"): (
        ContentKind.BIO_ENTITY.value,
        ContentType.OTHER_BIO_ENTITY.value,
        {},
    ),
    ("biosample", "dna_sample"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.DNA.value, {}),
    ("biosample", "dna"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.DNA.value, {}),
    ("biosample", "rna"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.RNA.value, {}),
    ("biosample", "protein"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.PROTEIN.value, {}),
    ("biosample", "sample_dna"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.DNA.value, {}),
    ("biosample", "dna_solution"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        _attrs(state="solution"),
    ),
    ("biosample", "dna_lysate"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        _attrs(state="lysate"),
    ),
    ("biosample", "dna_stock"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        _attrs(state="stock"),
    ),
    ("biosample", "purified_dna"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        _attrs(state="purified"),
    ),
    ("biosample", "template_dna"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        _attrs(role="template"),
    ),
    ("biosample", "amplicon"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        _attrs(product_type="amplicon"),
    ),
    ("biosample", "plasmid_vector"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        _attrs(molecule_subtype="plasmid", role="vector"),
    ),
    ("biosample", "dna_insert"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        _attrs(role="insert"),
    ),
    ("biosample", "extract"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.OTHER_BIOMOLECULE_OR_VIRUS.value, _attrs(state="extract")),
    ("biosample", "molecular_extract"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.OTHER_BIOMOLECULE_OR_VIRUS.value,
        _attrs(state="extract"),
    ),
    ("biosample", "reaction_mix"): (
        ContentKind.FORMULATION.value,
        ContentType.MASTER_MIX.value,
        _attrs(state="reaction_assembled"),
    ),
    ("biosample", "solution"): (ContentKind.BIO_FLUID.value, ContentType.OTHER_BODY_FLUID.value, _attrs(state="solution")),
    ("buffer", "buffer"): (ContentKind.FORMULATION.value, ContentType.BUFFER.value, {}),
    ("buffer", "water"): (ContentKind.CHEMICAL.value, ContentType.SOLVENT.value, _attrs(role="carrier")),
    ("buffer", "diluent"): (ContentKind.CHEMICAL.value, ContentType.SOLVENT.value, _attrs(role="carrier")),
    ("buffer", "culture_media"): (ContentKind.FORMULATION.value, ContentType.MEDIUM.value, {}),
    ("buffer", "culture_medium"): (ContentKind.FORMULATION.value, ContentType.MEDIUM.value, {}),
    ("buffer", "media"): (ContentKind.FORMULATION.value, ContentType.MEDIUM.value, {}),
    ("buffer", "reaction_media"): (ContentKind.FORMULATION.value, ContentType.MEDIUM.value, _attrs(role="reaction_environment")),
    ("buffer", "drug_stock"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(state="stock")),
    ("reagent", "taq_polymerase"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.PROTEIN.value, _attrs(role="enzyme")),
    ("reagent", "enzyme"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.PROTEIN.value, _attrs(role="enzyme")),
    ("reagent", "fluor_antibody"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.PROTEIN.value, _attrs(role="antibody")),
    ("reagent", "qpcr_master_mix"): (ContentKind.FORMULATION.value, ContentType.MASTER_MIX.value, {}),
    ("reagent", "standard_mix"): (ContentKind.FORMULATION.value, ContentType.MASTER_MIX.value, _attrs(role="standard")),
    ("reagent", "fluor_quant_mix"): (ContentKind.FORMULATION.value, ContentType.MASTER_MIX.value, _attrs(role="detection")),
    ("reagent", "feed"): (ContentKind.FORMULATION.value, ContentType.SUPPLEMENT.value, {}),
    ("reagent", "nutrient_feed"): (ContentKind.FORMULATION.value, ContentType.SUPPLEMENT.value, {}),
    ("reagent", "dna_stain"): (ContentKind.CHEMICAL.value, ContentType.DYE.value, _attrs(role="stain")),
    ("reagent", "plate_stain"): (ContentKind.CHEMICAL.value, ContentType.DYE.value, _attrs(role="stain")),
    ("reagent", "anticoagulant"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(role="anticoagulant")),
    ("reagent", "precipitation_reagent"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(role="precipitation")),
    ("reagent", "cleanup_reagent"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(role="cleanup")),
    ("reagent", "fragmentation_reagent"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(role="fragmentation")),
    ("reagent", "adapter_mix"): (ContentKind.FORMULATION.value, ContentType.MASTER_MIX.value, _attrs(role="adapter_ligation")),
    ("reagent", "ligation_reagent"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(role="ligation")),
    ("reagent", "amplification_reagent"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(role="amplification")),
    ("reagent", "ionization_reagent"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(role="ionization")),
    ("reagent", "magnetic_bead"): (ContentKind.PARTICULATE.value, ContentType.BEADS.value, _attrs(bead_property="magnetic")),
    ("reagent", "agarose_powder"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(chemical_class="polymer")),
    ("reagent", "powder"): (ContentKind.CHEMICAL.value, ContentType.OTHER_CHEMICAL.value, _attrs(state="powder")),
    ("reagent", "vehicle_control"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(workflow_role="control")),
    ("reagent", "positive_control_compound"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(workflow_role="control")),
    ("reagent", "compound_x_low"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(dose_group="low")),
    ("reagent", "compound_x_mid"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(dose_group="mid")),
    ("reagent", "compound_x_high"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(dose_group="high")),
    ("reagent", "compound_x_max"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(dose_group="max")),
    ("reagent", "drug_x"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, {}),
    ("reagent", "compound_x_stock"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, _attrs(state="stock")),
    ("fraction", "supernatant"): (ContentKind.BIO_FLUID.value, ContentType.OTHER_BODY_FLUID.value, _attrs(workflow_role="fraction", output_role="supernatant")),
    ("fraction", "filtrate"): (ContentKind.BIO_FLUID.value, ContentType.OTHER_BODY_FLUID.value, _attrs(workflow_role="fraction", output_role="filtrate")),
    ("fraction", "target_phase"): (ContentKind.BIO_FLUID.value, ContentType.OTHER_BODY_FLUID.value, _attrs(workflow_role="fraction", output_role="target_phase")),
    ("fraction", "pellet"): (ContentKind.BIO_CELLULAR.value, ContentType.OTHER_CELLULAR_MATERIAL.value, _attrs(workflow_role="fraction", output_role="pellet")),
    ("fraction", "precipitate"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.OTHER_BIOMOLECULE_OR_VIRUS.value, _attrs(workflow_role="fraction", output_role="precipitate")),
    ("fraction", "retentate"): (ContentKind.BIO_CELLULAR.value, ContentType.OTHER_CELLULAR_MATERIAL.value, _attrs(workflow_role="fraction", output_role="retentate")),
    ("fraction", "washed_dna_pellet"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.DNA.value, _attrs(state="washed_pellet")),
}

for _buffer_type, _role in {
    "lysis_buffer": "lysis",
    "wash_buffer": "wash",
    "te_buffer": "storage",
    "binding_buffer": "binding",
    "elution_buffer": "elution",
    "resuspension_buffer": "storage",
    "ethanol_wash_buffer": "wash",
    "column_wash_buffer": "wash",
    "column_wash_buffer_1": "wash",
    "column_wash_buffer_2": "wash",
    "phosphate_buffer": "reaction_environment",
    "reaction_buffer": "reaction_environment",
    "nucleic_acid_extraction_buffer": "lysis",
    "molecular_extraction_buffer": "lysis",
    "sequencing_read_buffer": "reaction_environment",
    "test_buffer": "reaction_environment",
}.items():
    attrs = _attrs(role=_role)
    if _buffer_type.endswith("_1"):
        attrs["kit_step"] = "1"
    elif _buffer_type.endswith("_2"):
        attrs["kit_step"] = "2"
    _LEGACY_TYPE_ALIASES[("buffer", _buffer_type)] = (ContentKind.FORMULATION.value, ContentType.BUFFER.value, attrs)

for _kind, _type in list(_LEGACY_TYPE_ALIASES):
    if _kind == "buffer":
        _LEGACY_TYPE_ALIASES[(ContentKind.FORMULATION.value, _type)] = _LEGACY_TYPE_ALIASES[(_kind, _type)]


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
    return kind_value in CONTENT_KIND_WHITELIST and is_standard_content_type(kind_value, type_value)


def is_legacy_content_kind(kind_value: str) -> bool:
    return kind_value in LEGACY_CONTENT_KINDS


def normalize_content_classification(kind_value: str, type_value: str) -> NormalizedContentClassification:
    kind = kind_value.lower()
    content_type = type_value.lower()
    original_kind = kind
    original_type = content_type
    if is_standard_content_type(kind, content_type):
        return NormalizedContentClassification(kind=kind, type=content_type, original_kind=original_kind, original_type=original_type)

    legacy = _LEGACY_TYPE_ALIASES.get((kind, content_type))
    if legacy is not None:
        target_kind, target_type, attrs = legacy
        return NormalizedContentClassification(
            kind=target_kind,
            type=target_type,
            attrs=dict(attrs),
            original_kind=original_kind,
            original_type=original_type,
        )

    if kind == "blood":
        return NormalizedContentClassification(
            kind=ContentKind.BIO_FLUID.value,
            type=ContentType.WHOLE_BLOOD.value,
            original_kind=original_kind,
            original_type=original_type,
        )

    if kind in CONTENT_KIND_WHITELIST:
        return NormalizedContentClassification(
            kind=kind,
            type=FALLBACK_CONTENT_TYPE_BY_KIND[kind],
            attrs={"original_type": content_type},
            original_kind=original_kind,
            original_type=original_type,
        )

    if kind == "biosample":
        return NormalizedContentClassification(
            kind=ContentKind.BIO_MOLECULE_OR_VIRUS.value,
            type=ContentType.OTHER_BIOMOLECULE_OR_VIRUS.value,
            attrs={"original_type": content_type},
            original_kind=original_kind,
            original_type=original_type,
        )
    if kind == "buffer":
        return NormalizedContentClassification(
            kind=ContentKind.FORMULATION.value,
            type=ContentType.BUFFER.value,
            attrs={"original_type": content_type},
            original_kind=original_kind,
            original_type=original_type,
        )
    if kind == "reagent":
        return NormalizedContentClassification(
            kind=ContentKind.CHEMICAL.value,
            type=ContentType.OTHER_CHEMICAL.value,
            attrs={"original_type": content_type},
            original_kind=original_kind,
            original_type=original_type,
        )
    if kind == "control":
        return NormalizedContentClassification(
            kind=ContentKind.CHEMICAL.value,
            type=ContentType.OTHER_CHEMICAL.value,
            attrs={"workflow_role": "control", "original_type": content_type},
            original_kind=original_kind,
            original_type=original_type,
        )
    if kind == "waste":
        return NormalizedContentClassification(
            kind=ContentKind.FORMULATION.value,
            type=ContentType.OTHER_FORMULATION.value,
            attrs={"disposition": "waste", "original_type": content_type},
            original_kind=original_kind,
            original_type=original_type,
        )
    if kind == "fraction":
        return NormalizedContentClassification(
            kind=ContentKind.BIO_FLUID.value,
            type=ContentType.OTHER_BODY_FLUID.value,
            attrs={"workflow_role": "fraction", "original_type": content_type},
            original_kind=original_kind,
            original_type=original_type,
        )
    return NormalizedContentClassification(
        kind=kind,
        type=content_type,
        original_kind=original_kind,
        original_type=original_type,
    )


def content_type_fallback_for_kind(kind_value: str) -> str | None:
    return FALLBACK_CONTENT_TYPE_BY_KIND.get(kind_value)


def parse_content_spec_sugar(value: str) -> ContentSpecSugar | None:
    try:
        return ContentSpecSugar(value)
    except ValueError:
        return None
