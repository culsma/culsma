"""Explicit capability-to-provider bindings for scientific-model resolution."""

from __future__ import annotations

from .contracts import CapabilityDescriptor, ScientificModelProvider


class ScientificModelRegistry:
    """Run-configuration registry with one selected provider per capability."""

    def __init__(self) -> None:
        self._providers: dict[str, ScientificModelProvider] = {}
        self._bindings: dict[tuple[str, str], str] = {}

    def register(self, provider: ScientificModelProvider, *, replace: bool = False) -> None:
        descriptor = provider.descriptor
        existing = self._providers.get(descriptor.provider_id)
        if existing is not None and not replace:
            raise ValueError(f"provider '{descriptor.provider_id}' is already registered")
        if existing is not None:
            supported = {capability.key for capability in descriptor.capabilities}
            stale = [
                key
                for key, provider_id in self._bindings.items()
                if provider_id == descriptor.provider_id and key not in supported
            ]
            if stale:
                raise ValueError(
                    f"replacement provider '{descriptor.provider_id}' no longer supports "
                    f"bound capabilities {stale!r}"
                )
        self._providers[descriptor.provider_id] = provider

    def bind(
        self,
        capability: str,
        contract_version: str,
        provider_id: str,
        *,
        replace: bool = False,
    ) -> None:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise LookupError(f"provider '{provider_id}' is not registered")
        if not provider.descriptor.supports(capability, contract_version):
            raise ValueError(
                f"provider '{provider_id}' does not declare capability "
                f"'{capability}' version '{contract_version}'"
            )
        key = capability, contract_version
        existing = self._bindings.get(key)
        if existing is not None and existing != provider_id and not replace:
            raise ValueError(
                f"capability '{capability}' version '{contract_version}' is already "
                f"bound to provider '{existing}'"
            )
        self._bindings[key] = provider_id

    def register_and_bind(
        self,
        provider: ScientificModelProvider,
        *,
        replace: bool = False,
    ) -> None:
        descriptor = provider.descriptor
        next_providers = dict(self._providers)
        next_bindings = dict(self._bindings)

        existing = next_providers.get(descriptor.provider_id)
        if existing is not None and not replace:
            raise ValueError(f"provider '{descriptor.provider_id}' is already registered")

        supported = {capability.key for capability in descriptor.capabilities}
        if existing is not None:
            stale = [
                key
                for key, provider_id in next_bindings.items()
                if provider_id == descriptor.provider_id and key not in supported
            ]
            if stale:
                raise ValueError(
                    f"replacement provider '{descriptor.provider_id}' no longer supports "
                    f"bound capabilities {stale!r}"
                )

        for key in supported:
            selected = next_bindings.get(key)
            if selected is not None and selected != descriptor.provider_id and not replace:
                raise ValueError(
                    f"capability '{key[0]}' version '{key[1]}' is already bound "
                    f"to provider '{selected}'"
                )

        next_providers[descriptor.provider_id] = provider
        for key in supported:
            next_bindings[key] = descriptor.provider_id
        self._providers = next_providers
        self._bindings = next_bindings

    def provider_for(
        self,
        capability: str,
        contract_version: str,
    ) -> ScientificModelProvider | None:
        provider_id = self._bindings.get((capability, contract_version))
        if provider_id is None:
            return None
        return self._providers[provider_id]

    def registered_provider(self, provider_id: str) -> ScientificModelProvider | None:
        return self._providers.get(provider_id)

    def capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        descriptors: list[CapabilityDescriptor] = []
        for key in sorted(self._bindings):
            provider = self._providers[self._bindings[key]]
            descriptors.extend(
                capability
                for capability in provider.descriptor.capabilities
                if capability.key == key
            )
        return tuple(descriptors)

    def selected_provider_id(self, capability: str, contract_version: str) -> str | None:
        return self._bindings.get((capability, contract_version))
