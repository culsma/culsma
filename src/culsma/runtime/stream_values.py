"""Observation value construction preserves seed data and vocabulary identity."""
from __future__ import annotations
from copy import deepcopy
from typing import Any, TYPE_CHECKING
from culsma.domains.stream import OBSERVATION_UNITS, ObservationUnitBase, ObservationUnit
if TYPE_CHECKING:
    from culsma.runtime.state import RuntimeState


class StreamValueBuilder:
    @staticmethod
    def build(kwargs, state, *, target_name=None):
        source_ref = kwargs.get("sample")
        if not isinstance(source_ref, str):
            source_ref = None
        unit_value = kwargs.get("unit")
        typed_unit = isinstance(unit_value, ObservationUnitBase)
        unit_kind = unit_value.value if typed_unit else unit_value
        if not isinstance(unit_kind, str):
            unit_kind = None
        panel_ref = kwargs.get("panel")
        stream = {
            "kind": "unit_stream_ref",
            "id": target_name or "unit_stream",
            "source_ref": source_ref,
            "unit_kind": unit_kind,
            "panel_ref": panel_ref,
            "items": StreamValueBuilder.seed_items(
                state=state,
                stream_name=target_name,
                source_ref=source_ref,
                unit_kind=unit_kind,
            ),
        }
        if typed_unit and type(unit_value) is not ObservationUnit:
            stream['unit_type'] = OBSERVATION_UNITS.current.encode(unit_value)
            for item in stream['items']:
                if item.get('unit_kind') == unit_kind:
                    item['unit_type'] = dict(stream['unit_type'])
        return stream

    @staticmethod
    def seed_items(
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
            normalized = StreamValueBuilder.normalize_seed(
                item=item,
                ordinal=idx,
                stream_name=stream_name,
                source_ref=source_ref,
                unit_kind=unit_kind,
            )
            if normalized is not None:
                out.append(normalized)
        return out


    @staticmethod
    def normalize_seed(
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
