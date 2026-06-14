"""Container contents-state runtime helpers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.diagnostics import diagnostic_result
from culsma.runtime.material.ledger import move_explicit
from culsma.runtime.material.refs import ref_display, resolve_structured_ref
from culsma.runtime.material.result import MaterialUpdateResult


@dataclass(frozen=True)
class ContentsPartSelection:
    source_id: str
    slot: str
    part: dict[str, Any]
    state_record: dict[str, Any]


@dataclass(frozen=True)
class ContentsStateImpact:
    action: str
    reason: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class ContentsStateSummary:
    source_id: str
    kind: str
    program_kind: str
    slots: list[str]


def is_container_contents_index(value: Any) -> bool:
    if not isinstance(value, dict) or value.get("kind") != "IRIndex":
        return False
    base = value.get("base")
    return isinstance(base, dict) and base.get("kind") == "IRMember" and base.get("member") == "contents"


def invalidate_contents_state(state: dict[str, Any], container_id: str, *, reason: str) -> None:
    contents_states = state.get("contents_states")
    if not isinstance(contents_states, dict):
        return
    record = contents_states.get(container_id)
    if not isinstance(record, dict):
        return
    record["valid"] = False
    record["invalid_reason"] = reason


def apply_target_addition_impact(
    *,
    step: PlanStep,
    state: dict[str, Any],
    target_id: str,
    moved_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    impact = _classify_target_addition(
        step=step,
        state=state,
        target_id=target_id,
        moved_snapshot=moved_snapshot,
    )
    action = impact.get("action")
    if action == "preserve_add_to_part":
        moved = deepcopy(moved_snapshot)
        if not isinstance(moved, dict):
            return {"action": "stale", "reason": "missing_material_snapshot"}
        part = impact.get("part")
        moved_uL = float(moved.get("volume_uL", 0.0))
        moved_mg = float(moved.get("mass_mg", 0.0))
        move_explicit(
            moved,
            part,
            moved_uL,
            moved_mg,
            component_ratio=1.0,
        )
        return {
            "action": "preserve_add_to_part",
            "slot": impact.get("slot"),
            "contract": impact.get("contract"),
        }
    if action == "stale":
        invalidate_contents_state(state, target_id, reason=str(impact.get("reason") or "material_transfer"))
    return {key: value for key, value in impact.items() if key != "part"}


def moved_snapshot_from_delta(source_before: Any, delta: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(source_before, dict):
        return None
    mode = delta.get("mode")
    source_volume = float(source_before.get("volume_uL", 0.0))
    source_mass = float(source_before.get("mass_mg", 0.0))
    if mode == "volume":
        moved_uL = float(delta.get("moved_uL", 0.0))
        ratio = 0.0 if source_volume == 0.0 else moved_uL / source_volume
        moved_mg = source_mass * ratio
    elif mode == "mass":
        moved_mg = float(delta.get("moved_mg", 0.0))
        ratio = 0.0 if source_mass == 0.0 else moved_mg / source_mass
        moved_uL = source_volume * ratio
    elif mode == "bridge_volume_to_mass":
        moved_uL = float(delta.get("requested_uL", 0.0))
        moved_mg = float(delta.get("converted_mg", 0.0))
        ratio = _best_effort_component_ratio(source_before, moved_uL=moved_uL, moved_mg=moved_mg)
    elif mode == "bridge_mass_to_volume":
        moved_uL = float(delta.get("converted_uL", 0.0))
        moved_mg = float(delta.get("requested_mg", 0.0))
        ratio = _best_effort_component_ratio(source_before, moved_uL=moved_uL, moved_mg=moved_mg)
    else:
        return None
    return moved_snapshot_from_explicit(source_before, moved_uL=moved_uL, moved_mg=moved_mg, ratio=ratio)


def moved_snapshot_from_explicit(
    source_before: dict[str, Any],
    *,
    moved_uL: float,
    moved_mg: float,
    ratio: float,
) -> dict[str, Any]:
    snapshot = {"volume_uL": 0.0, "mass_mg": 0.0, "components": {}, "metadata": {}}
    source_copy = deepcopy(source_before)
    move_explicit(source_copy, snapshot, moved_uL, moved_mg, component_ratio=ratio)
    return snapshot


def mark_contents_state_mixed(state: dict[str, Any], container_id: str, *, step_id: str) -> dict[str, Any]:
    contents_states = state.get("contents_states")
    if not isinstance(contents_states, dict):
        return {"action": "none", "reason": "no_contents_states"}
    record = contents_states.get(container_id)
    if not isinstance(record, dict) or record.get("valid") is False:
        return {"action": "none", "reason": "no_valid_contents_state"}
    previous_kind = record.get("kind")
    record["valid"] = False
    record["invalid_reason"] = "explicit_mixing"
    record["previous_kind"] = previous_kind
    record["kind"] = "mixed"
    record["mixed_by_step"] = step_id
    return {"action": "mixed", "reason": "explicit_mixing", "previous_kind": previous_kind}


class MaterialContentsStateManager:
    def resolve_indexed_part(
        self,
        *,
        step: PlanStep,
        state: dict[str, Any],
        contents_ref: dict[str, Any],
    ) -> ContentsPartSelection | MaterialUpdateResult:
        source_id = _resolve_contents_state_source_id(state, contents_ref)
        if source_id is None:
            return diagnostic_result(
                step,
                state,
                "MAT_BINDING_NOT_FOUND",
                f"Unknown container contents source '{ref_display(contents_ref)}'",
            )
        slot_key = _contents_state_slot_key(contents_ref)
        if slot_key is None:
            return diagnostic_result(step, state, "MAT_CONTENTS_STATE_INDEX_OUT_OF_RANGE", "container.contents index must be static")

        contents_states = _material_contents_states(state)
        record = contents_states.get(source_id)
        if not isinstance(record, dict) or record.get("valid") is False:
            return diagnostic_result(
                step,
                state,
                "MAT_CONTENTS_STATE_NOT_INDEXED",
                f"Container '{source_id}' has no active contents state",
            )
        parts = record.get("parts")
        part = parts.get(slot_key) if isinstance(parts, dict) else None
        if not isinstance(part, dict):
            return diagnostic_result(
                step,
                state,
                "MAT_CONTENTS_STATE_INDEX_OUT_OF_RANGE",
                f"Container '{source_id}' contents state has no slot {slot_key}",
            )
        return ContentsPartSelection(
            source_id=source_id,
            slot=slot_key,
            part=part,
            state_record=record,
        )

    def record_source_selection_impact(self, *, state: dict[str, Any], selection: ContentsPartSelection) -> dict[str, Any]:
        return {"action": "preserve_remove_from_part", "slot": selection.slot}

    def record_self_transfer_disturbance(self, *, state: dict[str, Any], selection: ContentsPartSelection) -> dict[str, Any]:
        invalidate_contents_state(state, selection.source_id, reason="contents_self_transfer")
        return {"action": "stale", "reason": "contents_self_transfer", "slot": selection.slot}

    def record_target_addition_impact(
        self,
        *,
        step: PlanStep,
        state: dict[str, Any],
        target_id: str,
        moved_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return apply_target_addition_impact(
            step=step,
            state=state,
            target_id=target_id,
            moved_snapshot=moved_snapshot,
        )

    def record_partitioned(
        self,
        *,
        state: dict[str, Any],
        source_id: str,
        source: dict[str, Any],
        parts: dict[str, dict[str, Any]],
        kind: str,
        producer_op: str,
        program_kind: str,
        slot_contract: Any,
        preservation_contract: dict[str, Any] | None,
        step_id: str,
    ) -> ContentsStateSummary:
        summary = record_partitioned_contents_state(
            state=state,
            source_id=source_id,
            source=source,
            parts=parts,
            kind=kind,
            producer_op=producer_op,
            program_kind=program_kind,
            slot_contract=slot_contract,
            preservation_contract=preservation_contract,
            step_id=step_id,
        )
        return ContentsStateSummary(
            source_id=str(summary["source"]),
            kind=str(summary["kind"]),
            program_kind=str(summary["program_kind"]),
            slots=list(summary["slots"]),
        )


def resolve_indexed_part(
    *,
    step: PlanStep,
    state: dict[str, Any],
    contents_ref: dict[str, Any],
) -> ContentsPartSelection | MaterialUpdateResult:
    return MaterialContentsStateManager().resolve_indexed_part(
        step=step,
        state=state,
        contents_ref=contents_ref,
    )


def record_source_selection_impact(*, state: dict[str, Any], selection: ContentsPartSelection) -> dict[str, Any]:
    return MaterialContentsStateManager().record_source_selection_impact(state=state, selection=selection)


def record_self_transfer_disturbance(*, state: dict[str, Any], selection: ContentsPartSelection) -> dict[str, Any]:
    return MaterialContentsStateManager().record_self_transfer_disturbance(state=state, selection=selection)


def record_target_addition_impact(
    *,
    step: PlanStep,
    state: dict[str, Any],
    target_id: str,
    moved_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    return MaterialContentsStateManager().record_target_addition_impact(
        step=step,
        state=state,
        target_id=target_id,
        moved_snapshot=moved_snapshot,
    )


def record_partitioned_contents_state(
    *,
    state: dict[str, Any],
    source_id: str,
    source: dict[str, Any],
    parts: dict[str, dict[str, Any]],
    kind: str,
    producer_op: str,
    program_kind: str,
    slot_contract: Any,
    preservation_contract: dict[str, Any] | None,
    step_id: str,
) -> dict[str, Any]:
    copied_parts = {slot: deepcopy(part) for slot, part in parts.items()}
    for slot_part in parts.values():
        if slot_part is source:
            continue
        residual_uL = float(slot_part.get("volume_uL", 0.0))
        residual_mg = float(slot_part.get("mass_mg", 0.0))
        if residual_uL or residual_mg:
            move_explicit(slot_part, source, residual_uL, residual_mg, component_ratio=1.0)
    contract = slot_contract if isinstance(slot_contract, dict) else {slot: f"slot_{slot}" for slot in copied_parts}
    record = {
        "kind": kind,
        "producer_op": producer_op,
        "program_kind": program_kind,
        "source": source_id,
        "slot_contract": dict(contract),
        "parts": copied_parts,
        "valid": True,
        "step_id": step_id,
    }
    if preservation_contract is not None:
        record["preservation_contract"] = dict(preservation_contract)
    contents_states = _material_contents_states(state)
    contents_states[source_id] = record
    return {
        "source": source_id,
        "kind": kind,
        "program_kind": program_kind,
        "slots": sorted(copied_parts),
    }


def remove_transient_containers(state: dict[str, Any], container_ids: list[str], *, preserve: str) -> None:
    containers = state.setdefault("containers", {})
    if not isinstance(containers, dict):
        return
    for container_id in container_ids:
        if container_id != preserve:
            containers.pop(container_id, None)


def _contents_index_source_expr(value: dict[str, Any]) -> Any:
    base = value.get("base")
    if not isinstance(base, dict):
        return None
    return base.get("base")


def _resolve_contents_state_source_id(state: dict[str, Any], value: dict[str, Any]) -> str | None:
    source_expr = _contents_index_source_expr(value)
    return resolve_structured_ref(state, source_expr, create_if_identifier=False)


def _contents_state_slot_key(value: dict[str, Any]) -> str | None:
    index = value.get("index")
    if isinstance(index, dict) and index.get("kind") == "IRQuantity":
        raw = index.get("value")
        unit = index.get("unit")
        if unit is None and isinstance(raw, (int, float)) and float(raw).is_integer():
            return str(int(raw))
    return None


def _material_contents_states(state: dict[str, Any]) -> dict[str, Any]:
    contents_states = state.setdefault("contents_states", {})
    if not isinstance(contents_states, dict):
        state["contents_states"] = {}
        contents_states = state["contents_states"]
    return contents_states


def _classify_target_addition(
    *,
    step: PlanStep,
    state: dict[str, Any],
    target_id: str,
    moved_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    contents_states = state.get("contents_states")
    if not isinstance(contents_states, dict):
        return {"action": "none", "reason": "no_contents_states"}
    record = contents_states.get(target_id)
    if not isinstance(record, dict) or record.get("valid") is False:
        return {"action": "none", "reason": "no_valid_target_contents_state"}
    if moved_snapshot is None:
        return {"action": "stale", "reason": "missing_material_snapshot"}
    contract = record.get("preservation_contract")
    if not _preservation_contract_satisfied(step=step, contract=contract):
        return {"action": "stale", "reason": "preservation_contract_not_satisfied"}
    parts = record.get("parts")
    slot_key = contract.get("default_incoming_slot") if isinstance(contract, dict) else None
    part = parts.get(slot_key) if isinstance(parts, dict) and isinstance(slot_key, str) else None
    if not isinstance(part, dict):
        return {"action": "stale", "reason": "preservation_contract_missing_incoming_slot"}
    return {
        "action": "preserve_add_to_part",
        "slot": slot_key,
        "part": part,
        "contract": contract.get("kind") if isinstance(contract, dict) else None,
    }


def _preservation_contract_satisfied(
    *,
    step: PlanStep,
    contract: Any,
) -> bool:
    if not isinstance(contract, dict):
        return False
    if contract.get("kind") != "field_retention":
        return False
    required_field = contract.get("field")
    if not isinstance(required_field, str) or not _step_gate_has_env_value(step, "field", required_field):
        return False
    return True


def _step_gate_has_env_value(step: PlanStep, key: str, expected: str) -> bool:
    gate = step.gate
    if not isinstance(gate, dict):
        return False
    layers = gate.get("env_layers")
    if isinstance(layers, list):
        return any(
            isinstance(layer, dict) and _env_payload_has_value(layer.get("env"), key, expected)
            for layer in layers
        )
    return _env_payload_has_value(gate.get("env"), key, expected)


def _env_payload_has_value(env: Any, key: str, expected: str) -> bool:
    if not isinstance(env, dict):
        return False
    value = env.get(key)
    if isinstance(value, dict):
        return value.get("name") == expected or value.get("value") == expected
    return value == expected


def _best_effort_component_ratio(source: dict[str, Any], *, moved_uL: float, moved_mg: float) -> float:
    source_mass = float(source.get("mass_mg", 0.0))
    if source_mass > 0.0:
        return moved_mg / source_mass
    source_volume = float(source.get("volume_uL", 0.0))
    if source_volume > 0.0:
        return moved_uL / source_volume
    return 0.0
