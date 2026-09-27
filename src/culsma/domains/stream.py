"""Observation unit identity does not imply a measurement or scientific model."""
from enum import Enum
from dataclasses import dataclass
from culsma.common.enum_registration import EnumTypeRegistry
from culsma.common.enum_parameters import CallParameterContract
from types import MappingProxyType


class ObservationUnitBase(Enum):
    """Python extensions declare members under this observation-only base."""


class ObservationUnit(ObservationUnitBase):
    SINGLE_CELL = 'single_cell'


@dataclass(frozen=True)
class StreamUnitContract:
    registry: EnumTypeRegistry
    enum_type = ObservationUnitBase
    standard = ObservationUnit
    allow_legacy_text = True

    @property
    def standard_registry(self):
        return self.registry

    @property
    def current(self):
        return self.registry.current

    @property
    def wire_values(self):
        return tuple(member.value for member in ObservationUnit)

    def validate(self, value):
        if not isinstance(value, ObservationUnitBase):
            raise TypeError('Expected an observation unit')
        self.current.registration(type(value))
        return value

    def decode(self, value):
        if type(value) is not str:
            raise TypeError('Expected an observation unit spelling')
        return ObservationUnit(value)


STANDARD_OBSERVATION_UNITS = EnumTypeRegistry.create(ObservationUnitBase, ObservationUnit, 'observation_unit')
OBSERVATION_UNITS = StreamUnitContract(STANDARD_OBSERVATION_UNITS)
CALL_PARAMETER_CONTRACTS = MappingProxyType({'stream': CallParameterContract({'unit': OBSERVATION_UNITS})})
