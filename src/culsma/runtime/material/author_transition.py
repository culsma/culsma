"""Author-supplied material relationship transitions.

This module is the operation-neutral core for PM #99.  It resolves the
frontend ``tube.materials[index]`` selector against the authoritative ordered
component-entry list, derives the source relationship from that entry, and
builds an immutable author decision for the one currently supported transition:
``CONTAINER_SURFACE -> FREE``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from culsma.runtime.material.component_entries import (
    ComponentEntryRelationError,
    component_entry_has_quantity,
    entry_association_target,
    normalize_entry_relation,
)
from culsma.scientific_model.material import (
    AssociationTarget,
    AssociationTargetKind,
    MaterialRelation,
    RelationshipTransition,
    StateTransitionDecision,
)


ALLOWED_AUTHOR_TRANSITIONS = frozenset(
    {(MaterialRelation.CONTAINER_SURFACE, MaterialRelation.FREE)}
)


@dataclass(frozen=True)
class AuthorTransitionIssue:
    code: str
    message: str


@dataclass(frozen=True)
class MaterialEntryIndexSelector:
    """Compiled form of ``container.materials[index]``."""

    container_ref: str
    index: int

    def __post_init__(self) -> None:
        _require_non_empty("container_ref", self.container_ref)
        if (
            isinstance(self.index, bool)
            or not isinstance(self.index, int)
            or self.index < 0
        ):
            raise ValueError("index must be a non-negative integer")


@dataclass(frozen=True)
class MaterialEntryRef:
    """Read-only reference to one authoritative component entry."""

    entry_id: str
    content_ref: str
    amount: float
    quantity: Mapping[str, Any] | None
    relation: MaterialRelation
    association_target: AssociationTarget | None
    preservation: str | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty("entry_id", self.entry_id)
        _require_non_empty("content_ref", self.content_ref)
        if self.quantity is not None:
            object.__setattr__(
                self,
                "quantity",
                MappingProxyType(deepcopy(dict(self.quantity))),
            )

    @property
    def associated_with(self) -> str | None:
        return (
            self.association_target.id
            if self.association_target is not None
            else None
        )

    @property
    def association_target_kind(self) -> AssociationTargetKind | None:
        return self.association_target.kind if self.association_target is not None else None


@dataclass(frozen=True)
class MaterialEntryResolution:
    entry: MaterialEntryRef | None = None
    index: int | None = None
    live_entry_count: int = 0
    issues: tuple[AuthorTransitionIssue, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.entry is not None and not self.issues


@dataclass(frozen=True)
class AuthorTransitionPairValidation:
    issues: tuple[AuthorTransitionIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class ExplicitMaterialTransition:
    subject: MaterialEntryIndexSelector
    output_key: str
    next_relation: MaterialRelation

    def __post_init__(self) -> None:
        if not isinstance(self.subject, MaterialEntryIndexSelector):
            raise TypeError("subject must be a MaterialEntryIndexSelector")
        _require_non_empty("output_key", self.output_key)
        if not isinstance(self.next_relation, MaterialRelation):
            raise TypeError("next_relation must be a MaterialRelation")


@dataclass(frozen=True)
class ResolvedExplicitMaterialTransition:
    source_entry_id: str
    output_key: str
    current_relation: MaterialRelation
    current_association_target: AssociationTarget | None
    next_relation: MaterialRelation


@dataclass(frozen=True)
class ComponentRelationshipProjection:
    relation: MaterialRelation
    associated_with: str | None
    association_target_kind: AssociationTargetKind | None
    preservation: str | None
    label: str | None


@dataclass(frozen=True)
class ExplicitMaterialTransitionResult:
    source_entry: MaterialEntryRef | None = None
    transition: ResolvedExplicitMaterialTransition | None = None
    projection: ComponentRelationshipProjection | None = None
    decision: StateTransitionDecision | None = None
    issues: tuple[AuthorTransitionIssue, ...] = ()

    @property
    def applied(self) -> bool:
        return (
            self.source_entry is not None
            and self.transition is not None
            and self.projection is not None
            and self.decision is not None
            and not self.issues
        )


@dataclass(frozen=True)
class ExplicitMaterialTransitionParseResult:
    transitions: tuple[ExplicitMaterialTransition, ...] = ()
    issues: tuple[AuthorTransitionIssue, ...] = ()


@dataclass(frozen=True)
class OutputFractionValidation:
    issues: tuple[AuthorTransitionIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class AuthorTransitionResolution:
    transitions_by_output: Mapping[
        tuple[str, str], ResolvedExplicitMaterialTransition
    ] = field(default_factory=lambda: MappingProxyType({}))
    issues: tuple[AuthorTransitionIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transitions_by_output",
            MappingProxyType(dict(self.transitions_by_output)),
        )


def parse_explicit_material_transitions(
    raw_rules: Any,
    *,
    output_contract: Mapping[str, str],
    declared_source_ref: str | None = None,
    source_id: str | None = None,
) -> ExplicitMaterialTransitionParseResult:
    """Parse serialized Plan IR into typed, enum-backed transition values."""

    if raw_rules is None:
        return ExplicitMaterialTransitionParseResult()
    if not isinstance(raw_rules, dict) or raw_rules.get("kind") != "IRList":
        return _parse_failure(
            "MAT_MATERIAL_TRANSITIONS_SHAPE_INVALID",
            "sep transitions must be a list",
        )
    elements = raw_rules.get("elements")
    if not isinstance(elements, list):
        return _parse_failure(
            "MAT_MATERIAL_TRANSITIONS_SHAPE_INVALID",
            "sep transitions must contain serialized transition calls",
        )

    output_aliases = {slot: slot for slot in output_contract}
    output_aliases.update({name: slot for slot, name in output_contract.items()})
    parsed: list[ExplicitMaterialTransition] = []
    for raw_rule in elements:
        args = _serialized_call_args(raw_rule, "transition")
        if args is None or set(args) != {"subject", "output", "to"}:
            return _parse_failure(
                "MAT_MATERIAL_TRANSITION_SHAPE_INVALID",
                "each transitions item must be transition(subject = ..., output = ..., to = ...)",
            )
        selector = _parse_material_selector(args["subject"])
        if selector is None:
            return _parse_failure(
                "MAT_MATERIAL_SELECTOR_INVALID",
                "transition subject must be sample.materials[index]",
            )
        if (
            declared_source_ref is not None
            and selector.container_ref != declared_source_ref
        ):
            return _parse_failure(
                "MAT_MATERIAL_SELECTOR_CONTAINER_MISMATCH",
                "transition subject container must be the same binding as sep sample",
            )
        if source_id is not None:
            selector = MaterialEntryIndexSelector(
                container_ref=source_id,
                index=selector.index,
            )
        raw_output = _serialized_identifier(args["output"])
        output_key = output_aliases.get(raw_output or "")
        if output_key is None:
            return _parse_failure(
                "MAT_MATERIAL_TRANSITION_OUTPUT_INVALID",
                f"transition output '{raw_output or '<invalid>'}' is not declared by the separation program",
            )
        raw_relation = _serialized_identifier(args["to"])
        try:
            next_relation = MaterialRelation(raw_relation)
        except (TypeError, ValueError):
            return _parse_failure(
                "MAT_MATERIAL_TRANSITION_TARGET_INVALID",
                "transition to must be a MaterialRelation enum identifier",
            )
        parsed.append(
            ExplicitMaterialTransition(
                subject=selector,
                output_key=output_key,
                next_relation=next_relation,
            )
        )
    return ExplicitMaterialTransitionParseResult(transitions=tuple(parsed))


def validate_positive_output_fraction(
    *,
    source_entry_id: str,
    output_key: str,
    output_bindings: Sequence[Any],
    fractions_by_component: Mapping[str, tuple[float, float]],
) -> OutputFractionValidation:
    output_index = next(
        (
            index
            for index, output in enumerate(output_bindings)
            if getattr(output, "part_id", None) == output_key
        ),
        None,
    )
    fractions = fractions_by_component.get(source_entry_id)
    if output_index is None or fractions is None or output_index >= len(fractions):
        return OutputFractionValidation(
            issues=(
                AuthorTransitionIssue(
                    code="MAT_MATERIAL_TRANSITION_OUTPUT_UNRESOLVED",
                    message=(
                        f"Cannot resolve output '{output_key}' for material entry "
                        f"'{source_entry_id}'"
                    ),
                ),
            )
        )
    if float(fractions[output_index]) <= 1e-12:
        return OutputFractionValidation(
            issues=(
                AuthorTransitionIssue(
                    code="MAT_MATERIAL_TRANSITION_OUTPUT_EMPTY",
                    message=(
                        f"Material entry '{source_entry_id}' has no positive quantity "
                        f"in output '{output_key}'"
                    ),
                ),
            )
        )
    return OutputFractionValidation()


def resolve_explicit_material_transitions(
    *,
    transitions: Sequence[ExplicitMaterialTransition],
    source_id: str,
    source_entries: Sequence[dict[str, Any]],
    output_bindings: Sequence[Any],
    fractions_by_component: Mapping[str, tuple[float, float]],
) -> AuthorTransitionResolution:
    """Resolve and index author rules by source entry and concrete output slot."""

    index: dict[tuple[str, str], ResolvedExplicitMaterialTransition] = {}
    for transition in transitions:
        result = apply_explicit_material_transition(
            transition=transition,
            source_id=source_id,
            source_entries=source_entries,
        )
        if not result.applied or result.transition is None:
            return AuthorTransitionResolution(issues=result.issues)
        fraction_validation = validate_positive_output_fraction(
            source_entry_id=result.transition.source_entry_id,
            output_key=result.transition.output_key,
            output_bindings=output_bindings,
            fractions_by_component=fractions_by_component,
        )
        if not fraction_validation.is_valid:
            return AuthorTransitionResolution(issues=fraction_validation.issues)
        key = (result.transition.source_entry_id, result.transition.output_key)
        if key in index:
            return AuthorTransitionResolution(
                issues=(
                    AuthorTransitionIssue(
                        code="MAT_MATERIAL_TRANSITION_DUPLICATE",
                        message=(
                            f"Material entry '{key[0]}' output '{key[1]}' has more "
                            "than one author transition"
                        ),
                    ),
                )
            )
        index[key] = result.transition
    return AuthorTransitionResolution(transitions_by_output=index)


def resolve_material_entry(
    *,
    selector: MaterialEntryIndexSelector,
    source_id: str,
    entries: Sequence[dict[str, Any]],
) -> MaterialEntryResolution:
    """Resolve one live entry by its position in the ordered materials list."""

    if selector.container_ref != source_id:
        return MaterialEntryResolution(
            issues=(
                AuthorTransitionIssue(
                    code="MAT_MATERIAL_SELECTOR_CONTAINER_MISMATCH",
                    message=(
                        f"Material selector references container "
                        f"'{selector.container_ref}', expected '{source_id}'"
                    ),
                ),
            )
        )

    live_entries = [
        entry
        for entry in entries
        if isinstance(entry, dict)
        and component_entry_has_quantity(entry)
    ]
    if selector.index >= len(live_entries):
        return MaterialEntryResolution(
            index=selector.index,
            live_entry_count=len(live_entries),
            issues=(
                AuthorTransitionIssue(
                    code="MAT_MATERIAL_INDEX_OUT_OF_RANGE",
                    message=(
                        f"Container '{source_id}' has {len(live_entries)} live material "
                        f"entries; index {selector.index} is out of range"
                    ),
                ),
            ),
        )

    entry = live_entries[selector.index]
    entry_id = entry.get("entry_id")
    content_ref = entry.get("content_ref")
    if (
        not isinstance(entry_id, str)
        or not entry_id
        or not isinstance(content_ref, str)
        or not content_ref
    ):
        return MaterialEntryResolution(
            index=selector.index,
            live_entry_count=len(live_entries),
            issues=(
                AuthorTransitionIssue(
                    code="MAT_MATERIAL_ENTRY_INVALID",
                    message="Resolved material entry has no stable entry_id or content_ref",
                ),
            ),
        )

    try:
        relation = MaterialRelation(normalize_entry_relation(entry.get("relation")))
    except (ComponentEntryRelationError, ValueError) as exc:
        return MaterialEntryResolution(
            index=selector.index,
            live_entry_count=len(live_entries),
            issues=(
                AuthorTransitionIssue(
                    code="MAT_MATERIAL_RELATION_INVALID",
                    message=str(exc),
                ),
            ),
        )

    quantity = entry.get("quantity")
    resolved = MaterialEntryRef(
        entry_id=entry_id,
        content_ref=content_ref,
        amount=float(entry.get("amount", 0.0)),
        quantity=quantity if isinstance(quantity, Mapping) else None,
        relation=relation,
        association_target=entry_association_target(entry),
        preservation=(
            str(entry["preservation"])
            if isinstance(entry.get("preservation"), str)
            else None
        ),
        label=str(entry["label"]) if isinstance(entry.get("label"), str) else None,
    )
    return MaterialEntryResolution(
        entry=resolved,
        index=selector.index,
        live_entry_count=len(live_entries),
    )


def validate_author_transition_pair(
    *,
    current_relation: MaterialRelation,
    current_target: AssociationTarget | None,
    source_id: str,
    next_relation: MaterialRelation,
) -> AuthorTransitionPairValidation:
    """Validate the closed #99 relationship transition and its source target."""

    if not isinstance(current_relation, MaterialRelation) or not isinstance(
        next_relation, MaterialRelation
    ):
        return AuthorTransitionPairValidation(
            issues=(
                AuthorTransitionIssue(
                    code="MAT_AUTHOR_TRANSITION_RELATION_INVALID",
                    message="Author transition relations must be MaterialRelation values",
                ),
            )
        )

    if (current_relation, next_relation) not in ALLOWED_AUTHOR_TRANSITIONS:
        return AuthorTransitionPairValidation(
            issues=(
                AuthorTransitionIssue(
                    code="MAT_AUTHOR_TRANSITION_NOT_ALLOWED",
                    message=(
                        f"Author transition '{current_relation.value}' to "
                        f"'{next_relation.value}' is not allowed"
                    ),
                ),
            )
        )

    expected_target = AssociationTarget(AssociationTargetKind.CONTAINER, source_id)
    if current_target != expected_target:
        return AuthorTransitionPairValidation(
            issues=(
                AuthorTransitionIssue(
                    code="MAT_AUTHOR_TRANSITION_SOURCE_TARGET_MISMATCH",
                    message=(
                        "CONTAINER_SURFACE source state must be associated with "
                        f"container '{source_id}'"
                    ),
                ),
            )
        )
    return AuthorTransitionPairValidation()


def project_component_relationship(
    *,
    source_entry: MaterialEntryRef,
    next_relation: MaterialRelation,
) -> ComponentRelationshipProjection:
    """Project the validated relationship without mutating the source entry."""

    if next_relation is not MaterialRelation.FREE:
        raise ValueError("PM #99 only projects MaterialRelation.FREE")
    return ComponentRelationshipProjection(
        relation=MaterialRelation.FREE,
        associated_with=None,
        association_target_kind=None,
        preservation=None,
        label=None,
    )


def build_author_state_transition_decision(
    *,
    projected_entry_id: str,
    transition: ResolvedExplicitMaterialTransition,
) -> StateTransitionDecision:
    """Build the typed scientific-model decision accepted by the coordinator."""

    _require_non_empty("projected_entry_id", projected_entry_id)
    return StateTransitionDecision(
        transitions=(
            RelationshipTransition(
                component_entry_id=projected_entry_id,
                next_relation=transition.next_relation.value,
                next_association_target=None,
                next_label=None,
            ),
        ),
        decision_source="author",
    )


def apply_explicit_material_transition(
    *,
    transition: ExplicitMaterialTransition,
    source_id: str,
    source_entries: Sequence[dict[str, Any]],
) -> ExplicitMaterialTransitionResult:
    """Resolve, validate, and project one #99 author transition."""

    resolution = resolve_material_entry(
        selector=transition.subject,
        source_id=source_id,
        entries=source_entries,
    )
    if not resolution.resolved or resolution.entry is None:
        return ExplicitMaterialTransitionResult(issues=resolution.issues)

    source_entry = resolution.entry
    validation = validate_author_transition_pair(
        current_relation=source_entry.relation,
        current_target=source_entry.association_target,
        source_id=source_id,
        next_relation=transition.next_relation,
    )
    if not validation.is_valid:
        return ExplicitMaterialTransitionResult(
            source_entry=source_entry,
            issues=validation.issues,
        )

    resolved_transition = ResolvedExplicitMaterialTransition(
        source_entry_id=source_entry.entry_id,
        output_key=transition.output_key,
        current_relation=source_entry.relation,
        current_association_target=source_entry.association_target,
        next_relation=transition.next_relation,
    )
    projection = project_component_relationship(
        source_entry=source_entry,
        next_relation=transition.next_relation,
    )
    decision = build_author_state_transition_decision(
        projected_entry_id=f"{source_entry.entry_id}@{transition.output_key}",
        transition=resolved_transition,
    )
    return ExplicitMaterialTransitionResult(
        source_entry=source_entry,
        transition=resolved_transition,
        projection=projection,
        decision=decision,
    )


def _require_non_empty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _parse_failure(code: str, message: str) -> ExplicitMaterialTransitionParseResult:
    return ExplicitMaterialTransitionParseResult(
        issues=(AuthorTransitionIssue(code=code, message=message),)
    )


def _serialized_call_args(value: Any, name: str) -> dict[str, Any] | None:
    if (
        not isinstance(value, dict)
        or value.get("kind") != "IRCall"
        or value.get("name") != name
    ):
        return None
    raw_args = value.get("args")
    if not isinstance(raw_args, list):
        return None
    args: dict[str, Any] = {}
    for raw_arg in raw_args:
        if not isinstance(raw_arg, dict) or raw_arg.get("kind") != "IRArg":
            return None
        arg_name = raw_arg.get("name")
        if not isinstance(arg_name, str) or arg_name in args:
            return None
        args[arg_name] = raw_arg.get("value")
    return args


def _parse_material_selector(value: Any) -> MaterialEntryIndexSelector | None:
    if not isinstance(value, dict) or value.get("kind") != "IRIndex":
        return None
    receiver = value.get("base")
    if (
        not isinstance(receiver, dict)
        or receiver.get("kind") != "IRMember"
        or receiver.get("member") != "materials"
    ):
        return None
    container_ref = _serialized_identifier(receiver.get("base"))
    index = _serialized_nonnegative_index(value.get("index"))
    if container_ref is None or index is None:
        return None
    return MaterialEntryIndexSelector(
        container_ref=container_ref,
        index=index,
    )


def _serialized_identifier(value: Any) -> str | None:
    if not isinstance(value, dict) or value.get("kind") != "IRIdentifier":
        return None
    name = value.get("name")
    return name if isinstance(name, str) and name else None


def _serialized_nonnegative_index(value: Any) -> int | None:
    if (
        not isinstance(value, dict)
        or value.get("kind") != "IRQuantity"
        or value.get("unit") is not None
    ):
        return None
    raw = value.get("value")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    numeric = float(raw)
    if numeric < 0 or not numeric.is_integer():
        return None
    return int(numeric)
