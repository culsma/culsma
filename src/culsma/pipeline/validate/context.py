"""Shared validation context and result objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.analysis import CompileAnalysis
from culsma.pipeline.ir_nodes import IRProgram
from culsma.pipeline.operation_specs import OperationSpec


@dataclass(frozen=True)
class _GroupBinding:
    kind: str
    size: int | None = None


@dataclass(frozen=True)
class ValidationOptions:
    initial_defined_names: set[str] = field(default_factory=set)
    enforce_binding: bool = False
    content_whitelist_mode: str = "compat"
    content_type_policy: str = "required"


@dataclass(frozen=True)
class ValidationSession:
    operations: Mapping[str, OperationSpec]
    analysis: CompileAnalysis
    options: ValidationOptions


@dataclass
class ValidationContext:
    literal_bindings: dict[str, Any] = field(default_factory=dict)
    expr_bindings: dict[str, Any] = field(default_factory=dict)
    group_bindings: dict[str, _GroupBinding] = field(default_factory=dict)
    defined_names: set[str] = field(default_factory=set)
    active_requirements: tuple[str, ...] = ()

    def derive_block(self) -> "ValidationContext":
        return ValidationContext(
            literal_bindings=dict(self.literal_bindings),
            expr_bindings=dict(self.expr_bindings),
            group_bindings=dict(self.group_bindings),
            defined_names=set(self.defined_names),
            active_requirements=self.active_requirements,
        )

    def derive_constraint(self, requirements: tuple[str, ...]) -> "ValidationContext":
        ctx = self.derive_block()
        ctx.active_requirements = requirements
        return ctx


@dataclass(frozen=True)
class ValidationResult:
    ir: IRProgram
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)
