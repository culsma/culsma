"""Schedule vocabulary."""
from enum import StrEnum
from .contracts import EnumParameter


class ScheduleMode(StrEnum):
    DISCRETE = "discrete"
    CONTINUOUS = "continuous"


SCHEDULE_MODE = EnumParameter(ScheduleMode)
DEFAULT_SCHEDULE_MODE = ScheduleMode.DISCRETE
