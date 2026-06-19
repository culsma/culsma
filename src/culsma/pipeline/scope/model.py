"""Data model for pipeline scope facts."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class ScopeFrame:
    frame_id: str
    protocol_id: str
    parent_id: str | None
    owner_node_id: str


@dataclass(frozen=True)
class ScopeSlot:
    slot_id: str
    frame_id: str
    protocol_id: str
    name: str
    kind: str
    mutable: bool
    declared_at: str


@dataclass(frozen=True)
class ScopeResolution:
    slot_id: str | None
    name: str
    frame_id: str


@dataclass(frozen=True)
class ScopeAssignmentEffect:
    node_id: str
    protocol_id: str
    frame_id: str
    name: str
    slot_id: str | None
    reads_before_write: bool


@dataclass(frozen=True)
class ScopeModel:
    frames: Mapping[str, ScopeFrame] = field(default_factory=lambda: MappingProxyType({}))
    slots: Mapping[str, ScopeSlot] = field(default_factory=lambda: MappingProxyType({}))
    slots_by_frame_name: Mapping[tuple[str, str], str] = field(default_factory=lambda: MappingProxyType({}))
    slots_by_protocol_name: Mapping[tuple[str, str], str] = field(default_factory=lambda: MappingProxyType({}))
    frame_id_by_node_id: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    assignment_effects_by_node_id: Mapping[str, tuple[ScopeAssignmentEffect, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def frame_slot(self, frame_id: str, name: str) -> ScopeSlot | None:
        slot_id = self.slots_by_frame_name.get((frame_id, name))
        if slot_id is None:
            return None
        return self.slots.get(slot_id)

    def protocol_slot(self, protocol_id: str, name: str) -> ScopeSlot | None:
        slot_id = self.slots_by_protocol_name.get((protocol_id, name))
        if slot_id is None:
            return None
        return self.slots.get(slot_id)
