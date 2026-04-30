"""Observation artifact recording for runtime steps."""

from __future__ import annotations

from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.session import RuntimeSession


_OBSERVATION_OPS = {"img", "ecp", "phy"}


class ObservationRecorder:
    def extract_binding_overwrite_events(self, material_delta: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not isinstance(material_delta, dict):
            return []
        raw_events = material_delta.get("binding_events")
        if not isinstance(raw_events, list):
            return []
        out: list[dict[str, Any]] = []
        for item in raw_events:
            if isinstance(item, dict) and item.get("event") == "BINDING_OVERWRITTEN":
                out.append(item)
        return out

    def record(
        self,
        step: PlanStep,
        session: RuntimeSession,
        *,
        driver_code: str,
        driver_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        if step.op not in _OBSERVATION_OPS:
            return None

        bind_name = step.args.get("bind")
        bind_name = bind_name if isinstance(bind_name, str) else None
        save_raw = _coerce_bool(step.args.get("save_raw"))
        sample_arg = step.args.get("sample")
        sample_group = session.value_resolver.resolve_runtime_ref_group(
            session.state.artifacts.get("material_state"),
            sample_arg,
        )
        if sample_group is None:
            data_id = f"{step.step_id}::data"
            raw_meta = self._record_raw_observation_meta(
                session=session,
                observation_id=data_id,
                step=step,
                driver_code=driver_code,
                save_raw=save_raw,
            )
            data_record = self._make_observation_record(
                session=session,
                observation_id=data_id,
                family=step.op,
                step=step,
                binding=bind_name,
                sample_ref=sample_arg,
                resolved_sample=session.value_resolver.resolve_runtime_ref(
                    session.state.artifacts.get("material_state"),
                    sample_arg,
                ),
                driver_payload=driver_payload,
                driver_code=driver_code,
                raw_meta=raw_meta,
            )
            data_objects = session.state.artifacts.setdefault("data_objects", {})
            if isinstance(data_objects, dict):
                data_objects[data_id] = data_record
            if bind_name is not None:
                data_bindings = session.state.artifacts.setdefault("data_bindings", {})
                if isinstance(data_bindings, dict):
                    data_bindings[bind_name] = data_id
            return {
                "op": step.op,
                "data_id": data_id,
                "observation_id": data_id,
                "binding": bind_name,
                "save_raw": save_raw,
                "raw_artifact": raw_meta,
            }

        group_id = f"{step.step_id}::data_group"
        item_ids: list[str] = []
        raw_artifacts: list[dict[str, Any]] = []
        data_objects = session.state.artifacts.setdefault("data_objects", {})
        for idx, item in enumerate(sample_group):
            data_id = f"{step.step_id}::data::{idx}"
            raw_meta = self._record_raw_observation_meta(
                session=session,
                observation_id=data_id,
                step=step,
                driver_code=driver_code,
                save_raw=save_raw,
            )
            data_record = self._make_observation_record(
                session=session,
                observation_id=data_id,
                family=step.op,
                step=step,
                binding=None,
                sample_ref=item["sample_ref"],
                resolved_sample=item["resolved_sample"],
                driver_payload=driver_payload,
                driver_code=driver_code,
                raw_meta=raw_meta,
            )
            if isinstance(data_objects, dict):
                data_objects[data_id] = data_record
            item_ids.append(data_id)
            if raw_meta is not None:
                raw_artifacts.append(raw_meta)

        group_record = {
            "kind": "data_group_ref",
            "data_group_id": group_id,
            "observation_group_id": group_id,
            "data_kind": "observation",
            "family": step.op,
            "step_id": step.step_id,
            "binding": bind_name,
            "sample_group": sample_arg,
            "resolved_samples": [item["resolved_sample"] for item in sample_group],
            "item_ids": item_ids,
            "observation_ids": item_ids,
            "contract_kind": _readout_contract_kind(step.op, step.args),
            "program_kind": _program_kind(step.args.get("program")),
            "status": "ok",
            "gate": step.gate,
        }
        data_groups = session.state.artifacts.setdefault("data_groups", {})
        if isinstance(data_groups, dict):
            data_groups[group_id] = group_record
        if bind_name is not None:
            data_group_bindings = session.state.artifacts.setdefault("data_group_bindings", {})
            if isinstance(data_group_bindings, dict):
                data_group_bindings[bind_name] = group_id
            indexed_group_bindings = session.state.artifacts.setdefault("data_group_indexed_bindings", {})
            if isinstance(indexed_group_bindings, dict):
                indexed_group_bindings[bind_name] = {str(idx): data_id for idx, data_id in enumerate(item_ids)}

        return {
            "op": step.op,
            "data_group_id": group_id,
            "observation_group_id": group_id,
            "binding": bind_name,
            "save_raw": save_raw,
            "item_ids": item_ids,
            "observation_ids": item_ids,
            "raw_artifacts": raw_artifacts,
        }

    def _make_observation_record(
        self,
        *,
        session: RuntimeSession,
        observation_id: str,
        family: str,
        step: PlanStep,
        binding: str | None,
        sample_ref: Any,
        resolved_sample: str | None,
        driver_payload: dict[str, Any],
        driver_code: str,
        raw_meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        export_refs = self._record_observation_export_refs(
            session=session,
            observation_id=observation_id,
            family=family,
            program=step.args.get("program"),
            driver_code=driver_code,
            raw_meta=raw_meta,
        )
        observation = {
            "kind": "data_ref",
            "data_id": observation_id,
            "observation_id": observation_id,
            "data_kind": "observation",
            "family": family,
            "op": family,
            "step_id": step.step_id,
            "binding": binding,
            "subject_ref": sample_ref,
            "sample_ref": sample_ref,
            "sample": sample_ref,
            "resolved_sample": resolved_sample,
            "contract_kind": _readout_contract_kind(step.op, step.args),
            "program_kind": _program_kind(step.args.get("program")),
            "program": step.args.get("program"),
            "status": "ok",
            "result": _merge_observation_result_payload(
                base=_merge_result_payloads(
                    _observation_result_payload(family=family, args=step.args),
                    _schema_result_payload(step.args.get("schema_ref")),
                ),
                driver_payload=driver_payload,
            ),
            "save_raw": _coerce_bool(step.args.get("save_raw")),
            "driver_payload": driver_payload,
            "gate": step.gate,
        }
        if raw_meta is not None:
            observation["raw_artifact"] = raw_meta
        if export_refs is not None:
            observation["export_refs"] = export_refs
        return observation

    def _record_raw_observation_meta(
        self,
        *,
        session: RuntimeSession,
        observation_id: str,
        step: PlanStep,
        driver_code: str,
        save_raw: bool,
    ) -> dict[str, Any] | None:
        if not save_raw:
            return None
        raw_meta = {
            "artifact_id": f"{observation_id}::raw",
            "step_id": step.step_id,
            "op": step.op,
            "driver_code": driver_code,
        }
        session.state.artifacts.setdefault("raw_data", {})[observation_id] = raw_meta
        return raw_meta

    def _record_observation_export_refs(
        self,
        *,
        session: RuntimeSession,
        observation_id: str,
        family: str,
        program: Any,
        driver_code: str,
        raw_meta: dict[str, Any] | None,
    ) -> dict[str, dict[str, Any]] | None:
        program_kind = _program_kind(program)
        export_ref = {
            "export_id": f"{observation_id}::driver_profile",
            "kind": family,
            "format": "json",
            "profile": f"driver:{driver_code}" if driver_code else "driver:unknown",
        }
        if raw_meta is not None:
            artifact_id = raw_meta.get("artifact_id")
            if isinstance(artifact_id, str):
                export_ref["artifact_id"] = artifact_id
        if program_kind is not None:
            export_ref["program_kind"] = program_kind
        export_refs = {"driver_profile": export_ref}
        data_exports = session.state.artifacts.setdefault("data_exports", {})
        if isinstance(data_exports, dict):
            data_exports[observation_id] = export_refs
        return export_refs


def _readout_contract_kind(family: str, args: dict[str, Any]) -> str | None:
    quantity = args.get("quantity") if isinstance(args, dict) else None
    quantity_scalar = _expr_scalar(quantity)
    if quantity_scalar is not None:
        return quantity_scalar
    return None


def _program_kind(program: Any) -> str | None:
    if isinstance(program, dict):
        kind = program.get("kind")
        if kind == "IRCall":
            name = program.get("name")
            if isinstance(name, str):
                args = program.get("args")
                if isinstance(args, list):
                    mode_or_quantity = _named_arg_scalar(args, {"mode", "quantity"})
                    if mode_or_quantity is not None:
                        return f"{name}:{mode_or_quantity}"
                return name
    return None


def _named_arg_scalar(args: list[Any], names: set[str]) -> str | None:
    for arg in args:
        if not isinstance(arg, dict):
            continue
        if arg.get("name") not in names:
            continue
        value = arg.get("value")
        if isinstance(value, dict):
            raw = value.get("value")
            if isinstance(raw, (str, int, float, bool)):
                return str(raw)
    return None


def _expr_scalar(value: Any) -> str | None:
    if isinstance(value, dict):
        kind = value.get("kind")
        if kind == "IRIdentifier":
            name = value.get("name")
            if isinstance(name, str):
                return name
        raw = value.get("value")
        if isinstance(raw, (str, int, float, bool)):
            return str(raw)
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def _observation_result_payload(*, family: str, args: dict[str, Any]) -> dict[str, Any]:
    contract_kind = _readout_contract_kind(family, args)
    if family == "img":
        return _image_result_payload(contract_kind)
    if family == "ecp":
        return _ecp_result_payload(contract_kind)
    if family == "phy":
        return _phy_result_payload(contract_kind)
    return {}


def _merge_observation_result_payload(*, base: dict[str, Any], driver_payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    raw_result = driver_payload.get("result")
    if not isinstance(raw_result, dict):
        return result
    for key, value in raw_result.items():
        if key in result:
            result[key] = value
    return result


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


def _merge_result_payloads(*parts: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for part in parts:
        if not isinstance(part, dict):
            continue
        for key, value in part.items():
            merged[key] = value
    return merged


def _image_result_payload(kind: str | None) -> dict[str, Any]:
    if kind in {"fluorescence", "uv_absorbance", "colorimetric"}:
        return {"signal": None, "channel": None}
    if kind == "optical_fluor":
        return {"signal": None, "channel": None, "background": None}
    if kind == "gel_readout":
        return {"band_present": None, "band_count": None, "lane_intensity": None}
    if kind == "microscopy":
        return {"focus_score": None, "cell_count": None, "field_quality": None}
    return {"signal": None, "channel": None}


def _ecp_result_payload(kind: str | None) -> dict[str, Any]:
    if kind == "ph":
        return {"ph": None}
    if kind == "conductivity":
        return {"conductivity": None}
    if kind == "dissolved_oxygen":
        return {"dissolved_oxygen": None}
    if kind == "orp":
        return {"orp": None}
    if kind == "ion_selective":
        return {"ion_value": None, "ion_name": None}
    if kind is not None:
        return {kind: None}
    return {}


def _phy_result_payload(kind: str | None) -> dict[str, Any]:
    if kind == "temperature":
        return {"temperature": None}
    if kind == "pressure":
        return {"pressure": None}
    if kind == "flow_rate":
        return {"flow_rate": None}
    if kind == "mass":
        return {"mass": None}
    if kind == "volume":
        return {"volume": None}
    if kind == "humidity":
        return {"humidity": None}
    if kind == "current":
        return {"current": None}
    return {}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict) and value.get("kind") == "IRBoolean":
        raw = value.get("value")
        if isinstance(raw, bool):
            return raw
    return False
