"""Typed material snapshots and scientific decision proposals."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from ..contracts import ProviderProvenance, freeze_mapping


MATERIAL_SEPARATION_FATE = "material.separation_fate"
MATERIAL_STATE_TRANSITION = "material.state_transition"
MATERIAL_CONTRACT_VERSION = "1.0"


class MaterialRelation(StrEnum):
    FREE = "free"
    CONTAINER_SURFACE = "container_surface"
    PELLET = "pellet"
    PRECIPITATE = "precipitate"
    DISRUPTED = "disrupted"
    BEAD_BOUND = "bead_bound"
    MEMBRANE_BOUND = "membrane_bound"
    CELL_BOUND = "cell_bound"
    FIELD_RETAINED = "field_retained"
    UNRESOLVED = "unresolved"


def empty_material_mapping() -> Mapping[str, object]:
    return MappingProxyType({})


@dataclass(frozen=True)
class OutputRoleSnapshot:
    part_id: str
    semantic_role: str


@dataclass(frozen=True)
class OperationSnapshot:
    program_kind: str
    effect_kind: str
    output_roles: tuple[OutputRoleSnapshot, ...]
    program_args: Mapping[str, object] = field(default_factory=empty_material_mapping)

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_roles", tuple(self.output_roles))
        object.__setattr__(self, "program_args", freeze_mapping(self.program_args))


@dataclass(frozen=True)
class QuantitySnapshot:
    value: float
    unit: str


@dataclass(frozen=True)
class RelationshipSnapshot:
    relation: str
    associated_with: str | None = None
    preservation: str | None = None
    label: str | None = None


@dataclass(frozen=True)
class ComponentSnapshot:
    entry_id: str
    content_ref: str
    canonical_kind: str
    canonical_type: str
    quantity: QuantitySnapshot
    relationship: RelationshipSnapshot


@dataclass(frozen=True)
class MaterialModelPayload:
    operation: OperationSnapshot
    components: tuple[ComponentSnapshot, ...]
    context: Mapping[str, object] = field(default_factory=empty_material_mapping)

    def __post_init__(self) -> None:
        object.__setattr__(self, "components", tuple(self.components))
        object.__setattr__(self, "context", freeze_mapping(self.context))


@dataclass(frozen=True)
class ComponentFate:
    component_entry_id: str
    fractions: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fractions", MappingProxyType(dict(self.fractions)))


@dataclass(frozen=True)
class SeparationDecision:
    component_fates: tuple[ComponentFate, ...]
    decision_source: str
    provenance: ProviderProvenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_fates", tuple(self.component_fates))


@dataclass(frozen=True)
class RelationshipTransition:
    component_entry_id: str
    next_relation: str
    next_label: str | None = None
    retire_quantity: bool = False
    replacement_quantity: QuantitySnapshot | None = None


@dataclass(frozen=True)
class StateTransitionDecision:
    transitions: tuple[RelationshipTransition, ...]
    decision_source: str
    provenance: ProviderProvenance | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "transitions", tuple(self.transitions))


MaterialDecision = SeparationDecision | StateTransitionDecision
