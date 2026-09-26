"""Observation unit identity does not imply a measurement or scientific model."""
from enum import Enum
from .vocabularies import VocabularyDomain


class ObservationUnitBase(Enum):
    """Python extensions declare members under this observation-only base."""


class ObservationUnit(ObservationUnitBase):
    SINGLE_CELL = 'single_cell'


OBSERVATION_UNITS = VocabularyDomain('observation_unit', ObservationUnitBase, ObservationUnit)
STANDARD_OBSERVATION_UNITS = OBSERVATION_UNITS.standard_registry
