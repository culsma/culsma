"""Container target-view member-path semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from culsma.pipeline.ir_nodes import (
    IRCall,
    IRIdentifier,
    IRIndex,
    IRMember,
    IRString,
)

CONTAINER_CONTENTS_MEMBER = "contents"
CONTAINER_STRUCTURE_MEMBER = "structure"
CONTAINER_MATERIALS_MEMBER = "materials"
CONTAINER_STRUCTURE_FACETS = frozenset({"top", "bottom", "sidewall"})


@dataclass(frozen=True)
class ContainerTargetView:
    root: Any
    members: tuple[str, ...]
    kind: str
    facet: str | None = None


@dataclass(frozen=True)
class MaterialsIndexExpression:
    """Static shape of ``container.materials[index]``."""

    container: Any
    index: Any


@dataclass(frozen=True)
class MaterialsGetExpression:
    """Static shape of ``container.materials.get(entry_id)``."""

    container: Any
    entry_id: str


def resolve_materials_index(
    expr: Any,
    *,
    expr_bindings: dict[str, Any],
) -> MaterialsIndexExpression | None:
    """Resolve the closed frontend selector shape without reading Runtime state."""

    expr = _resolve_expr_binding(expr, expr_bindings)
    if not isinstance(expr, IRIndex):
        return None
    receiver = expr.base
    if (
        not isinstance(receiver, IRMember)
        or receiver.member != CONTAINER_MATERIALS_MEMBER
    ):
        return None
    return MaterialsIndexExpression(container=receiver.base, index=expr.index)


def resolve_materials_get(
    expr: Any,
    *,
    expr_bindings: dict[str, Any],
) -> MaterialsGetExpression | None:
    """Resolve an exact entry-id selector without reading Runtime state."""

    expr = _resolve_expr_binding(expr, expr_bindings)
    if not isinstance(expr, IRCall) or expr.name != "get":
        return None
    args = {arg.name: arg.value for arg in expr.args}
    if len(args) != len(expr.args) or set(args) != {"self", "arg0"}:
        return None
    receiver = args["self"]
    if (
        not isinstance(receiver, IRMember)
        or receiver.member != CONTAINER_MATERIALS_MEMBER
    ):
        return None
    entry_id = _resolve_expr_binding(args["arg0"], expr_bindings)
    if not isinstance(entry_id, IRString) or not entry_id.value:
        return None
    return MaterialsGetExpression(
        container=receiver.base,
        entry_id=entry_id.value,
    )


def is_container_materials_index(expr: Any) -> bool:
    return (
        isinstance(expr, IRIndex)
        and isinstance(expr.base, IRMember)
        and expr.base.member == CONTAINER_MATERIALS_MEMBER
    )


def _resolve_expr_binding(expr: Any, expr_bindings: dict[str, Any]) -> Any:
    seen: set[str] = set()
    while (
        isinstance(expr, IRIdentifier)
        and expr.name in expr_bindings
        and expr.name not in seen
    ):
        seen.add(expr.name)
        expr = expr_bindings[expr.name]
    return expr


def split_member_path(expr: Any) -> tuple[Any, tuple[str, ...]] | None:
    members: list[str] = []
    current = expr
    while _is_member_expr(current):
        members.append(str(current.member))
        current = current.base
    if not members:
        return None
    members.reverse()
    return current, tuple(members)


def classify_container_target_view(expr: Any) -> ContainerTargetView | None:
    path = split_member_path(expr)
    if path is None:
        return None
    root, members = path
    if members == (CONTAINER_CONTENTS_MEMBER,):
        return ContainerTargetView(root=root, members=members, kind="contents")
    if (
        len(members) == 2
        and members[0] == CONTAINER_STRUCTURE_MEMBER
        and members[1] in CONTAINER_STRUCTURE_FACETS
    ):
        return ContainerTargetView(root=root, members=members, kind="structure_facet", facet=members[1])
    return None


def is_container_target_view(expr: Any) -> bool:
    return classify_container_target_view(expr) is not None


def is_container_target_view_namespace_path(expr: Any) -> bool:
    path = split_member_path(expr)
    if path is None:
        return False
    _, members = path
    return bool(members) and members[0] in {CONTAINER_CONTENTS_MEMBER, CONTAINER_STRUCTURE_MEMBER}


def container_view_path_error(expr: Any) -> str | None:
    path = split_member_path(expr)
    if path is None:
        return None
    _, members = path
    if not members:
        return None
    if members[0] == CONTAINER_CONTENTS_MEMBER:
        if members == (CONTAINER_CONTENTS_MEMBER,):
            return None
        return "container.contents does not define nested target-view members in the current surface"
    if members[0] == CONTAINER_STRUCTURE_MEMBER:
        if members == (CONTAINER_STRUCTURE_MEMBER,):
            return "container.structure is a target-view namespace; select .top, .bottom, or .sidewall"
        if len(members) == 2 and members[1] not in CONTAINER_STRUCTURE_FACETS:
            allowed = ", ".join(sorted(CONTAINER_STRUCTURE_FACETS))
            return f"container.structure only supports facets: {allowed}"
        if len(members) > 2:
            return "container.structure facets are terminal target views in the current surface"
    return None


def container_view_root(expr: Any) -> Any | None:
    view = classify_container_target_view(expr)
    if view is not None:
        return view.root
    path = split_member_path(expr)
    if path is None:
        return None
    root, members = path
    if members and members[0] in {CONTAINER_CONTENTS_MEMBER, CONTAINER_STRUCTURE_MEMBER}:
        return root
    return None


def _is_member_expr(expr: Any) -> bool:
    return hasattr(expr, "base") and hasattr(expr, "member")
