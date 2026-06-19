"""Compile-produced sidecar analysis for Canonical IR."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from culsma.pipeline.scope import ScopeAnalyzer, ScopeModel
from culsma.pipeline.ir_nodes import (
    IRAssign,
    IRConditional,
    IRIdentifier,
    IRInclude,
    IRIndex,
    IRLet,
    IRList,
    IRMember,
    IRPlateSelector,
    IRProgram,
    IRQuantity,
    IRRepeat,
    IRStatement,
    IRString,
    IRUnary,
    IRWithConstraint,
    IRWithEnv,
    IRCall,
)


def _empty_str_map() -> Mapping[str, str]:
    return MappingProxyType({})


@dataclass(frozen=True)
class ProtocolAnalysis:
    runtime_exports: frozenset[str] = frozenset()
    include_targets: Mapping[str, str] = field(default_factory=_empty_str_map)


@dataclass(frozen=True)
class CompileAnalysis:
    protocols: Mapping[str, ProtocolAnalysis] = field(default_factory=lambda: MappingProxyType({}))
    scope: ScopeModel = field(default_factory=ScopeModel)


@dataclass
class CompileAnalysisBuilder:
    _runtime_exports: dict[str, set[str]] = field(default_factory=dict)
    _include_targets: dict[str, dict[str, str]] = field(default_factory=dict)

    def record_statement_effects(
        self,
        *,
        protocol_id: str,
        statements: list[IRStatement],
        protocols_by_name: Mapping[str, str],
        collect_runtime_exports: bool,
        expr_bindings: dict[str, Any],
        env: dict[str, Any],
    ) -> None:
        for stmt in statements:
            if isinstance(stmt, IRInclude):
                target_id = protocols_by_name.get(stmt.name)
                if target_id is not None:
                    self._include_targets.setdefault(protocol_id, {})[stmt.id] = target_id
            if collect_runtime_exports:
                self._record_runtime_binding_effect(protocol_id, stmt, expr_bindings=expr_bindings, env=env)

    def build(self, *, protocol_ids: list[str], scope: ScopeModel | None = None) -> CompileAnalysis:
        protocol_analysis: dict[str, ProtocolAnalysis] = {}
        for protocol_id in protocol_ids:
            protocol_analysis[protocol_id] = ProtocolAnalysis(
                runtime_exports=frozenset(self._runtime_exports.get(protocol_id, set())),
                include_targets=MappingProxyType(dict(self._include_targets.get(protocol_id, {}))),
            )
        return CompileAnalysis(
            protocols=MappingProxyType(protocol_analysis),
            scope=scope if scope is not None else ScopeModel(),
        )

    def _record_runtime_binding_effect(
        self,
        protocol_id: str,
        stmt: IRStatement,
        *,
        expr_bindings: dict[str, Any],
        env: dict[str, Any],
    ) -> None:
        if isinstance(stmt, IRLet):
            if stmt.value is not None:
                expr_bindings[stmt.name] = stmt.value
            else:
                expr_bindings.pop(stmt.name, None)
            if _let_defines_runtime_name(stmt, expr_bindings=expr_bindings):
                self._runtime_exports.setdefault(protocol_id, set()).add(stmt.name)
            resolved = _resolve_let_value(stmt, env)
            if resolved is not None:
                env[stmt.name] = resolved
            return
        if isinstance(stmt, IRAssign):
            assign_root = _assign_target_root_name(stmt.target)
            if assign_root is not None and isinstance(stmt.target, IRIdentifier):
                env.pop(assign_root, None)
                expr_bindings[assign_root] = stmt.value


def build_compile_analysis(ir: IRProgram) -> CompileAnalysis:
    """Build sidecar analysis for downstream pipeline stages."""
    protocols_by_name = {protocol.name: protocol for protocol in ir.protocols}
    protocol_analysis: dict[str, ProtocolAnalysis] = {}
    for protocol in ir.protocols:
        include_targets = _collect_include_targets(protocol.statements, protocols_by_name=protocols_by_name)
        protocol_analysis[protocol.id] = ProtocolAnalysis(
            runtime_exports=frozenset(_compute_runtime_exports(protocol.statements)),
            include_targets=MappingProxyType(include_targets),
        )
    return CompileAnalysis(
        protocols=MappingProxyType(protocol_analysis),
        scope=ScopeAnalyzer().analyze(ir),
    )


def _collect_include_targets(
    statements: list[IRStatement],
    *,
    protocols_by_name: dict[str, Any],
) -> dict[str, str]:
    targets: dict[str, str] = {}
    for stmt in statements:
        if isinstance(stmt, IRInclude):
            target = protocols_by_name.get(stmt.name)
            if target is not None:
                targets[stmt.id] = target.id
            continue
        nested = _nested_statements(stmt)
        if nested:
            targets.update(_collect_include_targets(nested, protocols_by_name=protocols_by_name))
    return targets


def _nested_statements(stmt: IRStatement) -> list[IRStatement]:
    if isinstance(stmt, IRWithEnv):
        return stmt.statements
    if isinstance(stmt, IRWithConstraint):
        return stmt.statements
    if isinstance(stmt, IRRepeat):
        return stmt.statements
    if isinstance(stmt, IRConditional):
        return [*stmt.then_statements, *stmt.else_statements]
    return []


def _compute_runtime_exports(statements: list[IRStatement]) -> set[str]:
    env: dict[str, Any] = {}
    expr_bindings: dict[str, Any] = {}
    names: set[str] = set()
    for stmt in statements:
        if isinstance(stmt, IRLet):
            if stmt.value is not None:
                expr_bindings[stmt.name] = stmt.value
            else:
                expr_bindings.pop(stmt.name, None)
            if _let_defines_runtime_name(stmt, expr_bindings=expr_bindings):
                names.add(stmt.name)
            resolved = _resolve_let_value(stmt, env)
            if resolved is not None:
                env[stmt.name] = resolved
            continue
        if isinstance(stmt, IRAssign):
            assign_root = _assign_target_root_name(stmt.target)
            if assign_root is not None and isinstance(stmt.target, IRIdentifier):
                env.pop(assign_root, None)
                expr_bindings[assign_root] = stmt.value
    return names


def _assign_target_root_name(expr: Any) -> str | None:
    current = expr
    while isinstance(current, IRMember):
        current = current.base
    if isinstance(current, IRIdentifier):
        return current.name
    return None


def _resolve_let_value(stmt: IRLet, env: dict[str, Any]) -> str | list[str] | float | None:
    value = stmt.value
    if value is None:
        return None
    resolved_str = _to_string(value, env)
    if resolved_str is not None:
        return resolved_str
    resolved_num = _to_number(value, env)
    if resolved_num is not None:
        return resolved_num
    return _to_string_list(value, env)


def _let_defines_runtime_name(stmt: IRLet, *, expr_bindings: dict[str, Any]) -> bool:
    if stmt.value is None:
        return False
    resolved = _resolve_bound_expr(stmt.value, expr_bindings)
    if isinstance(resolved, (IRIdentifier, IRString, IRPlateSelector, IRIndex)):
        return True
    return isinstance(resolved, IRCall) and resolved.name in {
        "AllocContainer",
        "stream",
        "markers",
        "data_schema",
        "data_ref",
        "data_group_ref",
    }


def _resolve_bound_expr(expr: Any, expr_bindings: dict[str, Any]) -> Any:
    seen: set[str] = set()
    current = expr
    while isinstance(current, IRIdentifier) and current.name in expr_bindings and current.name not in seen:
        seen.add(current.name)
        current = expr_bindings[current.name]
    return current


def _to_string(expr: Any, env: dict[str, Any]) -> str | None:
    if isinstance(expr, IRString):
        return expr.value
    if isinstance(expr, IRIdentifier):
        bound = env.get(expr.name)
        return bound if isinstance(bound, str) else None
    return None


def _to_number(expr: Any, env: dict[str, Any]) -> float | None:
    if isinstance(expr, IRQuantity) and expr.unit is None:
        return float(expr.value)
    if isinstance(expr, IRUnary) and expr.op == "-":
        inner = _to_number(expr.operand, env)
        return None if inner is None else -inner
    if isinstance(expr, IRIdentifier):
        bound = env.get(expr.name)
        if isinstance(bound, (int, float)):
            return float(bound)
    return None


def _to_string_list(expr: Any, env: dict[str, Any]) -> list[str] | None:
    if isinstance(expr, IRList):
        values: list[str] = []
        for item in expr.elements:
            resolved = _to_string(item, env)
            if resolved is None:
                return None
            values.append(resolved)
        return values
    if isinstance(expr, IRIdentifier):
        bound = env.get(expr.name)
        if isinstance(bound, list) and all(isinstance(v, str) for v in bound):
            return list(bound)
    return None
