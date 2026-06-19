"""Shared compile session and block context objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from culsma.parser.ast_nodes import Expression, Program, ProtocolDecl, Quantity, ReturnStatement
from culsma.pipeline.analysis import CompileAnalysisBuilder


@dataclass
class _CompilerState:
    synthesized_wells: dict[tuple[str, str], str] = field(default_factory=dict)


def _build_qualified_protocol_lookup(ast: Program) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for protocol in ast.protocols:
        if protocol.module is None:
            continue
        qualified_name = f"{protocol.module}.{protocol.name}"
        existing = lookup.get(qualified_name)
        if existing is not None and existing != protocol.name:
            raise ValueError(f"Ambiguous qualified protocol reference: {qualified_name}")
        lookup[qualified_name] = protocol.name
    return lookup


def _build_protocol_decl_lookup(ast: Program) -> dict[str, ProtocolDecl]:
    lookup: dict[str, ProtocolDecl] = {}
    for protocol in ast.protocols:
        existing = lookup.get(protocol.name)
        if existing is not None and existing is not protocol:
            raise ValueError(f"Ambiguous protocol reference: {protocol.name}")
        lookup[protocol.name] = protocol
    return lookup


def _build_protocol_id_by_name(ast: Program) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for idx, protocol in enumerate(ast.protocols):
        existing = lookup.get(protocol.name)
        protocol_id = f"p{idx}"
        if existing is not None and existing != protocol_id:
            raise ValueError(f"Ambiguous protocol reference: {protocol.name}")
        lookup[protocol.name] = protocol_id
    return lookup


def _validate_protocol_return_contract(proto: ProtocolDecl) -> None:
    param_names = [param.name for param in proto.params]
    if len(param_names) != len(set(param_names)):
        raise ValueError(f"Protocol '{proto.name}' declares duplicate parameter names")

    if len(proto.returns) != len(set(proto.returns)):
        raise ValueError(f"Protocol '{proto.name}' declares duplicate return names")

    tail_return: ReturnStatement | None = None
    for idx, stmt in enumerate(proto.statements):
        if isinstance(stmt, ReturnStatement):
            if idx != len(proto.statements) - 1:
                raise ValueError(f"Protocol '{proto.name}' only supports top-level tail return statements")
            tail_return = stmt

    if proto.returns and tail_return is None:
        raise ValueError(f"Protocol '{proto.name}' declares returns but does not define a tail return")
    if tail_return is None:
        return

    if tail_return.bindings:
        binding_names = [binding.name for binding in tail_return.bindings]
        if len(binding_names) != len(set(binding_names)):
            raise ValueError(f"Protocol '{proto.name}' return statement declares duplicate binding names")
        if not proto.returns:
            raise ValueError(f"Protocol '{proto.name}' uses named return bindings without a returns(...) declaration")
        unknown = sorted(set(binding_names) - set(proto.returns))
        if unknown:
            raise ValueError(
                f"Protocol '{proto.name}' return statement references undeclared outputs: {', '.join(unknown)}"
            )
        missing = sorted(set(proto.returns) - set(binding_names))
        if missing:
            raise ValueError(
                f"Protocol '{proto.name}' return statement does not bind declared outputs: {', '.join(missing)}"
            )
        return

    if len(proto.returns) > 1:
        raise ValueError(
            f"Protocol '{proto.name}' declares multiple returns and must use named return bindings"
        )


def _protocol_tail_return(proto: ProtocolDecl) -> ReturnStatement | None:
    if not proto.statements:
        return None
    tail = proto.statements[-1]
    return tail if isinstance(tail, ReturnStatement) else None


def _require_span(node: object, label: str) -> None:
    span = getattr(node, "span", None)
    if span is None:
        raise ValueError(f"Missing span on {label}")


@dataclass(frozen=True)
class CompileSession:
    qualified_protocol_lookup: dict[str, str]
    protocol_lookup: dict[str, ProtocolDecl]
    protocol_id_by_name: dict[str, str]
    analysis_builder: CompileAnalysisBuilder
    state: _CompilerState

    @classmethod
    def from_program(cls, ast: Program) -> "CompileSession":
        return cls(
            qualified_protocol_lookup=_build_qualified_protocol_lookup(ast),
            protocol_lookup=_build_protocol_decl_lookup(ast),
            protocol_id_by_name=_build_protocol_id_by_name(ast),
            analysis_builder=CompileAnalysisBuilder(),
            state=_CompilerState(),
        )


_CTX_UNSET = object()


@dataclass
class BlockContext:
    scope_id: str
    const_env: dict[str, float | bool] = field(default_factory=dict)
    let_bindings: dict[str, Expression] = field(default_factory=dict)
    ir_const_env: dict[str, Any] = field(default_factory=dict)
    ir_expr_bindings: dict[str, Any] = field(default_factory=dict)
    local_names: set[str] = field(default_factory=set)
    mutable_local_names: set[str] = field(default_factory=set)
    param_names: set[str] = field(default_factory=set)
    env_time_boundary: Quantity | None = None
    env_time_boundary_deferred: bool = False

    def derive(
        self,
        *,
        scope_id: str | None = None,
        const_env: dict[str, float | bool] | None = None,
        let_bindings: dict[str, Expression] | None = None,
        ir_const_env: dict[str, Any] | None = None,
        ir_expr_bindings: dict[str, Any] | None = None,
        local_names: set[str] | None = None,
        mutable_local_names: set[str] | None = None,
        param_names: set[str] | None = None,
        env_time_boundary: Quantity | None | object = _CTX_UNSET,
        env_time_boundary_deferred: bool | None = None,
    ) -> "BlockContext":
        return BlockContext(
            scope_id=self.scope_id if scope_id is None else scope_id,
            const_env=self.const_env if const_env is None else const_env,
            let_bindings=self.let_bindings if let_bindings is None else let_bindings,
            ir_const_env=self.ir_const_env if ir_const_env is None else ir_const_env,
            ir_expr_bindings=self.ir_expr_bindings if ir_expr_bindings is None else ir_expr_bindings,
            local_names=self.local_names if local_names is None else local_names,
            mutable_local_names=(
                self.mutable_local_names if mutable_local_names is None else mutable_local_names
            ),
            param_names=self.param_names if param_names is None else param_names,
            env_time_boundary=(
                self.env_time_boundary if env_time_boundary is _CTX_UNSET else env_time_boundary
            ),
            env_time_boundary_deferred=(
                self.env_time_boundary_deferred if env_time_boundary_deferred is None else env_time_boundary_deferred
            ),
        )
