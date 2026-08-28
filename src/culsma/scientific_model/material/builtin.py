"""Official built-in material provider shell.

The Rulebook behavior is added in later implementation slices. Until then this
provider reports explicit unresolved coverage and never guesses a decision.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import (
    CapabilityDescriptor,
    ModelDiagnostic,
    ModelRequest,
    ModelResult,
    ProviderDescriptor,
    ProviderProvenance,
)
from .contracts import (
    MATERIAL_CONTRACT_VERSION,
    MATERIAL_SEPARATION_FATE,
    MATERIAL_STATE_TRANSITION,
)


BUILTIN_MATERIAL_RULEBOOK_PROVIDER_ID = "culsma.builtin.material_rulebook"


@dataclass(frozen=True)
class BuiltinMaterialRulebookProvider:
    provider_version: str = "1.0"

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(
            provider_id=BUILTIN_MATERIAL_RULEBOOK_PROVIDER_ID,
            provider_version=self.provider_version,
            capabilities=(
                CapabilityDescriptor(
                    capability=MATERIAL_SEPARATION_FATE,
                    contract_version=MATERIAL_CONTRACT_VERSION,
                ),
                CapabilityDescriptor(
                    capability=MATERIAL_STATE_TRANSITION,
                    contract_version=MATERIAL_CONTRACT_VERSION,
                ),
            ),
        )

    def resolve(self, request: ModelRequest) -> ModelResult:
        provenance = ProviderProvenance.from_descriptor(self.descriptor)
        if not self.descriptor.supports(request.capability, request.contract_version):
            return ModelResult.not_applicable(
                provenance=provenance,
                diagnostics=(
                    ModelDiagnostic(
                        code="MATERIAL_RULEBOOK_CAPABILITY_NOT_APPLICABLE",
                        message=(
                            f"built-in material Rulebook does not support capability "
                            f"'{request.capability}' version '{request.contract_version}'"
                        ),
                        severity="warning",
                    ),
                ),
            )
        return ModelResult.not_applicable(
            provenance=provenance,
            diagnostics=(
                ModelDiagnostic(
                    code="MATERIAL_RULEBOOK_UNRESOLVED",
                    message="built-in material Rulebook implementation is not installed yet",
                    severity="warning",
                ),
            ),
        )
