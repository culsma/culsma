"""A live index of installed enum classes, without a language-domain hierarchy."""
from collections.abc import Mapping
from types import MappingProxyType


class EnumTypeTable(Mapping):
    def __init__(self, closed_types, registration_sources):
        self.closed_types = MappingProxyType(dict(closed_types))
        # Each source pairs extensible Python bases with its current registry accessor.
        self.registration_sources = tuple(registration_sources)

    def snapshot(self):
        types = dict(self.closed_types)
        for bases, current in self.registration_sources:
            types.update(current().types)
        return types

    def __getitem__(self, name):
        return self.snapshot()[name]

    def __iter__(self):
        return iter(self.snapshot())

    def __len__(self):
        return len(self.snapshot())

    def registry_for_type(self, family):
        if isinstance(family, type):
            for bases, current in self.registration_sources:
                if issubclass(family, bases):
                    return current()
        return None

    def base_for_type(self, family):
        if isinstance(family, type):
            for bases, current in self.registration_sources:
                for base in bases:
                    if issubclass(family, base):
                        return base
        return None

    def same_parameter_family(self, first, second):
        base = self.base_for_type(self.get(first))
        return base is not None and base is self.base_for_type(self.get(second))

    def decode_registered(self, payload):
        if payload.get('kind') == 'DomainEnum':
            for bases, current in self.registration_sources:
                registry = current()
                if getattr(registry, 'wire_domain', None) == payload.get('domain'):
                    return registry.decode(payload)
        raise ValueError('Unknown enum registration identity')
