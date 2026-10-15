"""Execution plan node definitions for Kernel v0.1."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.common.source import Span


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    op: str
    args: dict[str, Any] = field(default_factory=dict)
    deps: list[str] = field(default_factory=list)
    gate: dict[str, Any] | None = None
    span: Span | None = None


@dataclass(frozen=True)
class ProtocolPlan:
    protocol_id: str
    protocol_name: str
    entry_kind: str = "protocol"
    output_name: str | None = None
    returns: list[str] = field(default_factory=list)
    return_value: Any | None = None
    return_bindings: dict[str, Any] = field(default_factory=dict)
    steps: list[PlanStep] = field(default_factory=list)
    span: Span | None = None


@dataclass(frozen=True)
class PlanProgram:
    plans: list[ProtocolPlan] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    span: Span | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


def _to_dict(value: Any) -> Any:
    if is_dataclass(value):
        data = asdict(value)
        data["kind"] = value.__class__.__name__
        return {k: _to_dict(v) for k, v in data.items()}
    if isinstance(value, list):
        return [_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_dict(val) for key, val in value.items()}
    return value


class PlanStepTree:
    """Walk operation envelopes without discarding the authoritative plan."""

    @staticmethod
    def children(step: PlanStep) -> list[PlanStep]:
        if step.op != "MutationGroup":
            return []
        members = step.args.get("members")
        if not isinstance(members, list) or not members:
            raise ValueError("RT_MUTATION_GROUP_INVALID")
        if any(not isinstance(member, PlanStep) or member.op != "Mutation" for member in members):
            raise ValueError("RT_MUTATION_GROUP_INVALID")
        identities = [member.step_id for member in members]
        if len(set(identities)) != len(identities) or step.step_id in identities:
            raise ValueError("RT_MUTATION_GROUP_INVALID")
        return members

    @classmethod
    def walk(cls, steps: list[PlanStep]) -> list[PlanStep]:
        result = []
        for step in steps:
            result.append(step)
            result.extend(cls.children(step))
        return result

    @classmethod
    def leaves(cls, steps: list[PlanStep]) -> list[PlanStep]:
        return [member for step in steps for member in (cls.children(step) if step.op == "MutationGroup" else [step])]
