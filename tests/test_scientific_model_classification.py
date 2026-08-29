from __future__ import annotations

import pytest

from culsma.scientific_model.material import (
    CLASSIFICATION_RULES,
    CalculationGroup,
    ComponentSnapshot,
    QuantitySnapshot,
    RelationshipSnapshot,
    classify_canonical_content,
    classify_component,
)


@pytest.mark.parametrize(
    ("kind", "content_type", "rule_id", "group"),
    [
        ("bio_fluid", "plasma", "C10", CalculationGroup.MOBILE_PHASE),
        ("bio_fluid", "bronchoalveolar_lavage_fluid", "C10", CalculationGroup.MOBILE_PHASE),
        ("chemical", "detergent", "C11", CalculationGroup.MOBILE_PHASE),
        ("formulation", "medium", "C12", CalculationGroup.MOBILE_PHASE),
        ("bio_entity", "tissue", "C20", CalculationGroup.SEDIMENTABLE_MATERIAL),
        ("bio_cellular", "cell_line", "C21", CalculationGroup.SEDIMENTABLE_MATERIAL),
        ("bio_subcellular", "vesicle", "C22", CalculationGroup.SEDIMENTABLE_MATERIAL),
        ("particulate", "particle", "C23", CalculationGroup.SEDIMENTABLE_MATERIAL),
        ("particulate", "beads", "C30", CalculationGroup.CAPTURE_SUPPORT),
        ("bio_molecule_or_virus", "dna", "C40", CalculationGroup.CONTEXT_DEPENDENT_TARGET),
    ],
)
def test_table_1_classifies_each_reference_rule(
    kind: str,
    content_type: str,
    rule_id: str,
    group: CalculationGroup,
) -> None:
    match = classify_canonical_content(kind, content_type)

    assert match.rule_id == rule_id
    assert match.group is group


@pytest.mark.parametrize(
    ("kind", "content_type"),
    [
        ("bio_fluid", "whole_blood"),
        ("bio_fluid", "buffy_coat"),
        ("bio_cellular", "other_cellular_material"),
        ("formulation", "other_formulation"),
        ("custom_kind", "custom_type"),
        ("BIO_CELLULAR", "CELL_LINE"),
    ],
)
def test_table_1_exhaustive_rule_preserves_unknown_or_unlisted_identity(
    kind: str,
    content_type: str,
) -> None:
    match = classify_canonical_content(kind, content_type)

    assert match.rule_id == "C99"
    assert match.group is CalculationGroup.COMPOSITE_OR_UNKNOWN


def test_table_1_classifies_component_snapshot_without_mutating_identity() -> None:
    component = ComponentSnapshot(
        entry_id="cells:0",
        content_ref="HEK293T",
        canonical_kind="bio_cellular",
        canonical_type="cell_line",
        quantity=QuantitySnapshot(value=200000.0, unit="cells"),
        relationship=RelationshipSnapshot(relation="free"),
    )

    match = classify_component(component)

    assert match.rule_id == "C21"
    assert match.group is CalculationGroup.SEDIMENTABLE_MATERIAL
    assert component.canonical_kind == "bio_cellular"
    assert component.canonical_type == "cell_line"


def test_table_1_rules_are_priority_ordered_and_end_in_one_exhaustive_rule() -> None:
    priorities = [rule.priority for rule in CLASSIFICATION_RULES]
    exhaustive = [
        rule
        for rule in CLASSIFICATION_RULES
        if rule.canonical_kind is None and rule.canonical_types is None
    ]

    assert priorities == sorted(priorities)
    assert len(exhaustive) == 1
    assert exhaustive[0].rule_id == "C99"
    assert CLASSIFICATION_RULES[-1] is exhaustive[0]
