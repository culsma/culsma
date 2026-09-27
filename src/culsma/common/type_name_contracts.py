"""Naming port and explicit, one-time composition binding for domain registries."""
from collections.abc import Iterator, Mapping, KeysView, ValuesView
from contextlib import AbstractContextManager
from typing import Protocol


class TypeNamespace(Protocol):
    """The naming behavior required by installation and source resolution."""

    def validate(self, owner: str, types: Mapping[str, type]) -> None: ...
    def activate(self, owner: str, types: Mapping[str, type]) -> AbstractContextManager: ...
    def snapshot(self) -> Mapping[str, type]: ...
    def __getitem__(self, name: str) -> type: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...
    def get(self, name: str, default=None): ...
    def keys(self) -> KeysView[str]: ...
    def values(self) -> ValuesView[type]: ...


class NamespaceBinding:
    """An instance-owned dependency, wired once after domain declarations exist.

    Domain definitions are built before the complete built-in name catalog.
    Explicit composition binding breaks that construction ordering dependency
    without a global service lookup or a reverse import from domain modules.
    """

    def __init__(self, service: TypeNamespace | None = None):
        self._service = service

    @property
    def service(self) -> TypeNamespace | None:
        return self._service

    def bind(self, service: TypeNamespace) -> None:
        if self.service is not None:
            raise RuntimeError('Namespace dependency is already bound')
        self._service = service

    def require(self) -> TypeNamespace:
        if self.service is None:
            raise RuntimeError('Namespace dependency must be bound by composition before activation')
        return self.service
