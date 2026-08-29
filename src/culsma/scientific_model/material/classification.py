"""Table 1 classification for the built-in material Rulebook provider."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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
    canonical_kind: str | None
    canonical_types: frozenset[str] | None
    result: CalculationGroup

    def matches(self, canonical_kind: str, canonical_type: str) -> bool:
        if self.canonical_kind is not None and canonical_kind != self.canonical_kind:
            return False
        return self.canonical_types is None or canonical_type in self.canonical_types


@dataclass(frozen=True)
class ClassificationMatch:
    rule_id: str
    group: CalculationGroup


CLASSIFICATION_RULES: tuple[ClassificationRule, ...] = (
    ClassificationRule(
        rule_id="C10",
        priority=10,
        canonical_kind="bio_fluid",
        canonical_types=frozenset(
            {
                "plasma",
                "serum",
                "urine",
                "saliva",
                "lymph",
                "cerebrospinal_fluid",
                "tears",
                "semen",
                "ascites",
                "synovial_fluid",
                "bronchoalveolar_lavage_fluid",
            }
        ),
        result=CalculationGroup.MOBILE_PHASE,
    ),
    ClassificationRule(
        rule_id="C11",
        priority=10,
        canonical_kind="chemical",
        canonical_types=frozenset(
            {"solvent", "organic_compound", "inorganic_compound", "detergent", "dye"}
        ),
        result=CalculationGroup.MOBILE_PHASE,
    ),
    ClassificationRule(
        rule_id="C12",
        priority=10,
        canonical_kind="formulation",
        canonical_types=frozenset(
            {"buffer", "medium", "gradient_medium", "supplement", "master_mix"}
        ),
        result=CalculationGroup.MOBILE_PHASE,
    ),
    ClassificationRule(
        rule_id="C20",
        priority=10,
        canonical_kind="bio_entity",
        canonical_types=frozenset({"organism", "organ", "tissue"}),
        result=CalculationGroup.SEDIMENTABLE_MATERIAL,
    ),
    ClassificationRule(
        rule_id="C21",
        priority=10,
        canonical_kind="bio_cellular",
        canonical_types=frozenset(
            {"cell_line", "primary_cells", "cell_population", "microbial_cells"}
        ),
        result=CalculationGroup.SEDIMENTABLE_MATERIAL,
    ),
    ClassificationRule(
        rule_id="C22",
        priority=10,
        canonical_kind="bio_subcellular",
        canonical_types=frozenset(
            {"organelle", "membrane", "vesicle", "cytoskeletal_structure"}
        ),
        result=CalculationGroup.SEDIMENTABLE_MATERIAL,
    ),
    ClassificationRule(
        rule_id="C23",
        priority=10,
        canonical_kind="particulate",
        canonical_types=frozenset({"particle"}),
        result=CalculationGroup.SEDIMENTABLE_MATERIAL,
    ),
    ClassificationRule(
        rule_id="C30",
        priority=10,
        canonical_kind="particulate",
        canonical_types=frozenset({"beads", "resin"}),
        result=CalculationGroup.CAPTURE_SUPPORT,
    ),
    ClassificationRule(
        rule_id="C40",
        priority=10,
        canonical_kind="bio_molecule_or_virus",
        canonical_types=frozenset({"dna", "rna", "protein", "virus"}),
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

    for rule in sorted(CLASSIFICATION_RULES, key=lambda candidate: candidate.priority):
        if rule.matches(canonical_kind, canonical_type):
            return ClassificationMatch(rule_id=rule.rule_id, group=rule.result)
    raise AssertionError("Table 1 must end in an exhaustive rule")


def classify_component(component: ComponentSnapshot) -> ClassificationMatch:
    return classify_canonical_content(component.canonical_kind, component.canonical_type)
