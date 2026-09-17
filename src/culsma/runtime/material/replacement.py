"""Atomic selector-keyed material replacement with one-to-many expansion."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.args import arg_quantity, arg_string
from culsma.runtime.material.author_transition import parse_material_selector, resolve_material_entry
from culsma.runtime.material.component_entries import (
    content_registry_partition_class,
    normalize_component_entries,
    replace_component_entries,
    validate_component_entry_set,
)
from culsma.runtime.material.container_content import apply_define_content
from culsma.runtime.material.contents_state import invalidate_contents_state
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.refs import resolve_target_ref
from culsma.runtime.material.result import MaterialUpdateResult
from culsma.runtime.material.units import COUNT_TO_CELLS, MASS_TO_MG, VOLUME_TO_UL
from culsma.runtime.material.unknown_quantity import unknown_mass


def apply_material_replace(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    def fail(code: str, message: str) -> MaterialUpdateResult:
        return diagnostic_result(step, state, code, message)

    receiver = step.args.get("self")
    if (
        not isinstance(receiver, dict)
        or receiver.get("kind") != "IRMember"
        or receiver.get("member") != "materials"
    ):
        return fail("MAT_MATERIAL_REPLACE_INVALID", "replace requires a materials receiver")
    source_id = resolve_target_ref(state, receiver.get("base"))
    source = state.get("containers", {}).get(source_id)
    if not isinstance(source, dict):
        return fail("MAT_BINDING_NOT_FOUND", "Replacement container does not exist")
    contents = state.get("contents_states", {}).get(source_id)
    if isinstance(contents, dict) and contents.get("valid") is not False:
        return fail(
            "MAT_MATERIAL_REPLACE_ACTIVE_PARTS",
            "Collect material into a container before replacing its components",
        )

    replacement_map = step.args.get("arg0")
    if (
        set(step.args) != {"self", "arg0"}
        or not isinstance(replacement_map, dict)
        or replacement_map.get("kind") != "IRList"
        or not replacement_map.get("elements")
    ):
        return fail(
            "MAT_MATERIAL_REPLACE_INVALID",
            "replace requires one nonempty selector-to-material map",
        )

    receiver_ref = arg_string(receiver.get("base"))
    entries = normalize_component_entries(source, state=state, container_id=source_id)
    resolved: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    retired_ids: set[str] = set()
    for mapping in replacement_map["elements"]:
        if not isinstance(mapping, dict) or mapping.get("kind") != "IRPair":
            return fail("MAT_MATERIAL_REPLACE_INVALID", "Replacement map entry is invalid")
        selector = parse_material_selector(mapping.get("left"))
        if selector is None:
            return fail("MAT_MATERIAL_SELECTOR_INVALID", "Replacement key must be a material selector")
        if selector.container_ref != receiver_ref:
            return fail(
                "MAT_MATERIAL_SELECTOR_CONTAINER_MISMATCH",
                "Replacement key belongs to another container",
            )
        selected = resolve_material_entry(
            selector=selector,
            source_id=receiver_ref,
            entries=entries,
        )
        if not selected.resolved:
            error = selected.issues[0]
            return fail(error.code, error.message)
        if selected.entry.entry_id in retired_ids:
            return fail(
                "MAT_MATERIAL_REPLACE_DUPLICATE_SUBJECT",
                f"Material entry '{selected.entry.entry_id}' is replaced more than once",
            )
        original = next(
            entry for entry in entries if entry["entry_id"] == selected.entry.entry_id
        )
        if not isinstance(original.get("quantity"), dict):
            return fail(
                "MAT_MATERIAL_REPLACE_SOURCE_UNSUPPORTED",
                "Replacement subject must have a tracked quantity",
            )
        products = _serialized_replacement_products(mapping.get("right"))
        if products is None:
            return fail(
                "MAT_MATERIAL_REPLACE_INVALID",
                "Replacement value must be one material or a nonempty material list",
            )
        retired_ids.add(selected.entry.entry_id)
        resolved.append((original, products))

    candidate = deepcopy(state)
    kept_entries = [deepcopy(entry) for entry in entries if entry["entry_id"] not in retired_ids]
    used_content_refs = {str(entry.get("content_ref")) for entry in kept_entries}
    replacements_by_entry_id: dict[str, list[dict[str, Any]]] = {}

    for replacement_ordinal, (original, products) in enumerate(resolved):
        new_entries: list[dict[str, Any]] = []
        for product_ordinal, product in enumerate(products):
            descriptor, raw_quantity = product.get("left"), product.get("right")
            if (
                not isinstance(descriptor, dict)
                or descriptor.get("kind") != "IRCall"
                or descriptor.get("name") != "DefineContent"
            ):
                return fail(
                    "MAT_MATERIAL_REPLACE_INVALID",
                    "Replacement value requires a content descriptor",
                )
            definition = PlanStep(
                step_id=(
                    f"{step.step_id}:replacement:{replacement_ordinal}:"
                    f"product:{product_ordinal}"
                ),
                op="DefineContent",
                args={arg["name"]: arg["value"] for arg in descriptor.get("args", [])},
                deps=[],
                span=step.span,
            )
            defined = apply_define_content(definition, candidate)
            if not defined.ok:
                return fail(defined.diagnostics[0].code, defined.diagnostics[0].message)
            content_id = defined.delta["content_id"]
            if content_id in used_content_refs:
                return fail(
                    "MAT_MATERIAL_REPLACE_DUPLICATE_PRODUCT",
                    f"Replacement content '{content_id}' already exists in the resulting container",
                )
            quantity = _replacement_quantity(
                raw_quantity,
                origin=(
                    f"{source_id}:{step.step_id}:{replacement_ordinal}:"
                    f"{product_ordinal}"
                ),
            )
            if quantity is None:
                return fail(
                    "MAT_MATERIAL_REPLACE_INVALID",
                    "Replacement quantity must be unit-bearing or unknown(dimension = mass)",
                )
            content = candidate.get("content_registry", {}).get(content_id, {})
            if (
                quantity.get("dimension") == "count"
                and content.get("content_kind") != "bio_cellular"
            ):
                return fail(
                    "MAT_MATERIAL_REPLACE_INVALID",
                    "A count replacement requires bio_cellular content",
                )
            new_entry = {
                "entry_id": content_id,
                "content_ref": content_id,
                "amount": quantity.get("value"),
                "quantity": quantity,
                "relation": "free",
                "associated_with": None,
                "association_target_kind": None,
                "relationship_source": "author_replace",
                "material_state_source": "author_replace",
                "provenance": {
                    "source": "author",
                    "operation_id": step.step_id,
                    "source_container_id": source_id,
                    "source_entry_id": original["entry_id"],
                },
            }
            partition_class = content_registry_partition_class(candidate, content_id)
            if isinstance(partition_class, str):
                new_entry["partition_class"] = partition_class
            new_entries.append(new_entry)
            used_content_refs.add(content_id)
        replacements_by_entry_id[original["entry_id"]] = new_entries

    updated = []
    for entry in entries:
        replacements = replacements_by_entry_id.get(entry["entry_id"])
        updated.extend(replacements if replacements is not None else [deepcopy(entry)])
    try:
        validate_component_entry_set(updated, owner="Material replacement")
    except ValueError as error:
        return fail("MAT_MATERIAL_REPLACE_INVALID", str(error))
    replace_component_entries(candidate["containers"][source_id], updated)

    records = []
    retired_quantities = {}
    for original, _products in resolved:
        new_entries = replacements_by_entry_id[original["entry_id"]]
        record = {
            "operation_id": step.step_id,
            "container_id": source_id,
            "source": "author",
            "retired_entry": deepcopy(original),
            "product_entry_ids": [entry["entry_id"] for entry in new_entries],
            "unlisted_constituents": "not_enumerated",
            "mass_balance": "not_quantified",
            "after_step_ids": list(step.deps),
        }
        records.append(record)
        retired_quantities[original["entry_id"]] = {
            **original["quantity"],
            "component_amount": original.get("amount"),
        }
    candidate.setdefault("material_replacements", []).extend(records)
    invalidate_contents_state(candidate, source_id, reason="materials_replace")
    return MaterialUpdateResult(
        material_state=candidate,
        diagnostics=[],
        delta={
            "op": "replace",
            "container_id": source_id,
            "replacements": records,
            "retired_quantities": retired_quantities,
        },
    )


def _serialized_replacement_products(value: Any) -> list[dict[str, Any]] | None:
    if isinstance(value, dict) and value.get("kind") == "IRPair":
        return [value]
    if not isinstance(value, dict) or value.get("kind") != "IRList":
        return None
    elements = value.get("elements")
    if not isinstance(elements, list) or not elements:
        return None
    if not all(
        isinstance(element, dict) and element.get("kind") == "IRPair"
        for element in elements
    ):
        return None
    return elements


def _replacement_quantity(value: Any, *, origin: str) -> dict[str, Any] | None:
    if isinstance(value, dict) and value.get("kind") == "IRCall" and value.get("name") == "unknown":
        args = value.get("args")
        if not isinstance(args, list) or len(args) != 1 or args[0].get("name") != "dimension":
            return None
        if arg_string(args[0].get("value")) != "mass":
            return None
        return unknown_mass(origin)
    quantity = arg_quantity(value)
    if quantity is None:
        return None
    raw_value = float(quantity["value"])
    unit = str(quantity["unit"])
    if raw_value < 0:
        return None
    if unit in MASS_TO_MG:
        return {"dimension": "mass", "unit": "mg", "value": raw_value * MASS_TO_MG[unit]}
    if unit in VOLUME_TO_UL:
        return {"dimension": "volume", "unit": "uL", "value": raw_value * VOLUME_TO_UL[unit]}
    if unit in COUNT_TO_CELLS and raw_value.is_integer():
        return {"dimension": "count", "unit": "cells", "value": raw_value * COUNT_TO_CELLS[unit]}
    return None
