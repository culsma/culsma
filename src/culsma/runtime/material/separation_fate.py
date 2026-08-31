"""Operation contracts and per-content physical fate for separations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from culsma.pipeline.program_registry import get_material_effect_kind
from culsma.runtime.material.args import arg_string, call_arg_string


_RATIO_EPSILON = 1e-9


@dataclass(frozen=True)
class SeparationOperationContract:
    program_kind: str
    effect_kind: str
    program_args: dict[str, Any]
    slot_contract: dict[str, str]
    preserved_association_slots: dict[str, str]
    released_associations: frozenset[str]
    preservation_contract: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_kind": self.program_kind,
            "effect_kind": self.effect_kind,
            "program_args": dict(self.program_args),
            "slot_contract": dict(self.slot_contract),
            "preserved_association_slots": dict(self.preserved_association_slots),
            "released_associations": sorted(self.released_associations),
            "preservation_contract": (
                dict(self.preservation_contract)
                if self.preservation_contract is not None
                else None
            ),
        }


@dataclass(frozen=True)
class ContentPhysicalState:
    association: str
    accessibility: str
    preservation_state: str
    source: str


@dataclass(frozen=True)
class ExplicitContentFate:
    component_id: str
    ratios: tuple[float, float]
    declared_slots: tuple[str, str]
    source: str = "author_explicit_fate"


@dataclass(frozen=True)
class ContentFateDecision:
    ratios: tuple[float, float]
    source: str
    association: str
    accessibility: str
    preservation_state: str
    retained_slot: str | None = None
    uncertainty_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ratios": {"0": self.ratios[0], "1": self.ratios[1]},
            "source": self.source,
            "association": self.association,
            "accessibility": self.accessibility,
            "preservation_state": self.preservation_state,
        }
        if self.retained_slot is not None:
            out["retained_slot"] = self.retained_slot
        if self.uncertainty_reason is not None:
            out["uncertainty_reason"] = self.uncertainty_reason
        return out


@dataclass(frozen=True)
class SeparationRuleIssue:
    code: str
    message: str


def resolve_separation_operation_contract(
    program: dict[str, Any],
    *,
    slot_contract: dict[str, str],
) -> SeparationOperationContract:
    program_kind = str(program.get("name")) if isinstance(program.get("name"), str) else "sep_program"
    program_args = _serialized_program_args(program)
    preserved: dict[str, str] = {}
    released: set[str] = set()
    preservation_contract: dict[str, Any] | None = None

    if program_kind == "centrifuge_program":
        preserved["pellet"] = "1"
    elif program_kind in {"filtration_program", "centrifugal_filtration_program"}:
        preserved["membrane"] = "1"
        membrane = _normalized_token(call_arg_string(program, "membrane"))
        drive = _normalized_token(call_arg_string(program, "drive"))
        if membrane == "adherent_cell_surface" and drive == "aspiration":
            preserved["container_surface"] = "1"
    elif program_kind == "magnetic_program":
        preserved["bead"] = "0"
        preservation_contract = {
            "kind": "field_retention",
            "field": "magnetic_rack",
            "retained_slot": "0",
            "default_incoming_slot": "1",
        }
    elif program_kind == "precipitation_program":
        preserved["precipitate"] = "0"
    elif program_kind == "disrupt_program":
        released.update({"cell", "container_surface"})

    return SeparationOperationContract(
        program_kind=program_kind,
        effect_kind=get_material_effect_kind(program_kind) or "separation_fate",
        program_args=program_args,
        slot_contract=dict(slot_contract),
        preserved_association_slots=preserved,
        released_associations=frozenset(released),
        preservation_contract=preservation_contract,
    )


def resolve_content_physical_state(
    state: dict[str, Any],
    source: dict[str, Any],
    component_id: str,
) -> ContentPhysicalState:
    registry = state.get("content_registry")
    record = registry.get(component_id) if isinstance(registry, dict) else None
    attrs = record.get("content_attrs") if isinstance(record, dict) else None
    attrs = attrs if isinstance(attrs, dict) else {}

    explicit_association = _normalized_association(attrs.get("association"))
    if explicit_association is not None:
        return ContentPhysicalState(
            association=explicit_association,
            accessibility="accessible" if explicit_association == "free" else "immobilized",
            preservation_state="declared",
            source="content_association",
        )

    relationship_state = _component_relationship_state(source, component_id)
    if relationship_state is not None:
        association = _association_from_material_state(relationship_state)
        if association is not None:
            return ContentPhysicalState(
                association=association,
                accessibility="accessible" if association == "free" else "immobilized",
                preservation_state="derived",
                source="material_relationship",
            )

    raw_state = attrs.get("state") or attrs.get("culture_state")
    association = _association_from_material_state(raw_state)
    if association is not None:
        return ContentPhysicalState(
            association=association,
            accessibility="accessible" if association == "free" else "immobilized",
            preservation_state="declared",
            source="content_state",
        )

    return ContentPhysicalState(
        association="unspecified",
        accessibility="unspecified",
        preservation_state="unspecified",
        source="none",
    )


def resolve_content_fate(
    *,
    contract: SeparationOperationContract,
    physical_state: ContentPhysicalState,
    default_ratios: tuple[float, float],
    explicit_fate: ExplicitContentFate | None,
) -> ContentFateDecision:
    if explicit_fate is not None:
        return ContentFateDecision(
            ratios=explicit_fate.ratios,
            source=explicit_fate.source,
            association=physical_state.association,
            accessibility=physical_state.accessibility,
            preservation_state=physical_state.preservation_state,
        )

    retained_slot = contract.preserved_association_slots.get(physical_state.association)
    if retained_slot in {"0", "1"}:
        ratios = (1.0, 0.0) if retained_slot == "0" else (0.0, 1.0)
        return ContentFateDecision(
            ratios=ratios,
            source="preserved_association",
            association=physical_state.association,
            accessibility="immobilized",
            preservation_state="satisfied",
            retained_slot=retained_slot,
        )

    if physical_state.association in contract.released_associations:
        return ContentFateDecision(
            ratios=default_ratios,
            source="released_association_reference_prediction",
            association="free",
            accessibility="accessible",
            preservation_state="released",
        )

    if physical_state.association not in {"free", "unspecified"}:
        return ContentFateDecision(
            ratios=(0.5, 0.5),
            source="conservative_unresolved_association",
            association=physical_state.association,
            accessibility=physical_state.accessibility,
            preservation_state=physical_state.preservation_state,
            uncertainty_reason="operation_effect_on_association_unspecified",
        )

    return ContentFateDecision(
        ratios=default_ratios,
        source="reference_prediction",
        association=physical_state.association,
        accessibility=physical_state.accessibility,
        preservation_state=physical_state.preservation_state,
    )


def parse_explicit_content_fates(
    raw_rules: Any,
    *,
    slot_contract: dict[str, str],
    known_components: set[str] | None = None,
) -> tuple[dict[str, ExplicitContentFate], list[SeparationRuleIssue]]:
    if raw_rules is None:
        return {}, []
    if not isinstance(raw_rules, dict):
        return {}, [
            SeparationRuleIssue(
                code="MAT_SEPARATION_FATE_RULE_SHAPE_INVALID",
                message="sep component_fates must be a record keyed by content id",
            )
        ]

    aliases = _slot_aliases(slot_contract)
    expected_slots = set(slot_contract)
    parsed: dict[str, ExplicitContentFate] = {}
    issues: list[SeparationRuleIssue] = []
    for raw_component_id, raw_fate in raw_rules.items():
        component_id = str(raw_component_id)
        if known_components is not None and component_id not in known_components:
            issues.append(
                SeparationRuleIssue(
                    code="MAT_SEPARATION_FATE_COMPONENT_NOT_FOUND",
                    message=f"component_fates references unknown source content '{component_id}'",
                )
            )
            continue
        if not isinstance(raw_fate, dict):
            issues.append(
                SeparationRuleIssue(
                    code="MAT_SEPARATION_FATE_RULE_SHAPE_INVALID",
                    message=f"component_fates entry '{component_id}' must be a record of output ratios",
                )
            )
            continue

        slot_values: dict[str, float] = {}
        declared_names: dict[str, str] = {}
        invalid = False
        for raw_slot, raw_value in raw_fate.items():
            slot_name = str(raw_slot)
            slot = aliases.get(slot_name)
            if slot is None:
                issues.append(
                    SeparationRuleIssue(
                        code="MAT_SEPARATION_FATE_RULE_SLOT_INVALID",
                        message=(
                            f"component_fates entry '{component_id}' uses unknown output '{slot_name}'; "
                            f"expected {', '.join(sorted(aliases))}"
                        ),
                    )
                )
                invalid = True
                continue
            value = _runtime_ratio_value(raw_value)
            if value is None or value < 0.0 or value > 1.0:
                issues.append(
                    SeparationRuleIssue(
                        code="MAT_SEPARATION_FATE_RULE_VALUE_INVALID",
                        message=f"component_fates ratio for '{component_id}.{slot_name}' must be between 0 and 1",
                    )
                )
                invalid = True
                continue
            if slot in slot_values:
                issues.append(
                    SeparationRuleIssue(
                        code="MAT_SEPARATION_FATE_RULE_SLOT_INVALID",
                        message=f"component_fates entry '{component_id}' declares output slot {slot} more than once",
                    )
                )
                invalid = True
                continue
            slot_values[slot] = value
            declared_names[slot] = slot_name

        missing = expected_slots - set(slot_values)
        if missing:
            issues.append(
                SeparationRuleIssue(
                    code="MAT_SEPARATION_FATE_RULE_SHAPE_INVALID",
                    message=f"component_fates entry '{component_id}' must declare both separation outputs",
                )
            )
            invalid = True
        if not invalid and abs(sum(slot_values.values()) - 1.0) > _RATIO_EPSILON:
            issues.append(
                SeparationRuleIssue(
                    code="MAT_SEPARATION_FATE_RULE_TOTAL_INVALID",
                    message=f"component_fates ratios for '{component_id}' must sum to 1",
                )
            )
            invalid = True
        if invalid:
            continue
        parsed[component_id] = ExplicitContentFate(
            component_id=component_id,
            ratios=(slot_values["0"], slot_values["1"]),
            declared_slots=(declared_names["0"], declared_names["1"]),
        )
    return parsed, issues


def _slot_aliases(slot_contract: dict[str, str]) -> dict[str, str]:
    aliases = {str(slot): str(slot) for slot in slot_contract}
    aliases.update({str(name): str(slot) for slot, name in slot_contract.items()})
    return aliases


def _runtime_ratio_value(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, dict) or value.get("kind") != "IRQuantity":
        return None
    raw = value.get("value")
    if not isinstance(raw, (int, float)):
        return None
    unit = value.get("unit")
    if unit is None:
        return float(raw)
    if unit in {"%", "pct"}:
        return float(raw) / 100.0
    return None


def _serialized_program_args(program: dict[str, Any]) -> dict[str, Any]:
    args = program.get("args")
    if not isinstance(args, list):
        return {}
    serialized: dict[str, Any] = {}
    for item in args:
        if not isinstance(item, dict) or item.get("kind") != "IRArg":
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        value = item.get("value")
        text = arg_string(value)
        serialized[name] = text if text is not None else value
    return serialized


def _component_relationship_state(source: dict[str, Any], component_id: str) -> str | None:
    relationships = source.get("material_relationships")
    if not isinstance(relationships, list):
        return None
    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue
        component_ids = relationship.get("dispersed_component_ids")
        if isinstance(component_ids, list) and component_id in component_ids:
            material_state = relationship.get("material_state")
            if isinstance(material_state, str):
                return material_state
    return None


def _association_from_material_state(value: Any) -> str | None:
    token = _normalized_token(value)
    if token in {"suspended", "suspension", "mixed", "free", "released"}:
        return "free"
    if token in {
        "adherent",
        "adherent_monolayer",
        "container_surface",
        "surface_bound",
        "surface_associated",
        "immobilized",
    }:
        return "container_surface"
    if token in {"pellet", "pelleted", "washed_pellet"}:
        return "pellet"
    if token in {"precipitate", "precipitated"}:
        return "precipitate"
    if token in {"bead_bound", "bead_associated", "magnetically_retained"}:
        return "bead"
    if token in {"membrane_bound", "membrane_associated"}:
        return "membrane"
    if token in {"cell_bound", "cell_associated"}:
        return "cell"
    if token == "field_retained":
        return "field_retained"
    if token == "disrupted":
        return "disrupted"
    return None


def _normalized_association(value: Any) -> str | None:
    token = _normalized_token(value)
    if token is None:
        return None
    aliases = {
        "free": "free",
        "container_surface": "container_surface",
        "surface": "container_surface",
        "surface_bound": "container_surface",
        "pellet": "pellet",
        "precipitate": "precipitate",
        "bead": "bead",
        "bead_bound": "bead",
        "membrane": "membrane",
        "membrane_bound": "membrane",
        "cell": "cell",
        "cell_associated": "cell",
    }
    return aliases.get(token, token)


def _normalized_token(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().lower()
