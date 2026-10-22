"""Exact adapter lookup and default runtime assembly."""
from __future__ import annotations

from functools import lru_cache
from culsma.runtime.value_adapters.contracts import ValueAdapter


class ValueAdapterRegistry:
    def __init__(self) -> None:
        self.adapters: dict[str, ValueAdapter] = {}

    def register(self, type_id: str, adapter: ValueAdapter) -> None:
        if not type_id or type_id in self.adapters:
            raise ValueError(f'Invalid or duplicate adapter identity: {type_id}')
        self.adapters[type_id] = adapter

    def resolve(self, type_id: str) -> ValueAdapter | None:
        """Return the registered adapter, without probing values or invoking handlers."""
        return self.adapters.get(type_id)


@lru_cache(maxsize=1)
def create_value_adapter_registry() -> ValueAdapterRegistry:
    from culsma.runtime.value_adapters.material import MaterialValueAdapter
    from culsma.runtime.value_adapters.configuration import ConfigurationValueAdapter
    registry = ValueAdapterRegistry()
    material = MaterialValueAdapter()
    for type_id in material.type_ids:
        registry.register(type_id, material)
    configuration = ConfigurationValueAdapter()
    for type_id in configuration.type_ids:
        registry.register(type_id, configuration)
    return registry
