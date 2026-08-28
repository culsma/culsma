"""Stable contracts for pluggable scientific-model providers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, runtime_checkable


def _empty_mapping() -> Mapping[str, object]:
    return MappingProxyType({})


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, frozenset):
        return frozenset(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze_value(item) for item in value)
    return value


def freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    """Copy a string-keyed mapping into a recursively read-only representation."""

    if any(not isinstance(key, str) for key in value):
        raise TypeError("scientific-model record keys must be strings")
    return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})


def _require_token(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


class ModelStatus(StrEnum):
    """Provider-level outcomes; kernel rejection is intentionally separate."""

    RESOLVED = "resolved"
    NOT_APPLICABLE = "not_applicable"
    FAILED = "failed"


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability: str
    contract_version: str
    lifecycle: str = "runtime_precommit"

    def __post_init__(self) -> None:
        _require_token(self.capability, "capability")
        _require_token(self.contract_version, "contract_version")
        _require_token(self.lifecycle, "lifecycle")

    @property
    def key(self) -> tuple[str, str]:
        return self.capability, self.contract_version


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_id: str
    provider_version: str
    capabilities: tuple[CapabilityDescriptor, ...]
    deterministic: bool = True

    def __post_init__(self) -> None:
        _require_token(self.provider_id, "provider_id")
        _require_token(self.provider_version, "provider_version")
        capabilities = tuple(self.capabilities)
        if not capabilities:
            raise ValueError("provider must declare at least one capability")
        keys = [descriptor.key for descriptor in capabilities]
        if len(keys) != len(set(keys)):
            raise ValueError("provider capability declarations must be unique")
        object.__setattr__(self, "capabilities", capabilities)

    def supports(self, capability: str, contract_version: str) -> bool:
        return any(
            descriptor.key == (capability, contract_version)
            for descriptor in self.capabilities
        )


@dataclass(frozen=True)
class ProviderProvenance:
    provider_id: str
    provider_version: str
    model_id: str | None = None
    model_version: str | None = None
    configuration: Mapping[str, object] = field(default_factory=_empty_mapping)

    def __post_init__(self) -> None:
        _require_token(self.provider_id, "provider_id")
        _require_token(self.provider_version, "provider_version")
        object.__setattr__(self, "configuration", freeze_mapping(self.configuration))

    @classmethod
    def from_descriptor(cls, descriptor: ProviderDescriptor) -> ProviderProvenance:
        return cls(
            provider_id=descriptor.provider_id,
            provider_version=descriptor.provider_version,
        )


@dataclass(frozen=True)
class ModelDiagnostic:
    code: str
    message: str
    severity: str = "error"

    def __post_init__(self) -> None:
        _require_token(self.code, "diagnostic code")
        _require_token(self.message, "diagnostic message")


@dataclass(frozen=True)
class ModelRequest:
    request_id: str
    capability: str
    contract_version: str
    payload: object
    lifecycle: str = "runtime_precommit"
    seed: int | None = None

    def __post_init__(self) -> None:
        _require_token(self.request_id, "request_id")
        _require_token(self.capability, "capability")
        _require_token(self.contract_version, "contract_version")
        _require_token(self.lifecycle, "lifecycle")
        object.__setattr__(self, "payload", _freeze_value(self.payload))

    @property
    def capability_key(self) -> tuple[str, str]:
        return self.capability, self.contract_version


@dataclass(frozen=True)
class ModelResult:
    status: ModelStatus
    proposal: object | None = None
    provenance: ProviderProvenance | None = None
    assumptions: Mapping[str, object] = field(default_factory=_empty_mapping)
    uncertainty: object | None = None
    diagnostics: tuple[ModelDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        status = ModelStatus(self.status)
        diagnostics = tuple(self.diagnostics)
        if status is ModelStatus.RESOLVED and self.proposal is None:
            raise ValueError("resolved scientific-model result requires a proposal")
        if status is ModelStatus.RESOLVED and self.provenance is None:
            raise ValueError("resolved scientific-model result requires provenance")
        if status is not ModelStatus.RESOLVED and self.proposal is not None:
            raise ValueError("non-resolved scientific-model result cannot carry a proposal")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "proposal", _freeze_value(self.proposal))
        object.__setattr__(self, "assumptions", freeze_mapping(self.assumptions))
        object.__setattr__(self, "uncertainty", _freeze_value(self.uncertainty))
        object.__setattr__(self, "diagnostics", diagnostics)

    @classmethod
    def resolved(
        cls,
        proposal: object,
        *,
        provenance: ProviderProvenance,
        assumptions: Mapping[str, object] | None = None,
        uncertainty: object | None = None,
        diagnostics: Sequence[ModelDiagnostic] = (),
    ) -> ModelResult:
        return cls(
            status=ModelStatus.RESOLVED,
            proposal=proposal,
            provenance=provenance,
            assumptions=assumptions or _empty_mapping(),
            uncertainty=uncertainty,
            diagnostics=tuple(diagnostics),
        )

    @classmethod
    def not_applicable(
        cls,
        *,
        provenance: ProviderProvenance | None = None,
        assumptions: Mapping[str, object] | None = None,
        diagnostics: Sequence[ModelDiagnostic] = (),
    ) -> ModelResult:
        return cls(
            status=ModelStatus.NOT_APPLICABLE,
            provenance=provenance,
            assumptions=assumptions or _empty_mapping(),
            diagnostics=tuple(diagnostics),
        )

    @classmethod
    def failed(
        cls,
        *,
        provenance: ProviderProvenance | None = None,
        diagnostics: Sequence[ModelDiagnostic] = (),
    ) -> ModelResult:
        return cls(
            status=ModelStatus.FAILED,
            provenance=provenance,
            diagnostics=tuple(diagnostics),
        )


@runtime_checkable
class ScientificModelProvider(Protocol):
    @property
    def descriptor(self) -> ProviderDescriptor:
        ...

    def resolve(self, request: ModelRequest) -> ModelResult:
        ...


@runtime_checkable
class ScientificModelResolver(Protocol):
    def capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        ...

    def resolve(self, request: ModelRequest) -> ModelResult:
        ...
