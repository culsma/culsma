"""Diagnostics for the deprecated protocol-header return declaration."""

from __future__ import annotations

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRProgram


def returns_header_diagnostics(ir: IRProgram) -> list[Diagnostic]:
    return [
        Diagnostic(
            code="SEM_RETURNS_HEADER_DEPRECATED",
            message=(
                f"Protocol '{protocol.name}' uses deprecated header returns(...); "
                "remove it and declare named outputs with a tail "
                "'return name = value' (or use 'return value' for an unnamed output)"
            ),
            span=protocol.span,
            severity="warning",
            node_id=protocol.id,
        )
        for protocol in ir.protocols
        if protocol.legacy_returns_header
    ]
