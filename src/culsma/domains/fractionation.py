"""Fractionation programs: density-gradient types and chromatography extension rules."""

from enum import StrEnum
from culsma.common.enum_parameters import EnumParameter
from culsma.common.enum_registration import EnumTypeRegistration
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
import re
from culsma.common.type_name_contracts import NamespaceBinding
from culsma.common.enum_parameters import CallParameterContract


class DensityGradientAxis(StrEnum):
    DENSITY = "density"


class DensityGradientOrder(StrEnum):
    TOP_TO_BOTTOM = "top_to_bottom"
    BOTTOM_TO_TOP = "bottom_to_top"


DENSITY_GRADIENT_AXIS = EnumParameter(DensityGradientAxis)
DENSITY_GRADIENT_ORDER = EnumParameter(DensityGradientOrder)


class ChromatographyAxisBase(Enum):
    """Extend this empty base with text-valued axis members."""


class ChromatographyOrderBase(Enum):
    """Order members declare (wire spelling, exact axis member)."""

    def __new__(cls, wire: str, axis: ChromatographyAxisBase):
        obj = object.__new__(cls)
        obj._value_ = wire
        obj.axis = axis
        return obj


class ChromatographyAxis(ChromatographyAxisBase):
    RETENTION_TIME = 'retention_time'


class ChromatographyOrder(ChromatographyOrderBase):
    EARLY_TO_LATE = ('early_to_late', ChromatographyAxis.RETENTION_TIME)


@dataclass(frozen=True)
class ChromatographyType:
    enum_type: type[Enum]
    stable_id: str
    version: int

    @property
    def family(self):
        return 'axis' if issubclass(self.enum_type, ChromatographyAxisBase) else 'order'


@dataclass(frozen=True)
class ChromatographyRegistry:
    entries: tuple[ChromatographyType, ...] = ()
    namespace: NamespaceBinding = field(default_factory=NamespaceBinding, compare=False, repr=False, kw_only=True)

    @property
    def types(self):
        return MappingProxyType({entry.enum_type.__name__: entry.enum_type for entry in self.entries})

    def __post_init__(self):
        object.__setattr__(self, 'entries', tuple(self.entries))
        for index, entry in enumerate(self.entries):
            if not isinstance(entry, ChromatographyType):
                raise TypeError('Expected a registered chromatography type descriptor')
            self.validate_type(entry.enum_type, entry.stable_id, entry.version, self.entries[:index])

    def with_type(self, enum_type, stable_id: str, version: int = 1):
        return ChromatographyRegistry((*self.entries, ChromatographyType(enum_type, stable_id, version)), namespace=self.namespace)

    @staticmethod
    def validate_type(enum_type, stable_id: str, version: int, entries):
        if not isinstance(enum_type, type) or not issubclass(enum_type, (ChromatographyAxisBase, ChromatographyOrderBase)):
            raise TypeError('Expected a chromatography axis or order subclass')
        base = ChromatographyAxisBase if issubclass(enum_type, ChromatographyAxisBase) else ChromatographyOrderBase
        EnumTypeRegistration.validate_family(enum_type, base)
        if not enum_type.__members__ or len(enum_type.__members__) != len(enum_type):
            raise ValueError('Extension members must be nonempty and must not be aliases')
        if not isinstance(stable_id, str) or not re.fullmatch(r'[a-z][a-z0-9_.-]*', stable_id):
            raise ValueError('Extension identity must be a stable lowercase identifier')
        if type(version) is not int or version < 1:
            raise ValueError('Extension version must be a positive integer')
        if any(entry.stable_id == stable_id or entry.enum_type.__name__ == enum_type.__name__
               or entry.enum_type is enum_type for entry in entries):
            raise ValueError('Duplicate extension identity or source type name')
        builtins = {ChromatographyAxis: 'culsma.chromatography.axis',
                    ChromatographyOrder: 'culsma.chromatography.order'}
        if enum_type in builtins:
            if stable_id != builtins[enum_type] or version != 1:
                raise ValueError('Standard type identity cannot be changed')
        elif stable_id.startswith('culsma.') or enum_type.__name__ in {'ChromatographyAxis', 'ChromatographyOrder'}:
            raise ValueError('Standard type identity is reserved')
        for member in enum_type:
            if type(member.value) is not str or not member.value:
                raise TypeError('Extension wire values must be nonempty text')
            if any(member.value == other.value for entry in entries
                   for other in entry.enum_type
                   if isinstance(member, ChromatographyAxisBase) == isinstance(other, ChromatographyAxisBase)):
                raise ValueError('Extension wire spelling collides with an installed member')
            if isinstance(member, ChromatographyOrderBase):
                if not any(type(member.axis) is entry.enum_type for entry in entries):
                    raise ValueError('Order axis must be registered first')
                if not isinstance(member.axis, ChromatographyAxisBase):
                    raise TypeError('Order must declare an exact registered axis member')


    def registration(self, member):
        for entry in self.entries:
            if type(member) is entry.enum_type:
                return entry
        raise ValueError('Chromatography member type is not registered')

    def encode(self, member):
        entry = self.registration(member)
        return {'kind': 'ChromatographyEnum', 'family': entry.family,
                'id': entry.stable_id, 'version': entry.version, 'member': member.name}

    def decode(self, payload):
        if not isinstance(payload, dict) or payload.get('kind') != 'ChromatographyEnum':
            raise ValueError('Invalid chromatography payload')
        if type(payload.get('version')) is not int or type(payload.get('member')) is not str:
            raise ValueError('Invalid chromatography identity')
        for entry in self.entries:
            if (entry.stable_id, entry.version, entry.family) == (payload.get('id'), payload.get('version'), payload.get('family')):
                try:
                    return entry.enum_type[payload['member']]
                except KeyError as error:
                    raise ValueError('Unknown chromatography member') from error
        raise ValueError('Unknown chromatography type or version')

    def same_parameter_family(self, first_name, second_name):
        first, second = self.types.get(first_name), self.types.get(second_name)
        if first is None or second is None:
            return False
        return any(issubclass(first, base) and issubclass(second, base)
                   for base in (ChromatographyAxisBase, ChromatographyOrderBase))

    def validate_pair(self, axis, order):
        if isinstance(axis, ChromatographyAxisBase) and isinstance(order, ChromatographyOrderBase):
            self.registration(axis)
            self.registration(order)
            if order.axis is not axis:
                raise ValueError('Chromatography order does not belong to the selected axis')
        elif self.is_extension(axis) or self.is_extension(order):
            raise ValueError('An extension requires a registered matching axis and order')

    def is_extension(self, value):
        if not isinstance(value, (ChromatographyAxisBase, ChromatographyOrderBase)):
            return False
        return self.registration(value).enum_type not in (ChromatographyAxis, ChromatographyOrder)

    @contextmanager
    def activate(self):
        if not all(entry in self.entries for entry in STANDARD_CHROMATOGRAPHY_REGISTRY.entries):
            raise ValueError('An active registry must preserve standard chromatography types')
        with self.namespace.require().activate('chromatography', self.types):
            token = ACTIVE_CHROMATOGRAPHY_REGISTRY.set(self)
            try:
                yield self
            finally:
                ACTIVE_CHROMATOGRAPHY_REGISTRY.reset(token)


STANDARD_CHROMATOGRAPHY_REGISTRY = (
    ChromatographyRegistry()
    .with_type(ChromatographyAxis, 'culsma.chromatography.axis')
    .with_type(ChromatographyOrder, 'culsma.chromatography.order')
)
ACTIVE_CHROMATOGRAPHY_REGISTRY = ContextVar('chromatography_registry', default=STANDARD_CHROMATOGRAPHY_REGISTRY)


@dataclass(frozen=True)
class ChromatographyParameter:
    allow_legacy_text = True
    enum_type: type[Enum]

    def validate(self, value):
        if not isinstance(value, self.enum_type):
            raise TypeError(f'Expected {self.enum_type.__name__}')
        ACTIVE_CHROMATOGRAPHY_REGISTRY.get().registration(value)
        return value

    @property
    def wire_values(self):
        return tuple(member.value for family in (ChromatographyAxis, ChromatographyOrder)
                     if issubclass(family, self.enum_type) for member in family)

    def decode(self, value):
        # Only canonical standard spellings are promoted. Extension text is never registration.
        for family in (ChromatographyAxis, ChromatographyOrder):
            if issubclass(family, self.enum_type):
                for member in family:
                    if member.value == value:
                        return member
        raise ValueError('Unknown standard chromatography spelling')


CHROMATOGRAPHY_AXIS = ChromatographyParameter(ChromatographyAxisBase)
CHROMATOGRAPHY_ORDER = ChromatographyParameter(ChromatographyOrderBase)


class ChromatographyPairRule:
    parameters = frozenset({'axis', 'order'})

    def validate(self, values, present):
        ACTIVE_CHROMATOGRAPHY_REGISTRY.get().validate_pair(values['axis'], values['order'])


CALL_PARAMETER_CONTRACTS = MappingProxyType({'density_gradient_program': CallParameterContract({'axis': DENSITY_GRADIENT_AXIS, 'order': DENSITY_GRADIENT_ORDER}), 'chromatography_program': CallParameterContract({'axis': CHROMATOGRAPHY_AXIS, 'order': CHROMATOGRAPHY_ORDER}, (ChromatographyPairRule(),))})
