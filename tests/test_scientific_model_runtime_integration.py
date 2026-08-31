from __future__ import annotations

import pytest

from culsma.pipeline.plan_nodes import PlanStep
from culsma.scientific_model import (
    CapabilityDescriptor,
    ModelRequest,
    ModelResult,
    ProviderDescriptor,
    ProviderProvenance,
    RegistryScientificModelResolver,
    ScientificModelRegistry,
    create_default_scientific_model_resolver,
)
from culsma.scientific_model.material import (
    MATERIAL_CONTRACT_VERSION,
    MATERIAL_SEPARATION_FATE,
    MATERIAL_STATE_TRANSITION,
    ComponentFate,
    SepEffectCoordinator,
    SeparationDecision,
    StateTransitionDecision,
    RelationshipTransition,
)
from culsma.runtime.material.compute import MaterialCompute
from culsma.runtime.material.conservation import state_totals
from culsma.runtime.material.component_entries import (
    append_free_component_quantity,
    container_component_entries,
    plan_component_entry_transfer,
    replace_component_entries,
)
from culsma.runtime.material.contents_state import refresh_scientific_model_relationships
from culsma.runtime.material.ledger import (
    component_quantity_merge_conflict,
    move_explicit,
    normalize_material_state_detail_ledger,
)
from culsma.runtime.material.suspension import refresh_cell_suspension_relationship
from culsma.runtime.material.movement import apply_material_movement
from culsma.runtime.material.separation import (
    MaterialCandidateValidationError,
    apply_separation_material,
    commit_separation_candidate,
    project_resolved_material_effect,
)
from culsma.runtime.material.scientific_model_adapter import (
    ResolvedComponentEffect,
    ResolvedComponentOutput,
    ResolvedMaterialEffect,
    ResolvedOutput,
    RuntimePartitionComponent,
    ScientificModelPartitionAdapter,
)
from culsma.runtime.material.separation_fate import (
    ContentPhysicalState,
    resolve_separation_operation_contract,
)


def _ir_identifier(name: str) -> dict[str, object]:
    return {"kind": "IRIdentifier", "name": name, "span": None}


def _ir_quantity(value: float, unit: str | None) -> dict[str, object]:
    return {"kind": "IRQuantity", "value": value, "unit": unit, "span": None}


def _ir_arg(name: str, value: dict[str, object]) -> dict[str, object]:
    return {"kind": "IRArg", "name": name, "value": value, "span": None}


def _sep_step() -> PlanStep:
    return PlanStep(
        step_id="p0.s0",
        op="sep",
        args={
            "sample": _ir_identifier("sample"),
            "program": {
                "kind": "IRCall",
                "name": "centrifuge_program",
                "args": [_ir_arg("drive", _ir_quantity(12000.0, "g"))],
                "span": None,
            },
            "bind": "parts",
        },
    )


def _state() -> dict[str, object]:
    return {
        "containers": {
            "sample": {
                "components": {"MEDIUM": 100.0},
                "component_quantities": {
                    "MEDIUM": {"dimension": "volume", "unit": "uL", "value": 100.0}
                },
                "volume_uL": 100.0,
                "mass_mg": 100.0,
                "metadata": {},
            }
        },
        "content_registry": {
            "MEDIUM": {
                "content_kind": "formulation",
                "content_type": "medium",
            }
        },
    }


class RuntimeMaterialProvider:
    def __init__(self, *, invalid_fraction: bool = False) -> None:
        self.invalid_fraction = invalid_fraction
        self.calls: list[str] = []
        self._descriptor = ProviderDescriptor(
            provider_id="test.runtime-material",
            provider_version="1.0",
            capabilities=(
                CapabilityDescriptor(MATERIAL_SEPARATION_FATE, MATERIAL_CONTRACT_VERSION),
                CapabilityDescriptor(MATERIAL_STATE_TRANSITION, MATERIAL_CONTRACT_VERSION),
            ),
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    def resolve(self, request: ModelRequest) -> ModelResult:
        self.calls.append(request.capability)
        provenance = ProviderProvenance.from_descriptor(self.descriptor)
        payload = request.payload
        if request.capability == MATERIAL_SEPARATION_FATE:
            fraction = 0.75 if self.invalid_fraction else 1.0
            decision = SeparationDecision(
                component_fates=tuple(
                    ComponentFate(
                        component_entry_id=component.entry_id,
                        fractions={"0": 0.0, "1": fraction},
                    )
                    for component in payload.components
                ),
                decision_source="provider",
                provenance=provenance,
            )
        else:
            decision = StateTransitionDecision(
                transitions=tuple(
                    RelationshipTransition(
                        component_entry_id=component.entry_id,
                        next_relation="pellet",
                        next_label="custom_pellet_output",
                    )
                    for component in payload.components
                ),
                decision_source="provider",
                provenance=provenance,
            )
        return ModelResult.resolved(proposal=decision, provenance=provenance)


def _resolver(provider: RuntimeMaterialProvider) -> RegistryScientificModelResolver:
    registry = ScientificModelRegistry()
    registry.register_and_bind(provider)
    return RegistryScientificModelResolver(registry)


def test_runtime_adapter_uses_one_custom_resolver_for_fate_and_transition() -> None:
    provider = RuntimeMaterialProvider()

    result = MaterialCompute(scientific_model=_resolver(provider)).apply_step(
        _sep_step(),
        _state(),
    )

    assert result.ok
    assert provider.calls == [MATERIAL_SEPARATION_FATE, MATERIAL_STATE_TRANSITION]
    slots = result.material_state["indexed_bindings"]["parts"]
    assert result.material_state["containers"][slots["0"]]["volume_uL"] == 0.0
    assert result.material_state["containers"][slots["1"]]["volume_uL"] == 100.0
    partition = result.delta["partition"]
    assert partition["fates_by_component"]["MEDIUM"]["provenance"]["provider_id"] == "test.runtime-material"
    assert partition["transitions_by_component"]["MEDIUM"]["1"]["next_label"] == "custom_pellet_output"


def test_public_partition_adapter_resolves_decisions_without_material_projection() -> None:
    provider = RuntimeMaterialProvider()
    adapter = ScientificModelPartitionAdapter(
        SepEffectCoordinator(_resolver(provider))
    )
    state = _state()
    source = state["containers"]["sample"]
    component = RuntimePartitionComponent(
        component_id="MEDIUM",
        amount=100.0,
        explicit_fate=None,
        physical_state=ContentPhysicalState(
            association="free",
            accessibility="accessible",
            preservation_state="declared",
            source="test",
        ),
        label="source_label",
    )
    operation_contract = resolve_separation_operation_contract(
        _sep_step().args["program"],
        slot_contract={"0": "supernatant", "1": "pellet"},
    )

    snapshot = adapter.build_component_snapshot(
        state=state,
        source=source,
        source_quantities=source["component_quantities"],
        component=component,
        source_id="sample",
    )
    resolution = adapter.resolve(
        state=state,
        source=source,
        source_quantities=source["component_quantities"],
        components={"MEDIUM": component},
        operation_contract=operation_contract,
        request_id="adapter-direct",
        source_id="sample",
    )

    assert snapshot.canonical_kind == "formulation"
    assert snapshot.canonical_type == "medium"
    assert snapshot.relationship.relation == "free"
    assert snapshot.relationship.label == "source_label"
    assert isinstance(resolution, ResolvedMaterialEffect)
    assert resolution.outputs[0].semantic_role == "supernatant"
    assert resolution.outputs[1].semantic_role == "pellet"
    assert len(resolution.component_effects) == 1
    component_effect = resolution.component_effects[0]
    assert component_effect.source_entry_id == "MEDIUM"
    assert tuple(output.fraction for output in component_effect.outputs) == (0.0, 1.0)
    assert component_effect.outputs[1].next_relation == "pellet"
    assert source["components"] == {"MEDIUM": 100.0}
    assert "indexed_bindings" not in state


def test_public_partition_entry_uses_injected_builtin_model_adapter() -> None:
    state = _state()
    source = state["containers"]["sample"]
    supernatant: dict[str, object] = {}
    pellet: dict[str, object] = {}

    partition_result = apply_separation_material(
        state=state,
        source=source,
        slot0=supernatant,
        slot1=pellet,
        program=_sep_step().args["program"],
        source_id="sample",
        material_effect_adapter=ScientificModelPartitionAdapter(
            SepEffectCoordinator(create_default_scientific_model_resolver())
        ),
    )

    assert isinstance(partition_result.effect, ResolvedMaterialEffect)
    partition = partition_result.record
    assert partition["ratios_by_component"] == {"MEDIUM": {"0": 1.0, "1": 0.0}}
    assert partition["fates_by_component"]["MEDIUM"]["source"] == (
        "scientific_model_provider"
    )
    assert supernatant["component_quantities"]["MEDIUM"]["value"] == 100.0
    assert pellet["component_quantities"]["MEDIUM"]["value"] == 0.0


def test_public_projector_consumes_one_resolved_effect_without_scientific_lookup() -> None:
    provenance = ProviderProvenance("test.provider", "1.0")
    effect = ResolvedMaterialEffect(
        operation_id="projector-direct",
        program_kind="centrifuge_program",
        outputs=(
            ResolvedOutput("0", "supernatant"),
            ResolvedOutput("1", "pellet"),
        ),
        component_effects=(
            ResolvedComponentEffect(
                source_component_id="CELLS",
                source_amount=1000.0,
                source_relation="free",
                source_accessibility="accessible",
                source_preservation="declared",
                outputs=(
                    ResolvedComponentOutput(
                        part_id="0",
                        semantic_role="supernatant",
                        fraction=0.0,
                        next_relation=None,
                        next_label=None,
                        retire_quantity=False,
                        replacement_quantity=None,
                        decision_source="scientific_model_provider",
                        fate_provenance=provenance,
                        transition_provenance=None,
                    ),
                    ResolvedComponentOutput(
                        part_id="1",
                        semantic_role="pellet",
                        fraction=1.0,
                        next_relation="pellet",
                        next_label="pellet_output",
                        retire_quantity=False,
                        replacement_quantity=None,
                        decision_source="scientific_model_provider",
                        fate_provenance=provenance,
                        transition_provenance=provenance,
                    ),
                ),
            ),
        ),
    )
    source = {
        "components": {"CELLS": 1000.0},
        "component_quantities": {
            "CELLS": {"dimension": "count", "unit": "cells", "value": 1000.0}
        },
    }

    with pytest.raises(
        MaterialCandidateValidationError,
        match="has no association",
    ):
        project_resolved_material_effect(
            effect,
            source_quantities=source["component_quantities"],
            source_classes={},
        )

    candidate = project_resolved_material_effect(
        effect,
        source_quantities=source["component_quantities"],
        source_classes={},
        output_ids_by_part={"0": "supernatant-output", "1": "pellet-output"},
    )

    assert source["components"] == {"CELLS": 1000.0}
    assert candidate.components_by_part == {
        "0": {"CELLS": 0.0},
        "1": {"CELLS": 1000.0},
    }
    assert candidate.entries_by_part["1"][0]["associated_with"] == "pellet-output"
    supernatant: dict[str, object] = {}
    pellet: dict[str, object] = {}
    commit_separation_candidate(
        candidate,
        source=source,
        outputs_by_part={"0": supernatant, "1": pellet},
    )
    assert source["components"] == {}
    assert supernatant["component_quantities"]["CELLS"]["value"] == 0.0
    assert pellet["component_quantities"]["CELLS"]["value"] == 1000.0


def test_source_partition_mutation_uses_runtime_configured_adapter() -> None:
    provider = RuntimeMaterialProvider()
    state = _state()
    state["containers"]["target"] = {
        "components": {},
        "volume_uL": 0.0,
        "mass_mg": 0.0,
        "metadata": {},
    }
    partition_ref = {
        "kind": "IRSourcePartitionRef",
        "source": _ir_identifier("sample"),
        "program": _sep_step().args["program"],
        "index": _ir_quantity(1.0, None),
        "span": None,
    }
    step = PlanStep(
        step_id="p0.s1",
        op="Mutation",
        args={
            "target": _ir_identifier("target"),
            "sources": [partition_ref],
        },
    )

    result = MaterialCompute(scientific_model=_resolver(provider)).apply_step(
        step,
        state,
    )

    assert result.ok
    assert provider.calls == [
        MATERIAL_SEPARATION_FATE,
        MATERIAL_STATE_TRANSITION,
        MATERIAL_STATE_TRANSITION,
    ]
    target = result.material_state["containers"]["target"]
    assert target["component_quantities"]["MEDIUM"]["value"] == 100.0


def test_runtime_adapter_rejects_invalid_provider_fraction_without_committing() -> None:
    provider = RuntimeMaterialProvider(invalid_fraction=True)
    source = _state()

    result = MaterialCompute(scientific_model=_resolver(provider)).apply_step(
        _sep_step(),
        source,
    )

    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "MAT_SCIENTIFIC_MODEL_REJECTED"
    ]
    assert "indexed_bindings" not in source
    assert source["containers"]["sample"]["volume_uL"] == 100.0


def test_runtime_adapter_reports_unresolved_builtin_rule_without_legacy_fallback() -> None:
    state = _state()
    state["content_registry"]["MEDIUM"] = {
        "content_kind": "bio_fluid",
        "content_type": "whole_blood",
    }

    result = MaterialCompute().apply_step(_sep_step(), state)

    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "MAT_SCIENTIFIC_MODEL_UNRESOLVED"
    ]
    assert "indexed_bindings" not in state
    assert state["containers"]["sample"]["volume_uL"] == 100.0


def test_runtime_adapter_commits_table_3_relation_for_non_cell_component() -> None:
    state = _state()
    state["containers"]["sample"]["components"] = {"BEADS": 100.0}
    state["containers"]["sample"]["component_quantities"] = {
        "BEADS": {"dimension": "volume", "unit": "uL", "value": 100.0}
    }
    state["content_registry"] = {
        "BEADS": {"content_kind": "particulate", "content_type": "beads"}
    }

    result = MaterialCompute().apply_step(_sep_step(), state)

    assert result.ok
    pellet_id = result.material_state["indexed_bindings"]["parts"]["1"]
    relationships = result.material_state["containers"][pellet_id]["material_relationships"]
    model_relationship = next(
        relationship
        for relationship in relationships
        if relationship.get("subtype") == "scientific_model_relation"
    )
    assert model_relationship["dispersed_component_ids"] == ["BEADS"]
    assert model_relationship["material_state"] == "pellet"
    assert model_relationship["associated_with"] == pellet_id
    assert model_relationship["label"] == "pellet_output"
    assert model_relationship["provenance"]["provider_id"] == "culsma.builtin.material_rulebook"

    pellet = result.material_state["containers"][pellet_id]
    pellet["metadata"].pop("component_partition_classes", None)
    repeat_step = PlanStep(
        step_id="p0.s1",
        op="sep",
        args={
            "sample": {
                "kind": "IRIndex",
                "base": _ir_identifier("parts"),
                "index": _ir_quantity(1.0, None),
                "span": None,
            },
            "program": {
                "kind": "IRCall",
                "name": "centrifuge_program",
                "args": [_ir_arg("drive", _ir_quantity(12000.0, "g"))],
                "span": None,
            },
            "bind": "repeated_parts",
        },
    )

    repeated = MaterialCompute().apply_step(repeat_step, result.material_state)

    assert repeated.ok
    assert repeated.delta["partition"]["fates_by_component"]["BEADS"]["association"] == "pellet"
    assert repeated.delta["partition"]["ratios_by_component"]["BEADS"] == {
        "0": 0.0,
        "1": 1.0,
    }


def test_public_relationship_refresh_only_projects_committed_entries() -> None:
    output = {
        "components": {"BEADS": 20.0, "WASH": 180.0},
        "material_relationships": [],
    }
    provenance = ProviderProvenance("test.provider", "1.0")
    effect = ResolvedMaterialEffect(
        operation_id="relationship-refresh",
        program_kind="centrifuge_program",
        outputs=(ResolvedOutput("1", "pellet"),),
        component_effects=(
            ResolvedComponentEffect(
                source_component_id="BEADS",
                source_amount=20.0,
                source_relation="free",
                source_accessibility="accessible",
                source_preservation="declared",
                outputs=(
                    ResolvedComponentOutput(
                        part_id="1",
                        semantic_role="pellet",
                        fraction=1.0,
                        next_relation="pellet",
                        next_label="pellet_output",
                        retire_quantity=False,
                        replacement_quantity=None,
                        decision_source="scientific_model_provider",
                        fate_provenance=provenance,
                        transition_provenance=provenance,
                    ),
                ),
            ),
            ResolvedComponentEffect(
                source_component_id="WASH",
                source_amount=180.0,
                source_relation="free",
                source_accessibility="accessible",
                source_preservation="declared",
                outputs=(
                    ResolvedComponentOutput(
                        part_id="1",
                        semantic_role="pellet",
                        fraction=1.0,
                        next_relation="free",
                        next_label=None,
                        retire_quantity=False,
                        replacement_quantity=None,
                        decision_source="scientific_model_provider",
                        fate_provenance=provenance,
                        transition_provenance=provenance,
                    ),
                ),
            ),
        ),
    )
    replace_component_entries(
        output,
        [
            {
                "entry_id": "BEADS",
                "content_ref": "BEADS",
                "amount": 20.0,
                "quantity": None,
                "relation": "pellet",
                "associated_with": "pellet-output",
                "preservation": "declared",
                "label": "pellet_output",
                "relationship_source": "scientific_model",
                "material_state_source": "scientific_model_provider",
                "provenance": {
                    "provider_id": "test.provider",
                    "provider_version": "1.0",
                    "model_id": None,
                    "model_version": None,
                    "configuration": {},
                },
            },
            {
                "entry_id": "WASH",
                "content_ref": "WASH",
                "amount": 180.0,
                "quantity": None,
                "relation": "free",
                "associated_with": None,
                "preservation": "declared",
                "label": None,
                "relationship_source": "scientific_model",
                "material_state_source": "scientific_model_provider",
            },
        ],
    )
    entries_before_refresh = [dict(entry) for entry in container_component_entries(output)]

    refresh_scientific_model_relationships(
        output,
        "pellet-output",
        slot="1",
        effect=effect,
    )

    assert container_component_entries(output) == entries_before_refresh
    assert output["material_relationships"] == [
        {
            "kind": "association",
            "subtype": "scientific_model_relation",
            "dispersed_component_ids": ["BEADS"],
            "material_state": "pellet",
            "material_state_source": "scientific_model_provider",
            "associated_with": "pellet-output",
            "label": "pellet_output",
            "provenance": {
                "provider_id": "test.provider",
                "provider_version": "1.0",
                "model_id": None,
                "model_version": None,
                "configuration": {},
            },
        }
    ]


def test_material_move_carries_scientific_component_relation_to_destination() -> None:
    source = {
        "components": {"DNA": 100.0},
        "component_quantities": {
            "DNA": {"dimension": "volume", "unit": "uL", "value": 100.0}
        },
        "metadata": {},
        "material_relationships": [
            {
                "kind": "association",
                "subtype": "scientific_model_relation",
                "dispersed_component_ids": ["DNA"],
                "material_state": "precipitate",
                "associated_with": "source",
            }
        ],
    }
    target = {
        "components": {},
        "component_quantities": {},
        "metadata": {},
    }

    move_explicit(
        source,
        target,
        component_ratio=1.0,
        destination_id="target",
    )

    assert target["material_relationships"] == [
        {
            "kind": "association",
            "subtype": "scientific_model_relation",
            "dispersed_component_ids": ["DNA"],
            "material_state": "precipitate",
            "associated_with": "target",
        }
    ]


def test_move_keeps_same_content_with_incompatible_states_as_distinct_entries() -> None:
    source = {
        "components": {"DNA": 100.0},
        "component_quantities": {
            "DNA": {"dimension": "volume", "unit": "uL", "value": 100.0}
        },
        "material_relationships": [
            {
                "kind": "association",
                "subtype": "scientific_model_relation",
                "dispersed_component_ids": ["DNA"],
                "material_state": "precipitate",
                "associated_with": "source",
            }
        ],
        "metadata": {},
    }
    target = {
        "components": {"DNA": 50.0},
        "component_quantities": {
            "DNA": {"dimension": "volume", "unit": "uL", "value": 50.0}
        },
        "metadata": {},
    }

    move_explicit(source, target, component_ratio=1.0, destination_id="target")

    entries = container_component_entries(target)
    assert target["components"] == {"DNA": 150.0}
    assert [(entry["entry_id"], entry["relation"], entry["amount"]) for entry in entries] == [
        ("DNA", "free", 50.0),
        ("DNA::1", "precipitate", 100.0),
    ]
    assert source["component_entries"] == []
    assert source["material_relationships"] == []


def test_full_move_then_reload_does_not_inherit_the_old_relationship() -> None:
    source = {
        "components": {"DNA": 100.0},
        "component_quantities": {
            "DNA": {"dimension": "volume", "unit": "uL", "value": 100.0}
        },
        "material_relationships": [
            {
                "kind": "association",
                "subtype": "scientific_model_relation",
                "dispersed_component_ids": ["DNA"],
                "material_state": "precipitate",
                "associated_with": "source",
            }
        ],
        "metadata": {},
    }
    target = {"components": {}, "component_quantities": {}, "metadata": {}}

    move_explicit(source, target, component_ratio=1.0, destination_id="target")
    append_free_component_quantity(
        source,
        content_ref="DNA",
        amount=25.0,
        quantity={"dimension": "volume", "unit": "uL", "value": 25.0},
    )

    assert [(entry["content_ref"], entry["relation"]) for entry in container_component_entries(source)] == [
        ("DNA", "free")
    ]
    assert source["material_relationships"] == []


def test_partial_relationship_move_splits_then_recompresses_the_same_state() -> None:
    source = {
        "components": {"DNA": 100.0},
        "component_quantities": {
            "DNA": {"dimension": "volume", "unit": "uL", "value": 100.0}
        },
        "material_relationships": [
            {
                "kind": "association",
                "subtype": "scientific_model_relation",
                "dispersed_component_ids": ["DNA"],
                "material_state": "precipitate",
                "associated_with": "source",
            }
        ],
        "metadata": {},
    }
    target = {"components": {}, "component_quantities": {}, "metadata": {}}

    move_explicit(source, target, component_ratio=0.25, destination_id="target")

    source_states = [
        (entry["amount"], entry["relation"], entry["associated_with"])
        for entry in container_component_entries(source)
    ]
    assert source_states == [
        (75.0, "precipitate", "source")
    ]
    target_states = [
        (entry["amount"], entry["relation"], entry["associated_with"])
        for entry in container_component_entries(target)
    ]
    assert target_states == [
        (25.0, "precipitate", "target")
    ]

    move_explicit(source, target, component_ratio=1.0, destination_id="target")

    assert source["component_entries"] == []
    assert [(entry["amount"], entry["relation"]) for entry in container_component_entries(target)] == [
        (100.0, "precipitate")
    ]


def test_same_content_compatible_units_convert_before_compression() -> None:
    source = {
        "components": {"BUFFER": 1.0},
        "component_quantities": {
            "BUFFER": {"dimension": "volume", "unit": "mL", "value": 1.0}
        },
        "volume_uL": 1000.0,
        "mass_mg": 1000.0,
        "metadata": {},
    }
    target = {
        "components": {"BUFFER": 100.0},
        "component_quantities": {
            "BUFFER": {"dimension": "volume", "unit": "uL", "value": 100.0}
        },
        "volume_uL": 100.0,
        "mass_mg": 100.0,
        "metadata": {},
    }

    before = state_totals({"containers": {"source": source, "target": target}})
    assert component_quantity_merge_conflict(source, target) is None
    move_explicit(source, target, component_ratio=1.0, destination_id="target")
    after = state_totals({"containers": {"source": source, "target": target}})

    assert target["components"] == {"BUFFER": 1100.0}
    assert target["component_quantities"]["BUFFER"] == {
        "dimension": "volume",
        "unit": "uL",
        "value": 1100.0,
    }
    assert len(container_component_entries(target)) == 1
    assert before == after


def test_mixed_same_content_states_remain_closed_under_next_separation() -> None:
    precipitate = {
        "components": {"DNA": 100.0},
        "component_quantities": {
            "DNA": {"dimension": "volume", "unit": "uL", "value": 100.0}
        },
        "material_relationships": [
            {
                "kind": "association",
                "subtype": "scientific_model_relation",
                "dispersed_component_ids": ["DNA"],
                "material_state": "precipitate",
                "associated_with": "precipitate",
            }
        ],
        "metadata": {},
    }
    sample = {
        "components": {"DNA": 50.0},
        "component_quantities": {
            "DNA": {"dimension": "volume", "unit": "uL", "value": 50.0}
        },
        "metadata": {},
    }
    move_explicit(precipitate, sample, component_ratio=1.0, destination_id="sample")
    state = {
        "containers": {"sample": sample},
        "content_registry": {
            "DNA": {"content_kind": "bio_molecule_or_virus", "content_type": "dna"}
        },
    }

    result = MaterialCompute().apply_step(_sep_step(), state)

    assert result.ok
    slots = result.material_state["indexed_bindings"]["parts"]
    assert result.material_state["containers"][slots["0"]]["components"]["DNA"] == 50.0
    assert result.material_state["containers"][slots["1"]]["components"]["DNA"] == 100.0


def test_safe_compression_keeps_distinct_entry_labels() -> None:
    container: dict[str, object] = {"metadata": {}}
    common = {
        "entry_id": "DNA",
        "content_ref": "DNA",
        "quantity": {"dimension": "volume", "unit": "uL", "value": 10.0},
        "relation": "pellet",
        "associated_with": "tube",
        "preservation": "derived",
        "relationship_source": "scientific_model",
        "material_state_source": "scientific_model_provider",
    }

    replace_component_entries(
        container,
        [
            {**common, "amount": 10.0, "label": "pellet_output"},
            {**common, "amount": 10.0, "label": "retentate_output"},
        ],
    )

    entries = container_component_entries(container)
    assert [(entry["entry_id"], entry["label"]) for entry in entries] == [
        ("DNA", "pellet_output"),
        ("DNA::1", "retentate_output"),
    ]
    assert container["components"] == {"DNA": 20.0}


def test_safe_compression_merges_semantically_identical_entries_despite_different_ids() -> None:
    container: dict[str, object] = {"metadata": {}}
    replace_component_entries(
        container,
        [
            {
                "entry_id": "DNA",
                "content_ref": "DNA",
                "amount": 10.0,
                "quantity": {"dimension": "volume", "unit": "uL", "value": 10.0},
                "relation": "free",
                "associated_with": None,
                "preservation": None,
                "label": None,
                "relationship_source": None,
            },
            {
                "entry_id": "DNA::9",
                "content_ref": "DNA",
                "amount": 15.0,
                "quantity": {"dimension": "volume", "unit": "uL", "value": 15.0},
                "relation": "free",
                "associated_with": None,
                "preservation": "declared",
                "label": None,
                "relationship_source": "content_registry",
            },
        ],
    )

    entries = container_component_entries(container)
    assert [(entry["entry_id"], entry["amount"]) for entry in entries] == [
        ("DNA", 25.0)
    ]
    assert entries[0]["preservation"] == "declared"
    assert entries[0]["relationship_source"] == "content_registry"


def test_safe_compression_preserves_distinct_provider_provenance() -> None:
    container: dict[str, object] = {"metadata": {}}
    common = {
        "content_ref": "DNA",
        "amount": 10.0,
        "quantity": {"dimension": "mass", "unit": "mg", "value": 10.0},
        "relation": "free",
        "associated_with": None,
        "preservation": None,
        "label": None,
        "relationship_source": "scientific_model",
    }
    replace_component_entries(
        container,
        [
            {
                **common,
                "entry_id": "DNA",
                "provenance": {"provider_id": "provider.a", "provider_version": "1"},
            },
            {
                **common,
                "entry_id": "DNA::1",
                "provenance": {"provider_id": "provider.b", "provider_version": "1"},
            },
        ],
    )

    entries = container_component_entries(container)

    assert len(entries) == 1
    assert entries[0]["amount"] == 20.0
    assert entries[0]["provenance_history"] == [
        {"provider_id": "provider.a", "provider_version": "1"},
        {"provider_id": "provider.b", "provider_version": "1"},
    ]


def test_existing_duplicate_entry_ids_are_canonicalized() -> None:
    state = {
        "containers": {
            "tube": {
                "component_entries": [
                    {
                        "entry_id": "DNA",
                        "content_ref": "DNA",
                        "amount": 25.0,
                        "quantity": {
                            "dimension": "volume",
                            "unit": "uL",
                            "value": 25.0,
                        },
                        "relation": "free",
                        "associated_with": None,
                        "preservation": None,
                        "label": None,
                        "relationship_source": None,
                    },
                    {
                        "entry_id": "DNA",
                        "content_ref": "DNA",
                        "amount": 75.0,
                        "quantity": {
                            "dimension": "volume",
                            "unit": "uL",
                            "value": 75.0,
                        },
                        "relation": "precipitate",
                        "associated_with": "tube",
                        "preservation": "derived",
                        "label": "precipitate_output",
                        "relationship_source": "scientific_model",
                    },
                ],
                "metadata": {},
            }
        }
    }

    assert normalize_material_state_detail_ledger(state) is None

    entries = container_component_entries(state["containers"]["tube"])
    assert [(entry["entry_id"], entry["relation"]) for entry in entries] == [
        ("DNA", "free"),
        ("DNA::1", "precipitate"),
    ]


def test_legacy_normalization_does_not_treat_noncell_state_as_physical_relation() -> None:
    state = {
        "containers": {
            "tube": {
                "components": {"DNA": 10.0},
                "component_quantities": {
                    "DNA": {"dimension": "volume", "unit": "uL", "value": 10.0}
                },
                "metadata": {},
            }
        },
        "content_registry": {
            "DNA": {
                "content_kind": "bio_molecule_or_virus",
                "content_type": "dna",
                "content_attrs": {"state": "stock"},
            }
        },
    }

    assert normalize_material_state_detail_ledger(state) is None

    entry = container_component_entries(state["containers"]["tube"])[0]
    assert entry["relation"] == "free"
    assert entry["associated_with"] is None


def test_legacy_cell_normalization_owns_initial_relation_and_compatibility_class() -> None:
    state = {
        "containers": {
            "well": {
                "components": {"CELLS": 100.0},
                "component_quantities": {
                    "CELLS": {"dimension": "count", "unit": "cells", "value": 100.0}
                },
                "metadata": {},
            }
        },
        "content_registry": {
            "CELLS": {
                "content_kind": "bio_cellular",
                "content_type": "cell_line",
                "content_attrs": {"state": "adherent"},
            }
        },
    }

    assert normalize_material_state_detail_ledger(state) is None

    entry = container_component_entries(state["containers"]["well"])[0]
    assert entry["relation"] == "container_surface"
    assert entry["associated_with"] == "well"
    assert entry["partition_class"] == "pelletable_cells"


def test_generic_surface_move_requires_a_scientific_release_decision() -> None:
    source = {
        "component_entries": [
            {
                "entry_id": "COATING",
                "content_ref": "COATING",
                "amount": 1.0,
                "quantity": {"dimension": "mass", "unit": "mg", "value": 1.0},
                "relation": "container_surface",
                "associated_with": "plate",
                "preservation": "declared",
                "label": None,
            }
        ],
        "metadata": {},
    }
    target = {"metadata": {}}
    state = {
        "containers": {"plate": source, "tube": target},
        "content_registry": {
            "COATING": {
                "content_kind": "chemical",
                "content_type": "other",
                "content_attrs": {},
            }
        },
    }
    adapter = ScientificModelPartitionAdapter(
        SepEffectCoordinator(create_default_scientific_model_resolver())
    )

    result = apply_material_movement(
        state=state,
        source=source,
        target=target,
        source_id="plate",
        destination_id="tube",
        ratio=1.0,
        material_effect_adapter=adapter,
        request_id="surface-coating-move",
    )

    assert result.failure is not None
    assert result.failure.code == "MAT_SCIENTIFIC_MODEL_UNRESOLVED"
    assert container_component_entries(source)[0]["relation"] == "container_surface"
    assert container_component_entries(target) == []


def test_counted_surface_cells_release_through_the_movement_transition_port() -> None:
    source = {
        "component_entries": [
            {
                "entry_id": "CELLS",
                "content_ref": "CELLS",
                "amount": 100.0,
                "quantity": {"dimension": "count", "unit": "cells", "value": 100.0},
                "relation": "container_surface",
                "associated_with": "well",
                "preservation": "declared",
                "label": None,
                "partition_class": "pelletable_cells",
            }
        ],
        "metadata": {},
    }
    target = {"metadata": {}}
    state = {
        "containers": {"well": source, "tube": target},
        "content_registry": {
            "CELLS": {
                "content_kind": "bio_cellular",
                "content_type": "cell_line",
                "content_attrs": {"state": "adherent"},
            }
        },
    }
    adapter = ScientificModelPartitionAdapter(
        SepEffectCoordinator(create_default_scientific_model_resolver())
    )

    result = apply_material_movement(
        state=state,
        source=source,
        target=target,
        source_id="well",
        destination_id="tube",
        ratio=0.5,
        material_effect_adapter=adapter,
        request_id="cell-release-move",
    )

    assert result.failure is None
    assert [(entry["amount"], entry["relation"]) for entry in container_component_entries(source)] == [
        (50.0, "container_surface")
    ]
    assert [(entry["amount"], entry["relation"]) for entry in container_component_entries(target)] == [
        (50.0, "free")
    ]


@pytest.mark.parametrize(
    (
        "content_kind",
        "content_type",
        "source_relation",
        "source_association",
        "expected_relation",
        "expected_association",
    ),
    [
        ("formulation", "buffer", "free", None, "free", None),
        ("bio_cellular", "cell_line", "pellet", "source", "pellet", "target"),
        (
            "bio_molecule_or_virus",
            "dna",
            "precipitate",
            "source",
            "precipitate",
            "target",
        ),
        ("bio_cellular", "cell_line", "disrupted", "source", "disrupted", "target"),
        ("particulate", "beads", "bead_bound", "BEADS", "bead_bound", "BEADS"),
        (
            "bio_subcellular",
            "membrane",
            "membrane_bound",
            "MEMBRANE",
            "membrane_bound",
            "MEMBRANE",
        ),
        (
            "bio_molecule_or_virus",
            "protein",
            "cell_bound",
            "CELLS",
            "cell_bound",
            "CELLS",
        ),
        ("particulate", "beads", "field_retained", "FIELD", "free", None),
    ],
)
def test_movement_transition_applies_relation_specific_association_policy(
    content_kind: str,
    content_type: str,
    source_relation: str,
    source_association: str | None,
    expected_relation: str,
    expected_association: str | None,
) -> None:
    support_entries = (
        [
            {
                "entry_id": source_association,
                "content_ref": f"SUPPORT_{source_association}",
                "amount": 1.0,
                "quantity": {"dimension": "mass", "unit": "mg", "value": 1.0},
                "relation": "free",
                "associated_with": None,
                "preservation": "declared",
                "label": None,
            }
        ]
        if source_relation in {"bead_bound", "membrane_bound", "cell_bound"}
        else []
    )
    source = {
        "component_entries": [
            {
                "entry_id": "CONTENT",
                "content_ref": "CONTENT",
                "amount": 1.0,
                "quantity": {"dimension": "mass", "unit": "mg", "value": 1.0},
                "relation": source_relation,
                "associated_with": source_association,
                "preservation": "declared",
                "label": "old_output",
            },
            *support_entries,
        ],
        "metadata": {},
    }
    target = {"metadata": {}}
    state = {
        "containers": {"source": source, "target": target},
        "content_registry": {
            "CONTENT": {
                "content_kind": content_kind,
                "content_type": content_type,
                "content_attrs": {},
            }
        },
    }
    adapter = ScientificModelPartitionAdapter(
        SepEffectCoordinator(create_default_scientific_model_resolver())
    )

    result = apply_material_movement(
        state=state,
        source=source,
        target=target,
        source_id="source",
        destination_id="target",
        ratio=1.0,
        material_effect_adapter=adapter,
        request_id=f"move:{source_relation}",
    )

    assert result.failure is None
    moved = next(
        entry
        for entry in container_component_entries(target)
        if entry["content_ref"] == "CONTENT"
    )
    assert moved["relation"] == expected_relation
    assert moved["associated_with"] == expected_association
    assert moved["label"] is None


def test_transfer_remaps_bound_target_when_support_entry_compresses() -> None:
    source = {
        "component_entries": [
            {
                "entry_id": "DNA",
                "content_ref": "DNA",
                "amount": 1.0,
                "quantity": {"dimension": "mass", "unit": "mg", "value": 1.0},
                "relation": "bead_bound",
                "associated_with": "BEADS",
                "association_target_kind": "component_entry",
            },
            {
                "entry_id": "BEADS",
                "content_ref": "BEADS",
                "amount": 1.0,
                "quantity": {"dimension": "mass", "unit": "mg", "value": 1.0},
                "relation": "free",
                "associated_with": None,
                "association_target_kind": None,
            },
        ]
    }
    target = {
        "component_entries": [
            {
                "entry_id": "BEADS_DEST",
                "content_ref": "BEADS",
                "amount": 2.0,
                "quantity": {"dimension": "mass", "unit": "mg", "value": 2.0},
                "relation": "free",
                "associated_with": None,
                "association_target_kind": None,
            }
        ]
    }
    transitions = {
        "DNA": {
            "next_relation": "bead_bound",
            "next_label": None,
            "next_association_target": {
                "kind": "component_entry",
                "id": "BEADS",
            },
            "scientific_decision": True,
        },
        "BEADS": {
            "next_relation": "free",
            "next_label": None,
            "next_association_target": None,
            "scientific_decision": True,
        },
    }

    transfer = plan_component_entry_transfer(
        source,
        target,
        ratio=1.0,
        destination_id="target",
        transitions_by_entry_id=transitions,
    )

    dna = next(
        entry for entry in transfer.target_entries if entry["content_ref"] == "DNA"
    )
    assert dna["associated_with"] == "BEADS_DEST"
    assert dna["association_target_kind"] == "component_entry"


def test_unknown_committed_relation_is_rejected_at_the_normalization_gate() -> None:
    state = {
        "containers": {
            "tube": {
                "component_entries": [
                    {
                        "entry_id": "DNA",
                        "content_ref": "DNA",
                        "amount": 1.0,
                        "quantity": {"dimension": "mass", "unit": "mg", "value": 1.0},
                        "relation": "mystery_relation",
                        "associated_with": "tube",
                    }
                ]
            }
        }
    }

    failure = normalize_material_state_detail_ledger(state)

    assert failure is not None
    assert failure.code == "MAT_STATE_INVARIANT_VIOLATION"
    assert "mystery_relation" in failure.message


def test_cell_suspension_refresh_preserves_distinct_scientific_entry_states() -> None:
    container: dict[str, object] = {"metadata": {}, "material_relationships": []}
    replace_component_entries(
        container,
        [
            {
                "entry_id": "CELLS",
                "content_ref": "CELLS",
                "amount": 100.0,
                "quantity": {"dimension": "count", "unit": "cells", "value": 100.0},
                "relation": "free",
                "associated_with": None,
                "preservation": None,
                "label": None,
                "relationship_source": "cell_suspension",
            },
            {
                "entry_id": "CELLS::1",
                "content_ref": "CELLS",
                "amount": 100.0,
                "quantity": {"dimension": "count", "unit": "cells", "value": 100.0},
                "relation": "pellet",
                "associated_with": "tube",
                "preservation": "derived",
                "label": "pellet_output",
                "relationship_source": "scientific_model",
            },
        ],
    )
    state = {
        "containers": {"tube": container},
        "content_registry": {
            "CELLS": {
                "content_kind": "biosample",
                "content_type": "cell_line",
                "content_attrs": {"state": "suspension"},
            }
        },
    }

    relationship = refresh_cell_suspension_relationship(state, "tube")

    assert [(entry["entry_id"], entry["relation"]) for entry in container_component_entries(container)] == [
        ("CELLS", "free"),
        ("CELLS::1", "pellet"),
    ]
    assert relationship is not None
    assert relationship["material_state"] == "mixed"
    assert relationship["material_state_source"] == "component_entries"


def test_cell_suspension_refresh_cannot_override_authoritative_entry_state() -> None:
    container: dict[str, object] = {"metadata": {}, "material_relationships": []}
    replace_component_entries(
        container,
        [
            {
                "entry_id": "CELLS",
                "content_ref": "CELLS",
                "amount": 100.0,
                "quantity": {"dimension": "count", "unit": "cells", "value": 100.0},
                "relation": "pellet",
                "associated_with": "tube",
                "preservation": "derived",
                "label": "pellet_output",
                "relationship_source": "scientific_model",
            },
        ],
    )
    state = {
        "containers": {"tube": container},
        "content_registry": {
            "CELLS": {
                "content_kind": "bio_cellular",
                "content_type": "cell_line",
                "content_attrs": {"state": "suspension"},
            }
        },
    }
    entries_before_refresh = [dict(entry) for entry in container_component_entries(container)]

    relationship = refresh_cell_suspension_relationship(
        state,
        "tube",
        forced_state="suspension",
    )

    assert container_component_entries(container) == entries_before_refresh
    assert relationship is not None
    assert relationship["material_state"] == "pellet"
    assert relationship["material_state_source"] == "component_entries"
