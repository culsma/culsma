"""Operation and named-call argument contracts."""

from __future__ import annotations

from typing import Mapping

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRCall
from culsma.pipeline.operation_specs import OperationSpec

_LET_CALL_CONTRACTS: dict[str, tuple[set[str], set[str]]] = {
    "AllocContainer": (
        set(),
        {"kind", "spec", "carrier_kind", "carrier_id", "carrier_position", "capacity", "open", "label", "barcode", "load"},
    ),
    "markers": ({"items"}, {"items"}),
    "stream": ({"sample", "unit"}, {"sample", "unit", "panel"}),
    "data_schema": ({"label", "fields"}, {"label", "fields"}),
    "data_ref": ({"kind"}, {"kind", "subject_ref", "context_ref", "schema_ref"}),
    "data_group_ref": ({"kind"}, {"kind"}),
    "sep": ({"sample", "program"}, {"sample", "program", "component_fates"}),
    "frac": ({"sample", "program"}, {"sample", "program"}),
}


class OperationContractValidator:
    @staticmethod
    def validate_call(
        call: IRCall,
        *,
        node_id: str | None,
        operations: Mapping[str, OperationSpec],
    ) -> list[Diagnostic]:
        required_args, allowed_args = _call_contract_for_name(call.name, operations=operations)
        if required_args is None or allowed_args is None:
            return []

        diagnostics: list[Diagnostic] = []
        arg_names = [arg.name for arg in call.args]
        arg_name_set = set(arg_names)

        for missing in sorted(required_args - arg_name_set):
            diagnostics.append(
                Diagnostic(
                    code="SEM_MISSING_REQUIRED_ARG",
                    message=f"Missing required arg '{missing}' in call '{call.name}'",
                    span=call.span,
                    node_id=node_id,
                )
            )

        for arg in call.args:
            if arg.name not in allowed_args:
                diagnostics.append(
                    Diagnostic(
                        code="SEM_UNKNOWN_ARG",
                        message=f"Unknown arg '{arg.name}' in call '{call.name}'",
                        span=arg.span or call.span,
                        node_id=node_id,
                    )
                )

        seen: set[str] = set()
        duplicates: list[str] = []
        for name in arg_names:
            if name in seen and name not in duplicates:
                duplicates.append(name)
            seen.add(name)
        for dup in duplicates:
            dup_span = next((arg.span for arg in call.args if arg.name == dup), call.span)
            diagnostics.append(
                Diagnostic(
                    code="SEM_DUPLICATE_ARG",
                    message=f"Duplicate arg '{dup}' in call '{call.name}'",
                    span=dup_span or call.span,
                    node_id=node_id,
                )
            )
        return diagnostics


def _call_contract_for_name(
    name: str,
    *,
    operations: Mapping[str, OperationSpec],
) -> tuple[frozenset[str] | set[str] | None, frozenset[str] | set[str] | None]:
    local = _LET_CALL_CONTRACTS.get(name)
    if local is not None:
        return local
    op_spec = operations.get(name)
    if op_spec is None:
        return None, None
    return op_spec.required_args, op_spec.allowed_args
