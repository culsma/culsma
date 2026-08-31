from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

import pytest

from culsma.driver.stub import StubDriver
from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
from culsma.scientific_model import (
    CapabilityDescriptor,
    ModelRequest,
    ModelResult,
    ModelStatus,
    ProviderDescriptor,
    ProviderProvenance,
    RegistryScientificModelResolver,
    ScientificModelRegistry,
    create_default_scientific_model_resolver,
)
from culsma.scientific_model.material import (
    BUILTIN_MATERIAL_RULEBOOK_PROVIDER_ID,
    MATERIAL_CONTRACT_VERSION,
    MATERIAL_SEPARATION_FATE,
    ComponentFate,
    ComponentSnapshot,
    CoordinationStatus,
    MaterialModelPayload,
    OperationSnapshot,
    OutputRoleSnapshot,
    QuantitySnapshot,
    RelationshipSnapshot,
    SepEffectCoordinator,
    SeparationDecision,
)
from culsma.runtime.executor import run
from culsma.runtime.material.compute import MaterialCompute
from culsma.runtime.state import init_state


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCIENTIFIC_MODEL_DIR = PROJECT_ROOT / "src" / "culsma" / "scientific_model"


class StaticProvider:
    def __init__(
        self,
        provider_id: str,
        *,
        result: ModelResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._descriptor = ProviderDescriptor(
            provider_id=provider_id,
            provider_version="1.0",
            capabilities=(
                CapabilityDescriptor(
                    capability=MATERIAL_SEPARATION_FATE,
                    contract_version=MATERIAL_CONTRACT_VERSION,
                ),
            ),
        )
        self.result = result
        self.error = error
        self.calls: list[ModelRequest] = []

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    def resolve(self, request: ModelRequest) -> ModelResult:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        if self.result is not None:
            return self.result
        return ModelResult.not_applicable(
            provenance=ProviderProvenance.from_descriptor(self.descriptor)
        )


def _request(payload: object | None = None) -> ModelRequest:
    return ModelRequest(
        request_id="run-1:model-1",
        capability=MATERIAL_SEPARATION_FATE,
        contract_version=MATERIAL_CONTRACT_VERSION,
        payload={} if payload is None else payload,
    )


def _material_payload() -> MaterialModelPayload:
    return MaterialModelPayload(
        operation=OperationSnapshot(
            program_kind="centrifuge_program",
            effect_kind="separation_fate",
            output_roles=(
                OutputRoleSnapshot(part_id="0", semantic_role="supernatant"),
                OutputRoleSnapshot(part_id="1", semantic_role="pellet"),
            ),
        ),
        components=(
            ComponentSnapshot(
                entry_id="cells:0",
                content_ref="HEK293T",
                canonical_kind="bio_cellular",
                canonical_type="cell_line",
                quantity=QuantitySnapshot(value=200000.0, unit="cells"),
                relationship=RelationshipSnapshot(relation="free"),
            ),
        ),
    )


def _runtime_plan() -> PlanProgram:
    return PlanProgram(
        plans=[
            ProtocolPlan(
                protocol_id="runtime-scientific-model",
                protocol_name="RuntimeScientificModel",
                steps=[PlanStep(step_id="p0.s0", op="Wait")],
            )
        ]
    )


def _separation_decision(
    provenance: ProviderProvenance,
    fractions: Mapping[str, float] | None = None,
) -> SeparationDecision:
    return SeparationDecision(
        component_fates=(
            ComponentFate(
                component_entry_id="cells:0",
                fractions=fractions or {"0": 0.0, "1": 1.0},
            ),
        ),
        decision_source="provider",
        provenance=provenance,
    )


def test_model_request_recursively_freezes_mapping_payload() -> None:
    source = {"operation": {"outputs": ["supernatant", "pellet"]}}

    request = _request(source)
    source["operation"]["outputs"].append("later")

    assert isinstance(request.payload, Mapping)
    assert request.payload["operation"]["outputs"] == ("supernatant", "pellet")
    with pytest.raises(TypeError):
        request.payload["new"] = "value"


def test_scientific_model_package_does_not_depend_on_runtime_pipeline_or_driver() -> None:
    forbidden_prefixes = (
        "culsma.runtime",
        "culsma.pipeline",
        "culsma.driver",
        "culsma.parser",
    )
    offenders: list[tuple[str, str]] = []
    for path in SCIENTIFIC_MODEL_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                if node.module.startswith(forbidden_prefixes):
                    offenders.append((path.name, node.module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_prefixes):
                        offenders.append((path.name, alias.name))

    assert offenders == []


def test_registry_requires_explicit_replacement_for_existing_binding() -> None:
    first = StaticProvider("test.first")
    second = StaticProvider("test.second")
    registry = ScientificModelRegistry()
    registry.register_and_bind(first)
    registry.register(second)

    with pytest.raises(ValueError, match="already bound"):
        registry.bind(
            MATERIAL_SEPARATION_FATE,
            MATERIAL_CONTRACT_VERSION,
            second.descriptor.provider_id,
        )

    registry.bind(
        MATERIAL_SEPARATION_FATE,
        MATERIAL_CONTRACT_VERSION,
        second.descriptor.provider_id,
        replace=True,
    )
    assert registry.selected_provider_id(
        MATERIAL_SEPARATION_FATE,
        MATERIAL_CONTRACT_VERSION,
    ) == "test.second"


def test_resolver_dispatches_to_only_the_selected_provider() -> None:
    first = StaticProvider("test.first")
    second = StaticProvider("test.second")
    registry = ScientificModelRegistry()
    registry.register_and_bind(first)
    registry.register_and_bind(second, replace=True)
    resolver = RegistryScientificModelResolver(registry)

    result = resolver.resolve(_request())

    assert result.status is ModelStatus.NOT_APPLICABLE
    assert first.calls == []
    assert len(second.calls) == 1


def test_resolver_rejects_lifecycle_mismatch_without_calling_provider() -> None:
    provider = StaticProvider("test.precommit")
    registry = ScientificModelRegistry()
    registry.register_and_bind(provider)
    request = ModelRequest(
        request_id="run-1:postcommit",
        capability=MATERIAL_SEPARATION_FATE,
        contract_version=MATERIAL_CONTRACT_VERSION,
        lifecycle="postcommit",
        payload=_material_payload(),
    )

    result = RegistryScientificModelResolver(registry).resolve(request)

    assert result.status is ModelStatus.FAILED
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "SCIENTIFIC_MODEL_LIFECYCLE_MISMATCH"
    ]
    assert provider.calls == []


def test_resolver_contains_provider_exception_as_failed_result() -> None:
    provider = StaticProvider("test.failing", error=RuntimeError("model unavailable"))
    registry = ScientificModelRegistry()
    registry.register_and_bind(provider)

    result = RegistryScientificModelResolver(registry).resolve(_request())

    assert result.status is ModelStatus.FAILED
    assert result.provenance is not None
    assert result.provenance.provider_id == "test.failing"
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "SCIENTIFIC_MODEL_PROVIDER_FAILED"
    ]


def test_resolver_rejects_provider_result_with_false_provenance() -> None:
    false_provenance = ProviderProvenance(
        provider_id="test.someone-else",
        provider_version="9.0",
    )
    provider = StaticProvider(
        "test.selected",
        result=ModelResult.resolved(
            proposal={"component_fates": []},
            provenance=false_provenance,
        ),
    )
    registry = ScientificModelRegistry()
    registry.register_and_bind(provider)

    result = RegistryScientificModelResolver(registry).resolve(_request())

    assert result.status is ModelStatus.FAILED
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "SCIENTIFIC_MODEL_PROVENANCE_MISMATCH"
    ]


def test_default_resolver_binds_builtin_provider_and_resolves_covered_rule() -> None:
    resolver = create_default_scientific_model_resolver()

    result = resolver.resolve(_request(_material_payload()))

    assert {descriptor.capability for descriptor in resolver.capabilities()} == {
        "material.separation_fate",
        "material.state_transition",
    }
    assert result.status is ModelStatus.RESOLVED
    assert result.provenance is not None
    assert result.provenance.provider_id == BUILTIN_MATERIAL_RULEBOOK_PROVIDER_ID
    assert isinstance(result.proposal, SeparationDecision)
    assert dict(result.proposal.component_fates[0].fractions) == {"0": 0.0, "1": 1.0}


def test_run_passes_custom_resolver_to_session_owned_material_compute(monkeypatch) -> None:
    plan = _runtime_plan()
    state = init_state(plan)
    state.artifacts["material_state"] = {"containers": {}}
    resolver = RegistryScientificModelResolver()
    observed: list[object] = []
    original_apply_step = MaterialCompute.apply_step

    def recording_apply_step(self, step, material_state):
        observed.append(self.scientific_model)
        return original_apply_step(self, step, material_state)

    monkeypatch.setattr(MaterialCompute, "apply_step", recording_apply_step)

    result = run(
        plan=plan,
        driver=StubDriver(),
        state=state,
        scientific_model=resolver,
    )

    assert result.ok
    assert observed
    assert all(selected is resolver for selected in observed)


def test_run_builds_default_resolver_once_for_material_compute(monkeypatch) -> None:
    plan = _runtime_plan()
    state = init_state(plan)
    state.artifacts["material_state"] = {"containers": {}}
    observed: list[object] = []
    original_apply_step = MaterialCompute.apply_step

    def recording_apply_step(self, step, material_state):
        observed.append(self.scientific_model)
        return original_apply_step(self, step, material_state)

    monkeypatch.setattr(MaterialCompute, "apply_step", recording_apply_step)

    result = run(plan=plan, driver=StubDriver(), state=state)

    assert result.ok
    assert observed
    assert len({id(selected) for selected in observed}) == 1
    default_resolver = observed[0]
    assert isinstance(default_resolver, RegistryScientificModelResolver)
    assert {descriptor.capability for descriptor in default_resolver.capabilities()} == {
        "material.separation_fate",
        "material.state_transition",
    }


def test_coordinator_validates_provider_fraction_proposal() -> None:
    provider = StaticProvider("test.material")
    provenance = ProviderProvenance.from_descriptor(provider.descriptor)
    provider.result = ModelResult.resolved(
        proposal=_separation_decision(provenance, {"0": 0.0, "1": 0.75}),
        provenance=provenance,
    )
    registry = ScientificModelRegistry()
    registry.register_and_bind(provider)
    coordinator = SepEffectCoordinator(RegistryScientificModelResolver(registry))

    result = coordinator.resolve(_request(_material_payload()))

    assert result.status is CoordinationStatus.REJECTED
    assert [issue.code for issue in result.validation_issues] == [
        "MATERIAL_MODEL_FRACTION_TOTAL_INVALID"
    ]


def test_coordinator_rejects_decision_provenance_mismatch() -> None:
    provider = StaticProvider("test.selected")
    selected_provenance = ProviderProvenance.from_descriptor(provider.descriptor)
    spoofed_provenance = ProviderProvenance(
        provider_id="test.spoofed",
        provider_version="9.0",
    )
    provider.result = ModelResult.resolved(
        proposal=_separation_decision(spoofed_provenance),
        provenance=selected_provenance,
    )
    registry = ScientificModelRegistry()
    registry.register_and_bind(provider)

    result = SepEffectCoordinator(RegistryScientificModelResolver(registry)).resolve(
        _request(_material_payload())
    )

    assert result.status is CoordinationStatus.REJECTED
    assert [issue.code for issue in result.validation_issues] == [
        "MATERIAL_MODEL_PROVENANCE_MISMATCH"
    ]


def test_coordinator_accepts_complete_valid_provider_proposal() -> None:
    provider = StaticProvider("test.material")
    provenance = ProviderProvenance.from_descriptor(provider.descriptor)
    decision = _separation_decision(provenance)
    provider.result = ModelResult.resolved(proposal=decision, provenance=provenance)
    registry = ScientificModelRegistry()
    registry.register_and_bind(provider)

    result = SepEffectCoordinator(RegistryScientificModelResolver(registry)).resolve(
        _request(_material_payload())
    )

    assert result.status is CoordinationStatus.RESOLVED
    assert result.source == "provider"
    assert result.decision == decision
    assert result.provenance == provenance


def test_coordinator_uses_validated_author_decision_before_provider() -> None:
    provider = StaticProvider("test.material", error=AssertionError("must not run"))
    registry = ScientificModelRegistry()
    registry.register_and_bind(provider)
    coordinator = SepEffectCoordinator(RegistryScientificModelResolver(registry))
    author_decision = _separation_decision(
        ProviderProvenance(provider_id="culsma.author", provider_version="1"),
    )

    result = coordinator.resolve(
        _request(_material_payload()),
        validated_author_decision=author_decision,
    )

    assert result.status is CoordinationStatus.RESOLVED
    assert result.source == "author"
    assert result.decision is author_decision
    assert result.provenance == author_decision.provenance
    assert provider.calls == []
