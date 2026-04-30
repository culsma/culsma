"""Shared state for IR -> Plan lowering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRProtocol


@dataclass
class PlanLoweringContext:
    protocols_by_name: Mapping[str, IRProtocol]
    diagnostics: list[Diagnostic]
    local_env: dict[str, Any]
    protected_names: set[str]
    protocol_name: str
    caller_stack: list[str]
    gate_base: dict[str, Any] | None
    statement_lowerer: Any = None
    serializer: Any = None
    reference_resolver: Any = None
    step_id_prefix: str = ""
    call_path: list[str] = field(default_factory=list)

    def derive(
        self,
        *,
        local_env: dict[str, Any] | None = None,
        protected_names: set[str] | None = None,
        protocol_name: str | None = None,
        caller_stack: list[str] | None = None,
        gate_base: dict[str, Any] | None = None,
        step_id_prefix: str | None = None,
        call_path: list[str] | None = None,
    ) -> PlanLoweringContext:
        return PlanLoweringContext(
            protocols_by_name=self.protocols_by_name,
            diagnostics=self.diagnostics,
            local_env=self.local_env if local_env is None else local_env,
            protected_names=self.protected_names if protected_names is None else protected_names,
            protocol_name=self.protocol_name if protocol_name is None else protocol_name,
            caller_stack=list(self.caller_stack if caller_stack is None else caller_stack),
            gate_base=self.gate_base if gate_base is None else gate_base,
            statement_lowerer=self.statement_lowerer,
            serializer=self.serializer,
            reference_resolver=self.reference_resolver,
            step_id_prefix=self.step_id_prefix if step_id_prefix is None else step_id_prefix,
            call_path=list(self.call_path if call_path is None else call_path),
        )

    def emit_diagnostic(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def extend_diagnostics(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics.extend(diagnostics)
