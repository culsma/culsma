"""Resolve material-container roles from a lowered runtime plan."""

from __future__ import annotations

from typing import Any, Iterator


def collect_container_roles(
    *,
    plan: Any,
    final_material_state: dict[str, Any] | None,
    step_status: dict[str, str] | None = None,
) -> dict[str, set[str]]:
    """Return completed operation roles keyed by stable container id."""

    roles: dict[str, set[str]] = {}
    bindings: dict[str, Any] = {}
    containers: dict[str, Any] = {}
    if isinstance(final_material_state, dict):
        raw_bindings = final_material_state.get("bindings")
        raw_containers = final_material_state.get("containers")
        bindings = raw_bindings if isinstance(raw_bindings, dict) else {}
        containers = raw_containers if isinstance(raw_containers, dict) else {}

    for protocol in getattr(plan, "plans", []):
        for step in getattr(protocol, "steps", []):
            if (
                step_status is not None
                and step_status.get(getattr(step, "step_id", "")) != "completed"
            ):
                continue
            args = getattr(step, "args", {})
            if not isinstance(args, dict):
                continue
            if getattr(step, "op", "") == "Mutation":
                target = _normalize_container_ref(
                    _arg_string(args.get("target")), bindings=bindings, containers=containers
                )
                if target:
                    roles.setdefault(target, set()).add("dest")
                sources = args.get("sources")
                if isinstance(sources, list):
                    for source in sources:
                        if not isinstance(source, dict):
                            continue
                        ref = _normalize_container_ref(
                            _arg_string(source.get("left")),
                            bindings=bindings,
                            containers=containers,
                        )
                        if ref:
                            roles.setdefault(ref, set()).add("source")

            direct_sample = _normalize_container_ref(
                _arg_string(args.get("sample")), bindings=bindings, containers=containers
            )
            if direct_sample:
                roles.setdefault(direct_sample, set()).add("sample")

            for expression in args.values():
                for candidate in _nested_sample_refs(expression):
                    sample = _normalize_container_ref(
                        candidate, bindings=bindings, containers=containers
                    )
                    if sample:
                        roles.setdefault(sample, set()).add("sample")
    return roles


def _nested_sample_refs(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        if value.get("kind") == "IRCall":
            args = value.get("args")
            if isinstance(args, list):
                for arg in args:
                    if not isinstance(arg, dict):
                        continue
                    if arg.get("name") in {"sample", "subject_ref"}:
                        candidate = _arg_string(arg.get("value"))
                        if candidate:
                            yield candidate
                    yield from _nested_sample_refs(arg.get("value"))
        else:
            for nested in value.values():
                yield from _nested_sample_refs(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _nested_sample_refs(nested)


def _arg_string(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value.get("kind") == "IRIdentifier":
        inner = value.get("name")
        return inner if isinstance(inner, str) else None
    if isinstance(value, dict) and value.get("kind") == "IRString":
        inner = value.get("value")
        return inner if isinstance(inner, str) else None
    return None


def _normalize_container_ref(
    name: str | None, *, bindings: dict[str, Any], containers: dict[str, Any]
) -> str | None:
    if not isinstance(name, str) or not name:
        return None
    resolved = bindings.get(name)
    if isinstance(resolved, str) and resolved:
        return resolved
    if name in containers:
        return name
    return name
