"""Shared data models for driver projection workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MappingRecord:
    step_id: str
    semantic_op: str
    semantic_args: dict[str, Any] = field(default_factory=dict)
    program_kind: str | None = None
    program_args: dict[str, Any] = field(default_factory=dict)
    requirements: tuple[str, ...] = ()
    constraint_options: dict[str, Any] = field(default_factory=dict)
    env: dict[str, Any] | None = None
    env_targets: Any = None
    trace_ref: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DriverProjection:
    step_id: str
    semantic_op: str
    channel: str
    label: str
    summary: str
    details: tuple[str, ...] = ()
    category: str = "instruction"
    binding: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
