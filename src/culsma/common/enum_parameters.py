"""Exact enum-family parameter contracts; legacy text belongs to boundary adapters."""

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar, Protocol, Mapping, AbstractSet, Any
from types import MappingProxyType

E = TypeVar("E", bound=Enum)


def enum_wire_value(member: Enum) -> str:
    """Return the stable text representation of a supported domain member."""
    role = getattr(member, "semantic_role", None)
    value = role if role is not None else member.value
    if not isinstance(value, str):
        raise TypeError("Domain enum wire values must be text")
    return value


@dataclass(frozen=True)
class EnumParameter(Generic[E]):
    """A closed domain parameter; enum family identity is part of its type."""

    enum_type: type[E]
    allowed_members: frozenset[E] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.enum_type, type) or not issubclass(self.enum_type, Enum):
            raise TypeError("enum_type must be an Enum class")
        members = frozenset(self.enum_type) if self.allowed_members is None else frozenset(self.allowed_members)
        if any(type(member) is not self.enum_type for member in members):
            raise TypeError("Allowed members must belong to the exact declared enum family")
        if not members:
            raise ValueError("A closed enum parameter must allow at least one member")
        wires = [enum_wire_value(member) for member in members]
        if len(wires) != len(set(wires)):
            raise ValueError("Enum parameter wire values must be unique")
        object.__setattr__(self, "allowed_members", members)

    def validate(self, value: E) -> E:
        if type(value) is not self.enum_type:
            raise TypeError(f"Expected {self.enum_type.__name__}, got {type(value).__name__}")
        if value not in self.allowed_members:
            raise ValueError(f"{value.name} is not allowed for this parameter")
        return value

    def encode(self, value: E) -> str:
        """Serialize a validated member at an explicit wire boundary."""
        return enum_wire_value(self.validate(value))

    def decode(self, value: str) -> E:
        """Validate stored text and restore identity; this is not source resolution."""
        if type(value) is not str:
            raise TypeError("Serialized enum value must be a plain string")
        for member in self.enum_type:
            if enum_wire_value(member) == value:
                return self.validate(member)
        raise ValueError(f"Unknown {self.enum_type.__name__} value: {value!r}")

    @property
    def wire_values(self) -> tuple[str, ...]:
        return tuple(enum_wire_value(member) for member in self.enum_type if member in self.allowed_members)


class EnumParameterContract(Protocol):
    enum_type: type[Enum]

    def validate(self, value: Any) -> Enum: ...

    def decode(self, value: str) -> Enum | str: ...

    @property
    def wire_values(self) -> tuple[str, ...]: ...


class ParameterRule(Protocol):
    parameters: AbstractSet[str]

    def validate(self, values: Mapping[str, Any], present: AbstractSet[str]) -> None: ...


@dataclass(frozen=True)
class CallParameterContract:
    """Domain fields and dependent rules; stages own resolution and diagnostics."""

    fields: Mapping[str, "EnumParameterContract | RecordParameterContract"]
    rules: tuple[ParameterRule, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, 'fields', MappingProxyType(dict(self.fields)))
        object.__setattr__(self, 'rules', tuple(self.rules))
        for rule in self.rules:
            if not set(rule.parameters) <= self.fields.keys():
                raise ValueError('Rule dependencies must have registered parameter contracts')

    def validate_resolved(self, values: Mapping[str, Any], present: AbstractSet[str]) -> None:
        for rule in self.rules:
            if set(rule.parameters) <= values.keys():
                rule.validate(values, present)


@dataclass(frozen=True)
class RecordParameterContract:
    """Known typed fields within an otherwise open metadata record."""
    fields: Mapping[str, "EnumParameterContract | RecordParameterContract"]

    def __post_init__(self):
        object.__setattr__(self, 'fields', MappingProxyType(dict(self.fields)))
