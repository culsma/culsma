"""Legacy taxonomy aliases and historical content classification normalization.

This data adapter is independent of source syntax and validation. Retiring old
source spelling does not require retiring historical classification conversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from culsma.common.content_contracts import (
    CONTENT_KIND_WHITELIST,
    FALLBACK_CONTENT_TYPE_BY_KIND,
    ContentKind,
    ContentType,
    ContentClassification,
    parse_content_classification,
    is_standard_content_type,
)

LEGACY_CONTENT_KINDS = frozenset({"blood", "biosample", "reagent", "buffer", "control", "fraction", "waste", "other"})
KNOWN_CONTENT_KINDS = CONTENT_KIND_WHITELIST | LEGACY_CONTENT_KINDS


@dataclass(frozen=True)
class NormalizedContentClassification:
    kind: str
    type: str
    attrs: dict[str, str] = field(default_factory=dict)
    original_kind: str | None = None
    original_type: str | None = None

    @property
    def classification(self) -> ContentClassification | None:
        """Promote only valid canonical results, preserving unknown historical data."""
        return parse_content_classification(self.kind, self.type)

    @property
    def changed(self) -> bool:
        return (self.original_kind is not None and self.original_kind != self.kind) or (
            self.original_type is not None and self.original_type != self.type
        )


def classification_attrs(**values: str) -> dict[str, str]:
    return {key: value for key, value in values.items() if value}


LEGACY_TYPE_ALIASES: dict[tuple[str, str], tuple[str, str, dict[str, str]]] = {
    ("biosample", "whole_blood"): (ContentKind.BIO_FLUID.value, ContentType.WHOLE_BLOOD.value, {}),
    ("biosample", "plasma"): (ContentKind.BIO_FLUID.value, ContentType.PLASMA.value, {}),
    ("biosample", "serum"): (ContentKind.BIO_FLUID.value, ContentType.SERUM.value, {}),
    ("biosample", "cell_pellet"): (
        ContentKind.BIO_CELLULAR.value,
        ContentType.OTHER_CELLULAR_MATERIAL.value,
        classification_attrs(state="pellet"),
    ),
    ("biosample", "cell_lysate"): (
        ContentKind.BIO_CELLULAR.value,
        ContentType.OTHER_CELLULAR_MATERIAL.value,
        classification_attrs(state="lysate"),
    ),
    ("biosample", "cell_suspension"): (
        ContentKind.BIO_CELLULAR.value,
        ContentType.OTHER_CELLULAR_MATERIAL.value,
        classification_attrs(state="suspension"),
    ),
    ("biosample", "mixed_cells"): (
        ContentKind.BIO_CELLULAR.value,
        ContentType.CELL_POPULATION.value,
        classification_attrs(state="mixed"),
    ),
    ("biosample", "adherent_cells"): (
        ContentKind.BIO_CELLULAR.value,
        ContentType.CELL_LINE.value,
        classification_attrs(state="adherent"),
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
        classification_attrs(state="solution"),
    ),
    ("biosample", "dna_lysate"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        classification_attrs(state="lysate"),
    ),
    ("biosample", "dna_stock"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        classification_attrs(state="stock"),
    ),
    ("biosample", "purified_dna"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        classification_attrs(state="purified"),
    ),
    ("biosample", "template_dna"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        classification_attrs(role="template"),
    ),
    ("biosample", "amplicon"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        classification_attrs(product_type="amplicon"),
    ),
    ("biosample", "plasmid_vector"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        classification_attrs(molecule_subtype="plasmid", role="vector"),
    ),
    ("biosample", "dna_insert"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.DNA.value,
        classification_attrs(role="insert"),
    ),
    ("biosample", "extract"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.OTHER_BIOMOLECULE_OR_VIRUS.value, classification_attrs(state="extract")),
    ("biosample", "molecular_extract"): (
        ContentKind.BIO_MOLECULE_OR_VIRUS.value,
        ContentType.OTHER_BIOMOLECULE_OR_VIRUS.value,
        classification_attrs(state="extract"),
    ),
    ("biosample", "reaction_mix"): (
        ContentKind.FORMULATION.value,
        ContentType.MASTER_MIX.value,
        classification_attrs(state="reaction_assembled"),
    ),
    ("biosample", "solution"): (ContentKind.BIO_FLUID.value, ContentType.OTHER_BODY_FLUID.value, classification_attrs(state="solution")),
    ("buffer", "buffer"): (ContentKind.FORMULATION.value, ContentType.BUFFER.value, {}),
    ("buffer", "water"): (ContentKind.CHEMICAL.value, ContentType.SOLVENT.value, classification_attrs(role="carrier")),
    ("buffer", "diluent"): (ContentKind.CHEMICAL.value, ContentType.SOLVENT.value, classification_attrs(role="carrier")),
    ("buffer", "culture_media"): (ContentKind.FORMULATION.value, ContentType.MEDIUM.value, {}),
    ("buffer", "culture_medium"): (ContentKind.FORMULATION.value, ContentType.MEDIUM.value, {}),
    ("buffer", "media"): (ContentKind.FORMULATION.value, ContentType.MEDIUM.value, {}),
    ("buffer", "reaction_media"): (ContentKind.FORMULATION.value, ContentType.MEDIUM.value, classification_attrs(role="reaction_environment")),
    ("buffer", "drug_stock"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(state="stock")),
    ("reagent", "taq_polymerase"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.PROTEIN.value, classification_attrs(role="enzyme")),
    ("reagent", "enzyme"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.PROTEIN.value, classification_attrs(role="enzyme")),
    ("reagent", "fluor_antibody"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.PROTEIN.value, classification_attrs(role="antibody")),
    ("reagent", "qpcr_master_mix"): (ContentKind.FORMULATION.value, ContentType.MASTER_MIX.value, {}),
    ("reagent", "standard_mix"): (ContentKind.FORMULATION.value, ContentType.MASTER_MIX.value, classification_attrs(role="standard")),
    ("reagent", "fluor_quant_mix"): (ContentKind.FORMULATION.value, ContentType.MASTER_MIX.value, classification_attrs(role="detection")),
    ("reagent", "feed"): (ContentKind.FORMULATION.value, ContentType.SUPPLEMENT.value, {}),
    ("reagent", "nutrient_feed"): (ContentKind.FORMULATION.value, ContentType.SUPPLEMENT.value, {}),
    ("reagent", "dna_stain"): (ContentKind.CHEMICAL.value, ContentType.DYE.value, classification_attrs(role="stain")),
    ("reagent", "plate_stain"): (ContentKind.CHEMICAL.value, ContentType.DYE.value, classification_attrs(role="stain")),
    ("reagent", "anticoagulant"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(role="anticoagulant")),
    ("reagent", "precipitation_reagent"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(role="precipitation")),
    ("reagent", "cleanup_reagent"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(role="cleanup")),
    ("reagent", "fragmentation_reagent"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(role="fragmentation")),
    ("reagent", "adapter_mix"): (ContentKind.FORMULATION.value, ContentType.MASTER_MIX.value, classification_attrs(role="adapter_ligation")),
    ("reagent", "ligation_reagent"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(role="ligation")),
    ("reagent", "amplification_reagent"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(role="amplification")),
    ("reagent", "ionization_reagent"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(role="ionization")),
    ("reagent", "magnetic_bead"): (ContentKind.PARTICULATE.value, ContentType.BEADS.value, classification_attrs(bead_property="magnetic")),
    ("reagent", "agarose_powder"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(chemical_class="polymer")),
    ("reagent", "powder"): (ContentKind.CHEMICAL.value, ContentType.OTHER_CHEMICAL.value, classification_attrs(state="powder")),
    ("reagent", "vehicle_control"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(workflow_role="control")),
    ("reagent", "positive_control_compound"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(workflow_role="control")),
    ("reagent", "compound_x_low"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(dose_group="low")),
    ("reagent", "compound_x_mid"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(dose_group="mid")),
    ("reagent", "compound_x_high"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(dose_group="high")),
    ("reagent", "compound_x_max"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(dose_group="max")),
    ("reagent", "drug_x"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, {}),
    ("reagent", "compound_x_stock"): (ContentKind.CHEMICAL.value, ContentType.ORGANIC_COMPOUND.value, classification_attrs(state="stock")),
    ("fraction", "supernatant"): (ContentKind.BIO_FLUID.value, ContentType.OTHER_BODY_FLUID.value, classification_attrs(workflow_role="fraction", output_role="supernatant")),
    ("fraction", "filtrate"): (ContentKind.BIO_FLUID.value, ContentType.OTHER_BODY_FLUID.value, classification_attrs(workflow_role="fraction", output_role="filtrate")),
    ("fraction", "target_phase"): (ContentKind.BIO_FLUID.value, ContentType.OTHER_BODY_FLUID.value, classification_attrs(workflow_role="fraction", output_role="target_phase")),
    ("fraction", "pellet"): (ContentKind.BIO_CELLULAR.value, ContentType.OTHER_CELLULAR_MATERIAL.value, classification_attrs(workflow_role="fraction", output_role="pellet")),
    ("fraction", "precipitate"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.OTHER_BIOMOLECULE_OR_VIRUS.value, classification_attrs(workflow_role="fraction", output_role="precipitate")),
    ("fraction", "retentate"): (ContentKind.BIO_CELLULAR.value, ContentType.OTHER_CELLULAR_MATERIAL.value, classification_attrs(workflow_role="fraction", output_role="retentate")),
    ("fraction", "washed_dna_pellet"): (ContentKind.BIO_MOLECULE_OR_VIRUS.value, ContentType.DNA.value, classification_attrs(state="washed_pellet")),
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
    attrs = classification_attrs(role=_role)
    if _buffer_type.endswith("_1"):
        attrs["kit_step"] = "1"
    elif _buffer_type.endswith("_2"):
        attrs["kit_step"] = "2"
    LEGACY_TYPE_ALIASES[("buffer", _buffer_type)] = (ContentKind.FORMULATION.value, ContentType.BUFFER.value, attrs)

for _kind, _type in list(LEGACY_TYPE_ALIASES):
    if _kind == "buffer":
        LEGACY_TYPE_ALIASES[(ContentKind.FORMULATION.value, _type)] = LEGACY_TYPE_ALIASES[(_kind, _type)]


def is_legacy_content_kind(kind_value: str) -> bool:
    return kind_value in LEGACY_CONTENT_KINDS


def normalize_content_classification(kind_value: str, type_value: str) -> NormalizedContentClassification:
    kind = kind_value.lower()
    content_type = type_value.lower()
    original_kind = kind
    original_type = content_type
    if is_standard_content_type(kind, content_type):
        return NormalizedContentClassification(kind=kind, type=content_type, original_kind=original_kind, original_type=original_type)

    legacy = LEGACY_TYPE_ALIASES.get((kind, content_type))
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


CONTENT_TYPE_CUSTOM_PREFIX = "custom_"


def is_custom_content_type(type_value: str) -> bool:
    return type_value.startswith(CONTENT_TYPE_CUSTOM_PREFIX) and len(type_value) > len(CONTENT_TYPE_CUSTOM_PREFIX)


def legacy_runtime_container_kind(value: str) -> str | None:
    """Preserve the generic container kind accepted by historical material plans."""
    return value if value == 'container' else None
