"""Shared state for Canonical IR typecheck."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.content_inputs import ContentArgumentScope
from culsma.pipeline.ir_nodes import IRProgram
from culsma.pipeline.operation_specs import OperationSpec
from culsma.pipeline.scope import ScopeQueryService


@dataclass(frozen=True)
class TypecheckResult:
    ir: IRProgram
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)


@dataclass
class TypecheckContext:
    operation_specs: Mapping[str, OperationSpec]
    diagnostics: list[Diagnostic]
    expr_bindings: dict[str, Any] = field(default_factory=dict)
    scope_query: ScopeQueryService | None = None
    statement_typechecker: Any = None
    parameter_names: frozenset[str] = frozenset()

    def content_scope(self) -> ContentArgumentScope:
        return ContentArgumentScope(expr_bindings=self.expr_bindings, defined_names=self.parameter_names)

    def derive_with_bindings(self, bindings: dict[str, Any]) -> TypecheckContext:
        return TypecheckContext(
            operation_specs=self.operation_specs,
            diagnostics=self.diagnostics,
            expr_bindings=bindings,
            scope_query=self.scope_query,
            statement_typechecker=self.statement_typechecker,
            parameter_names=self.parameter_names,
        )

    def emit(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def extend(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics.extend(diagnostics)
