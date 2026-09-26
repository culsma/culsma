"""Program-owned separation outputs and closed disruption parameters."""
from __future__ import annotations
from enum import Enum, StrEnum
from types import MappingProxyType
from .contracts import EnumParameter


class ProgramOutput(Enum):
    """Closed, program-owned identity for one ordered separation output."""

    def __new__(cls, part_id: str, semantic_role: str) -> ProgramOutput:
        member = object.__new__(cls)
        member._value_ = (part_id, semantic_role)
        return member

    @property
    def part_id(self) -> str:
        return self.value[0]

    @property
    def semantic_role(self) -> str:
        return self.value[1]


class SepProgramOutput(ProgramOutput):
    FRACTION_A = ("0", "fraction_0")
    FRACTION_B = ("1", "fraction_1")


class CentrifugeProgramOutput(ProgramOutput):
    SUPERNATANT = ("0", "supernatant")
    PELLET = ("1", "pellet")


class MagneticProgramOutput(ProgramOutput):
    BOUND = ("0", "bound")
    FLOWTHROUGH = ("1", "flowthrough")


class DisruptProgramOutput(ProgramOutput):
    LYSATE = ("0", "lysate")
    DEBRIS_OR_RESIDUE = ("1", "debris_or_residue")


class FieldProgramOutput(ProgramOutput):
    TARGET_BAND_FRACTION = ("0", "target_band_fraction")
    NON_TARGET_FRACTION = ("1", "non_target_fraction")


class FiltrationProgramOutput(ProgramOutput):
    FILTRATE = ("0", "filtrate")
    RETENTATE = ("1", "retentate")


class CentrifugalFiltrationProgramOutput(ProgramOutput):
    FILTRATE = ("0", "filtrate")
    RETENTATE = ("1", "retentate")


class PhasePartitionProgramOutput(ProgramOutput):
    TARGET_PHASE = ("0", "target_phase")
    OTHER_PHASE = ("1", "other_phase")


class PrecipitationProgramOutput(ProgramOutput):
    PRECIPITATE = ("0", "precipitate")
    SUPERNATANT = ("1", "supernatant")


class DisruptionMethod(StrEnum):
    MECHANICAL = "mechanical"
    SONICATION = "sonication"
    SHEAR_HOMOGENIZATION = "shear_homogenization"
    HIGH_PRESSURE_DISRUPTION = "high_pressure_disruption"
    BEAD_IMPACT = "bead_impact"


CENTRIFUGE_KEEP_SOURCE = EnumParameter(CentrifugeProgramOutput)
DISRUPTION_METHOD = EnumParameter(DisruptionMethod)


PROGRAM_OUTPUT_TYPES = MappingProxyType({family.__name__: family for family in (
    SepProgramOutput, CentrifugeProgramOutput, MagneticProgramOutput,
    DisruptProgramOutput, FieldProgramOutput, FiltrationProgramOutput,
    CentrifugalFiltrationProgramOutput, PhasePartitionProgramOutput, PrecipitationProgramOutput,
)})
