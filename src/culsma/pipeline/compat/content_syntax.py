"""Legacy textual constructor inputs and source compatibility diagnostics.

The constructor validator is the source admission boundary. Bare/string tokens
remain accepted in strict mode; that mode controls taxonomy normalization only.
Explicit enum syntax and stricter dynamic binding contracts are a later change.
"""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.parser.ast_nodes import Arg, StringLiteral
from culsma.pipeline.content_vocab import CONTENT_KIND_WHITELIST, is_allowed_content_type
from culsma.pipeline.ir_nodes import IRArg, IRIdentifier, IRString

from .content_taxonomy import normalize_content_classification


def resolve_string_binding(value: Any, literal_bindings: dict[str, Any]) -> str | None:
    """Resolve the existing textual literal or statically known string binding."""
    if isinstance(value, IRString):
        return value.value
    if isinstance(value, IRIdentifier):
        bound = literal_bindings.get(value.name)
        return bound if isinstance(bound, str) else None
    return None


def resolve_kind_token(arg: IRArg | None, literal_bindings: dict[str, Any], defined_names: set[str] | None) -> str | None:
    """Read a kind token without treating an unresolved binding as a literal name."""
    if arg is None:
        return None
    value = resolve_string_binding(arg.value, literal_bindings)
    if value is not None:
        return value
    if isinstance(arg.value, IRIdentifier):
        name = arg.value.name
        if name not in literal_bindings and name not in (defined_names or ()):
            return name
    # Preserve existing handling of non-text values and deferred bindings.
    return None


def resolve_type_token(arg: IRArg | None, literal_bindings: dict[str, Any]) -> str | None:
    """Preserve the pre-enum type token behavior, including unresolved names."""
    if arg is None:
        return None
    value = resolve_string_binding(arg.value, literal_bindings)
    if value is not None:
        return value
    return arg.value.name if isinstance(arg.value, IRIdentifier) else None


def normalization_diagnostics(
    *,
    kind_value: str,
    type_value: str,
    span,
    node_id: str | None,
    compat_mode: bool,
) -> list[Diagnostic]:
    if not compat_mode or is_allowed_content_type(kind_value, type_value):
        return []
    normalized = normalize_content_classification(kind_value, type_value)
    if normalized.kind in CONTENT_KIND_WHITELIST and is_allowed_content_type(normalized.kind, normalized.type):
        suggested = format_content_suggestion(normalized.kind, normalized.type, normalized.attrs)
        return [
            Diagnostic(
                code="SEM_CONTENT_TAXONOMY_COMPAT_NORMALIZED",
                message=(
                    f"Content taxonomy value '{kind_value}/{type_value}' is deprecated; "
                    f"compatibility mode normalizes it to {suggested}. "
                    "Use that canonical content form to avoid this warning."
                ),
                span=span,
                severity="warning",
                node_id=node_id,
            )
        ]
    return []


def format_content_suggestion(kind_value: str, type_value: str, attrs: dict[str, str]) -> str:
    parts = [f'kind="{kind_value}"', f'type="{type_value}"']
    if attrs:
        attrs_text = ", ".join(f'{key}: "{value}"' for key, value in sorted(attrs.items()))
        parts.append(f"attrs={{{attrs_text}}}")
    return f"content({', '.join(parts)})"


LEGACY_CONTENT_CONSTRUCTOR_DEFAULTS = {
    "blood": {"kind": "blood", "type": "whole_blood"},
    "reagent": {"kind": "reagent"},
    "buffer": {"kind": "buffer", "type": "buffer"},
}


def lower_legacy_content_callable(name: str, args: list[Arg], span) -> tuple[str, list[Arg]] | None:
    """Expand retired taxonomy constructors without overriding explicit arguments."""
    defaults = LEGACY_CONTENT_CONSTRUCTOR_DEFAULTS.get(name)
    if defaults is None:
        return None
    lowered_args = list(args)
    existing = {arg.name for arg in args}
    for arg_name, value in defaults.items():
        if arg_name not in existing:
            lowered_args.insert(0, Arg(name=arg_name, value=StringLiteral(value=value, span=span), span=span))
    return "DefineContent", lowered_args
