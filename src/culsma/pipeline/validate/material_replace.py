"""Semantic contract for selector-keyed, one-to-one material replacement."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.common.quantity_arithmetic import UNIT_TO_DIMENSION
from culsma.pipeline.container_views import resolve_materials_get, resolve_materials_index
from culsma.pipeline.ir_nodes import (
    IRCall,
    IRIdentifier,
    IRList,
    IRMember,
    IRPair,
    IRQuantity,
    IRString,
    IRStep,
)


def validate_material_replace(
    stmt: IRStep, bindings: dict[str, Any], defined_names: set[str]
) -> list[Diagnostic]:
    def issue(message: str) -> list[Diagnostic]:
        return [
            Diagnostic(
                code="SEM_MATERIAL_REPLACE_INVALID",
                message=message,
                span=stmt.span,
                node_id=stmt.id,
            )
        ]

    args = {arg.name: arg.value for arg in stmt.args}
    if len(args) != len(stmt.args) or set(args) != {"self", "arg0"}:
        return issue("materials.replace requires one selector-to-material map")
    receiver = args["self"]
    if not (
        isinstance(receiver, IRMember)
        and receiver.member == "materials"
        and isinstance(receiver.base, IRIdentifier)
    ):
        return issue("replace receiver must be container.materials")
    if receiver.base.name not in defined_names:
        return issue("materials.replace requires a defined container")

    replacements = args["arg0"]
    if not isinstance(replacements, IRList) or not replacements.elements:
        return issue("replacement map must contain at least one selector-to-material entry")
    for replacement in replacements.elements:
        if not isinstance(replacement, IRPair):
            return issue("replacement map entries must be material-selector:content(...):quantity")
        selector = (
            resolve_materials_index(replacement.left, expr_bindings=bindings)
            or resolve_materials_get(replacement.left, expr_bindings=bindings)
        )
        if (
            selector is None
            or not isinstance(selector.container, IRIdentifier)
            or selector.container.name != receiver.base.name
        ):
            return issue("replacement keys must select entries from the receiver's materials")
        error = _validate_replacement_material(replacement.right)
        if error is not None:
            return issue(error)
    return []


def _validate_replacement_material(value: Any) -> str | None:
    if (
        not isinstance(value, IRPair)
        or not isinstance(value.left, IRCall)
        or value.left.name != "DefineContent"
    ):
        return "each replacement value must be one content(...):quantity material"
    quantity = value.right
    if isinstance(quantity, IRQuantity):
        if quantity.unit is None:
            return "replacement material quantities must carry a unit"
        dimension = UNIT_TO_DIMENSION.get(quantity.unit)
        if dimension not in {"mass", "volume", "count"}:
            return "replacement quantities must use a mass, volume, or count unit"
        if quantity.value < 0:
            return "replacement quantities must be non-negative"
        if dimension == "count" and not float(quantity.value).is_integer():
            return "replacement counts must be whole numbers"
        return None
    if (
        not isinstance(quantity, IRCall)
        or quantity.name != "unknown"
        or len(quantity.args) != 1
        or quantity.args[0].name != "dimension"
    ):
        return "replacement quantity must be unit-bearing or unknown(dimension = mass)"
    dimension = quantity.args[0].value
    if not (
        (isinstance(dimension, IRIdentifier) and dimension.name == "mass")
        or (isinstance(dimension, IRString) and dimension.value == "mass")
    ):
        return "unknown replacement quantities currently support mass only"
    return None
