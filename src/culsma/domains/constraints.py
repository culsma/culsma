"""Domain-owned requirement identities and existing application rules."""
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from .vocabularies import VocabularyDomain


@dataclass(frozen=True)
class RequirementSpec:
    category: str
    allowed_on: frozenset[str]
    scopes: frozenset[str]
    conflicts: frozenset[str] = frozenset()
    needs_context: frozenset[str] = frozenset()

    def __post_init__(self):
        operations = {'mutation', 'sep', 'frac', 'img', 'ecp', 'phy', 'stream', 'env_hold'}
        if not isinstance(self.category, str) or not self.category or not self.allowed_on or not set(self.allowed_on) <= operations:
            raise ValueError('Requirement must declare supported operation families')
        if not self.scopes or not set(self.scopes) <= {'stmt', 'block'}:
            raise ValueError('Requirement must declare statement/block scopes')
        if self.needs_context:
            raise ValueError('Custom context predicates are not supported')
        if any(not isinstance(item, str) or not item for item in self.conflicts):
            raise TypeError('Requirement conflicts must name requirement spellings')
        for name in ('allowed_on', 'scopes', 'conflicts', 'needs_context'):
            object.__setattr__(self, name, frozenset(getattr(self, name)))


class ConstraintRequirementBase(StrEnum):
    def __new__(cls, wire, spec):
        if not isinstance(spec, RequirementSpec):
            raise TypeError('Requirement members need a RequirementSpec')
        member = str.__new__(cls, wire)
        member._value_ = wire
        member.spec = spec
        return member


class ConstraintRequirement(ConstraintRequirementBase):
    DROPWISE = ('dropwise', RequirementSpec(
        category="delivery_mode",
        allowed_on=frozenset({"mutation"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    SPREAD = ('spread', RequirementSpec(
        category="delivery_mode",
        allowed_on=frozenset({"mutation"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    PRESERVE_BOUNDARY = ('preserve_boundary', RequirementSpec(
        category="structure_preservation",
        allowed_on=frozenset({"mutation", "sep", "frac"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    PRESERVE_LAYERING = ('preserve_layering', RequirementSpec(
        category="structure_preservation",
        allowed_on=frozenset({"mutation", "sep", "frac"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    PRESERVE_FRACTION_ORDER = ('preserve_fraction_order', RequirementSpec(
        category="structure_preservation",
        allowed_on=frozenset({"sep", "frac"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    ASEPTIC = ('aseptic', RequirementSpec(
        category="contamination_control",
        allowed_on=frozenset({"mutation", "sep", "img", "ecp", "phy", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    LOW_CARRYOVER = ('low_carryover', RequirementSpec(
        category="contamination_control",
        allowed_on=frozenset({"mutation", "sep", "img", "ecp", "phy", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    CROSS_CONTAM_CONTROL = ('cross_contam_control', RequirementSpec(
        category="contamination_control",
        allowed_on=frozenset({"mutation", "sep", "img", "ecp", "phy", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    GENTLE = ('gentle', RequirementSpec(
        category="material_integrity",
        allowed_on=frozenset({"mutation", "sep", "frac", "stream", "env_hold"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    AVOID_RESUSPENSION = ('avoid_resuspension', RequirementSpec(
        category="material_integrity",
        allowed_on=frozenset({"mutation", "sep", "frac"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    AVOID_SHEAR = ('avoid_shear', RequirementSpec(
        category="material_integrity",
        allowed_on=frozenset({"mutation", "sep", "frac", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    PRESERVE_VIABILITY = ('preserve_viability', RequirementSpec(
        category="material_integrity",
        allowed_on=frozenset({"mutation", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    COLD_CHAIN = ('cold_chain', RequirementSpec(
        category="environmental_protection",
        allowed_on=frozenset({"mutation", "sep", "frac", "img", "ecp", "phy", "stream", "env_hold"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    DARK_PROTECTED = ('dark_protected', RequirementSpec(
        category="environmental_protection",
        allowed_on=frozenset({"mutation", "img", "ecp", "phy", "stream", "env_hold"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    SEALED = ('sealed', RequirementSpec(
        category="environmental_protection",
        allowed_on=frozenset({"env_hold"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    CONTROLLED_ATMOSPHERE = ('controlled_atmosphere', RequirementSpec(
        category="environmental_protection",
        allowed_on=frozenset({"mutation", "img", "ecp", "phy", "stream", "env_hold"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    HIGH_PRECISION = ('high_precision', RequirementSpec(
        category="quantitative_quality",
        allowed_on=frozenset({"mutation", "sep", "frac", "ecp", "phy"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    LOW_LOSS = ('low_loss', RequirementSpec(
        category="quantitative_quality",
        allowed_on=frozenset({"mutation", "sep", "frac", "ecp", "phy"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    QUANTITATIVE_RECOVERY = ('quantitative_recovery', RequirementSpec(
        category="quantitative_quality",
        allowed_on=frozenset({"mutation", "sep", "frac"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    STABILIZED_READING = ('stabilized_reading', RequirementSpec(
        category="measurement_quality",
        allowed_on=frozenset({"img", "ecp", "phy"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    LOW_NOISE = ('low_noise', RequirementSpec(
        category="measurement_quality",
        allowed_on=frozenset({"img", "ecp", "phy"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    NONINVASIVE = ('noninvasive', RequirementSpec(
        category="measurement_quality",
        allowed_on=frozenset({"img", "ecp", "phy"}),
        scopes=frozenset({"stmt", "block"}),
    ))
    CUSTOMIZED = ('customized', RequirementSpec(
        category="customized",
        allowed_on=frozenset({"mutation", "sep", "frac", "img", "ecp", "phy", "stream"}),
        scopes=frozenset({"stmt", "block"}),
    ))


CONSTRAINT_REQUIREMENTS = VocabularyDomain(
    'constraint_requirement', ConstraintRequirementBase, ConstraintRequirement, allow_legacy_text=False)
STANDARD_CONSTRAINT_REQUIREMENTS = CONSTRAINT_REQUIREMENTS.standard_registry


class RequirementSpecRegistry(Mapping):
    def __getitem__(self, name):
        if isinstance(name, ConstraintRequirementBase):
            CONSTRAINT_REQUIREMENTS.validate(name)
            return name.spec
        for member in ConstraintRequirement:
            if type(name) is str and member.value == name:
                return member.spec
        raise KeyError(name)

    def __iter__(self):
        return iter(member.value for member in ConstraintRequirement)

    def __len__(self):
        return len(ConstraintRequirement)


REQUIREMENT_REGISTRY = RequirementSpecRegistry()
