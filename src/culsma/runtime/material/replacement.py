"""Atomic author declaration exposing components of a counted cellular source."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.args import arg_string
from culsma.runtime.material.author_transition import parse_material_selector, resolve_material_entry
from culsma.runtime.material.component_entries import normalize_component_entries, replace_component_entries, validate_component_entry_set
from culsma.runtime.material.container_content import apply_define_content
from culsma.runtime.material.contents_state import invalidate_contents_state
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.refs import resolve_target_ref
from culsma.runtime.material.result import MaterialUpdateResult
from culsma.runtime.material.unknown_quantity import unknown_mass


def apply_material_replace(step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
    def fail(code: str, message: str) -> MaterialUpdateResult:
        return diagnostic_result(step, state, code, message)
    receiver = step.args.get("self")
    if not isinstance(receiver, dict) or receiver.get("kind") != "IRMember" or receiver.get("member") != "materials":
        return fail("MAT_MATERIAL_REPLACE_INVALID", "replace requires a materials receiver")
    source_id = resolve_target_ref(state, receiver.get("base"))
    source = state.get("containers", {}).get(source_id)
    if not isinstance(source, dict):
        return fail("MAT_BINDING_NOT_FOUND", "Replacement container does not exist")
    # Indexed partitions are independent authoritative containers; editing their parent
    # would otherwise leave stale aliases. Require a collected material first.
    contents = state.get("contents_states", {}).get(source_id)
    if isinstance(contents, dict) and contents.get("valid") is not False:
        return fail("MAT_MATERIAL_REPLACE_ACTIVE_PARTS", "Collect material into a container before replacing its components")
    selector = parse_material_selector(step.args.get("subject"))
    if selector is None:
        return fail("MAT_MATERIAL_SELECTOR_INVALID", "Replacement requires a material entry selector")
    receiver_ref = arg_string(receiver.get("base"))
    if selector.container_ref != receiver_ref:
        return fail("MAT_MATERIAL_SELECTOR_CONTAINER_MISMATCH", "Replacement subject belongs to another container")
    entries = normalize_component_entries(source, state=state, container_id=source_id)
    resolved = resolve_material_entry(selector=selector, source_id=receiver_ref, entries=entries)
    if not resolved.resolved:
        error = resolved.issues[0]
        return fail(error.code, error.message)
    original = next(e for e in entries if e["entry_id"] == resolved.entry.entry_id)
    quantity = original.get("quantity")
    content = state.get("content_registry", {}).get(original["content_ref"], {})
    if not isinstance(quantity, dict) or quantity.get("dimension") != "count" or content.get("content_kind") != "bio_cellular":
        return fail("MAT_MATERIAL_REPLACE_SOURCE_UNSUPPORTED", "This prototype replaces a counted cellular entry; it does not convert mass or volume")
    products = step.args.get("products")
    if set(step.args) != {"self", "subject", "products"} or not isinstance(products, dict) or products.get("kind") != "IRList" or not products.get("elements"):
        return fail("MAT_MATERIAL_REPLACE_INVALID", "Replacement requires a nonempty product list")
    candidate = deepcopy(state)
    new_entries = []
    for ordinal, product in enumerate(products["elements"]):
        if not isinstance(product, dict) or product.get("kind") != "IRPair":
            return fail("MAT_MATERIAL_REPLACE_INVALID", "Products must be content:unknown pairs")
        descriptor, amount = product.get("left"), product.get("right")
        if not isinstance(descriptor, dict) or descriptor.get("kind") != "IRCall" or descriptor.get("name") != "DefineContent":
            return fail("MAT_MATERIAL_REPLACE_INVALID", "Each product needs a content descriptor")
        if not isinstance(amount, dict) or amount.get("kind") != "IRCall" or amount.get("name") != "unknown":
            return fail("MAT_MATERIAL_REPLACE_INVALID", "This prototype requires unknown mass")
        qargs = amount.get("args", [])
        if len(qargs) != 1 or qargs[0].get("name") != "dimension" or arg_string(qargs[0].get("value")) != "mass":
            return fail("MAT_MATERIAL_REPLACE_INVALID", "Use unknown(dimension = mass)")
        definition = PlanStep(step_id=f"{step.step_id}:product:{ordinal}", op="DefineContent",
                              args={a["name"]: a["value"] for a in descriptor.get("args", [])},
                              deps=[], span=step.span)
        defined = apply_define_content(definition, candidate)
        if not defined.ok:
            return fail(defined.diagnostics[0].code, defined.diagnostics[0].message)
        content_id = defined.delta["content_id"]
        if any(e["content_ref"] == content_id for e in entries + new_entries):
            return fail("MAT_MATERIAL_REPLACE_DUPLICATE_PRODUCT", "Replacement product must have a new content identity in this container")
        origin = f"{source_id}:{step.step_id}:{ordinal}"
        new_entries.append({"entry_id": content_id, "content_ref": content_id,
                            "amount": None, "quantity": unknown_mass(origin), "relation": "free",
                            "associated_with": None, "association_target_kind": None,
                            "relationship_source": "author_replace", "material_state_source": "author_replace",
                            "provenance": {"source": "author", "operation_id": step.step_id,
                                           "source_container_id": source_id, "source_entry_id": original["entry_id"]}})
    updated = []
    for entry in entries:
        updated.extend(new_entries if entry["entry_id"] == original["entry_id"] else [entry])
    try:
        validate_component_entry_set(updated, owner="Material replacement")
    except ValueError as error:
        return fail("MAT_MATERIAL_REPLACE_INVALID", str(error))
    replace_component_entries(candidate["containers"][source_id], updated)
    record = {"operation_id": step.step_id, "container_id": source_id, "source": "author",
              "retired_entry": deepcopy(original), "product_entry_ids": [e["entry_id"] for e in new_entries],
              "unlisted_constituents": "not_enumerated", "mass_balance": "not_quantified",
              "after_step_ids": list(step.deps)}
    candidate.setdefault("material_replacements", []).append(record)
    invalidate_contents_state(candidate, source_id, reason="materials_replace")
    return MaterialUpdateResult(material_state=candidate, diagnostics=[], delta={
        "op": "replace", **record,
        "retired_quantities": {original["entry_id"]: {**quantity, "component_amount": original["amount"]}},
    })
