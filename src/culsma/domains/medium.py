"""Typed external media. Requirements do not predict uptake or modify inventory."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from math import isclose
from typing import ClassVar

from culsma.common.enum_parameters import CallParameterContract, EnumParameter
from culsma.common.value_contracts import VALUE_CONTRACTS, ReadCallContract
from culsma.common.quantity_arithmetic import QuantityDimension, quantity_parts, UNIT_TO_DIMENSION


class MediumPhase(StrEnum):
    GAS = "gas"
    LIQUID = "liquid"


class CompositionCoverage(StrEnum):
    PARTIAL = "partial"
    COMPLETE = "complete"


class CompositionBasis(StrEnum):
    MOLE_FRACTION = "mole_fraction"
    VOLUME_FRACTION = "volume_fraction"
    MASS_FRACTION = "mass_fraction"
    MASS_CONCENTRATION = "mass_concentration"


@dataclass(frozen=True)
class ComponentRequirement:
    material: str
    quantity: tuple[float, str]
    basis: CompositionBasis

    def __post_init__(self):
        if not isinstance(self.material, str) or not self.material.strip():
            raise ValueError("medium component material must be a nonempty material code")
        if type(self.basis) is not CompositionBasis:
            raise ValueError("medium component basis must be CompositionBasis")
        number, unit = quantity_parts(self.quantity)
        expected = (QuantityDimension.MASS_CONCENTRATION
                    if self.basis is CompositionBasis.MASS_CONCENTRATION else QuantityDimension.PERCENT)
        if UNIT_TO_DIMENSION.get(unit) is not expected:
            raise ValueError(f"{self.basis.value} requires a {expected.value} quantity")
        if number < 0 or (expected is QuantityDimension.PERCENT and number > 100):
            raise ValueError("medium composition quantity is outside its permitted range")
        object.__setattr__(self, 'quantity', (number, '%' if unit == 'pct' else unit))


@dataclass(frozen=True)
class CompositionSpec:
    components: tuple[ComponentRequirement, ...] = ()
    coverage: CompositionCoverage = CompositionCoverage.PARTIAL

    def __post_init__(self):
        if type(self.coverage) is not CompositionCoverage:
            raise ValueError("composition coverage must be CompositionCoverage")
        if not isinstance(self.components, (tuple, list)) or any(
                not isinstance(c, ComponentRequirement) for c in self.components):
            raise ValueError("composition components must be ComponentRequirement values")
        object.__setattr__(self, 'components', tuple(self.components))
        identities = [c.material for c in self.components]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate medium component material")
        fractions = [c for c in self.components if c.basis is not CompositionBasis.MASS_CONCENTRATION]
        bases = {c.basis for c in fractions}
        if len(bases) > 1:
            raise ValueError("composition fractions must use one common basis")
        total = sum(c.quantity[0] for c in fractions)
        if total > 100 and not isclose(total, 100, rel_tol=0, abs_tol=1e-9):
            raise ValueError("composition fractions exceed 100%")
        if self.coverage is CompositionCoverage.COMPLETE and (
                not fractions or len(fractions) != len(self.components)
                or not isclose(total, 100, rel_tol=0, abs_tol=1e-9)):
            raise ValueError("complete composition requires fractions totaling 100% on one basis")


@dataclass(frozen=True)
class Medium(ABC):
    composition: CompositionSpec = field(default_factory=CompositionSpec)
    source: str | None = None
    phase: ClassVar[MediumPhase]

    def __post_init__(self):
        if type(self.phase) is not MediumPhase:
            raise ValueError("medium phase must be MediumPhase")
        if any(type(basis) is not CompositionBasis for basis in self.allowed_bases):
            raise ValueError("allowed_bases must contain CompositionBasis members")
        if not isinstance(self.composition, CompositionSpec):
            raise ValueError("medium composition must be CompositionSpec")
        if self.source is not None and (not isinstance(self.source, str) or not self.source.strip()):
            raise ValueError("medium source must be a nonempty resolved container identity")
        if self.phase is MediumPhase.LIQUID and self.source is None and not self.composition.components:
            raise ValueError("liquid medium requires composition requirements or an actual source")
        self.validate_composition()

    def validate_composition(self) -> None:
        """Reject composition measures unsupported by this medium category."""
        if any(c.basis not in self.allowed_bases for c in self.composition.components):
            raise ValueError(f"unsupported composition basis for {self.phase} medium")

    @property
    @abstractmethod
    def allowed_bases(self) -> frozenset[CompositionBasis]:
        """Measures accepted by the concrete medium type."""


@dataclass(frozen=True)
class GasMedium(Medium):
    """An empty, source-free gas descriptor denotes ordinary atmosphere."""
    phase: ClassVar[MediumPhase] = MediumPhase.GAS

    allowed_bases: ClassVar[frozenset[CompositionBasis]] = frozenset({
        CompositionBasis.MOLE_FRACTION, CompositionBasis.VOLUME_FRACTION, CompositionBasis.MASS_FRACTION})


@dataclass(frozen=True)
class LiquidMedium(Medium):
    phase: ClassVar[MediumPhase] = MediumPhase.LIQUID

    allowed_bases: ClassVar[frozenset[CompositionBasis]] = frozenset(CompositionBasis)


DEFAULT_MEDIUM: Medium = GasMedium()


CALL_PARAMETER_CONTRACTS = {
    "medium_component": CallParameterContract({"basis": EnumParameter(CompositionBasis)}),
    "composition": CallParameterContract({"coverage": EnumParameter(CompositionCoverage)}),
}

for _name in ('gas_medium', 'liquid_medium', 'composition', 'medium_component'):
    VALUE_CONTRACTS.register_call(_name, ReadCallContract('configuration.medium'))
