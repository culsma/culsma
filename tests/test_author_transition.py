from __future__ import annotations

from copy import deepcopy

import pytest

from culsma.runtime.material.author_transition import (
    ExplicitMaterialTransition,
    MaterialEntryIndexSelector,
    apply_explicit_material_transition,
    resolve_material_entry,
    validate_author_transition_state,
)
from culsma.scientific_model.material import (
    AUTHOR_SETTABLE_MATERIAL_RELATIONS,
    COMPONENT_BOUND_MATERIAL_RELATIONS,
    AssociationTarget,
    AssociationTargetKind,
    MaterialRelation,
    RelationshipTransition,
)


def _entry(
    *,
    entry_id: str = "RPE1",
    content_ref: str = "RPE1",
    relation: str = "container_surface",
    associated_with: str | None = "source",
    association_target_kind: str | None = "container",
    amount: float = 100000.0,
) -> dict[str, object]:
    return {
        "entry_id": entry_id,
        "content_ref": content_ref,
        "amount": amount,
        "quantity": {
            "dimension": "count",
            "unit": "cells",
            "value": amount,
        },
        "relation": relation,
        "associated_with": associated_with,
        "association_target_kind": association_target_kind,
        "preservation": "adherent_monolayer",
        "label": "source_surface",
    }


def _transition(
    index: int = 0,
    *,
    to: MaterialRelation = MaterialRelation.FREE,
    associated_index: int | None = None,
) -> ExplicitMaterialTransition:
    return ExplicitMaterialTransition(
        subject=MaterialEntryIndexSelector(
            container_ref="source",
            index=index,
        ),
        output_key="1",
        next_relation=to,
        next_association_selector=(
            MaterialEntryIndexSelector("source", associated_index)
            if associated_index is not None
            else None
        ),
    )


def test_apply_explicit_material_transition_releases_unique_surface_entry() -> None:
    entries = [
        _entry(),
        _entry(
            entry_id="DMEM",
            content_ref="DMEM",
            relation="free",
            associated_with=None,
            association_target_kind=None,
            amount=300.0,
        ),
    ]
    original = deepcopy(entries)

    result = apply_explicit_material_transition(
        transition=_transition(),
        source_id="source",
        source_entries=entries,
    )

    assert result.applied
    assert result.issues == ()
    assert result.source_entry is not None
    assert result.source_entry.entry_id == "RPE1"
    assert result.source_entry.relation is MaterialRelation.CONTAINER_SURFACE
    assert result.source_entry.associated_with == "source"
    assert result.projection is not None
    assert result.projection.relation is MaterialRelation.FREE
    assert result.projection.associated_with is None
    assert result.projection.association_target_kind is None
    assert result.projection.preservation is None
    assert result.projection.label is None
    assert result.decision is not None
    assert result.decision.decision_source == "author"
    assert len(result.decision.transitions) == 1
    decision = result.decision.transitions[0]
    assert decision.component_entry_id == "RPE1@1"
    assert decision.next_relation is MaterialRelation.FREE
    assert decision.next_association_target is None
    assert entries == original


def test_resolve_material_entry_returns_read_only_material_entry_ref() -> None:
    resolution = resolve_material_entry(
        selector=MaterialEntryIndexSelector("source", 0),
        source_id="source",
        entries=[_entry()],
    )

    assert resolution.resolved
    assert resolution.entry is not None
    assert resolution.entry.content_ref == "RPE1"
    assert resolution.entry.quantity == {
        "dimension": "count",
        "unit": "cells",
        "value": 100000.0,
    }
    assert resolution.entry.quantity is not None
    with pytest.raises(TypeError):
        resolution.entry.quantity["value"] = 1.0


def test_resolve_material_entry_rejects_out_of_range_index() -> None:
    result = apply_explicit_material_transition(
        transition=_transition(1),
        source_id="source",
        source_entries=[_entry()],
    )

    assert not result.applied
    assert [issue.code for issue in result.issues] == [
        "MAT_MATERIAL_INDEX_OUT_OF_RANGE"
    ]


def test_resolve_material_entry_indexes_duplicate_content_refs_independently() -> None:
    entries = [
        _entry(entry_id="RPE1@surface"),
        _entry(
            entry_id="RPE1@free",
            relation="free",
            associated_with=None,
            association_target_kind=None,
        ),
    ]

    first = resolve_material_entry(
        selector=MaterialEntryIndexSelector("source", 0),
        source_id="source",
        entries=entries,
    )
    second = resolve_material_entry(
        selector=MaterialEntryIndexSelector("source", 1),
        source_id="source",
        entries=entries,
    )

    assert first.resolved and first.entry is not None
    assert second.resolved and second.entry is not None
    assert first.entry.entry_id == "RPE1@surface"
    assert second.entry.entry_id == "RPE1@free"


def test_resolve_material_entry_ignores_zero_quantity_compatibility_entry() -> None:
    entries = [
        _entry(entry_id="RPE1@empty", amount=0.0),
        _entry(entry_id="RPE1@surface"),
    ]

    resolution = resolve_material_entry(
        selector=MaterialEntryIndexSelector("source", 0),
        source_id="source",
        entries=entries,
    )

    assert resolution.resolved
    assert resolution.entry is not None
    assert resolution.entry.entry_id == "RPE1@surface"


def test_transition_rejects_subject_from_another_container() -> None:
    transition = ExplicitMaterialTransition(
        subject=MaterialEntryIndexSelector("other", 0),
        output_key="1",
        next_relation=MaterialRelation.FREE,
    )

    result = apply_explicit_material_transition(
        transition=transition,
        source_id="source",
        source_entries=[_entry()],
    )

    assert not result.applied
    assert [issue.code for issue in result.issues] == [
        "MAT_MATERIAL_SELECTOR_CONTAINER_MISMATCH"
    ]


def test_transition_graph_accepts_free_to_free_without_pair_whitelist() -> None:
    free_entry = _entry(
        relation="free",
        associated_with=None,
        association_target_kind=None,
    )

    result = apply_explicit_material_transition(
        transition=_transition(),
        source_id="source",
        source_entries=[free_entry],
    )

    assert result.applied
    assert result.source_entry is not None
    assert result.source_entry.relation is MaterialRelation.FREE
    assert result.issues == ()


def test_transition_rejects_unresolved_source_relation() -> None:
    result = apply_explicit_material_transition(
        transition=_transition(),
        source_id="source",
        source_entries=[
            _entry(
                relation="unresolved",
                associated_with=None,
                association_target_kind=None,
            )
        ],
    )

    assert not result.applied
    assert [issue.code for issue in result.issues] == [
        "MAT_MATERIAL_RELATION_INVALID"
    ]


def test_transition_target_must_be_material_relation_enum() -> None:
    with pytest.raises(TypeError):
        ExplicitMaterialTransition(
            subject=MaterialEntryIndexSelector("source", 0),
            output_key="1",
            next_relation="free",
        )

    with pytest.raises(TypeError):
        RelationshipTransition(
            component_entry_id="RPE1",
            next_relation="free",
        )


def test_author_target_domain_is_closed_and_excludes_unresolved() -> None:
    assert AUTHOR_SETTABLE_MATERIAL_RELATIONS == frozenset(MaterialRelation) - {
        MaterialRelation.UNRESOLVED
    }


@pytest.mark.parametrize("current_relation", AUTHOR_SETTABLE_MATERIAL_RELATIONS)
@pytest.mark.parametrize("next_relation", AUTHOR_SETTABLE_MATERIAL_RELATIONS)
def test_every_defined_author_state_pair_is_accepted(
    current_relation: MaterialRelation,
    next_relation: MaterialRelation,
) -> None:
    target = (
        AssociationTarget(AssociationTargetKind.COMPONENT_ENTRY, "support")
        if next_relation in COMPONENT_BOUND_MATERIAL_RELATIONS
        else None
    )

    result = validate_author_transition_state(
        current_relation=current_relation,
        next_relation=next_relation,
        next_association_target=target,
    )

    assert result.is_valid, result.issues


def test_bead_bound_to_free_clears_component_entry_association() -> None:
    result = apply_explicit_material_transition(
        transition=_transition(),
        source_id="source",
        source_entries=[
            _entry(
                entry_id="GFP_TARGET_PROTEIN",
                content_ref="GFP_TARGET_PROTEIN",
                relation="bead_bound",
                associated_with="PROTEIN_G_MAGNETIC_BEADS",
                association_target_kind="component_entry",
            ),
            _entry(
                entry_id="PROTEIN_G_MAGNETIC_BEADS",
                content_ref="PROTEIN_G_MAGNETIC_BEADS",
                relation="free",
                associated_with=None,
                association_target_kind=None,
            ),
        ],
    )

    assert result.applied, result.issues
    assert result.source_entry is not None
    assert result.source_entry.relation is MaterialRelation.BEAD_BOUND
    assert result.projection is not None
    assert result.projection.relation is MaterialRelation.FREE
    assert result.projection.associated_with is None
    assert result.projection.association_target_kind is None


def test_component_bound_target_requires_typed_association_selector() -> None:
    missing = apply_explicit_material_transition(
        transition=_transition(to=MaterialRelation.BEAD_BOUND),
        source_id="source",
        source_entries=[_entry()],
    )
    accepted = apply_explicit_material_transition(
        transition=_transition(
            to=MaterialRelation.BEAD_BOUND,
            associated_index=1,
        ),
        source_id="source",
        source_entries=[
            _entry(),
            _entry(
                entry_id="BEADS",
                content_ref="BEADS",
                relation="free",
                associated_with=None,
                association_target_kind=None,
            ),
        ],
    )

    assert [issue.code for issue in missing.issues] == [
        "MAT_MATERIAL_TRANSITION_ASSOCIATION_REQUIRED"
    ]
    assert accepted.applied, accepted.issues
    assert accepted.projection is not None
    assert accepted.projection.associated_with == "BEADS"
    assert (
        accepted.projection.association_target_kind
        is AssociationTargetKind.COMPONENT_ENTRY
    )


@pytest.mark.parametrize("index", [-1, 0.5, True])
def test_material_entry_index_selector_requires_nonnegative_integer(index: object) -> None:
    with pytest.raises(ValueError):
        MaterialEntryIndexSelector("source", index)
