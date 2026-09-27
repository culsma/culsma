"""Immutable enum identity registration and scoped installation; no language taxonomy."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
import re
from .type_name_contracts import NamespaceBinding


@dataclass(frozen=True)
class EnumTypeRegistration:
    enum_type: type[Enum]
    stable_id: str
    version: int = 1

    @staticmethod
    def validate_family(enum_type, base_type):
        """Accept one enum inheritance family, including its empty intermediates."""
        if not isinstance(enum_type, type) or not issubclass(enum_type, base_type):
            raise TypeError('Enum type belongs to another domain')
        for ancestor in enum_type.__mro__:
            if issubclass(ancestor, Enum) and not (
                issubclass(ancestor, base_type) or issubclass(base_type, ancestor)
            ):
                raise TypeError('Registered types must belong to one enum family')


@dataclass(frozen=True)
class EnumTypeRegistry:
    base_type: type[Enum]
    standard_type: type[Enum]
    wire_domain: str
    entries: tuple[EnumTypeRegistration, ...]
    namespace: NamespaceBinding = field(default_factory=NamespaceBinding, compare=False, repr=False)
    active: ContextVar = field(default_factory=lambda: ContextVar('enum_registration', default=None), compare=False, repr=False)

    @classmethod
    def create(cls, base_type, standard_type, wire_domain):
        return cls(base_type, standard_type, wire_domain,
                   (EnumTypeRegistration(standard_type, f'culsma.{wire_domain}'),))

    @property
    def current(self):
        return self.active.get() or self


    def __post_init__(self):
        object.__setattr__(self, 'entries', tuple(self.entries))
        names, identities, wires = set(), set(), set()
        standard_found = False
        for entry in self.entries:
            if not isinstance(entry, EnumTypeRegistration):
                raise TypeError('Expected an enum registration')
            family = entry.enum_type
            EnumTypeRegistration.validate_family(family, self.base_type)
            if not family.__members__ or len(family.__members__) != len(family):
                raise ValueError('Enum members must be nonempty and may not alias one another')
            if type(entry.version) is not int or entry.version < 1:
                raise ValueError('Enum version must be a positive integer')
            if not isinstance(entry.stable_id, str) or not re.fullmatch(r'[a-z][a-z0-9_.-]*', entry.stable_id):
                raise ValueError('Invalid stable enum identity')
            if family.__name__ in names or entry.stable_id in identities:
                raise ValueError('Duplicate enum identity or source namespace')
            names.add(family.__name__)
            identities.add(entry.stable_id)
            if family is self.standard_type:
                standard_found = True
                if (entry.stable_id, entry.version) != (f'culsma.{self.wire_domain}', 1):
                    raise ValueError('Standard enum identity cannot change')
            elif entry.stable_id.startswith('culsma.') or family.__name__ == self.standard_type.__name__:
                raise ValueError('Standard enum identity is reserved')
            for member in family:
                if type(member.value) is not str or not member.value:
                    raise TypeError('Enum member values must be nonempty strings')
                if member.value in wires:
                    raise ValueError('Enum spelling collides with an installed member')
                wires.add(member.value)
        if not standard_found:
            raise ValueError('Registry must retain its standard enum')

    @property
    def types(self):
        return MappingProxyType({entry.enum_type.__name__: entry.enum_type for entry in self.entries})

    def with_type(self, enum_type, stable_id, version=1):
        return replace(self, entries=(*self.entries, EnumTypeRegistration(enum_type, stable_id, version)))

    def registration(self, family):
        for entry in self.entries:
            if entry.enum_type is family:
                return entry
        raise ValueError(f'Uninstalled {self.wire_domain} enum')

    def encode(self, member):
        entry = self.registration(type(member))
        return {'kind': 'DomainEnum', 'domain': self.wire_domain, 'id': entry.stable_id,
                'version': entry.version, 'member': member.name}

    def decode(self, payload):
        if payload.get('kind') != 'DomainEnum' or payload.get('domain') != self.wire_domain:
            raise ValueError('Wrong enum payload domain')
        if type(payload.get('version')) is not int or type(payload.get('member')) is not str:
            raise ValueError('Invalid enum identity')
        for entry in self.entries:
            if (entry.stable_id, entry.version) == (payload.get('id'), payload.get('version')):
                try:
                    return entry.enum_type[payload['member']]
                except KeyError as error:
                    raise ValueError('Unknown enum member') from error
        raise ValueError('Unknown enum identity or version')

    @contextmanager
    def activate(self):
        with self.namespace.require().activate(self.wire_domain, self.types):
            token = self.active.set(self)
            try:
                yield self
            finally:
                self.active.reset(token)
