"""Schedule vocabulary."""

from culsma.common.value_contracts import VALUE_CONTRACTS, ReadCallContract
from enum import StrEnum
from culsma.common.enum_parameters import EnumParameter
from types import MappingProxyType
from culsma.common.enum_parameters import CallParameterContract


class ScheduleMode(StrEnum):
    DISCRETE = "discrete"
    CONTINUOUS = "continuous"


SCHEDULE_MODE = EnumParameter(ScheduleMode)
DEFAULT_SCHEDULE_MODE = ScheduleMode.DISCRETE


CALL_PARAMETER_CONTRACTS = MappingProxyType({'schedule': CallParameterContract({'mode': SCHEDULE_MODE})})


VALUE_CONTRACTS.register_call('schedule', ReadCallContract('configuration.schedule'))
