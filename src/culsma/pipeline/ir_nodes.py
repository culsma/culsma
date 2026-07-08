"""Canonical IR node definitions for Execution Kernel v0.1."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

from culsma.common.source import Span


@dataclass(frozen=True)
class IRQuantity:
    value: float
    unit: str | None
    span: Span | None = None


@dataclass(frozen=True)
class IRString:
    value: str
    span: Span | None = None


@dataclass(frozen=True)
class IRBoolean:
    value: bool
    span: Span | None = None


@dataclass(frozen=True)
class IRIdentifier:
    name: str
    span: Span | None = None


@dataclass(frozen=True)
class IRList:
    elements: list[IRExpr] = field(default_factory=list)
    span: Span | None = None


@dataclass(frozen=True)
class IRRecord:
    entries: dict[str, IRExpr] = field(default_factory=dict)
    span: Span | None = None


@dataclass(frozen=True)
class IRGroup:
    elements: list[IRExpr] = field(default_factory=list)
    span: Span | None = None


@dataclass(frozen=True)
class IRCall:
    name: str
    args: list[IRArg] = field(default_factory=list)
    span: Span | None = None


@dataclass(frozen=True)
class IRSelectorRegion:
    start: str
    end: str | None = None
    span: Span | None = None


@dataclass(frozen=True)
class IRPlateSelector:
    base: IRIdentifier
    regions: list[IRSelectorRegion] = field(default_factory=list)
    span: Span | None = None


@dataclass(frozen=True)
class IRIndex:
    base: IRExpr
    index: IRExpr
    span: Span | None = None


@dataclass(frozen=True)
class IRMember:
    base: IRExpr
    member: str
    span: Span | None = None


@dataclass(frozen=True)
class IRSourcePartitionRef:
    source: IRExpr
    program: IRExpr
    index: IRExpr
    span: Span | None = None


@dataclass(frozen=True)
class IRPair:
    left: IRExpr
    right: IRExpr
    span: Span | None = None


@dataclass(frozen=True)
class IRUnary:
    op: str
    operand: IRExpr
    span: Span | None = None


@dataclass(frozen=True)
class IRBinary:
    op: str
    left: IRExpr
    right: IRExpr
    span: Span | None = None


@dataclass(frozen=True)
class IRArg:
    name: str
    value: IRExpr
    span: Span | None = None


IRExpr = IRQuantity | IRString | IRBoolean | IRIdentifier | IRList | IRRecord | IRGroup | IRCall | IRPlateSelector | IRIndex | IRMember | IRSourcePartitionRef | IRPair | IRUnary | IRBinary


@dataclass(frozen=True)
class IRInclude:
    id: str
    name: str
    args: list[IRArg] = field(default_factory=list)
    span: Span | None = None


@dataclass(frozen=True)
class IRParam:
    name: str
    default: IRExpr | None = None
    span: Span | None = None


@dataclass(frozen=True)
class IRLet:
    id: str
    name: str
    value: IRExpr | None = None
    span: Span | None = None


@dataclass(frozen=True)
class IRAssign:
    id: str
    target: IRExpr
    value: IRExpr
    span: Span | None = None


@dataclass(frozen=True)
class IRStep:
    id: str
    name: str
    args: list[IRArg] = field(default_factory=list)
    span: Span | None = None


@dataclass(frozen=True)
class IRWithEnv:
    id: str
    env_args: list[IRArg] = field(default_factory=list)
    targets: list[IRExpr] = field(default_factory=list)
    statements: list[IRStatement] = field(default_factory=list)
    explicit_hold: bool = False
    span: Span | None = None


@dataclass(frozen=True)
class IRWithConstraint:
    id: str
    requirements: list[str] = field(default_factory=list)
    options: list[IRArg] = field(default_factory=list)
    statements: list[IRStatement] = field(default_factory=list)
    span: Span | None = None


@dataclass(frozen=True)
class IRMutation:
    id: str
    target: IRExpr | None = None
    sources: list[IRExpr] = field(default_factory=list)
    span: Span | None = None


@dataclass(frozen=True)
class IRConditional:
    id: str
    condition: IRExpr
    then_statements: list[IRStatement] = field(default_factory=list)
    else_statements: list[IRStatement] = field(default_factory=list)
    span: Span | None = None


@dataclass(frozen=True)
class IRControl:
    id: str
    action: str
    span: Span | None = None


@dataclass(frozen=True)
class IRRepeat:
    id: str
    binding: str
    iterable: IRExpr
    statements: list[IRStatement] = field(default_factory=list)
    span: Span | None = None


IRStatement = IRInclude | IRLet | IRAssign | IRStep | IRWithEnv | IRWithConstraint | IRMutation | IRConditional | IRControl | IRRepeat


@dataclass(frozen=True)
class IRProtocol:
    id: str
    name: str
    module: str | None = None
    source_path: str | None = None
    source_role: str | None = None
    params: list[IRParam] = field(default_factory=list)
    returns: list[str] = field(default_factory=list)
    return_value: IRExpr | None = None
    return_bindings: list[IRArg] = field(default_factory=list)
    statements: list[IRStatement] = field(default_factory=list)
    span: Span | None = None


@dataclass(frozen=True)
class IRScriptEntry:
    id: str
    statements: list[IRStatement] = field(default_factory=list)
    returns: list[str] = field(default_factory=list)
    return_value: IRExpr | None = None
    return_bindings: list[IRArg] = field(default_factory=list)
    source_paths: tuple[str, ...] = ()
    span: Span | None = None


@dataclass(frozen=True)
class IRProgram:
    protocols: list[IRProtocol] = field(default_factory=list)
    script_entry: IRScriptEntry | None = None
    span: Span | None = None

    def to_dict(self) -> dict[str, Any]:
        return _to_dict(self)


def _to_dict(value: Any) -> Any:
    """Recursively convert dataclass objects to JSON-friendly dictionaries."""
    if is_dataclass(value):
        data = asdict(value)
        data["kind"] = value.__class__.__name__
        return {k: _to_dict(v) for k, v in data.items()}
    if isinstance(value, list):
        return [_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_dict(val) for key, val in value.items()}
    return value
