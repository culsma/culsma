"""Entrypoint resolution and isolated legacy compatibility policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import (
    IRConditional,
    IRInclude,
    IRProgram,
    IRProtocol,
    IRRepeat,
    IRStatement,
    IRWithConstraint,
    IRWithEnv,
)


EntryKind = Literal["protocol", "script", "none"]
EntrySource = Literal["explicit", "script", "legacy_single_protocol", "none"]
CompatibilityPolicy = Literal["legacy_single_protocol", "strict"]


@dataclass(frozen=True)
class EntryResolution:
    kind: EntryKind
    entry_protocol: str | None
    source: EntrySource
    diagnostics: list[Diagnostic] = field(default_factory=list)


__all__ = [
    "CompatibilityPolicy",
    "EntryKind",
    "EntryResolution",
    "EntrySource",
    "collect_referenced_protocol_names",
    "collect_entry_protocols",
    "collect_user_protocols",
    "resolve_entry",
    "resolve_legacy_single_protocol_entry",
]


def resolve_entry(
    ir: IRProgram,
    *,
    explicit_entry: str | None = None,
    compatibility_policy: CompatibilityPolicy = "legacy_single_protocol",
    warn_on_legacy: bool = True,
) -> EntryResolution:
    """Resolve the executable entry while isolating 1.0 compatibility fallback."""
    protocol_by_name = {protocol.name: protocol for protocol in ir.protocols}

    if explicit_entry is not None:
        if explicit_entry not in protocol_by_name:
            return EntryResolution(
                kind="none",
                entry_protocol=None,
                source="none",
                diagnostics=[
                    Diagnostic(
                        code="ENTRY_PROTOCOL_NOT_FOUND",
                        message=f"Entry protocol '{explicit_entry}' not found",
                        span=ir.span,
                        node_id=None,
                    )
                ],
            )
        return EntryResolution(kind="protocol", entry_protocol=explicit_entry, source="explicit")

    if ir.script_entry is not None:
        return EntryResolution(kind="script", entry_protocol=None, source="script")

    if compatibility_policy == "legacy_single_protocol":
        protocol = resolve_legacy_single_protocol_entry(ir)
        if protocol is not None:
            diagnostics = []
            if warn_on_legacy:
                diagnostics.append(
                    Diagnostic(
                        code="ENTRY_LEGACY_IMPLICIT_SINGLE_PROTOCOL",
                        message=(
                            f"Implicitly running protocol '{protocol.name}' is deprecated; "
                            "add top-level script statements or select an entry protocol explicitly"
                        ),
                        span=protocol.span,
                        severity="warning",
                        node_id=protocol.id,
                    )
                )
            return EntryResolution(
                kind="protocol",
                entry_protocol=protocol.name,
                source="legacy_single_protocol",
                diagnostics=diagnostics,
            )

    return EntryResolution(
        kind="none",
        entry_protocol=None,
        source="none",
        diagnostics=[
            Diagnostic(
                code="ENTRY_NO_ENTRYPOINT",
                message="No executable entrypoint; add top-level script statements or select an entry protocol explicitly",
                span=ir.span,
                severity="warning",
                node_id=None,
            )
        ],
    )


def collect_user_protocols(ir: IRProgram) -> list[IRProtocol]:
    return list(ir.protocols)


def collect_entry_protocols(ir: IRProgram) -> list[IRProtocol]:
    return [
        protocol
        for protocol in collect_user_protocols(ir)
        if protocol.source_role in (None, "entry")
    ]


def resolve_legacy_single_protocol_entry(ir: IRProgram) -> IRProtocol | None:
    user_protocols = collect_entry_protocols(ir)
    referenced = {
        name
        for protocol in user_protocols
        for name in collect_referenced_protocol_names(protocol.statements)
    }
    candidates = [protocol for protocol in user_protocols if protocol.name not in referenced]
    if len(candidates) == 1:
        return candidates[0]
    return None


def collect_referenced_protocol_names(statements: list[IRStatement]) -> list[str]:
    names: list[str] = []
    for stmt in statements:
        if isinstance(stmt, IRInclude):
            names.append(stmt.name)
        elif isinstance(stmt, IRWithEnv):
            names.extend(collect_referenced_protocol_names(stmt.statements))
        elif isinstance(stmt, IRWithConstraint):
            names.extend(collect_referenced_protocol_names(stmt.statements))
        elif isinstance(stmt, IRRepeat):
            names.extend(collect_referenced_protocol_names(stmt.statements))
        elif isinstance(stmt, IRConditional):
            names.extend(collect_referenced_protocol_names(stmt.then_statements))
            names.extend(collect_referenced_protocol_names(stmt.else_statements))
    return names
