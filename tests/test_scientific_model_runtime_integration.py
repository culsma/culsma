from __future__ import annotations

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
from culsma.runtime.material.contents_state import refresh_scientific_model_relationships
from culsma.runtime.material.partition import (
    commit_partition_candidate,
    partition_sep_material,
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
    assert isinstance(resolution, ResolvedMaterialEffect)
    assert resolution.outputs[0].semantic_role == "supernatant"
    assert resolution.outputs[1].semantic_role == "pellet"
    assert len(resolution.component_effects) == 1
    component_effect = resolution.component_effects[0]
    assert component_effect.source_component_id == "MEDIUM"
    assert tuple(output.fraction for output in component_effect.outputs) == (0.0, 1.0)
    assert component_effect.outputs[1].next_relation == "pellet"
    assert source["components"] == {"MEDIUM": 100.0}
    assert "indexed_bindings" not in state


def test_public_partition_entry_uses_injected_builtin_model_adapter() -> None:
    state = _state()
    source = state["containers"]["sample"]
    supernatant: dict[str, object] = {}
    pellet: dict[str, object] = {}

    partition_result = partition_sep_material(
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

    candidate = project_resolved_material_effect(
        effect,
        source_quantities=source["component_quantities"],
        source_classes={},
    )

    assert source["components"] == {"CELLS": 1000.0}
    assert candidate.components_by_part == {
        "0": {"CELLS": 0.0},
        "1": {"CELLS": 1000.0},
    }
    supernatant: dict[str, object] = {}
    pellet: dict[str, object] = {}
    commit_partition_candidate(
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
    assert provider.calls == [MATERIAL_SEPARATION_FATE, MATERIAL_STATE_TRANSITION]
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


def test_public_relationship_refresh_applies_transition_to_one_output() -> None:
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

    refresh_scientific_model_relationships(
        output,
        "pellet-output",
        slot="1",
        effect=effect,
    )

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
