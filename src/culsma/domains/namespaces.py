"""Source type names shared by domain installation and language resolution.

This module owns naming mechanics only. The domain composition root supplies
built-in types; registries supply context-local extension types.
"""
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType


class SourceTypeNamespace(Mapping):
    def __init__(self):
        self.builtins = None
        self.reserved = frozenset()
        self.active = ContextVar('source_type_names', default=MappingProxyType({}))

    def configure(self, builtins, reserved=()):
        if self.builtins is not None:
            raise RuntimeError('Source type namespace is already configured')
        types = dict(builtins)
        if any(name != family.__name__ for name, family in types.items()):
            raise ValueError('Source type names must match their declared classes')
        self.builtins = MappingProxyType(types)
        self.reserved = frozenset(reserved)

    def validate(self, owner, types):
        if self.builtins is None:
            raise RuntimeError('Domain composition has not configured source types')
        for name, family in types.items():
            if name != family.__name__ or not name.isidentifier():
                raise ValueError('Invalid source type name')
            builtin = self.builtins.get(name)
            if (builtin is not None and builtin is not family) or name in self.reserved:
                raise ValueError(f'Vocabulary namespace collision: {name}')
            for other_owner, installed in self.active.get().items():
                if other_owner != owner and name in installed:
                    raise ValueError(f'Vocabulary namespace collision: {name}')

    @contextmanager
    def activate(self, owner, types):
        installed = MappingProxyType(dict(types))
        self.validate(owner, installed)
        token = self.active.set(MappingProxyType({**self.active.get(), owner: installed}))
        try:
            yield self
        finally:
            self.active.reset(token)

    def snapshot(self):
        if self.builtins is None:
            raise RuntimeError('Domain composition has not configured source types')
        types = dict(self.builtins)
        for installed in self.active.get().values():
            types.update(installed)
        return MappingProxyType(types)

    def __getitem__(self, name):
        return self.snapshot()[name]

    def __iter__(self):
        return iter(self.snapshot())

    def __len__(self):
        return len(self.snapshot())

