"""Table 1 classification for the built-in material Rulebook provider."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from culsma.common.content_contracts import ContentClassification, ContentKind, ContentType, parse_content_classification

from .contracts import ComponentSnapshot


class CalculationGroup(StrEnum):
    MOBILE_PHASE = "mobile_phase"
    SEDIMENTABLE_MATERIAL = "sedimentable_material"
    CAPTURE_SUPPORT = "capture_support"
    CONTEXT_DEPENDENT_TARGET = "context_dependent_target"
    COMPOSITE_OR_UNKNOWN = "composite_or_unknown"


@dataclass(frozen=True)
class ClassificationRule:
    rule_id: str
    priority: int
    canonical_kind: ContentKind | None
    canonical_types: frozenset[ContentType] | None
    result: CalculationGroup

    def matches(self, canonical_kind: str, canonical_type: str) -> bool:
        return self.matches_classification(parse_content_classification(canonical_kind, canonical_type))

    def matches_classification(self, classification: ContentClassification | None) -> bool:
        if self.canonical_kind is None and self.canonical_types is None:
            return True
        if classification is None:
            return False
        if self.canonical_kind is not None and classification.kind is not self.canonical_kind:
            return False
        return self.canonical_types is None or classification.type in self.canonical_types


@dataclass(frozen=True)
class ClassificationMatch:
    rule_id: str
    group: CalculationGroup


CLASSIFICATION_RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        rule_id="C10",
        priority=10,
        canonical_kind=ContentKind.BIO_FLUID,
        canonical_types=frozenset(
            {
                ContentType.PLASMA,
                ContentType.SERUM,
                ContentType.URINE,
                ContentType.SALIVA,
                ContentType.LYMPH,
                ContentType.CEREBROSPINAL_FLUID,
                ContentType.TEARS,
                ContentType.SEMEN,
                ContentType.ASCITES,
                ContentType.SYNOVIAL_FLUID,
                ContentType.BRONCHOALVEOLAR_LAVAGE_FLUID,
            }
        ),
        result=CalculationGroup.MOBILE_PHASE,
    ),
    ClassificationRule(
        rule_id="C11",
        priority=10,
        canonical_kind=ContentKind.CHEMICAL,
        canonical_types=frozenset(
            {ContentType.SOLVENT, ContentType.ORGANIC_COMPOUND, ContentType.INORGANIC_COMPOUND, ContentType.DETERGENT, ContentType.DYE}
        ),
        result=CalculationGroup.MOBILE_PHASE,
    ),
    ClassificationRule(
        rule_id="C12",
        priority=10,
        canonical_kind=ContentKind.FORMULATION,
        canonical_types=frozenset(
            {ContentType.BUFFER, ContentType.MEDIUM, ContentType.GRADIENT_MEDIUM, ContentType.SUPPLEMENT, ContentType.MASTER_MIX}
        ),
        result=CalculationGroup.MOBILE_PHASE,
    ),
    ClassificationRule(
        rule_id="C20",
        priority=10,
        canonical_kind=ContentKind.BIO_ENTITY,
        canonical_types=frozenset({ContentType.ORGANISM, ContentType.ORGAN, ContentType.TISSUE}),
        result=CalculationGroup.SEDIMENTABLE_MATERIAL,
    ),
    ClassificationRule(
        rule_id="C21",
        priority=10,
        canonical_kind=ContentKind.BIO_CELLULAR,
        canonical_types=frozenset(
            {ContentType.CELL_LINE, ContentType.PRIMARY_CELLS, ContentType.CELL_POPULATION, ContentType.MICROBIAL_CELLS}
        ),
        result=CalculationGroup.SEDIMENTABLE_MATERIAL,
    ),
    ClassificationRule(
        rule_id="C22",
        priority=10,
        canonical_kind=ContentKind.BIO_SUBCELLULAR,
        canonical_types=frozenset(
            {ContentType.ORGANELLE, ContentType.MEMBRANE, ContentType.VESICLE, ContentType.CYTOSKELETAL_STRUCTURE}
        ),
        result=CalculationGroup.SEDIMENTABLE_MATERIAL,
    ),
    ClassificationRule(
        rule_id="C23",
        priority=10,
        canonical_kind=ContentKind.PARTICULATE,
        canonical_types=frozenset({ContentType.PARTICLE}),
        result=CalculationGroup.SEDIMENTABLE_MATERIAL,
    ),
    ClassificationRule(
        rule_id="C30",
        priority=10,
        canonical_kind=ContentKind.PARTICULATE,
        canonical_types=frozenset({ContentType.BEADS, ContentType.RESIN}),
        result=CalculationGroup.CAPTURE_SUPPORT,
    ),
    ClassificationRule(
        rule_id="C40",
        priority=10,
        canonical_kind=ContentKind.BIO_MOLECULE_OR_VIRUS,
        canonical_types=frozenset({ContentType.DNA, ContentType.RNA, ContentType.PROTEIN, ContentType.VIRUS}),
        result=CalculationGroup.CONTEXT_DEPENDENT_TARGET,
    ),
    ClassificationRule(
        rule_id="C99",
        priority=99,
        canonical_kind=None,
        canonical_types=None,
        result=CalculationGroup.COMPOSITE_OR_UNKNOWN,
    ),
)


def classify_canonical_content(canonical_kind: str, canonical_type: str) -> ClassificationMatch:
    """Return the first Table 1 match without rewriting canonical identity."""

    return classify_content_classification(parse_content_classification(canonical_kind, canonical_type))


def classify_content_classification(classification: ContentClassification | None) -> ClassificationMatch:
    for rule in sorted(CLASSIFICATION_RULES, key=lambda candidate: candidate.priority):
        if rule.matches_classification(classification):
            return ClassificationMatch(rule_id=rule.rule_id, group=rule.result)
    raise AssertionError("Table 1 must end in an exhaustive rule")


def classify_component(component: ComponentSnapshot) -> ClassificationMatch:
    return classify_content_classification(component.classification)
