"""Shared declarations of value identity and read-only call capabilities."""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any

UNRESOLVED_VALUE = object()


@dataclass(frozen=True)
class ReadCallContract:
    type_id: str
    parameters: tuple[str, ...] | None = None
    capture_at_binding: bool = False
    receiver_member: str | None = None

    def accepts(self, args: list[Any]) -> bool:
        if not isinstance(args, list):
            return False
        names = [arg.get('name') if isinstance(arg, dict) else getattr(arg, 'name', None) for arg in args]
        if any(not isinstance(name, str) for name in names):
            return False
        return (len(names) == len(set(names)) and
                (self.parameters is None or set(names) == set(self.parameters)))


class ValueContractRegistry:
    def __init__(self) -> None:
        self.types: set[str] = set()
        self.calls: dict[str, ReadCallContract] = {}

    def register_type(self, type_id: str) -> None:
        if not type_id:
            raise ValueError('Value type identity must be nonempty')
        self.types.add(type_id)

    def register_call(self, name: str, contract: ReadCallContract) -> None:
        if name in self.calls and self.calls[name] != contract:
            raise ValueError(f'Conflicting read contract for {name}')
        self.register_type(contract.type_id)
        self.calls[name] = contract

    def resolve(self, type_id: str) -> bool:
        return type_id in self.types

    def resolve_call(self, name: str) -> ReadCallContract | None:
        return self.calls.get(name)

    def contains_read_call(self, expr: Any) -> bool:
        kind = expr.get('kind') if isinstance(expr, dict) else type(expr).__name__
        if kind == 'IRCall':
            name = expr.get('name') if isinstance(expr, dict) else expr.name
            if self.resolve_call(name) is not None:
                return True
        if is_dataclass(expr):
            return any(self.contains_read_call(getattr(expr, f.name)) for f in fields(expr) if f.name != 'span')
        if isinstance(expr, dict):
            return any(self.contains_read_call(value) for value in expr.values())
        if isinstance(expr, (list, tuple)):
            return any(self.contains_read_call(value) for value in expr)
        return False

    def requires_capture(self, expr: Any) -> bool:
        """Capture scalar query results; retain reference and descriptor identities."""
        kind = expr.get('kind') if isinstance(expr, dict) else type(expr).__name__
        if kind == 'IRMember' and self.contains_read_call(expr):
            return True
        if isinstance(kind, str) and kind in {'IRCall', 'Call'}:
            name = expr.get('name') if isinstance(expr, dict) else expr.name
            contract = self.resolve_call(name)
            if contract is not None and contract.capture_at_binding:
                return True
        if is_dataclass(expr):
            return any(self.requires_capture(getattr(expr, f.name)) for f in fields(expr) if f.name != 'span')
        if isinstance(expr, dict):
            return any(self.requires_capture(value) for value in expr.values())
        if isinstance(expr, (list, tuple)):
            return any(self.requires_capture(value) for value in expr)
        return False


VALUE_CONTRACTS = ValueContractRegistry()
