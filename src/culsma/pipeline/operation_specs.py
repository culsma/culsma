"""Canonical IR builtin operation signatures."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


def _empty_dimensions() -> Mapping[str, frozenset[str]]:
    return MappingProxyType({})


@dataclass(frozen=True)
class OperationSpec:
    required_args: frozenset[str]
    allowed_args: frozenset[str]
    arg_dimensions: Mapping[str, frozenset[str]] = field(default_factory=_empty_dimensions)


def _spec(
    *,
    required: set[str] | frozenset[str] = frozenset(),
    allowed: set[str] | frozenset[str],
    dimensions: dict[str, set[str] | frozenset[str]] | None = None,
) -> OperationSpec:
    return OperationSpec(
        required_args=frozenset(required),
        allowed_args=frozenset(allowed),
        arg_dimensions=MappingProxyType(
            {name: frozenset(expected) for name, expected in (dimensions or {}).items()}
        ),
    )


BUILTIN_OPERATION_SPECS: Mapping[str, OperationSpec] = MappingProxyType(
    {
        "agit": _spec(
            required={"sample", "mode"},
            allowed={"sample", "mode", "duration", "rate", "cycles"},
            dimensions={
                "duration": {"time"},
                "rate": {"rotation_rate"},
            },
        ),
        "sep": _spec(
            required={"sample", "program"},
            allowed={"sample", "program", "component_fates"},
        ),
        "frac": _spec(
            required={"sample", "program"},
            allowed={"sample", "program"},
        ),
        "img": _spec(
            required={"sample", "quantity"},
            allowed={"sample", "quantity", "schema_ref", "save_raw"},
        ),
        "ecp": _spec(
            required={"sample", "quantity"},
            allowed={"sample", "quantity", "schema_ref", "save_raw"},
        ),
        "phy": _spec(
            required={"sample", "quantity"},
            allowed={"sample", "quantity", "schema_ref", "save_raw"},
        ),
        "AllocContainer": _spec(
            required={"kind"},
            allowed={
                "kind",
                "spec",
                "carrier_kind",
                "carrier_id",
                "carrier_position",
                "capacity",
                "label",
                "barcode",
            },
            dimensions={"capacity": {"volume"}},
        ),
        "DefineContent": _spec(
            required={"kind"},
            allowed={"kind", "type", "code", "name", "attrs"},
        ),
        "LoadContent": _spec(
            required={"container", "content", "amount"},
            allowed={"container", "content", "amount"},
            dimensions={"amount": {"volume", "mass", "count"}},
        ),
        "AnnotateContent": _spec(
            required={"content"},
            allowed={"content", "attrs", "name"},
        ),
    }
)
