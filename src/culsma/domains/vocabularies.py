"""Scoped registry mechanics shared by distinct, domain-owned vocabulary bases."""
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
import re
from .namespace_contracts import NamespaceBinding

ACTIVE_VOCABULARIES = ContextVar('active_vocabularies', default=MappingProxyType({}))


@dataclass(frozen=True)
class VocabularyType:
    enum_type: type[Enum]
    stable_id: str
    version: int = 1


@dataclass(frozen=True)
class VocabularyDomain:
    name: str
    enum_type: type[Enum]
    standard: type[Enum]
    allow_legacy_text: bool = True
    preserve_legacy_values: bool = False
    namespace: NamespaceBinding = field(default_factory=NamespaceBinding, compare=False, repr=False, kw_only=True)

    @property
    def standard_registry(self):
        return VocabularyRegistry(self, (VocabularyType(self.standard, f'culsma.{self.name}'),))

    @property
    def current(self):
        return ACTIVE_VOCABULARIES.get().get(self.name, self.standard_registry)

    @property
    def wire_values(self):
        return tuple(member.value for member in self.standard)

    def validate(self, value):
        if not isinstance(value, self.enum_type):
            raise TypeError(f'Expected {self.enum_type.__name__}')
        self.current.registration(type(value))
        return value

    def decode(self, value):
        for member in self.standard:
            if type(value) is str and member.value == value:
                return member
        raise ValueError(f'Unknown standard {self.name} spelling')


@dataclass(frozen=True)
class VocabularyRegistry:
    domain: VocabularyDomain
    entries: tuple[VocabularyType, ...]

    def __post_init__(self):
        object.__setattr__(self, 'entries', tuple(self.entries))
        names, identities, wires = set(), set(), set()
        standard_found = False
        for entry in self.entries:
            if not isinstance(entry, VocabularyType):
                raise TypeError('Expected a vocabulary registration')
            family = entry.enum_type
            if not isinstance(family, type) or not issubclass(family, self.domain.enum_type):
                raise TypeError('Vocabulary type belongs to another domain')
            if not family.__members__ or len(family.__members__) != len(family):
                raise ValueError('Vocabulary members must be nonempty and may not alias one another')
            if type(entry.version) is not int or entry.version < 1:
                raise ValueError('Vocabulary version must be a positive integer')
            if not isinstance(entry.stable_id, str) or not re.fullmatch(r'[a-z][a-z0-9_.-]*', entry.stable_id):
                raise ValueError('Invalid stable vocabulary identity')
            if family.__name__ in names or entry.stable_id in identities:
                raise ValueError('Duplicate vocabulary identity or source namespace')
            names.add(family.__name__)
            identities.add(entry.stable_id)
            if family is self.domain.standard:
                standard_found = True
                if (entry.stable_id, entry.version) != (f'culsma.{self.domain.name}', 1):
                    raise ValueError('Standard vocabulary identity cannot change')
            elif entry.stable_id.startswith('culsma.') or family.__name__ == self.domain.standard.__name__:
                raise ValueError('Standard vocabulary identity is reserved')
            for member in family:
                if type(member.value) is not str or not member.value:
                    raise TypeError('Vocabulary member values must be nonempty strings')
                if member.value in wires:
                    raise ValueError('Vocabulary spelling collides with an installed member')
                wires.add(member.value)
        if not standard_found:
            raise ValueError('Registry must retain its standard vocabulary')

    @property
    def types(self):
        return MappingProxyType({entry.enum_type.__name__: entry.enum_type for entry in self.entries})

    def with_type(self, enum_type, stable_id, version=1):
        return VocabularyRegistry(self.domain, (*self.entries, VocabularyType(enum_type, stable_id, version)))

    def registration(self, family):
        for entry in self.entries:
            if entry.enum_type is family:
                return entry
        raise ValueError(f'Uninstalled {self.domain.name} vocabulary')

    def encode(self, member):
        entry = self.registration(type(member))
        return {'kind': 'DomainEnum', 'domain': self.domain.name, 'id': entry.stable_id,
                'version': entry.version, 'member': member.name}

    def decode(self, payload):
        if payload.get('kind') != 'DomainEnum' or payload.get('domain') != self.domain.name:
            raise ValueError('Wrong vocabulary payload domain')
        if type(payload.get('version')) is not int or type(payload.get('member')) is not str:
            raise ValueError('Invalid vocabulary identity')
        for entry in self.entries:
            if (entry.stable_id, entry.version) == (payload.get('id'), payload.get('version')):
                try:
                    return entry.enum_type[payload['member']]
                except KeyError as error:
                    raise ValueError('Unknown vocabulary member') from error
        raise ValueError('Unknown vocabulary identity or version')

    @contextmanager
    def activate(self):
        with self.domain.namespace.require().activate(self.domain.name, self.types):
            token = ACTIVE_VOCABULARIES.set(MappingProxyType({**ACTIVE_VOCABULARIES.get(), self.domain.name: self}))
            try:
                yield self
            finally:
                ACTIVE_VOCABULARIES.reset(token)



class VocabularyCatalog(Mapping):
    def __init__(self, fallback, domains):
        self.fallback = fallback
        self.domains = tuple(domains)

    def __getitem__(self, name):
        for domain in self.domains:
            if name in domain.current.types:
                return domain.current.types[name]
        return self.fallback[name]

    def __iter__(self):
        names = set(self.fallback)
        for domain in self.domains:
            names.update(domain.current.types)
        return iter(sorted(names))

    def __len__(self):
        return sum(1 for _ in self)

    def domain_for_type(self, family):
        for domain in self.domains:
            if isinstance(family, type) and issubclass(family, domain.enum_type):
                return domain
        return None

    def decode(self, payload):
        for domain in self.domains:
            if domain.name == payload.get('domain'):
                return domain.current.decode(payload)
        raise ValueError('Unknown vocabulary domain')

    def same_parameter_family(self, first, second):
        first_domain = self.domain_for_type(self.get(first))
        return first_domain is not None and first_domain is self.domain_for_type(self.get(second))
