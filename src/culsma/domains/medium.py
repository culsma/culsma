"""Typed external media. Requirements do not predict uptake or modify inventory."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from math import isclose
from types import MappingProxyType
from typing import ClassVar, Mapping

from culsma.common.enum_parameters import CallParameterContract, EnumParameter
from culsma.common.value_contracts import VALUE_CONTRACTS, ReadCallContract
from culsma.common.quantity_arithmetic import QuantityDimension, quantity_parts, UNIT_TO_DIMENSION, convert_value


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
    contents: Mapping[str, tuple[float, str]] | None = None
    basis: CompositionBasis | None = None
    volume: tuple[float, str] | None = None

    def __post_init__(self):
        super().__post_init__()
        if self.contents is None:
            if self.source is None and not self.composition.components:
                raise ValueError("liquid medium requires contents or an actual source")
            if self.basis is not None or self.volume is not None:
                raise ValueError("basis and volume require liquid medium contents")
            return
        if self.source is not None or self.composition.components:
            raise ValueError("liquid medium contents must be specified separately from source or composition")
        contents, volume = normalize_liquid_contents(self.contents, basis=self.basis, volume=self.volume)
        object.__setattr__(self, "contents", contents)
        object.__setattr__(self, "volume", volume)


def normalize_liquid_contents(
    contents: Mapping[str, tuple[float, str]],
    *,
    basis: CompositionBasis | None = None,
    volume: tuple[float, str] | None = None,
) -> tuple[Mapping[str, tuple[float, str]], tuple[float, str] | None]:
    """Validate one liquid composition and normalize its quantities and final volume."""
    if not isinstance(contents, Mapping) or not contents:
        raise ValueError("liquid medium contents must be a nonempty map")
    if volume is not None:
        value, unit = quantity_parts(volume)
        if UNIT_TO_DIMENSION.get(unit) is not QuantityDimension.VOLUME or value <= 0:
            raise ValueError("liquid medium volume must be a positive volume quantity")
        volume = (convert_value(value, unit, "uL"), "uL")
    if basis is not None and (type(basis) is not CompositionBasis or basis is CompositionBasis.MASS_CONCENTRATION):
        raise ValueError("liquid medium basis must be a fraction member of CompositionBasis")

    expected = QuantityDimension.PERCENT if basis is not None else QuantityDimension.VOLUME
    canonical_unit = "%" if basis is not None else "uL"
    normalized = {}
    for identity, quantity in contents.items():
        if type(identity) is not str or not identity.strip():
            raise ValueError("liquid medium contents require a content identity")
        number, unit = quantity_parts(quantity)
        if UNIT_TO_DIMENSION.get(unit) is not expected or number < 0:
            raise ValueError(f"liquid medium contents require nonnegative {expected.value} quantities")
        normalized[identity] = (convert_value(number, unit, canonical_unit), canonical_unit)

    total, _ = quantity_parts(sum(value for value, _ in normalized.values()))
    if basis is not None:
        if not isclose(total, 100, rel_tol=0, abs_tol=1e-9):
            raise ValueError("liquid medium fractions must total 100%")
    else:
        if total <= 0:
            raise ValueError("liquid medium contents must have positive total volume")
        if volume is not None and not isclose(total, volume[0], rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError("liquid medium volume conflicts with the sum of its contents")
        volume = (total, "uL")
    return MappingProxyType(normalized), volume


DEFAULT_MEDIUM: Medium = GasMedium()


CALL_PARAMETER_CONTRACTS = {
    "liquid_medium": CallParameterContract({"basis": EnumParameter(CompositionBasis)}),
    "medium_component": CallParameterContract({"basis": EnumParameter(CompositionBasis)}),
    "composition": CallParameterContract({"coverage": EnumParameter(CompositionCoverage)}),
}

for _name in ('gas_medium', 'liquid_medium', 'composition', 'medium_component'):
    VALUE_CONTRACTS.register_call(_name, ReadCallContract('configuration.medium'))
