from __future__ import annotations

import pytest

from culsma.scientific_model import ModelRequest, ModelStatus, create_default_scientific_model_resolver
from culsma.scientific_model.material import (
    MATERIAL_CONTRACT_VERSION,
    MATERIAL_SEPARATION_FATE,
    MATERIAL_STATE_TRANSITION,
    ComponentSnapshot,
    MaterialModelPayload,
    OperationSnapshot,
    OutputRoleSnapshot,
    QuantitySnapshot,
    RelationshipSnapshot,
    SeparationDecision,
    StateTransitionDecision,
)


def _component(
    *,
    entry_id: str,
    kind: str,
    content_type: str,
    relation: str = "free",
    quantity_value: float = 1.0,
    quantity_unit: str = "uL",
) -> ComponentSnapshot:
    return ComponentSnapshot(
        entry_id=entry_id,
        content_ref=entry_id.split(":", 1)[0],
        canonical_kind=kind,
        canonical_type=content_type,
        quantity=QuantitySnapshot(value=quantity_value, unit=quantity_unit),
        relationship=RelationshipSnapshot(relation=relation),
    )


def _request(capability: str, payload: MaterialModelPayload) -> ModelRequest:
    return ModelRequest(
        request_id=f"rulebook:{capability}",
        capability=capability,
        contract_version=MATERIAL_CONTRACT_VERSION,
        payload=payload,
    )


def _centrifuge_payload(component: ComponentSnapshot) -> MaterialModelPayload:
    return _separation_payload(
        component,
        program_kind="centrifuge_program",
        output_roles=("supernatant", "pellet"),
    )


def _separation_payload(
    component: ComponentSnapshot,
    *,
    program_kind: str,
    output_roles: tuple[str, str],
    context: dict[str, object] | None = None,
) -> MaterialModelPayload:
    return MaterialModelPayload(
        operation=OperationSnapshot(
            program_kind=program_kind,
            effect_kind="separation_fate",
            output_roles=(
                OutputRoleSnapshot(part_id="0", semantic_role=output_roles[0]),
                OutputRoleSnapshot(part_id="1", semantic_role=output_roles[1]),
            ),
        ),
        components=(component,),
        context=context or {},
    )


@pytest.mark.parametrize(
    ("component", "expected"),
    [
        (
            _component(entry_id="PBS:0", kind="formulation", content_type="buffer"),
            {"0": 1.0, "1": 0.0},
        ),
        (
            _component(
                entry_id="HEK293T:0",
                kind="bio_cellular",
                content_type="cell_line",
                quantity_value=200000.0,
                quantity_unit="cells",
            ),
            {"0": 0.0, "1": 1.0},
        ),
        (
            _component(entry_id="BEADS:0", kind="particulate", content_type="beads"),
            {"0": 0.0, "1": 1.0},
        ),
        (
            _component(entry_id="DNA:0", kind="bio_molecule_or_virus", content_type="dna"),
            {"0": 1.0, "1": 0.0},
        ),
        (
            _component(
                entry_id="PELLET:0",
                kind="bio_cellular",
                content_type="cell_line",
                relation="pellet",
            ),
            {"0": 0.0, "1": 1.0},
        ),
    ],
)
def test_table_2_centrifuge_exact_fates(
    component: ComponentSnapshot,
    expected: dict[str, float],
) -> None:
    result = create_default_scientific_model_resolver().resolve(
        _request(MATERIAL_SEPARATION_FATE, _centrifuge_payload(component))
    )

    assert result.status is ModelStatus.RESOLVED
    assert isinstance(result.proposal, SeparationDecision)
    assert dict(result.proposal.component_fates[0].fractions) == expected


def test_table_2_returns_unresolved_for_composite_group_instead_of_guessing() -> None:
    payload = _centrifuge_payload(
        _component(entry_id="BLOOD:0", kind="bio_fluid", content_type="whole_blood")
    )

    result = create_default_scientific_model_resolver().resolve(
        _request(MATERIAL_SEPARATION_FATE, payload)
    )

    assert result.status is ModelStatus.NOT_APPLICABLE
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "MATERIAL_RULEBOOK_UNRESOLVED"
    ]


@pytest.mark.parametrize(
    ("program_kind", "roles", "component", "context", "expected"),
    [
        (
            "centrifuge_program",
            ("supernatant", "pellet"),
            _component(
                entry_id="DNA_PRECIPITATE:0",
                kind="bio_molecule_or_virus",
                content_type="dna",
                relation="precipitate",
            ),
            {},
            {"0": 0.0, "1": 1.0},
        ),
        (
            "filtration_program",
            ("filtrate", "retentate"),
            _component(entry_id="PBS:0", kind="formulation", content_type="buffer"),
            {},
            {"0": 1.0, "1": 0.0},
        ),
        (
            "filtration_program",
            ("filtrate", "retentate"),
            _component(
                entry_id="CELLS:0",
                kind="bio_cellular",
                content_type="cell_population",
            ),
            {"filter_retains": {"CELLS:0": True}},
            {"0": 0.0, "1": 1.0},
        ),
        (
            "filtration_program",
            ("filtrate", "retentate"),
            _component(
                entry_id="DNA:0",
                kind="bio_molecule_or_virus",
                content_type="dna",
            ),
            {"filter_retains": {"DNA:0": True}},
            {"0": 0.0, "1": 1.0},
        ),
        (
            "filtration_program",
            ("filtrate", "retentate"),
            _component(
                entry_id="ADHERENT:0",
                kind="bio_cellular",
                content_type="cell_line",
                relation="container_surface",
            ),
            {"surface_preserved": {"ADHERENT:0": True}},
            {"0": 0.0, "1": 1.0},
        ),
        (
            "centrifugal_filtration_program",
            ("filtrate", "retentate"),
            _component(
                entry_id="MEMBRANE:0",
                kind="formulation",
                content_type="buffer",
                relation="membrane_bound",
            ),
            {},
            {"0": 0.0, "1": 1.0},
        ),
        (
            "precipitation_program",
            ("precipitate", "supernatant"),
            _component(entry_id="PBS:0", kind="formulation", content_type="buffer"),
            {},
            {"0": 0.0, "1": 1.0},
        ),
        (
            "precipitation_program",
            ("precipitate", "supernatant"),
            _component(
                entry_id="DNA:0",
                kind="bio_molecule_or_virus",
                content_type="dna",
                relation="precipitate",
            ),
            {},
            {"0": 1.0, "1": 0.0},
        ),
        (
            "magnetic_program",
            ("bound", "flowthrough"),
            _component(entry_id="PBS:0", kind="formulation", content_type="buffer"),
            {},
            {"0": 0.0, "1": 1.0},
        ),
        (
            "magnetic_program",
            ("bound", "flowthrough"),
            _component(entry_id="BEADS:0", kind="particulate", content_type="beads"),
            {"is_magnetic_support": {"BEADS:0": True}},
            {"0": 1.0, "1": 0.0},
        ),
    ],
)
def test_table_2_registered_exact_fates(
    program_kind: str,
    roles: tuple[str, str],
    component: ComponentSnapshot,
    context: dict[str, object],
    expected: dict[str, float],
) -> None:
    payload = _separation_payload(
        component,
        program_kind=program_kind,
        output_roles=roles,
        context=context,
    )

    result = create_default_scientific_model_resolver().resolve(
        _request(MATERIAL_SEPARATION_FATE, payload)
    )

    assert result.status is ModelStatus.RESOLVED
    assert isinstance(result.proposal, SeparationDecision)
    assert dict(result.proposal.component_fates[0].fractions) == expected


@pytest.mark.parametrize(
    ("program_kind", "roles"),
    [
        ("phase_partition_program", ("target_phase", "other_phase")),
        ("field_program", ("target_band_fraction", "non_target_fraction")),
    ],
)
def test_table_2_controlled_unresolved_programs_do_not_guess(
    program_kind: str,
    roles: tuple[str, str],
) -> None:
    payload = _separation_payload(
        _component(entry_id="DNA:0", kind="bio_molecule_or_virus", content_type="dna"),
        program_kind=program_kind,
        output_roles=roles,
    )

    result = create_default_scientific_model_resolver().resolve(
        _request(MATERIAL_SEPARATION_FATE, payload)
    )

    assert result.status is ModelStatus.NOT_APPLICABLE
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "MATERIAL_RULEBOOK_UNRESOLVED"
    ]


@pytest.mark.parametrize(
    ("component", "output_role", "expected_relation", "expected_label"),
    [
        (
            _component(entry_id="PBS:0", kind="formulation", content_type="buffer"),
            "supernatant",
            "free",
            "supernatant_output",
        ),
        (
            _component(
                entry_id="HEK293T:0",
                kind="bio_cellular",
                content_type="cell_line",
                quantity_value=200000.0,
                quantity_unit="cells",
            ),
            "pellet",
            "pellet",
            "pellet_output",
        ),
        (
            _component(
                entry_id="PELLET:0",
                kind="bio_cellular",
                content_type="cell_line",
                relation="pellet",
            ),
            "pellet",
            "pellet",
            "pellet_output",
        ),
    ],
)
def test_table_3_centrifuge_output_relationships(
    component: ComponentSnapshot,
    output_role: str,
    expected_relation: str,
    expected_label: str,
) -> None:
    payload = MaterialModelPayload(
        operation=OperationSnapshot(
            program_kind="centrifuge_program",
            effect_kind="separate",
            output_roles=(OutputRoleSnapshot(part_id="selected", semantic_role=output_role),),
        ),
        components=(component,),
    )

    result = create_default_scientific_model_resolver().resolve(
        _request(MATERIAL_STATE_TRANSITION, payload)
    )

    assert result.status is ModelStatus.RESOLVED
    assert isinstance(result.proposal, StateTransitionDecision)
    transition = result.proposal.transitions[0]
    assert transition.next_relation == expected_relation
    assert transition.next_label == expected_label


def test_table_3_returns_unresolved_for_unlisted_relationship() -> None:
    payload = MaterialModelPayload(
        operation=OperationSnapshot(
            program_kind="centrifuge_program",
            effect_kind="separate",
            output_roles=(OutputRoleSnapshot(part_id="1", semantic_role="pellet"),),
        ),
        components=(
            _component(
                entry_id="SURFACE:0",
                kind="bio_cellular",
                content_type="cell_line",
                relation="container_surface",
            ),
        ),
    )

    result = create_default_scientific_model_resolver().resolve(
        _request(MATERIAL_STATE_TRANSITION, payload)
    )

    assert result.status is ModelStatus.NOT_APPLICABLE
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "MATERIAL_RULEBOOK_UNRESOLVED"
    ]


@pytest.mark.parametrize(
    (
        "component",
        "effect_kind",
        "output_role",
        "context",
        "expected_relation",
        "expected_label",
    ),
    [
        (
            _component(
                entry_id="DNA:0",
                kind="bio_molecule_or_virus",
                content_type="dna",
            ),
            "separate",
            "precipitate",
            {"precipitation_established": True},
            "precipitate",
            "precipitate_output",
        ),
        (
            _component(
                entry_id="DNA:0",
                kind="bio_molecule_or_virus",
                content_type="dna",
            ),
            "separate",
            "bound",
            {"binding_established": True},
            "bead_bound",
            "bound_output",
        ),
        (
            _component(entry_id="BEADS:0", kind="particulate", content_type="beads"),
            "separate",
            "bound",
            {"field_retention_established": True},
            "field_retained",
            "bound_output",
        ),
        (
            _component(
                entry_id="ADHERENT:0",
                kind="bio_cellular",
                content_type="cell_line",
                relation="container_surface",
            ),
            "separate",
            "retentate",
            {"surface_preserved": True},
            "container_surface",
            "retentate_output",
        ),
        (
            _component(
                entry_id="PELLET:0",
                kind="bio_cellular",
                content_type="cell_line",
                relation="pellet",
            ),
            "resuspend",
            "destination",
            {"declared": True},
            "free",
            None,
        ),
    ],
)
def test_table_3_registered_relationship_transitions(
    component: ComponentSnapshot,
    effect_kind: str,
    output_role: str,
    context: dict[str, object],
    expected_relation: str,
    expected_label: str | None,
) -> None:
    payload = MaterialModelPayload(
        operation=OperationSnapshot(
            program_kind="test_program",
            effect_kind=effect_kind,
            output_roles=(OutputRoleSnapshot(part_id="selected", semantic_role=output_role),),
        ),
        components=(component,),
        context=context,
    )

    result = create_default_scientific_model_resolver().resolve(
        _request(MATERIAL_STATE_TRANSITION, payload)
    )

    assert result.status is ModelStatus.RESOLVED
    assert isinstance(result.proposal, StateTransitionDecision)
    transition = result.proposal.transitions[0]
    assert transition.next_relation == expected_relation
    assert transition.next_label == expected_label


def test_table_3_disrupt_retires_intact_cell_count() -> None:
    component = _component(
        entry_id="CELLS:0",
        kind="bio_cellular",
        content_type="cell_line",
        quantity_value=200000.0,
        quantity_unit="cells",
    )
    payload = MaterialModelPayload(
        operation=OperationSnapshot(
            program_kind="disrupt_program",
            effect_kind="disrupt",
            output_roles=(
                OutputRoleSnapshot(part_id="result", semantic_role="result_material"),
            ),
        ),
        components=(component,),
        context={"disruption_target": True},
    )

    result = create_default_scientific_model_resolver().resolve(
        _request(MATERIAL_STATE_TRANSITION, payload)
    )

    assert result.status is ModelStatus.RESOLVED
    assert isinstance(result.proposal, StateTransitionDecision)
    transition = result.proposal.transitions[0]
    assert transition.next_relation == "disrupted"
    assert transition.next_label == "lysate_material"
    assert transition.retire_quantity is True
