"""Normalize human driver backend output into runtime payloads."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class HumanReceiptNormalizer:
    def normalize(self, *, base_payload: dict[str, Any], emitted_payload: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(base_payload)
        for key, value in emitted_payload.items():
            merged[key] = deepcopy(value)
        merged.setdefault("receipt", {"status": "acknowledged"})
        return merged
