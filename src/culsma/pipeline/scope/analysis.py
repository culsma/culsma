"""Build pipeline scope facts from source and IR."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import Any

from culsma.parser.ast_nodes import (
    AssignStatement,
    Identifier,
    IfStatement,
    LetStatement,
    RepeatStatement,
    Statement,
    WithConstraintStmt,
    WithEnvStmt,
)
from culsma.pipeline.ir_nodes import (
    IRAssign,
    IRConditional,
    IRIdentifier,
    IRLet,
    IRProgram,
    IRRepeat,
    IRStatement,
    IRWithConstraint,
    IRWithEnv,
)

from .model import ScopeAssignmentEffect, ScopeFrame, ScopeModel, ScopeSlot


@dataclass(frozen=True)
class ScopeChildBlock:
    label: str
    statements: list[IRStatement]
    repeat_binding: str | None = None


class ScopeAnalyzer:
    def assigned_source_local_names(self, statements: list[Statement]) -> frozenset[str]:
        """Return source local names assigned anywhere in this statement tree."""
        return frozenset(self.collect_assigned_source_local_names(statements))

    def validate_unique_source_local_names(
        self,
        statements: list[Statement],
        *,
        reserved_names: set[str] | frozenset[str] | None = None,
        protocol_name: str = "protocol",
    ) -> None:
        declared = set(reserved_names or set())
        for name in self.collect_declared_source_local_names(statements):
            if self.is_internal_generated_name(name):
                continue
            if name in declared:
                raise ValueError(f"local name '{name}' is already declared in protocol '{protocol_name}'")
            declared.add(name)

    def is_internal_generated_name(self, name: str) -> bool:
        return name.startswith("__cmp_")

    def analyze(self, ir: IRProgram) -> ScopeModel:
        frames: dict[str, ScopeFrame] = {}
        slots: dict[str, ScopeSlot] = {}
        slots_by_frame_name: dict[tuple[str, str], str] = {}
        slots_by_protocol_name: dict[tuple[str, str], str] = {}
        frame_id_by_node_id: dict[str, str] = {}
        assignment_effects_by_node_id: dict[str, list[ScopeAssignmentEffect]] = {}

        if ir.script_entry is not None:
            self.record_scope_root(
                root_id=ir.script_entry.id,
                statements=ir.script_entry.statements,
                params=[],
                frames=frames,
                slots=slots,
                slots_by_frame_name=slots_by_frame_name,
                slots_by_protocol_name=slots_by_protocol_name,
                frame_id_by_node_id=frame_id_by_node_id,
                assignment_effects_by_node_id=assignment_effects_by_node_id,
            )

        for protocol in ir.protocols:
            self.record_scope_root(
                root_id=protocol.id,
                statements=protocol.statements,
                params=protocol.params,
                frames=frames,
                slots=slots,
                slots_by_frame_name=slots_by_frame_name,
                slots_by_protocol_name=slots_by_protocol_name,
                frame_id_by_node_id=frame_id_by_node_id,
                assignment_effects_by_node_id=assignment_effects_by_node_id,
            )

        return ScopeModel(
            frames=MappingProxyType(frames),
            slots=MappingProxyType(slots),
            slots_by_frame_name=MappingProxyType(slots_by_frame_name),
            slots_by_protocol_name=MappingProxyType(slots_by_protocol_name),
            frame_id_by_node_id=MappingProxyType(frame_id_by_node_id),
            assignment_effects_by_node_id=MappingProxyType(
                {node_id: tuple(effects) for node_id, effects in assignment_effects_by_node_id.items()}
            ),
        )

    def record_scope_root(
        self,
        *,
        root_id: str,
        statements: list[IRStatement],
        params: list[Any],
        frames: dict[str, ScopeFrame],
        slots: dict[str, ScopeSlot],
        slots_by_frame_name: dict[tuple[str, str], str],
        slots_by_protocol_name: dict[tuple[str, str], str],
        frame_id_by_node_id: dict[str, str],
        assignment_effects_by_node_id: dict[str, list[ScopeAssignmentEffect]],
    ) -> None:
        frame_id = self.scope_frame_id(root_id)
        frames[frame_id] = ScopeFrame(
            frame_id=frame_id,
            protocol_id=root_id,
            parent_id=None,
            owner_node_id=root_id,
        )
        frame_id_by_node_id[root_id] = frame_id
        mutable_names = self.collect_assigned_ir_local_names(statements)
        for param in params:
            self.add_slot(
                slots=slots,
                slots_by_frame_name=slots_by_frame_name,
                slots_by_protocol_name=slots_by_protocol_name,
                frame_id=frame_id,
                protocol_id=root_id,
                name=param.name,
                kind="parameter",
                mutable=param.name in mutable_names,
                declared_at=root_id,
            )
        for stmt in statements:
            self.record_statement_scope(
                stmt,
                protocol_id=root_id,
                frame_id=frame_id,
                mutable_names=mutable_names,
                frames=frames,
                slots=slots,
                slots_by_frame_name=slots_by_frame_name,
                slots_by_protocol_name=slots_by_protocol_name,
                frame_id_by_node_id=frame_id_by_node_id,
                assignment_effects_by_node_id=assignment_effects_by_node_id,
            )

    def record_statement_scope(
        self,
        stmt: IRStatement,
        *,
        protocol_id: str,
        frame_id: str,
        mutable_names: set[str],
        frames: dict[str, ScopeFrame],
        slots: dict[str, ScopeSlot],
        slots_by_frame_name: dict[tuple[str, str], str],
        slots_by_protocol_name: dict[tuple[str, str], str],
        frame_id_by_node_id: dict[str, str],
        assignment_effects_by_node_id: dict[str, list[ScopeAssignmentEffect]],
    ) -> list[ScopeAssignmentEffect]:
        effects: list[ScopeAssignmentEffect] = []
        if hasattr(stmt, "id"):
            node_id = getattr(stmt, "id")
        else:
            node_id = protocol_id
        frame_id_by_node_id[node_id] = frame_id

        if isinstance(stmt, IRLet):
            name = stmt.name
            self.add_slot(
                slots=slots,
                slots_by_frame_name=slots_by_frame_name,
                slots_by_protocol_name=slots_by_protocol_name,
                frame_id=frame_id,
                protocol_id=protocol_id,
                name=name,
                kind="local",
                mutable=name in mutable_names,
                declared_at=node_id,
            )

        if isinstance(stmt, IRAssign) and isinstance(stmt.target, IRIdentifier):
            slot = self.resolve_slot_from_frame(frames, slots, slots_by_frame_name, frame_id, stmt.target.name)
            effects.append(
                ScopeAssignmentEffect(
                    node_id=node_id,
                    protocol_id=protocol_id,
                    frame_id=frame_id,
                    name=stmt.target.name,
                    slot_id=slot.slot_id if slot is not None else None,
                    reads_before_write=self.expr_references_identifier(stmt.value, stmt.target.name),
                )
            )

        for child in self.child_blocks(stmt):
            child_frame_id = self.child_frame_id(frame_id, node_id, child.label)
            frames[child_frame_id] = ScopeFrame(
                frame_id=child_frame_id,
                protocol_id=protocol_id,
                parent_id=frame_id,
                owner_node_id=node_id,
            )
            if child.repeat_binding is not None:
                self.add_slot(
                    slots=slots,
                    slots_by_frame_name=slots_by_frame_name,
                    slots_by_protocol_name=slots_by_protocol_name,
                    frame_id=child_frame_id,
                    protocol_id=protocol_id,
                    name=child.repeat_binding,
                    kind="repeat_binding",
                    mutable=False,
                    declared_at=node_id,
                    index_by_protocol=False,
                )
            for nested in child.statements:
                effects.extend(
                    self.record_statement_scope(
                        nested,
                        protocol_id=protocol_id,
                        frame_id=child_frame_id,
                        mutable_names=mutable_names,
                        frames=frames,
                        slots=slots,
                        slots_by_frame_name=slots_by_frame_name,
                        slots_by_protocol_name=slots_by_protocol_name,
                        frame_id_by_node_id=frame_id_by_node_id,
                        assignment_effects_by_node_id=assignment_effects_by_node_id,
                    )
                )

        if effects:
            assignment_effects_by_node_id.setdefault(node_id, []).extend(effects)
        return effects

    def add_slot(
        self,
        *,
        slots: dict[str, ScopeSlot],
        slots_by_frame_name: dict[tuple[str, str], str],
        slots_by_protocol_name: dict[tuple[str, str], str],
        frame_id: str,
        protocol_id: str,
        name: str,
        kind: str,
        mutable: bool,
        declared_at: str,
        index_by_protocol: bool = True,
    ) -> ScopeSlot:
        existing_id = slots_by_frame_name.get((frame_id, name))
        if existing_id is not None:
            existing = slots[existing_id]
            if existing.mutable == mutable:
                return existing
            slot = ScopeSlot(
                slot_id=existing.slot_id,
                frame_id=existing.frame_id,
                protocol_id=existing.protocol_id,
                name=existing.name,
                kind=existing.kind,
                mutable=existing.mutable or mutable,
                declared_at=existing.declared_at,
            )
            slots[existing.slot_id] = slot
            return slot

        slot_id = f"{frame_id}.{name}"
        slot = ScopeSlot(
            slot_id=slot_id,
            frame_id=frame_id,
            protocol_id=protocol_id,
            name=name,
            kind=kind,
            mutable=mutable,
            declared_at=declared_at,
        )
        slots[slot_id] = slot
        slots_by_frame_name[(frame_id, name)] = slot_id
        if index_by_protocol:
            slots_by_protocol_name[(protocol_id, name)] = slot_id
        return slot

    def resolve_slot_from_frame(
        self,
        frames: dict[str, ScopeFrame],
        slots: dict[str, ScopeSlot],
        slots_by_frame_name: dict[tuple[str, str], str],
        frame_id: str,
        name: str,
    ) -> ScopeSlot | None:
        current_id: str | None = frame_id
        while current_id is not None:
            slot_id = slots_by_frame_name.get((current_id, name))
            if slot_id is not None:
                return slots.get(slot_id)
            frame = frames.get(current_id)
            current_id = frame.parent_id if frame is not None else None
        return None

    def scope_frame_id(self, root_id: str) -> str:
        return f"{root_id}.scope"

    def child_frame_id(self, parent_frame_id: str, node_id: str, label: str) -> str:
        return f"{parent_frame_id}.{node_id}.{label}"

    def child_blocks(self, stmt: IRStatement) -> list[ScopeChildBlock]:
        if isinstance(stmt, IRConditional):
            return [
                ScopeChildBlock(label="then", statements=stmt.then_statements),
                ScopeChildBlock(label="else", statements=stmt.else_statements),
            ]
        if isinstance(stmt, IRRepeat):
            return [ScopeChildBlock(label="body", statements=stmt.statements, repeat_binding=stmt.binding)]
        if isinstance(stmt, (IRWithEnv, IRWithConstraint)):
            return [ScopeChildBlock(label="body", statements=stmt.statements)]
        return []

    def collect_assigned_source_local_names(self, statements: list[Statement]) -> set[str]:
        names: set[str] = set()
        for stmt in statements:
            if isinstance(stmt, AssignStatement) and isinstance(stmt.target, Identifier):
                names.add(stmt.target.name)
            elif isinstance(stmt, IfStatement):
                names.update(self.collect_assigned_source_local_names(stmt.then_statements))
                names.update(self.collect_assigned_source_local_names(stmt.else_statements))
            elif isinstance(stmt, RepeatStatement):
                names.update(self.collect_assigned_source_local_names(stmt.statements))
            elif isinstance(stmt, (WithEnvStmt, WithConstraintStmt)):
                names.update(self.collect_assigned_source_local_names(stmt.statements))
        return names

    def collect_declared_source_local_names(self, statements: list[Statement]) -> list[str]:
        names: list[str] = []
        for stmt in statements:
            if isinstance(stmt, LetStatement):
                names.append(stmt.name)
            elif isinstance(stmt, IfStatement):
                names.extend(self.collect_declared_source_local_names(stmt.then_statements))
                names.extend(self.collect_declared_source_local_names(stmt.else_statements))
            elif isinstance(stmt, RepeatStatement):
                if stmt.binding is not None:
                    names.append(stmt.binding)
                names.extend(self.collect_declared_source_local_names(stmt.statements))
            elif isinstance(stmt, (WithEnvStmt, WithConstraintStmt)):
                names.extend(self.collect_declared_source_local_names(stmt.statements))
        return names

    def collect_assigned_ir_local_names(self, statements: list[IRStatement]) -> set[str]:
        names: set[str] = set()
        for stmt in statements:
            if isinstance(stmt, IRAssign) and isinstance(stmt.target, IRIdentifier):
                names.add(stmt.target.name)
            for child in self.child_blocks(stmt):
                names.update(self.collect_assigned_ir_local_names(child.statements))
        return names

    def expr_references_identifier(self, expr: Any, name: str) -> bool:
        if isinstance(expr, IRIdentifier):
            return expr.name == name
        if isinstance(expr, dict):
            if expr.get("kind") == "IRIdentifier" and expr.get("name") == name:
                return True
            return any(self.expr_references_identifier(value, name) for value in expr.values())
        if isinstance(expr, list):
            return any(self.expr_references_identifier(value, name) for value in expr)
        if is_dataclass(expr):
            return any(self.expr_references_identifier(getattr(expr, field.name), name) for field in fields(expr))
        return False
