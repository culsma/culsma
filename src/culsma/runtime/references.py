"""Protocol-reference reuse helpers for runtime scheduling."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.session import RuntimeSession
from culsma.runtime.state import RuntimeState


@dataclass(frozen=True)
class RefGroup:
    ref_call_id: str
    ref_protocol: str
    call_path: str
    ref_policy: str
    step_ids: list[str]
    subtree_step_ids: list[str]
    first_step_id: str
    last_step_id: str


@dataclass(frozen=True)
class RefDecision:
    action: str
    policy: str
    cache_key: str
    input_signature: str
    reason: str


class RefReuseDecider:
    def build_groups(self, steps: list[PlanStep]) -> dict[str, RefGroup]:
        base: dict[str, dict[str, Any]] = {}
        for step in steps:
            ref_meta = self.extract_ref_meta(step)
            if ref_meta is None:
                continue
            ref_call_id = str(ref_meta.get("ref_call_id") or "")
            if not ref_call_id:
                continue
            call_path = str(ref_meta.get("call_path") or ref_call_id)
            record = base.setdefault(
                ref_call_id,
                {
                    "ref_protocol": str(ref_meta.get("ref_protocol") or ""),
                    "call_path": call_path,
                    "ref_policy": str(ref_meta.get("ref_policy") or "auto"),
                    "step_ids": [],
                },
            )
            record["step_ids"].append(step.step_id)

        if not base:
            return {}

        group_by_call: dict[str, RefGroup] = {}
        for ref_call_id, data in base.items():
            call_path = str(data["call_path"])
            subtree_step_ids: list[str] = []
            for step in steps:
                ref_meta = self.extract_ref_meta(step)
                if ref_meta is None:
                    continue
                candidate_call_id = str(ref_meta.get("ref_call_id") or "")
                if candidate_call_id == ref_call_id or candidate_call_id.startswith(f"{ref_call_id}::"):
                    subtree_step_ids.append(step.step_id)
            if not subtree_step_ids:
                subtree_step_ids = list(data["step_ids"])
            group_by_call[ref_call_id] = RefGroup(
                ref_call_id=ref_call_id,
                ref_protocol=str(data["ref_protocol"]),
                call_path=call_path,
                ref_policy=str(data["ref_policy"]),
                step_ids=list(data["step_ids"]),
                subtree_step_ids=subtree_step_ids,
                first_step_id=str(data["step_ids"][0]),
                last_step_id=subtree_step_ids[-1],
            )
        return group_by_call

    def ensure_cache(self, state: RuntimeState) -> dict[str, Any]:
        existing = state.artifacts.get("ref_cache")
        if isinstance(existing, dict):
            return existing
        cache: dict[str, Any] = {}
        state.artifacts["ref_cache"] = cache
        return cache

    def group_for_step(self, step_id: str, session: RuntimeSession) -> RefGroup | None:
        return session.ref_groups_by_first.get(step_id)

    def extract_ref_meta(self, step: PlanStep) -> dict[str, Any] | None:
        if not isinstance(step.gate, dict):
            return None
        ref_meta = step.gate.get("ref_meta")
        if isinstance(ref_meta, dict):
            return ref_meta
        return None

    def decide(self, group: RefGroup, session: RuntimeSession) -> RefDecision:
        cache_key = self._compute_cache_key(group.ref_protocol, group.call_path)
        input_signature = self._compute_ref_input_signature(group=group, step_by_id=session.step_by_id)
        policy = group.ref_policy if group.ref_policy in {"auto", "force_reuse", "force_rerun"} else "auto"

        cache_entry = session.ref_cache.get(cache_key)
        if policy == "force_rerun":
            return RefDecision("rerun", policy, cache_key, input_signature, "policy_force_rerun")

        if policy == "force_reuse":
            if isinstance(cache_entry, dict):
                return RefDecision("reuse", policy, cache_key, input_signature, "policy_force_reuse")
            return RefDecision("rerun", policy, cache_key, input_signature, "forced_reuse_cache_miss")

        if isinstance(cache_entry, dict) and cache_entry.get("input_signature") == input_signature:
            return RefDecision("reuse", policy, cache_key, input_signature, "signature_match")

        reason = "cache_miss"
        if isinstance(cache_entry, dict):
            reason = "signature_changed"
        return RefDecision("rerun", policy, cache_key, input_signature, reason)

    def mark_reused(self, group: RefGroup, session: RuntimeSession) -> None:
        for step_id in group.subtree_step_ids:
            if session.state.step_status.get(step_id) != "pending":
                continue
            step = session.step_by_id.get(step_id)
            if step is None:
                continue
            session.state.step_status[step_id] = "completed"
            session.state.history.append(
                {
                    "step_id": step_id,
                    "status": "completed",
                    "driver_code": "REF_REUSED",
                    "reason": "ref_reuse",
                    "ref_call_id": group.ref_call_id,
                }
            )
            session.event_log.emit(
                "STEP_COMPLETED",
                step_id,
                payload={
                    "driver_code": "REF_REUSED",
                    "driver_payload": {},
                    "ref_decision": "reuse",
                    "ref_call_id": group.ref_call_id,
                    "call_path": group.call_path,
                },
                span=step.span,
            )

    def cache_update_payload(self, group: RefGroup, decision: RefDecision) -> dict[str, Any]:
        return {
            "cache_key": decision.cache_key,
            "input_signature": decision.input_signature,
            "ref_protocol": group.ref_protocol,
            "call_path": group.call_path,
            "ref_call_id": group.ref_call_id,
            "step_ids": list(group.subtree_step_ids),
        }

    def _compute_cache_key(self, ref_protocol: str, call_path: str) -> str:
        payload = {"ref_protocol": ref_protocol, "call_path": call_path}
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _compute_ref_input_signature(self, group: RefGroup, step_by_id: dict[str, PlanStep]) -> str:
        payload_steps: list[dict[str, Any]] = []
        for step_id in group.subtree_step_ids:
            step = step_by_id.get(step_id)
            if step is None:
                continue
            payload_steps.append({"op": step.op, "args": step.args})
        payload = {
            "ref_protocol": group.ref_protocol,
            "call_path": group.call_path,
            "steps": payload_steps,
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
