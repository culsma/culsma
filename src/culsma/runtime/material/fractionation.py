"""Authored fraction allocation through the existing material movement boundary."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from culsma.domains.material_allocation import allocation_ratio, validate_allocation_ratios
from culsma.pipeline.plan_nodes import PlanStep
from .args import arg_call, arg_string, call_arg_int
from .component_entries import (
    component_entry_has_quantity, normalize_component_entries,
    replace_component_entries, split_component_entry,
)
from .ledger import container, container_count_cells, ensure_container, refresh_container_aggregates
from .movement import apply_material_movement
from .refs import ref_display, resolve_structured_ref
from .scientific_model_adapter import MaterialEffectFailure, ScientificModelMaterialAdapter
from .suspension import refresh_cell_suspension_relationship


@dataclass(frozen=True)
class FractionationRequest:
    source_id: str
    program_kind: str
    bins: int
    bind_name: str | None
    fates: dict[str, tuple[float, ...]]


def resolve_fractionation_request(
    step: PlanStep, state: dict[str, Any],
) -> FractionationRequest | MaterialEffectFailure:
    """Resolve the operation boundary before allocating any output material."""
    from .solution import has_solution_solutes

    program = arg_call(step.args.get("program"))
    if program is None:
        return MaterialEffectFailure("MAT_BINDING_NOT_FOUND", "frac requires sample/program")
    bins = call_arg_int(program, "bins")
    if bins is None or bins <= 0:
        return MaterialEffectFailure("MAT_BINDING_NOT_FOUND", "frac requires positive bins")
    sample = step.args.get("sample")
    source_id = resolve_structured_ref(state, sample, create_if_identifier=False)
    source = container(state, source_id) if source_id is not None else None
    if source is None:
        return MaterialEffectFailure("MAT_BINDING_NOT_FOUND", f"Unknown frac sample '{ref_display(sample)}'")
    if has_solution_solutes(source):
        return MaterialEffectFailure("MAT_SOLUTION_OPERATION_UNSUPPORTED",
                                     "Concentration-bearing solution fractionation is not supported")
    fates = parse_fraction_fates(
        step.args.get("component_fates", {}), bins=bins,
        known_components=set(source.get("components", {})),
    )
    if isinstance(fates, MaterialEffectFailure):
        return fates
    program_kind = program.get("name")
    return FractionationRequest(
        source_id=source_id, program_kind=program_kind if isinstance(program_kind, str) else "frac_program",
        bins=bins, bind_name=arg_string(step.args.get("bind")), fates=fates,
    )


def equal_fraction_ratio(
    initial: tuple[float, float, float], current: tuple[float, float, float], bins: int,
) -> float:
    """Preserve the legacy volume, mass, then count precedence and arithmetic."""
    return next((total * (1.0 / bins) / available
                 for total, available in zip(initial, current) if available > 0), 0.0)


def allocate_equal_fraction_parts(
    *, state: dict[str, Any], source_id: str, bins: int, step_id: str,
    material_effect_adapter: ScientificModelMaterialAdapter | None,
) -> dict[str, dict[str, Any]] | MaterialEffectFailure:
    """Distribute equal parts in a caller-owned candidate state, never a live state."""
    source = container(state, source_id)
    if source is None:
        return MaterialEffectFailure("MAT_BINDING_NOT_FOUND", f"Unknown frac sample '{source_id}'")
    initial = (float(source.get("volume_uL", 0.0)), float(source.get("mass_mg", 0.0)),
               container_count_cells(source))
    parts = {}
    for index in range(bins):
        last = index == bins - 1
        current = (float(source.get("volume_uL", 0.0)), float(source.get("mass_mg", 0.0)),
                   container_count_cells(source))
        slot_id = f"{step_id}::{index}"
        slot = ensure_container(state, slot_id)
        movement = apply_material_movement(
            state=state, source=source, target=slot, source_id=source_id, destination_id=slot_id,
            ratio=1.0 if last else equal_fraction_ratio(initial, current, bins),
            material_effect_adapter=material_effect_adapter,
            request_id=f"{step_id}:fraction:{'last' if last else index}",
        )
        if movement.failure is not None:
            return movement.failure
        refresh_cell_suspension_relationship(state, slot_id, forced_state="suspension")
        parts[str(index)] = slot
    refresh_cell_suspension_relationship(state, source_id)
    return parts


def parse_fraction_fates(
    raw: Any, *, bins: int, known_components: set[str],
) -> dict[str, tuple[float, ...]] | MaterialEffectFailure:
    """Validate wire values again, including plans supplied without a frontend."""
    if not isinstance(raw, dict):
        return MaterialEffectFailure("MAT_FRACTION_FATE_RULE_SHAPE_INVALID",
                                     "frac component_fates must be a content-identity record")
    parsed = {}
    for content_id, raw_values in raw.items():
        if content_id not in known_components:
            return MaterialEffectFailure("MAT_FRACTION_FATE_COMPONENT_NOT_FOUND",
                                         f"Fraction fate references unknown source content '{content_id}'")
        values = (raw_values.get("elements") if isinstance(raw_values, dict)
                  and raw_values.get("kind") == "IRList" else raw_values)
        if not isinstance(values, list):
            return MaterialEffectFailure("MAT_FRACTION_FATE_RULE_SHAPE_INVALID",
                                         f"Fraction fate for '{content_id}' requires an ordered ratio list")
        ratios = tuple(
            allocation_ratio(value.get("value"), value.get("unit"))
            if isinstance(value, dict) and value.get("kind") == "IRQuantity"
            else allocation_ratio(value) for value in values
        )
        error = validate_allocation_ratios(ratios, bins)
        if error:
            return MaterialEffectFailure(f"MAT_FRACTION_FATE_RULE_{error}",
                                         f"Fraction fate for '{content_id}' requires {bins} ratios in 0..1 totaling 100%")
        # Tolerated floating-point sum error must not create or discard material.
        total = sum(ratios)
        parsed[content_id] = tuple(value / total for value in ratios)
    return parsed


def allocate_fraction_parts(
    *, state: dict[str, Any], source: dict[str, Any], source_id: str,
    bins: int, fates: dict[str, tuple[float, ...]], step_id: str,
    material_effect_adapter: ScientificModelMaterialAdapter | None,
) -> dict[str, dict[str, Any]] | MaterialEffectFailure:
    """Project all outputs without mutating the input; movement owns relations."""
    source_copy = deepcopy(source)
    entries = normalize_component_entries(source_copy, state=state, container_id=source_id)
    remaining_entries = deepcopy(entries)
    parts = {}
    for index in range(bins):
        selected_entries = []
        for offset, entry in enumerate(entries):
            ratios = fates.get(str(entry["content_ref"]), (1.0 / bins,) * bins)
            # The last positive destination receives the residual exactly;
            # declared zero destinations must never receive rounding residue.
            remaining_ratio = sum(ratios[index:])
            remaining_entries[offset], selected = split_component_entry(
                remaining_entries[offset], ratios[index] / remaining_ratio if remaining_ratio else 0.0,
            )
            if component_entry_has_quantity(selected):
                selected_entries.append(selected)
        selected_source = deepcopy(source_copy)
        replace_component_entries(selected_source, selected_entries)
        refresh_container_aggregates(selected_source)
        part: dict[str, Any] = {}
        movement = apply_material_movement(
            state=state, source=selected_source, target=part, source_id=source_id,
            destination_id=f"{step_id}::{index}", ratio=1.0,
            material_effect_adapter=material_effect_adapter, request_id=f"{step_id}:fraction:{index}",
        )
        if movement.failure is not None:
            return movement.failure
        parts[str(index)] = part
    return parts
