"""Closed prototype contract for author-declared component replacement."""

from __future__ import annotations

from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRCall, IRIdentifier, IRList, IRMember, IRPair, IRString, IRStep
from culsma.pipeline.container_views import resolve_materials_index, resolve_materials_get


def validate_material_replace(
    stmt: IRStep, bindings: dict[str, Any], defined_names: set[str]
) -> list[Diagnostic]:
    def issue(message: str) -> list[Diagnostic]:
        return [Diagnostic(code="SEM_MATERIAL_REPLACE_INVALID", message=message,
                           span=stmt.span, node_id=stmt.id)]
    args = {arg.name: arg.value for arg in stmt.args}
    if len(args) != len(stmt.args) or set(args) != {"self", "subject", "products"}:
        return issue("materials.replace requires subject and products")
    receiver = args["self"]
    if not (isinstance(receiver, IRMember) and receiver.member == "materials"
            and isinstance(receiver.base, IRIdentifier)):
        return issue("replace receiver must be container.materials")
    if receiver.base.name not in defined_names:
        return issue("materials.replace requires a defined container")
    selector = (resolve_materials_index(args["subject"], expr_bindings=bindings)
                or resolve_materials_get(args["subject"], expr_bindings=bindings))
    if selector is None or not isinstance(selector.container, IRIdentifier) or selector.container.name != receiver.base.name:
        return issue("subject must select an entry from the receiver's materials")
    products = args["products"]
    if not isinstance(products, IRList) or not products.elements:
        return issue("products must be a nonempty list of content(...):unknown(dimension = mass)")
    for product in products.elements:
        if not isinstance(product, IRPair) or not isinstance(product.left, IRCall) or product.left.name != "DefineContent":
            return issue("replacement products must be content(...):unknown(dimension = mass)")
        quantity = product.right
        if not isinstance(quantity, IRCall) or quantity.name != "unknown" or len(quantity.args) != 1 or quantity.args[0].name != "dimension":
            return issue("this prototype requires unknown(dimension = mass) for each product")
        dimension = quantity.args[0].value
        if not ((isinstance(dimension, IRIdentifier) and dimension.name == "mass") or
                (isinstance(dimension, IRString) and dimension.value == "mass")):
            return issue("this prototype supports unknown mass only")
    return []
