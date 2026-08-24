"""Runtime value and expression resolution helpers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.state import RuntimeState


_LOCAL_RUNTIME_CONSTRUCTORS = {"markers", "stream", "data_ref", "data_group_ref", "data_schema"}
UNRESOLVED = object()


class RuntimeValueResolver:
    def eval_expr(self, expr: Any, state: RuntimeState) -> Any:
        return _eval_runtime_expr(expr, state)

    def eval_local_value(self, target: str, expr: Any, state: RuntimeState) -> Any:
        return _eval_runtime_local_value(target, expr, state)

    def eval_method_arg(self, expr: Any, state: RuntimeState) -> Any:
        return _eval_runtime_method_arg(expr, state)

    def resolve_append_target(self, expr: Any, state: RuntimeState) -> Any:
        return _resolve_runtime_append_target(expr, state)

    def resolve_member_assign_target(self, expr: Any, state: RuntimeState) -> Any:
        return _resolve_runtime_member_assign_target(expr, state)

    def value_to_serialized(self, value: Any) -> Any:
        return _runtime_value_to_serialized(value)

    def deep_serialize(self, value: Any) -> Any:
        return _runtime_deep_serialize(value)

    def protocol_output_serialize(self, value: Any) -> Any:
        return _runtime_protocol_output_serialize(value)

    def resolve_step_args(self, step: PlanStep, state: RuntimeState) -> PlanStep:
        return _resolve_step_runtime_args(step, state)

    def eval_repeat_items(self, expr: Any, state: RuntimeState) -> Any:
        return _eval_runtime_repeat_items(expr, state)

    def resolve_runtime_ref(self, material_state: Any, value: Any) -> str | None:
        return _resolve_runtime_ref(material_state, value)

    def resolve_runtime_ref_group(self, material_state: Any, value: Any) -> list[dict[str, Any]] | None:
        return _resolve_runtime_ref_group(material_state, value)

    def container_ref_payload(self, material_state: Any, container_id: str) -> dict[str, Any] | None:
        return _container_ref_payload(material_state, container_id)

    def eval_protocol_output_expr(self, expr: Any, state: RuntimeState) -> Any:
        value = _eval_runtime_expr(expr, state)
        if value is not UNRESOLVED:
            return value
        material_value = _resolve_runtime_material_output_value(state.artifacts.get("material_state"), expr)
        if material_value is not None:
            return material_value
        return UNRESOLVED


def _eval_runtime_expr(expr: Any, state: RuntimeState) -> Any:
    if isinstance(expr, dict):
        kind = expr.get("kind")
        if kind == "IRBoolean":
            return expr.get("value")
        if kind == "IRString":
            return expr.get("value")
        if kind == "IRQuantity":
            unit = expr.get("unit")
            if unit is None:
                return expr.get("value")
            return (expr.get("value"), unit)
        if kind in {"IRList", "IRGroup"}:
            elements = expr.get("elements")
            if not isinstance(elements, list):
                return UNRESOLVED
            out: list[Any] = []
            for item in elements:
                resolved = _eval_runtime_expr(item, state)
                if resolved is UNRESOLVED:
                    return UNRESOLVED
                out.append(resolved)
            return out
        if kind == "IRIdentifier":
            return _resolve_runtime_identifier(expr.get("name"), state)
        if kind == "IRIndex":
            return _resolve_runtime_index(expr, state)
        if kind == "IRMember":
            base = _eval_runtime_expr(expr.get("base"), state)
            if base is UNRESOLVED or not isinstance(base, dict):
                return UNRESOLVED
            member = expr.get("member")
            if not isinstance(member, str) or member not in base:
                return UNRESOLVED
            return base[member]
        if kind == "IRCall":
            return _eval_runtime_call(expr, state)
        if kind == "IRUnary":
            operand = _eval_runtime_expr(expr.get("operand"), state)
            if operand is UNRESOLVED:
                return UNRESOLVED
            if expr.get("op") == "-" and isinstance(operand, (int, float)):
                return -operand
            return UNRESOLVED
        if kind == "IRBinary":
            return _eval_runtime_binary(expr, state)
    if isinstance(expr, (bool, int, float, str)):
        return expr
    return UNRESOLVED


def _resolve_runtime_identifier(name: Any, state: RuntimeState) -> Any:
    if not isinstance(name, str):
        return UNRESOLVED
    local_bindings = state.artifacts.get("local_bindings", {})
    if isinstance(local_bindings, dict) and name in local_bindings:
        return _runtime_bound_value(local_bindings.get(name), state)
    data_bindings = state.artifacts.get("data_bindings", {})
    if isinstance(data_bindings, dict):
        data_id = data_bindings.get(name)
        data_objects = state.artifacts.get("data_objects", {})
        if isinstance(data_id, str) and isinstance(data_objects, dict):
            record = data_objects.get(data_id)
            if isinstance(record, dict):
                return record
    data_group_bindings = state.artifacts.get("data_group_bindings", {})
    if isinstance(data_group_bindings, dict):
        group_id = data_group_bindings.get(name)
        groups = state.artifacts.get("data_groups", {})
        if isinstance(group_id, str) and isinstance(groups, dict):
            record = groups.get(group_id)
            if isinstance(record, dict):
                return record
    return UNRESOLVED


def _eval_runtime_call(expr: dict[str, Any], state: RuntimeState) -> Any:
    name = expr.get("name")
    if not isinstance(name, str):
        return UNRESOLVED
    if name in _LOCAL_RUNTIME_CONSTRUCTORS:
        return _eval_local_runtime_constructor(expr, state)
    if name == "detects":
        return _eval_runtime_detects(expr, state)
    return UNRESOLVED


def _eval_runtime_local_value(target: str, expr: Any, state: RuntimeState) -> Any:
    if isinstance(expr, dict) and expr.get("kind") == "IRCall":
        name = expr.get("name")
        if isinstance(name, str) and name in _LOCAL_RUNTIME_CONSTRUCTORS:
            return _eval_local_runtime_constructor(expr, state, target_name=target)
    return _eval_runtime_expr(expr, state)


def _eval_local_runtime_constructor(
    expr: dict[str, Any],
    state: RuntimeState,
    *,
    target_name: str | None = None,
) -> Any:
    name = expr.get("name")
    if not isinstance(name, str):
        return UNRESOLVED
    raw_args = expr.get("args")
    if not isinstance(raw_args, list):
        raw_args = []
    kwargs: dict[str, Any] = {}
    for raw_arg in raw_args:
        if not isinstance(raw_arg, dict):
            continue
        arg_name = raw_arg.get("name")
        if not isinstance(arg_name, str):
            continue
        kwargs[arg_name] = _eval_runtime_constructor_arg(raw_arg.get("value"), state)

    if name == "markers":
        raw_items = kwargs.get("items")
        items = raw_items if isinstance(raw_items, list) else []
        return {
            "kind": "marker_panel_ref",
            "label": target_name,
            "items": list(items),
        }
    if name == "stream":
        source_ref = kwargs.get("sample")
        if not isinstance(source_ref, str):
            source_ref = None
        unit_kind = kwargs.get("unit")
        if not isinstance(unit_kind, str):
            unit_kind = None
        panel_ref = kwargs.get("panel")
        return {
            "kind": "unit_stream_ref",
            "id": target_name or "unit_stream",
            "source_ref": source_ref,
            "unit_kind": unit_kind,
            "panel_ref": panel_ref,
            "items": _seed_runtime_stream_items(
                state=state,
                stream_name=target_name,
                source_ref=source_ref,
                unit_kind=unit_kind,
            ),
        }
    if name == "data_ref":
        schema_ref = kwargs.get("schema_ref")
        return {
            "kind": "data_ref",
            "data_kind": kwargs.get("kind"),
            "subject_ref": kwargs.get("subject_ref"),
            "context_ref": kwargs.get("context_ref"),
            "schema_ref": schema_ref,
            "result": _merge_result_payloads(_schema_result_payload(schema_ref), {}),
        }
    if name == "data_group_ref":
        schema_ref = kwargs.get("schema_ref")
        return {
            "kind": "data_group_ref",
            "data_kind": kwargs.get("kind"),
            "schema_ref": schema_ref,
            "items": [],
            "result": _merge_result_payloads(_schema_result_payload(schema_ref), {}),
        }
    if name == "data_schema":
        return {
            "kind": "data_schema_ref",
            "label": kwargs.get("label"),
            "fields": kwargs.get("fields"),
        }
    return UNRESOLVED


def _eval_runtime_constructor_arg(expr: Any, state: RuntimeState) -> Any:
    if isinstance(expr, dict):
        kind = expr.get("kind")
        if kind == "IRIdentifier":
            resolved = _resolve_runtime_identifier(expr.get("name"), state)
            if resolved is not UNRESOLVED:
                return resolved
            material_ref = _resolve_runtime_ref(
                state.artifacts.get("material_state"),
                expr,
            )
            if material_ref is not None:
                return material_ref
            name = expr.get("name")
            if isinstance(name, str):
                return name
            return UNRESOLVED
        if kind in {"IRList", "IRGroup"}:
            elements = expr.get("elements")
            if not isinstance(elements, list):
                return []
            return [_eval_runtime_constructor_arg(item, state) for item in elements]
    value = _eval_runtime_expr(expr, state)
    if value is not UNRESOLVED:
        return value
    return expr


def _seed_runtime_stream_items(
    *,
    state: RuntimeState,
    stream_name: str | None,
    source_ref: str | None,
    unit_kind: str | None,
) -> list[dict[str, Any]]:
    raw_seed = state.artifacts.get("stream_units", {})
    if not isinstance(raw_seed, dict):
        return []
    candidates: list[Any] = []
    if isinstance(stream_name, str) and stream_name in raw_seed:
        candidates = raw_seed.get(stream_name)
    elif isinstance(source_ref, str) and source_ref in raw_seed:
        candidates = raw_seed.get(source_ref)
    if not isinstance(candidates, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(candidates):
        normalized = _normalize_runtime_unit_seed(
            item=item,
            ordinal=idx,
            stream_name=stream_name,
            source_ref=source_ref,
            unit_kind=unit_kind,
        )
        if normalized is not None:
            out.append(normalized)
    return out


def _normalize_runtime_unit_seed(
    *,
    item: Any,
    ordinal: int,
    stream_name: str | None,
    source_ref: str | None,
    unit_kind: str | None,
) -> dict[str, Any] | None:
    base_id = f"{stream_name or 'unit_stream'}::{ordinal}"
    if isinstance(item, dict):
        if item.get("kind") == "unit_ref":
            normalized = deepcopy(item)
            normalized.setdefault("id", base_id)
            normalized.setdefault("stream_ref", stream_name)
            normalized.setdefault("source_ref", source_ref)
            normalized.setdefault("unit_kind", unit_kind)
            return normalized
        normalized = {
            "kind": "unit_ref",
            "id": str(item.get("id", base_id)),
            "stream_ref": stream_name,
            "source_ref": source_ref,
            "unit_kind": unit_kind,
        }
        for key, value in item.items():
            if key not in normalized:
                normalized[key] = deepcopy(value)
        return normalized
    if isinstance(item, str):
        return {
            "kind": "unit_ref",
            "id": item,
            "stream_ref": stream_name,
            "source_ref": source_ref,
            "unit_kind": unit_kind,
        }
    return {
        "kind": "unit_ref",
        "id": base_id,
        "stream_ref": stream_name,
        "source_ref": source_ref,
        "unit_kind": unit_kind,
        "value": deepcopy(item),
    }


def _eval_runtime_method_arg(expr: Any, state: RuntimeState) -> Any:
    if isinstance(expr, dict) and expr.get("kind") == "IRIdentifier":
        resolved = _resolve_runtime_identifier(expr.get("name"), state)
        if resolved is not UNRESOLVED:
            return resolved
        name = expr.get("name")
        if isinstance(name, str):
            return name
    return _eval_runtime_expr(expr, state)


def _eval_runtime_detects(expr: dict[str, Any], state: RuntimeState) -> Any:
    raw_args = expr.get("args")
    if not isinstance(raw_args, list) or len(raw_args) < 2:
        return UNRESOLVED
    receiver_expr = raw_args[0].get("value") if isinstance(raw_args[0], dict) else None
    target_expr = raw_args[1].get("value") if isinstance(raw_args[1], dict) else None
    receiver_candidates = _runtime_detect_key_candidates(receiver_expr, state)
    target_candidates = _runtime_detect_key_candidates(target_expr, state)
    if not receiver_candidates or not target_candidates:
        return UNRESOLVED
    detect_hits = state.artifacts.get("detect_hits", {})
    if not isinstance(detect_hits, dict):
        return False
    for receiver_key in receiver_candidates:
        hit_spec = detect_hits.get(receiver_key)
        if hit_spec is None:
            continue
        if hit_spec is True:
            return True
        if isinstance(hit_spec, (list, tuple, set)):
            hit_set = {item for item in hit_spec if isinstance(item, str)}
            if any(target_key in hit_set for target_key in target_candidates):
                return True
        if isinstance(hit_spec, dict):
            for target_key in target_candidates:
                if bool(hit_spec.get(target_key)):
                    return True
    return False


def _eval_runtime_repeat_items(expr: Any, state: RuntimeState) -> Any:
    value = _eval_runtime_expr(expr, state)
    if value is UNRESOLVED:
        return UNRESOLVED
    if isinstance(value, list):
        return [deepcopy(item) for item in value]
    if isinstance(value, dict):
        items = value.get("items")
        if isinstance(items, list):
            return [deepcopy(item) for item in items]
    return UNRESOLVED


def _runtime_detect_key_candidates(expr: Any, state: RuntimeState) -> list[str]:
    candidates: list[str] = []
    if not isinstance(expr, dict):
        return candidates
    if expr.get("kind") == "IRIdentifier":
        name = expr.get("name")
        if isinstance(name, str):
            candidates.append(name)
        material_ref = _resolve_runtime_ref(state.artifacts.get("material_state"), expr)
        if isinstance(material_ref, str) and material_ref not in candidates:
            candidates.append(material_ref)
        local_bindings = state.artifacts.get("local_bindings", {})
        if isinstance(name, str) and isinstance(local_bindings, dict) and name in local_bindings:
            candidates.append(name)
            bound_value = local_bindings.get(name)
            if isinstance(bound_value, dict):
                bound_id = bound_value.get("id")
                if isinstance(bound_id, str) and bound_id not in candidates:
                    candidates.append(bound_id)
        return candidates
    resolved = _eval_runtime_expr(expr, state)
    if isinstance(resolved, dict):
        ref_id = resolved.get("id")
        if isinstance(ref_id, str):
            candidates.append(ref_id)
    return candidates


def _resolve_runtime_index(expr: dict[str, Any], state: RuntimeState) -> Any:
    base = expr.get("base")
    index = expr.get("index")
    if not isinstance(base, dict) or base.get("kind") != "IRIdentifier":
        return UNRESOLVED
    group_name = base.get("name")
    if not isinstance(group_name, str):
        return UNRESOLVED
    slot = _runtime_static_index_key(index)
    if slot is None:
        return UNRESOLVED
    indexed_group_bindings = state.artifacts.get("data_group_indexed_bindings", {})
    data_objects = state.artifacts.get("data_objects", {})
    if not isinstance(indexed_group_bindings, dict) or not isinstance(data_objects, dict):
        return UNRESOLVED
    group = indexed_group_bindings.get(group_name)
    if not isinstance(group, dict):
        return UNRESOLVED
    data_id = group.get(slot)
    if not isinstance(data_id, str):
        return UNRESOLVED
    record = data_objects.get(data_id)
    if not isinstance(record, dict):
        return UNRESOLVED
    return record


def _resolve_runtime_append_target(expr: Any, state: RuntimeState) -> Any:
    if not isinstance(expr, dict):
        return UNRESOLVED
    if expr.get("kind") == "IRIdentifier":
        resolved = _resolve_runtime_identifier(expr.get("name"), state)
        return resolved if isinstance(resolved, list) else UNRESOLVED
    if expr.get("kind") != "IRMember":
        return UNRESOLVED

    base = _resolve_runtime_mutable_path(expr.get("base"), state)
    if base is UNRESOLVED or not isinstance(base, dict):
        return UNRESOLVED
    member = expr.get("member")
    if not isinstance(member, str):
        return UNRESOLVED
    current = base.get(member)
    if current is None:
        base[member] = []
        current = base[member]
    return current if isinstance(current, list) else UNRESOLVED


def _resolve_runtime_member_assign_target(expr: Any, state: RuntimeState) -> Any:
    path = _runtime_member_path(expr)
    if path is None:
        return UNRESOLVED
    root_name, members = path
    if len(members) < 2 or members[0] != "result":
        return UNRESOLVED
    root = _resolve_runtime_identifier(root_name, state)
    if root is UNRESOLVED or not isinstance(root, dict):
        return UNRESOLVED
    if root.get("kind") not in {"data_ref", "data_group_ref"}:
        return UNRESOLVED
    current = root
    for member in members[:-1]:
        next_value = current.get(member)
        if next_value is None:
            current[member] = {}
            next_value = current[member]
        if not isinstance(next_value, dict):
            return UNRESOLVED
        current = next_value
    return current, members[-1]


def _runtime_member_path(expr: Any) -> tuple[str, list[str]] | None:
    if not isinstance(expr, dict):
        return None
    members: list[str] = []
    current = expr
    while isinstance(current, dict) and current.get("kind") == "IRMember":
        member = current.get("member")
        if not isinstance(member, str):
            return None
        members.append(member)
        current = current.get("base")
    if not isinstance(current, dict) or current.get("kind") != "IRIdentifier":
        return None
    name = current.get("name")
    if not isinstance(name, str):
        return None
    members.reverse()
    return name, members


def _resolve_runtime_mutable_path(expr: Any, state: RuntimeState) -> Any:
    if not isinstance(expr, dict):
        return UNRESOLVED
    kind = expr.get("kind")
    if kind == "IRIdentifier":
        return _resolve_runtime_identifier(expr.get("name"), state)
    if kind != "IRMember":
        return UNRESOLVED
    base = _resolve_runtime_mutable_path(expr.get("base"), state)
    if base is UNRESOLVED or not isinstance(base, dict):
        return UNRESOLVED
    member = expr.get("member")
    if not isinstance(member, str):
        return UNRESOLVED
    current = base.get(member)
    if current is None:
        base[member] = {}
        current = base[member]
    return current if isinstance(current, dict) else UNRESOLVED


def _eval_runtime_binary(expr: dict[str, Any], state: RuntimeState) -> Any:
    op = expr.get("op")
    left = _eval_runtime_expr(expr.get("left"), state)
    right = _eval_runtime_expr(expr.get("right"), state)
    if left is UNRESOLVED or right is UNRESOLVED:
        return UNRESOLVED
    if op == "and":
        return bool(left) and bool(right)
    if op == "or":
        return bool(left) or bool(right)
    if op in {"==", "!=", "<", ">", "<=", ">="}:
        left_cmp, right_cmp = _runtime_comparable_pair(left, right)
        if left_cmp is UNRESOLVED or right_cmp is UNRESOLVED:
            return UNRESOLVED
        try:
            if op == "==":
                return left_cmp == right_cmp
            if op == "!=":
                return left_cmp != right_cmp
            if op == "<":
                return left_cmp < right_cmp
            if op == ">":
                return left_cmp > right_cmp
            if op == "<=":
                return left_cmp <= right_cmp
            return left_cmp >= right_cmp
        except TypeError:
            return UNRESOLVED
    quantity_result = _eval_runtime_quantity_binary(op=op, left=left, right=right)
    if quantity_result is not UNRESOLVED:
        return quantity_result
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return UNRESOLVED
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        if right == 0:
            return UNRESOLVED
        return left / right
    return UNRESOLVED


def _runtime_comparable_pair(left: Any, right: Any) -> tuple[Any, Any]:
    if isinstance(left, tuple) and isinstance(right, tuple):
        if len(left) == 2 and len(right) == 2 and left[1] == right[1]:
            return left[0], right[0]
        return UNRESOLVED, UNRESOLVED
    if isinstance(left, tuple) or isinstance(right, tuple):
        return UNRESOLVED, UNRESOLVED
    return left, right


def _eval_runtime_quantity_binary(*, op: Any, left: Any, right: Any) -> Any:
    if not isinstance(left, tuple) or not isinstance(right, tuple):
        return UNRESOLVED
    if len(left) != 2 or len(right) != 2:
        return UNRESOLVED
    left_value, left_unit = left
    right_value, right_unit = right
    if left_unit != right_unit:
        return UNRESOLVED
    if not isinstance(left_value, (int, float)) or not isinstance(right_value, (int, float)):
        return UNRESOLVED
    if op == "+":
        return (left_value + right_value, left_unit)
    if op == "-":
        return (left_value - right_value, left_unit)
    return UNRESOLVED


def _runtime_bound_value(value: Any, state: RuntimeState) -> Any:
    if isinstance(value, dict):
        kind = value.get("kind")
        if kind == "IRQuantity":
            raw = value.get("value")
            unit = value.get("unit")
            if isinstance(raw, (int, float)) and isinstance(unit, str):
                return (float(raw), unit)
            return UNRESOLVED
        if not isinstance(kind, str) or not kind.startswith("IR"):
            return value
        return _eval_runtime_expr(value, state)
    return value


def _runtime_value_to_serialized(value: Any) -> Any:
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], (int, float)) and isinstance(value[1], str):
        return {"kind": "IRQuantity", "value": float(value[0]), "unit": value[1]}
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _runtime_deep_serialize(value: Any) -> Any:
    if isinstance(value, list):
        return [_runtime_deep_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _runtime_deep_serialize(item) for key, item in value.items()}
    return _runtime_value_to_serialized(value)


def _runtime_protocol_output_serialize(value: Any) -> Any:
    if isinstance(value, list):
        return [_runtime_protocol_output_serialize(item) for item in value]
    if isinstance(value, dict):
        if value.get("kind") == "container_group_ref":
            return {
                "kind": "container_group_ref",
                "member_count": value.get("member_count", 0),
                "members": _runtime_protocol_output_serialize(value.get("members", [])),
            }
        if value.get("kind") == "container_ref":
            public_keys = {
                "kind",
                "id",
                "volume_uL",
                "mass_mg",
                "count_cells",
                "component_quantities",
                "material_relationships",
                "container_kind",
                "label",
                "barcode",
            }
            return {
                key: _runtime_protocol_output_serialize(item)
                for key, item in value.items()
                if key in public_keys
            }
        return {key: _runtime_protocol_output_serialize(item) for key, item in value.items()}
    return _runtime_value_to_serialized(value)


def _resolve_step_runtime_args(step: PlanStep, state: RuntimeState) -> PlanStep:
    return PlanStep(
        step_id=step.step_id,
        op=step.op,
        args=_resolve_runtime_arg_value(step.args, state),
        deps=list(step.deps),
        gate=step.gate,
        span=step.span,
    )


def _resolve_runtime_arg_value(value: Any, state: RuntimeState) -> Any:
    if isinstance(value, dict):
        kind = value.get("kind")
        if isinstance(kind, str) and kind == "IRIdentifier":
            name = value.get("name")
            local_bindings = state.artifacts.get("local_bindings", {})
            if isinstance(name, str) and isinstance(local_bindings, dict) and name in local_bindings:
                return local_bindings[name]
        if isinstance(kind, str) and kind in {"IRBinary", "IRUnary"}:
            evaluated = _eval_runtime_expr(value, state)
            if evaluated is not UNRESOLVED:
                return _runtime_value_to_serialized(evaluated)
        return {key: _resolve_runtime_arg_value(item, state) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_runtime_arg_value(item, state) for item in value]
    return value


def _resolve_runtime_material_output_value(material_state: Any, expr: Any) -> dict[str, Any] | None:
    group_value = _container_group_ref_payload(material_state, expr)
    if group_value is not None:
        return group_value
    return _resolve_runtime_material_value(material_state, expr)


def _resolve_runtime_material_value(material_state: Any, expr: Any) -> dict[str, Any] | None:
    container_id = _resolve_runtime_ref(material_state, expr)
    if not isinstance(container_id, str):
        return None
    return _container_ref_payload(material_state, container_id)


def _container_ref_payload(material_state: Any, container_id: str) -> dict[str, Any] | None:
    if not isinstance(material_state, dict):
        return None
    containers = material_state.get("containers")
    if not isinstance(containers, dict):
        return None
    raw = containers.get(container_id)
    if not isinstance(raw, dict):
        return None
    metadata = raw.get("metadata")
    metadata_out = deepcopy(metadata) if isinstance(metadata, dict) else {}
    components = raw.get("components")
    component_map: dict[str, Any] = {}
    if isinstance(components, dict):
        for name, amount in components.items():
            if isinstance(amount, (int, float)):
                component_map[str(name)] = round(float(amount), 6)
    raw_quantities = raw.get("component_quantities")
    component_quantities: dict[str, Any] = {}
    count_cells = 0.0
    if isinstance(raw_quantities, dict):
        for name, quantity in raw_quantities.items():
            if not isinstance(quantity, dict):
                continue
            record = deepcopy(quantity)
            value = record.get("value")
            if isinstance(value, (int, float)):
                record["value"] = round(float(value), 6)
                if record.get("dimension") == "count" and record.get("unit") == "cells":
                    count_cells += float(value)
            component_quantities[str(name)] = record
    payload: dict[str, Any] = {
        "kind": "container_ref",
        "id": container_id,
        "volume_uL": round(float(raw.get("volume_uL", 0.0)), 6),
        "mass_mg": round(float(raw.get("mass_mg", 0.0)), 6),
        "components": component_map,
        "metadata": metadata_out,
    }
    if count_cells > 0.0:
        payload["component_quantities"] = component_quantities
        payload["count_cells"] = round(count_cells, 6)
        relationships = raw.get("material_relationships")
        if isinstance(relationships, list):
            payload["material_relationships"] = deepcopy(relationships)
    container_kind = metadata_out.get("kind")
    if isinstance(container_kind, str):
        payload["container_kind"] = container_kind
    label = metadata_out.get("label")
    if isinstance(label, str):
        payload["label"] = label
    barcode = metadata_out.get("barcode")
    if isinstance(barcode, str):
        payload["barcode"] = barcode
    return payload


def _container_group_ref_payload(material_state: Any, expr: Any) -> dict[str, Any] | None:
    container_ids = _resolve_runtime_ref_group_ids(material_state, expr)
    if container_ids is None:
        return None
    members: list[dict[str, Any]] = []
    for container_id in container_ids:
        payload = _container_ref_payload(material_state, container_id)
        if payload is None:
            return None
        members.append(payload)
    return {
        "kind": "container_group_ref",
        "member_count": len(members),
        "members": members,
    }


def _merge_result_payloads(*parts: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for part in parts:
        if not isinstance(part, dict):
            continue
        for key, value in part.items():
            merged[key] = value
    return merged


def _schema_result_payload(schema_ref: Any) -> dict[str, Any]:
    if not isinstance(schema_ref, dict):
        return {}
    if schema_ref.get("kind") != "data_schema_ref":
        return {}
    fields = schema_ref.get("fields")
    if not isinstance(fields, list):
        return {}
    payload: dict[str, Any] = {}
    for field in fields:
        if isinstance(field, str):
            payload[field] = None
    return payload


def _resolve_runtime_ref(material_state: Any, value: Any) -> str | None:
    if not isinstance(material_state, dict) or not isinstance(value, dict):
        return None
    containers = material_state.get("containers")
    if not isinstance(containers, dict):
        return None

    kind = value.get("kind")
    if kind == "IRIdentifier":
        name = value.get("name")
        if not isinstance(name, str):
            return None
        bindings = material_state.get("bindings")
        if isinstance(bindings, dict):
            bound = bindings.get(name)
            if isinstance(bound, str) and bound in containers:
                return bound
        if name in containers:
            return name
        return None

    if kind != "IRIndex":
        return None

    base = value.get("base")
    index = value.get("index")
    if not isinstance(base, dict) or base.get("kind") != "IRIdentifier":
        return None
    group_name = base.get("name")
    if not isinstance(group_name, str):
        return None
    slot = _runtime_static_index_key(index)
    if slot is None:
        return None
    indexed_bindings = material_state.get("indexed_bindings")
    if not isinstance(indexed_bindings, dict):
        return None
    group = indexed_bindings.get(group_name)
    if not isinstance(group, dict):
        return None
    bound = group.get(slot)
    if isinstance(bound, str) and bound in containers:
        return bound
    return None


def _resolve_runtime_ref_group(material_state: Any, value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, dict) or value.get("kind") != "IRGroup":
        return None
    elements = value.get("elements")
    if not isinstance(elements, list):
        return None
    resolved: list[dict[str, Any]] = []
    for item in elements:
        resolved_item = _resolve_runtime_ref(material_state, item)
        if resolved_item is None:
            return None
        resolved.append({"sample_ref": item, "resolved_sample": resolved_item})
    return resolved


def _resolve_runtime_ref_group_ids(material_state: Any, value: Any) -> list[str] | None:
    if not isinstance(material_state, dict) or not isinstance(value, dict):
        return None
    containers = material_state.get("containers")
    if not isinstance(containers, dict):
        return None

    if value.get("kind") == "IRGroup":
        elements = value.get("elements")
        if not isinstance(elements, list):
            return None
        resolved: list[str] = []
        for item in elements:
            container_id = _resolve_runtime_ref(material_state, item)
            if not isinstance(container_id, str):
                return None
            resolved.append(container_id)
        return resolved

    if value.get("kind") != "IRIdentifier":
        return None
    group_name = value.get("name")
    if not isinstance(group_name, str):
        return None
    indexed_bindings = material_state.get("indexed_bindings")
    if not isinstance(indexed_bindings, dict):
        return None
    group = indexed_bindings.get(group_name)
    if not isinstance(group, dict):
        return None
    resolved: list[str] = []
    for slot in sorted(group, key=_runtime_index_slot_sort_key):
        container_id = group.get(slot)
        if not isinstance(container_id, str) or container_id not in containers:
            return None
        resolved.append(container_id)
    return resolved


def _runtime_index_slot_sort_key(slot: Any) -> tuple[int, int | str]:
    if isinstance(slot, str) and slot.isdigit():
        return (0, int(slot))
    return (1, str(slot))


def _runtime_static_index_key(value: Any) -> str | None:
    if not isinstance(value, dict) or value.get("kind") != "IRQuantity":
        return None
    raw = value.get("value")
    unit = value.get("unit")
    if unit is not None or not isinstance(raw, (int, float)) or float(raw) < 0 or not float(raw).is_integer():
        return None
    return str(int(raw))
