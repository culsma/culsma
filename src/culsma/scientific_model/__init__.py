"""Pluggable scientific-model resolution boundary."""

from .contracts import (
    CapabilityDescriptor,
    ModelDiagnostic,
    ModelRequest,
    ModelResult,
    ModelStatus,
    ProviderDescriptor,
    ProviderProvenance,
    ScientificModelProvider,
    ScientificModelResolver,
    empty_mapping,
    freeze_mapping,
    freeze_value,
    require_token,
)
from .registry import ScientificModelRegistry
from .resolver import NoScientificModelResolver, RegistryScientificModelResolver


def create_default_scientific_model_resolver() -> RegistryScientificModelResolver:
    """Create the default resolver with the official material provider binding."""

    from .material import BuiltinMaterialRulebookProvider

    registry = ScientificModelRegistry()
    registry.register_and_bind(BuiltinMaterialRulebookProvider())
    return RegistryScientificModelResolver(registry=registry)


__all__ = [
    "CapabilityDescriptor",
    "ModelDiagnostic",
    "ModelRequest",
    "ModelResult",
    "ModelStatus",
    "NoScientificModelResolver",
    "ProviderDescriptor",
    "ProviderProvenance",
    "RegistryScientificModelResolver",
    "ScientificModelProvider",
    "ScientificModelRegistry",
    "ScientificModelResolver",
    "create_default_scientific_model_resolver",
    "empty_mapping",
    "freeze_mapping",
    "freeze_value",
    "require_token",
]
