"""Data reference kinds; kind identity does not supply measurement behavior."""
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from culsma.common.enum_parameters import CallParameterContract
from culsma.common.enum_registration import EnumTypeRegistry


class DataKindBase(Enum):
    """Base for explicitly installed data reference kind extensions."""


class DataKind(DataKindBase):
    OBSERVATION = 'observation'
    SEQUENCE_READ = 'sequence_read'
    SORT_RECORD = 'sort_record'


@dataclass(frozen=True)
class DataKindContract:
    registry: EnumTypeRegistry
    enum_type = DataKindBase
    standard = DataKind
    allow_legacy_text = True

    @property
    def current(self):
        return self.registry.current

    @property
    def wire_values(self):
        return tuple(member.value for member in self.standard)

    def validate(self, value):
        if not isinstance(value, DataKindBase):
            raise TypeError('Expected a data kind member')
        self.current.registration(type(value))
        return value

    def decode(self, value):
        if type(value) is not str:
            raise TypeError('Expected a data kind spelling')
        return self.standard(value)


STANDARD_DATA_KINDS = EnumTypeRegistry.create(DataKindBase, DataKind, 'data_kind')
DATA_KINDS = DataKindContract(STANDARD_DATA_KINDS)

CALL_PARAMETER_CONTRACTS = MappingProxyType({
    name: CallParameterContract({'kind': DATA_KINDS})
    for name in ('data_ref', 'data_group_ref')
})
