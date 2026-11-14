"""Canonical IR builtin operation signatures."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from culsma.common.quantity_arithmetic import QuantityDimension


def _empty_dimensions() -> Mapping[str, frozenset[QuantityDimension]]:
    return MappingProxyType({})


@dataclass(frozen=True)
class OperationSpec:
    required_args: frozenset[str]
    allowed_args: frozenset[str]
    arg_dimensions: Mapping[str, frozenset[QuantityDimension]] = field(default_factory=_empty_dimensions)


def _spec(
    *,
    required: set[str] | frozenset[str] = frozenset(),
    allowed: set[str] | frozenset[str],
    dimensions: dict[str, set[QuantityDimension] | frozenset[QuantityDimension]] | None = None,
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
            allowed={"sample", "mode", "motion", "duration", "rate", "cycles", "drive"},
            dimensions={
                "duration": {QuantityDimension.TIME},
                "rate": {QuantityDimension.ROTATION_RATE, QuantityDimension.FREQUENCY},
            },
        ),
        "sep": _spec(
            required={"sample", "program"},
            allowed={"sample", "program", "component_fates", "transitions"},
        ),
        "frac": _spec(
            required={"sample", "program"},
            allowed={"sample", "program", "component_fates"},
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
            dimensions={"capacity": {QuantityDimension.VOLUME}},
        ),
        "DefineContent": _spec(
            required={"kind"},
            allowed={"kind", "type", "code", "name", "attrs", "concentration"},
        ),
        "LoadContent": _spec(
            required={"container", "content", "amount"},
            allowed={"container", "content", "amount", "concentration"},
            dimensions={"amount": {QuantityDimension.VOLUME, QuantityDimension.MASS, QuantityDimension.COUNT}},
        ),
        "AnnotateContent": _spec(
            required={"content"},
            allowed={"content", "attrs", "name"},
        ),
    }
)
