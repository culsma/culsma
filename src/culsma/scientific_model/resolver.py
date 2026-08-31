"""Scientific-model resolvers and provider failure containment."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import (
    CapabilityDescriptor,
    ModelDiagnostic,
    ModelRequest,
    ModelResult,
    ProviderDescriptor,
    ProviderProvenance,
)
from .registry import ScientificModelRegistry


def provider_provenance(descriptor: ProviderDescriptor) -> ProviderProvenance:
    return ProviderProvenance.from_descriptor(descriptor)


@dataclass(frozen=True)
class NoScientificModelResolver:
    """Explicitly disabled scientific-model configuration."""

    def capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        return ()

    def resolve(self, request: ModelRequest) -> ModelResult:
        return ModelResult.not_applicable(
            diagnostics=(
                ModelDiagnostic(
                    code="SCIENTIFIC_MODEL_PROVIDER_UNBOUND",
                    message=(
                        f"no scientific-model provider is bound for capability "
                        f"'{request.capability}' version '{request.contract_version}'"
                    ),
                    severity="warning",
                ),
            )
        )


@dataclass
class RegistryScientificModelResolver:
    registry: ScientificModelRegistry = field(default_factory=ScientificModelRegistry)

    def capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        return self.registry.capabilities()

    def resolve(self, request: ModelRequest) -> ModelResult:
        provider = self.registry.provider_for(request.capability, request.contract_version)
        if provider is None:
            return NoScientificModelResolver().resolve(request)

        descriptor = provider.descriptor
        provenance = provider_provenance(descriptor)
        capability = next(
            (
                declared
                for declared in descriptor.capabilities
                if declared.key == request.capability_key
            ),
            None,
        )
        if capability is None or capability.lifecycle != request.lifecycle:
            declared_lifecycle = (
                capability.lifecycle if capability is not None else "unavailable"
            )
            return ModelResult.failed(
                provenance=provenance,
                diagnostics=(
                    ModelDiagnostic(
                        code="SCIENTIFIC_MODEL_LIFECYCLE_MISMATCH",
                        message=(
                            f"provider '{descriptor.provider_id}' declares lifecycle "
                            f"'{declared_lifecycle}' for capability '{request.capability}' "
                            f"version '{request.contract_version}', but request lifecycle is "
                            f"'{request.lifecycle}'"
                        ),
                    ),
                ),
            )
        try:
            result = provider.resolve(request)
        except Exception as error:  # Provider failures must not cross the runtime boundary.
            return ModelResult.failed(
                provenance=provenance,
                diagnostics=(
                    ModelDiagnostic(
                        code="SCIENTIFIC_MODEL_PROVIDER_FAILED",
                        message=(
                            f"provider '{descriptor.provider_id}' failed with "
                            f"{type(error).__name__}: {error}"
                        ),
                    ),
                ),
            )

        if not isinstance(result, ModelResult):
            return ModelResult.failed(
                provenance=provenance,
                diagnostics=(
                    ModelDiagnostic(
                        code="SCIENTIFIC_MODEL_RESULT_TYPE_INVALID",
                        message=(
                            f"provider '{descriptor.provider_id}' returned "
                            f"'{type(result).__name__}' instead of ModelResult"
                        ),
                    ),
                ),
            )

        if result.provenance is None:
            return ModelResult.failed(
                provenance=provenance,
                diagnostics=(
                    ModelDiagnostic(
                        code="SCIENTIFIC_MODEL_PROVENANCE_MISSING",
                        message=f"provider '{descriptor.provider_id}' returned no provenance",
                    ),
                ),
            )

        if (
            result.provenance.provider_id != descriptor.provider_id
            or result.provenance.provider_version != descriptor.provider_version
        ):
            return ModelResult.failed(
                provenance=provenance,
                diagnostics=(
                    ModelDiagnostic(
                        code="SCIENTIFIC_MODEL_PROVENANCE_MISMATCH",
                        message=(
                            f"provider '{descriptor.provider_id}' returned provenance for "
                            f"'{result.provenance.provider_id}' version "
                            f"'{result.provenance.provider_version}'"
                        ),
                    ),
                ),
            )

        return result
