"""Tables 2–3 for the built-in material Rulebook provider."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .classification import CalculationGroup
from .contracts import MaterialRelation


class RulebookOutcome(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    KEEP_SEPARATE = "KEEP_SEPARATE"
    REJECT = "REJECT"


@dataclass(frozen=True)
class SeparationFateMatch:
    rule_id: str
    ordered_fractions: tuple[float, float]


@dataclass(frozen=True)
class RelationshipTransitionMatch:
    rule_id: str
    next_relation: MaterialRelation
    next_label: str | None
    retire_quantity: bool = False
    outcome: RulebookOutcome = RulebookOutcome.RESOLVED


_CENTRIFUGE_OPERATIONS = frozenset({"centrifuge", "centrifuge_program"})
_FILTRATION_OPERATIONS = frozenset(
    {
        "filtration",
        "filtration_program",
        "centrifugal_filtration",
        "centrifugal_filtration_program",
    }
)
_PRECIPITATION_OPERATIONS = frozenset({"precipitation", "precipitation_program"})
_MAGNETIC_OPERATIONS = frozenset({"magnetic", "magnetic_program"})


def resolve_separation_fate_rule(
    *,
    program_kind: str,
    group: CalculationGroup,
    current_relation: str,
    filter_retains: bool = False,
    is_magnetic_support: bool = False,
    surface_preserved: bool = False,
) -> SeparationFateMatch | None:
    """Resolve the first matching Table 2 row; `None` is UNRESOLVED."""

    if program_kind in _CENTRIFUGE_OPERATIONS:
        if current_relation == MaterialRelation.PELLET:
            return SeparationFateMatch("F_CEN_PRESERVE", (0.0, 1.0))
        if current_relation != MaterialRelation.FREE:
            return None
        if group is CalculationGroup.MOBILE_PHASE:
            return SeparationFateMatch("F_CEN_MOBILE", (1.0, 0.0))
        if group is CalculationGroup.SEDIMENTABLE_MATERIAL:
            return SeparationFateMatch("F_CEN_SEDIMENT", (0.0, 1.0))
        if group is CalculationGroup.CAPTURE_SUPPORT:
            return SeparationFateMatch("F_CEN_SUPPORT", (0.0, 1.0))
        if group is CalculationGroup.CONTEXT_DEPENDENT_TARGET:
            return SeparationFateMatch("F_CEN_TARGET", (1.0, 0.0))
        return None

    if program_kind in _FILTRATION_OPERATIONS:
        if (
            current_relation == MaterialRelation.CONTAINER_SURFACE
            and surface_preserved
        ):
            return SeparationFateMatch("F_FIL_SURFACE_PRESERVE", (0.0, 1.0))
        if current_relation == MaterialRelation.MEMBRANE_BOUND:
            return SeparationFateMatch("F_FIL_PRESERVE", (0.0, 1.0))
        if current_relation != MaterialRelation.FREE:
            return None
        if group is CalculationGroup.MOBILE_PHASE:
            return SeparationFateMatch("F_FIL_MOBILE", (1.0, 0.0))
        if filter_retains and group in {
            CalculationGroup.SEDIMENTABLE_MATERIAL,
            CalculationGroup.CAPTURE_SUPPORT,
            CalculationGroup.CONTEXT_DEPENDENT_TARGET,
        }:
            return SeparationFateMatch("F_FIL_RETAIN", (0.0, 1.0))
        return None

    if program_kind in _PRECIPITATION_OPERATIONS:
        if current_relation == MaterialRelation.PRECIPITATE:
            return SeparationFateMatch("F_PRE_PRESERVE", (1.0, 0.0))
        if current_relation == MaterialRelation.FREE and group is CalculationGroup.MOBILE_PHASE:
            return SeparationFateMatch("F_PRE_MOBILE", (0.0, 1.0))
        return None

    if program_kind in _MAGNETIC_OPERATIONS:
        if current_relation in {
            MaterialRelation.BEAD_BOUND,
            MaterialRelation.FIELD_RETAINED,
        }:
            return SeparationFateMatch("F_MAG_PRESERVE", (1.0, 0.0))
        if current_relation != MaterialRelation.FREE:
            return None
        if group in {
            CalculationGroup.MOBILE_PHASE,
            CalculationGroup.SEDIMENTABLE_MATERIAL,
        }:
            return SeparationFateMatch("F_MAG_MOBILE", (0.0, 1.0))
        if group is CalculationGroup.CAPTURE_SUPPORT and is_magnetic_support:
            return SeparationFateMatch("F_MAG_SUPPORT", (1.0, 0.0))
    return None


def resolve_relationship_transition_rule(
    *,
    group: CalculationGroup,
    current_relation: str,
    effect_kind: str,
    output_role: str,
    declared: bool = False,
    cross_container: bool = False,
    release_declared: bool = False,
    disruption_target: bool = False,
    target_remains_identifiable: bool = False,
    precipitation_established: bool = False,
    binding_established: bool = False,
    field_retention_established: bool = False,
    binding_preserved: bool = False,
    membrane_preserved: bool = False,
    cell_integrity_preserved: bool = False,
    field_preserved: bool = False,
    surface_preserved: bool = False,
    label_has_persistent_relation: bool = True,
    quantity_is_intact_cell_count: bool = False,
) -> RelationshipTransitionMatch | None:
    """Resolve the first matching Table 3 row for one affected output entry."""

    if (
        current_relation == MaterialRelation.PELLET
        and effect_kind == "resuspend"
        and output_role == "destination"
        and declared
    ):
        return RelationshipTransitionMatch("T_RESUSPEND", MaterialRelation.FREE, None)
    if (
        current_relation == MaterialRelation.PRECIPITATE
        and effect_kind == "dissolve"
        and output_role == "destination"
        and declared
    ):
        return RelationshipTransitionMatch("T_DISSOLVE", MaterialRelation.FREE, None)
    if (
        current_relation == MaterialRelation.BEAD_BOUND
        and effect_kind == "elute"
        and output_role == "destination"
        and declared
    ):
        return RelationshipTransitionMatch("T_ELUTE", MaterialRelation.FREE, None)

    if effect_kind == "disrupt" and output_role == "result_material":
        if (
            current_relation
            in {
                MaterialRelation.FREE,
                MaterialRelation.CONTAINER_SURFACE,
                MaterialRelation.CELL_BOUND,
            }
            and group is CalculationGroup.SEDIMENTABLE_MATERIAL
            and disruption_target
        ):
            return RelationshipTransitionMatch(
                "T_DISRUPT_TARGET",
                MaterialRelation.DISRUPTED,
                "lysate_material",
                retire_quantity=quantity_is_intact_cell_count,
            )
        if (
            current_relation == MaterialRelation.FREE
            and group is CalculationGroup.MOBILE_PHASE
            and declared
        ):
            return RelationshipTransitionMatch(
                "T_DISRUPT_MOBILE",
                MaterialRelation.FREE,
                "lysate_material",
            )
        if (
            current_relation == MaterialRelation.FREE
            and group is CalculationGroup.CONTEXT_DEPENDENT_TARGET
            and target_remains_identifiable
        ):
            return RelationshipTransitionMatch(
                "T_DISRUPT_FREE_TARGET",
                MaterialRelation.FREE,
                "lysate_material",
            )
        return None

    if (
        current_relation == MaterialRelation.CONTAINER_SURFACE
        and effect_kind == "separate"
        and output_role == "retentate"
        and surface_preserved
    ):
        return RelationshipTransitionMatch(
            "T_PRESERVE_CONTAINER_SURFACE",
            MaterialRelation.CONTAINER_SURFACE,
            "retentate_output",
        )
    if (
        current_relation == MaterialRelation.CONTAINER_SURFACE
        and effect_kind == "add_only"
        and output_role == "same_container"
        and not cross_container
    ):
        return RelationshipTransitionMatch(
            "T_SURFACE_STAY", MaterialRelation.CONTAINER_SURFACE, None
        )
    if (
        current_relation == MaterialRelation.CONTAINER_SURFACE
        and effect_kind == "release_move"
        and output_role == "destination"
        and group is CalculationGroup.SEDIMENTABLE_MATERIAL
        and cross_container
        and release_declared
    ):
        return RelationshipTransitionMatch("T_SURFACE_RELEASE", MaterialRelation.FREE, None)

    if (
        effect_kind == "separate"
        and current_relation == MaterialRelation.FREE
        and output_role == "pellet"
        and group
        in {
            CalculationGroup.SEDIMENTABLE_MATERIAL,
            CalculationGroup.CAPTURE_SUPPORT,
        }
    ):
        return RelationshipTransitionMatch(
            rule_id="T_CREATE_PELLET",
            next_relation=MaterialRelation.PELLET,
            next_label="pellet_output",
        )
    if (
        effect_kind == "separate"
        and current_relation == MaterialRelation.FREE
        and output_role == "precipitate"
        and group
        in {
            CalculationGroup.SEDIMENTABLE_MATERIAL,
            CalculationGroup.CONTEXT_DEPENDENT_TARGET,
        }
        and precipitation_established
    ):
        return RelationshipTransitionMatch(
            "T_CREATE_PRECIPITATE",
            MaterialRelation.PRECIPITATE,
            "precipitate_output",
        )
    if (
        effect_kind == "separate"
        and current_relation == MaterialRelation.FREE
        and output_role == "bound"
        and group is CalculationGroup.CONTEXT_DEPENDENT_TARGET
        and binding_established
    ):
        return RelationshipTransitionMatch(
            "T_CREATE_BEAD_BINDING", MaterialRelation.BEAD_BOUND, "bound_output"
        )
    if (
        effect_kind == "separate"
        and current_relation == MaterialRelation.FREE
        and output_role == "bound"
        and group is CalculationGroup.CAPTURE_SUPPORT
        and field_retention_established
    ):
        return RelationshipTransitionMatch(
            "T_CREATE_FIELD_RETENTION", MaterialRelation.FIELD_RETAINED, "bound_output"
        )
    if effect_kind == "separate" and current_relation == MaterialRelation.FREE:
        return RelationshipTransitionMatch(
            rule_id="T_FREE_OUTPUT",
            next_relation=MaterialRelation.FREE,
            next_label=output_label(output_role),
        )
    if (
        current_relation == MaterialRelation.PELLET
        and effect_kind in {"move", "separate"}
        and not release_declared
    ):
        return RelationshipTransitionMatch(
            rule_id="T_PRESERVE_PELLET",
            next_relation=MaterialRelation.PELLET,
            next_label=output_label(output_role),
        )
    if (
        current_relation == MaterialRelation.PRECIPITATE
        and effect_kind in {"move", "separate"}
        and not release_declared
    ):
        return RelationshipTransitionMatch(
            "T_PRESERVE_PRECIPITATE",
            MaterialRelation.PRECIPITATE,
            output_label(output_role),
        )
    if (
        current_relation == MaterialRelation.BEAD_BOUND
        and effect_kind in {"move", "separate"}
        and binding_preserved
    ):
        return RelationshipTransitionMatch(
            "T_PRESERVE_BEAD_BOUND",
            MaterialRelation.BEAD_BOUND,
            output_label(output_role),
        )
    if (
        current_relation == MaterialRelation.MEMBRANE_BOUND
        and effect_kind in {"move", "separate"}
        and membrane_preserved
    ):
        return RelationshipTransitionMatch(
            "T_PRESERVE_MEMBRANE_BOUND",
            MaterialRelation.MEMBRANE_BOUND,
            output_label(output_role),
        )
    if (
        current_relation == MaterialRelation.CELL_BOUND
        and effect_kind in {"move", "separate"}
        and cell_integrity_preserved
    ):
        return RelationshipTransitionMatch(
            "T_PRESERVE_CELL_BOUND",
            MaterialRelation.CELL_BOUND,
            output_label(output_role),
        )
    if (
        current_relation == MaterialRelation.FIELD_RETAINED
        and effect_kind in {"move", "separate"}
        and output_role == "bound"
        and field_preserved
    ):
        return RelationshipTransitionMatch(
            "T_PRESERVE_FIELD", MaterialRelation.FIELD_RETAINED, "bound_output"
        )
    if (
        current_relation == MaterialRelation.FIELD_RETAINED
        and effect_kind == "move"
        and output_role == "destination"
        and not field_preserved
    ):
        return RelationshipTransitionMatch("T_FIELD_RELEASE", MaterialRelation.FREE, None)
    if effect_kind in {"mix", "cross_container_move", "new_separation"} and not (
        label_has_persistent_relation
    ):
        try:
            unchanged_relation = MaterialRelation(current_relation)
        except ValueError:
            return None
        if unchanged_relation is MaterialRelation.UNRESOLVED:
            return None
        return RelationshipTransitionMatch("T_EXPIRE_LABEL", unchanged_relation, None)
    return None


def output_label(output_role: str) -> str:
    return output_role if output_role.endswith("_output") else f"{output_role}_output"
