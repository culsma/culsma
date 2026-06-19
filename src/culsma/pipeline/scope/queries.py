"""Query API for pipeline scope facts."""

from __future__ import annotations

from .model import ScopeAssignmentEffect, ScopeModel, ScopeResolution, ScopeSlot


class ScopeQueryService:
    def __init__(self, model: ScopeModel) -> None:
        self.model = model

    @classmethod
    def from_model(cls, model: ScopeModel) -> "ScopeQueryService":
        return cls(model)

    def resolve_read(self, node_id: str, name: str) -> ScopeResolution:
        current_id = self.model.frame_id_by_node_id.get(node_id)
        while current_id is not None:
            slot = self.model.frame_slot(current_id, name)
            if slot is not None:
                return ScopeResolution(slot_id=slot.slot_id, name=name, frame_id=slot.frame_id)
            frame = self.model.frames.get(current_id)
            current_id = frame.parent_id if frame is not None else None
        return ScopeResolution(slot_id=None, name=name, frame_id="")

    def check_assignment_target(self, node_id: str, name: str) -> bool:
        return self.resolve_read(node_id, name).slot_id is not None

    def binding_for(self, node_id: str, name: str) -> ScopeResolution:
        return self.resolve_read(node_id, name)

    def slot_kind(self, slot_id: str) -> str | None:
        slot = self.model.slots.get(slot_id)
        return slot.kind if slot is not None else None

    def is_mutable(self, slot_id: str) -> bool:
        slot = self.model.slots.get(slot_id)
        return bool(slot is not None and slot.mutable)

    def is_mutable_name(self, protocol_id: str, name: str) -> bool:
        slot = self.model.protocol_slot(protocol_id, name)
        return bool(slot is not None and slot.mutable)

    def runtime_local_slots(self, protocol_id: str) -> list[ScopeSlot]:
        return [
            slot
            for slot in self.model.slots.values()
            if slot.protocol_id == protocol_id and slot.kind in {"local", "parameter"} and slot.mutable
        ]

    def assignment_effects(self, node_id: str) -> tuple[ScopeAssignmentEffect, ...]:
        return self.model.assignment_effects_by_node_id.get(node_id, ())
