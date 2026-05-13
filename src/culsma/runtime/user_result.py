"""Derived user-facing run summary for runtime results."""

from __future__ import annotations

from typing import Any

from culsma.pipeline.content_vocab import ContentKind, ContentType
from culsma.pipeline.program_registry import program_tool_label


def build_user_result(
    *,
    ok: bool,
    diagnostics: list[Any],
    state: Any,
    events: list[Any],
    plan: Any,
    initial_material_state: dict[str, Any] | None,
) -> dict[str, Any]:
    status_counts = {
        "total_steps": len(state.step_status),
        "completed_steps": sum(1 for s in state.step_status.values() if s == "completed"),
        "failed_steps": sum(1 for s in state.step_status.values() if s == "failed"),
        "skipped_steps": sum(1 for s in state.step_status.values() if s == "skipped"),
    }
    execution = {
        "ok": ok,
        "diagnostic_count": len(diagnostics),
        **status_counts,
    }
    base = {
        "schema": "lab_report_v1",
        "execution": execution,
    }

    final_material_state = getattr(state, "artifacts", {}).get("material_state")
    if not isinstance(final_material_state, dict):
        base["headline"] = _headline(execution)
        base["materials"] = {
            "has_material_state": False,
            "input_inventory": [],
            "final_products": [],
            "intermediate_materials": [],
            "reagent_consumption": [],
        }
        base["qc_results"] = []
        base["resource_summary"] = {
            "containers": _container_usage_summary(plan=plan, final_material_state=None),
            "instruments": _instrument_usage_summary(plan=plan),
        }
        base["process_summary"] = {
            "mutation_steps": 0,
            "separation_steps": 0,
            "environment_steps": 0,
            "readout_steps": 0,
        }
        base["alerts"] = _alerts(diagnostics)
        return base

    initial_containers = (
        initial_material_state.get("containers", {}) if isinstance(initial_material_state, dict) else {}
    )
    final_containers = final_material_state.get("containers", {})
    initial_containers = initial_containers if isinstance(initial_containers, dict) else {}
    final_containers = final_containers if isinstance(final_containers, dict) else {}

    container_stats: dict[str, dict[str, Any]] = {}

    for name in sorted(set(initial_containers.keys()) | set(final_containers.keys())):
        before = _container_metrics(initial_containers.get(name))
        after = _container_metrics(final_containers.get(name))
        delta = {
            "volume_uL": round(after["volume_uL"] - before["volume_uL"], 6),
            "mass_mg": round(after["mass_mg"] - before["mass_mg"], 6),
            "components_total": round(after["components_total"] - before["components_total"], 6),
        }
        container_stats[name] = {
            "before": before,
            "after": after,
            "delta": delta,
            "final_raw": final_containers.get(name),
        }

    measurements = final_material_state.get("measurements", [])
    measurements = measurements if isinstance(measurements, list) else []
    calculations = _extract_calculation_summary(events)
    artifacts = getattr(state, "artifacts", None)
    if isinstance(artifacts, dict):
        data_objects = artifacts.get("data_objects", {})
        if isinstance(data_objects, dict):
            calculations["readout_steps"] = max(calculations.get("readout_steps", 0), len(data_objects))
    roles = _collect_container_roles(plan=plan, final_material_state=final_material_state)
    input_inventory = _input_inventory(initial_containers=initial_containers)
    content_registry = final_material_state.get("content_registry", {})
    content_registry = content_registry if isinstance(content_registry, dict) else {}
    final_products = _final_products(
        container_stats=container_stats,
        roles=roles,
        measurements=measurements,
        content_registry=content_registry,
    )
    intermediate_materials = _intermediate_materials(
        container_stats=container_stats,
        roles=roles,
        final_products=final_products,
        content_registry=content_registry,
    )
    reagent_consumption = _reagent_consumption(
        container_stats=container_stats,
        roles=roles,
        initial_containers=initial_containers,
        bindings=final_material_state.get("bindings", {}),
        containers=final_containers,
        events=events,
    )
    qc_results = _qc_results(measurements)
    alerts = _alerts(diagnostics)

    base["headline"] = _headline(execution)
    base["materials"] = {
        "has_material_state": True,
        "input_inventory": input_inventory,
        "final_products": final_products,
        "intermediate_materials": intermediate_materials,
        "reagent_consumption": reagent_consumption,
    }
    base["qc_results"] = qc_results
    base["resource_summary"] = {
        "containers": _container_usage_summary(plan=plan, final_material_state=final_material_state),
        "instruments": _instrument_usage_summary(plan=plan),
    }
    base["process_summary"] = calculations
    base["alerts"] = alerts
    return base


def _container_metrics(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {"volume_uL": 0.0, "mass_mg": 0.0, "components_total": 0.0}
    comp = raw.get("components", {})
    if isinstance(comp, dict):
        comp_total = sum(float(v) for v in comp.values())
    else:
        comp_total = 0.0
    return {
        "volume_uL": float(raw.get("volume_uL", 0.0)),
        "mass_mg": float(raw.get("mass_mg", 0.0)),
        "components_total": float(comp_total),
    }


def _has_material(metrics: dict[str, float]) -> bool:
    return metrics["volume_uL"] > 1e-12 or metrics["mass_mg"] > 1e-12 or metrics["components_total"] > 1e-12


def _extract_calculation_summary(events: list[Any]) -> dict[str, Any]:
    out = {
        "mutation_steps": 0,
        "separation_steps": 0,
        "environment_steps": 0,
        "readout_steps": 0,
    }
    for event in events:
        if getattr(event, "kind", None) != "STEP_STARTED":
            continue
        payload = getattr(event, "payload", None)
        if not isinstance(payload, dict):
            continue
        op = str(payload.get("op", ""))
        if op == "Mutation":
            out["mutation_steps"] += 1
        elif op == "sep":
            out["separation_steps"] += 1
        elif op == "env_hold":
            out["environment_steps"] += 1
        elif op in {"img", "ecp", "phy"}:
            out["readout_steps"] += 1
    return out


def _headline(execution: dict[str, Any]) -> str:
    if execution.get("ok"):
        return "Experiment completed successfully with no runtime errors."
    return "Experiment did not complete successfully; review alerts for blocking issues."


def _alerts(diagnostics: list[Any]) -> list[str]:
    if not diagnostics:
        return []
    return [f"{d.code}: {d.message}" for d in diagnostics[:5]]


def _arg_string_from_plan(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and value.get("kind") == "IRIdentifier":
        inner = value.get("name")
        return inner if isinstance(inner, str) else None
    if isinstance(value, dict) and value.get("kind") == "IRString":
        inner = value.get("value")
        return inner if isinstance(inner, str) else None
    return None


def _collect_container_roles(*, plan: Any, final_material_state: dict[str, Any] | None) -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {}
    bindings = {}
    containers = {}
    if isinstance(final_material_state, dict):
        raw_bindings = final_material_state.get("bindings")
        raw_containers = final_material_state.get("containers")
        bindings = raw_bindings if isinstance(raw_bindings, dict) else {}
        containers = raw_containers if isinstance(raw_containers, dict) else {}
    for protocol in getattr(plan, "plans", []):
        for step in getattr(protocol, "steps", []):
            args = getattr(step, "args", {})
            if not isinstance(args, dict):
                continue
            if getattr(step, "op", "") == "Mutation":
                target = _normalize_container_ref(
                    _arg_string_from_plan(args.get("target")),
                    bindings=bindings,
                    containers=containers,
                )
                if target:
                    roles.setdefault(target, set()).add("dest")
                sources = args.get("sources")
                if isinstance(sources, list):
                    for source in sources:
                        if not isinstance(source, dict):
                            continue
                        left = source.get("left")
                        ref = _normalize_container_ref(
                            _arg_string_from_plan(left),
                            bindings=bindings,
                            containers=containers,
                        )
                        if ref:
                            roles.setdefault(ref, set()).add("source")
            sample = _normalize_container_ref(
                _arg_string_from_plan(args.get("sample")),
                bindings=bindings,
                containers=containers,
            )
            if sample:
                roles.setdefault(sample, set()).add("sample")
    return roles


def _normalize_container_ref(name: str | None, *, bindings: dict[str, Any], containers: dict[str, Any]) -> str | None:
    if not isinstance(name, str) or not name:
        return None
    resolved = bindings.get(name)
    if isinstance(resolved, str) and resolved:
        return resolved
    if name in containers:
        return name
    return name


def _final_products(
    *,
    container_stats: dict[str, dict[str, Any]],
    roles: dict[str, set[str]],
    measurements: list[Any],
    content_registry: dict[str, Any],
) -> list[dict[str, Any]]:
    measured_names = {
        str(m.get("sample"))
        for m in measurements
        if isinstance(m, dict) and isinstance(m.get("sample"), str)
    }
    rows: list[dict[str, Any]] = []
    for name, data in container_stats.items():
        after = data["after"]
        delta = data["delta"]
        if after["volume_uL"] <= 1e-9 and after["mass_mg"] <= 1e-9:
            continue
        if "::" in name:
            continue
        name_roles = roles.get(name, set())
        is_reagent_only = "source" in name_roles and not (name_roles & {"dest", "mix_target", "sample"})
        if is_reagent_only and name not in measured_names:
            continue
        if not (
            delta["volume_uL"] > 1e-9
            or delta["mass_mg"] > 1e-9
            or name in measured_names
        ):
            continue
        if not (name_roles & {"dest", "mix_target", "sample"} or name in measured_names):
            continue
        rows.append(
            _merge_row_with_state(
                {
                "name": name,
                "volume_uL": round(after["volume_uL"], 3),
                "volume_mL": round(after["volume_uL"] / 1000.0, 6),
                },
                data.get("final_raw"),
                content_registry=content_registry,
            )
        )
    rows.sort(key=lambda x: x["volume_uL"], reverse=True)
    return rows[:8]


def _input_inventory(*, initial_containers: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, raw in initial_containers.items():
        if "::" in name:
            continue
        metrics = _container_metrics(raw)
        if not _has_material(metrics):
            continue
        rows.append(
            {
                "name": name,
                "initial_uL": round(metrics["volume_uL"], 3),
                "initial_mL": round(metrics["volume_uL"] / 1000.0, 6),
                "initial_mg": round(metrics["mass_mg"], 3),
            }
        )
    rows.sort(key=lambda x: x["initial_uL"], reverse=True)
    return rows[:20]


def _intermediate_materials(
    *,
    container_stats: dict[str, dict[str, Any]],
    roles: dict[str, set[str]],
    final_products: list[dict[str, Any]],
    content_registry: dict[str, Any],
) -> list[dict[str, Any]]:
    final_names = {x["name"] for x in final_products}
    rows: list[dict[str, Any]] = []
    for name, data in container_stats.items():
        if name in final_names or "::" in name:
            continue
        after = data["after"]
        if after["volume_uL"] <= 1e-9:
            continue
        name_roles = roles.get(name, set())
        is_process_container = bool(name_roles & {"dest", "mix_target"}) and not _is_user_output_name(name)
        if not is_process_container:
            continue
        rows.append(
            _merge_row_with_state(
                {
                "name": name,
                "final_uL": round(after["volume_uL"], 3),
                "final_mL": round(after["volume_uL"] / 1000.0, 6),
                },
                data.get("final_raw"),
                content_registry=content_registry,
            )
        )
    rows.sort(key=lambda x: x["final_uL"], reverse=True)
    return rows[:10]


def _reagent_consumption(
    *,
    container_stats: dict[str, dict[str, Any]],
    roles: dict[str, set[str]],
    initial_containers: dict[str, Any],
    bindings: dict[str, Any],
    containers: dict[str, Any],
    events: list[Any],
) -> list[dict[str, Any]]:
    if not initial_containers:
        return _reagent_consumption_from_events(
            events=events,
            roles=roles,
            bindings=bindings,
            containers=containers,
        )
    rows: list[dict[str, Any]] = []
    for name in initial_containers.keys():
        if "::" in name:
            continue
        data = container_stats.get(name)
        if not isinstance(data, dict):
            continue
        before = data["before"]
        after = data["after"]
        consumed_uL = max(0.0, before["volume_uL"] - after["volume_uL"])
        consumed_mg = max(0.0, before["mass_mg"] - after["mass_mg"])
        if consumed_uL <= 1e-9 and consumed_mg <= 1e-9:
            continue
        name_roles = roles.get(name, set())
        rows.append(
            {
                "name": name,
                "roles": sorted(name_roles),
                "consumed_uL": round(consumed_uL, 3),
                "consumed_mL": round(consumed_uL / 1000.0, 6),
                "consumed_mg": round(consumed_mg, 3),
            }
        )
    rows.sort(key=lambda x: x["consumed_uL"], reverse=True)
    return rows[:20]


def _reagent_consumption_from_events(
    *,
    events: list[Any],
    roles: dict[str, set[str]],
    bindings: dict[str, Any],
    containers: dict[str, Any],
) -> list[dict[str, Any]]:
    totals_uL: dict[str, float] = {}
    totals_mg: dict[str, float] = {}
    for event in events:
        if getattr(event, "kind", None) != "STEP_COMPLETED":
            continue
        payload = getattr(event, "payload", None)
        if not isinstance(payload, dict):
            continue
        delta = payload.get("material_delta")
        if not isinstance(delta, dict):
            continue
        _accumulate_consumption_from_delta(delta=delta, totals_uL=totals_uL, totals_mg=totals_mg)
    rows = [
        {
            "name": _display_container_name(name, bindings=bindings, containers=containers),
            "roles": sorted(roles.get(name, set())),
            "consumed_uL": round(value_uL, 3),
            "consumed_mL": round(value_uL / 1000.0, 6),
            "consumed_mg": round(totals_mg.get(name, 0.0), 3) if name in totals_mg else None,
        }
        for name, value_uL in totals_uL.items()
        if value_uL > 1e-9 or totals_mg.get(name, 0.0) > 1e-9
    ]
    rows.sort(key=lambda x: x["consumed_uL"], reverse=True)
    return rows[:20]


def _accumulate_consumption_from_delta(
    *,
    delta: dict[str, Any],
    totals_uL: dict[str, float],
    totals_mg: dict[str, float],
) -> None:
    if str(delta.get("op", "")) == "Mutation":
        for item in delta.get("sources", []):
            if not isinstance(item, dict):
                continue
            nested = item.get("transfer_delta")
            if isinstance(nested, dict):
                _accumulate_consumption_from_delta(delta=nested, totals_uL=totals_uL, totals_mg=totals_mg)
            nested = item.get("collection_delta")
            if isinstance(nested, dict):
                _accumulate_consumption_from_delta(delta=nested, totals_uL=totals_uL, totals_mg=totals_mg)
            _accumulate_consumption_from_source_like(item=item, totals_uL=totals_uL, totals_mg=totals_mg)
        return

    _accumulate_consumption_from_source_like(item=delta, totals_uL=totals_uL, totals_mg=totals_mg)


def _accumulate_consumption_from_source_like(
    *,
    item: dict[str, Any],
    totals_uL: dict[str, float],
    totals_mg: dict[str, float],
) -> None:
    source = item.get("source")
    if not isinstance(source, str) or not source:
        return

    amount_uL = _first_positive_number(
        item.get("moved_uL"),
        item.get("removed_uL"),
        item.get("requested_uL"),
        item.get("converted_uL"),
    )
    amount_mg = _first_positive_number(
        item.get("moved_mg"),
        item.get("removed_mg"),
        item.get("requested_mg"),
        item.get("converted_mg"),
    )

    if amount_uL is not None:
        totals_uL[source] = totals_uL.get(source, 0.0) + amount_uL
    if amount_mg is not None:
        totals_mg[source] = totals_mg.get(source, 0.0) + amount_mg


def _first_positive_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, (int, float)) and float(value) > 1e-9:
            return float(value)
    return None


def _display_container_name(
    container_id: str,
    *,
    bindings: dict[str, Any],
    containers: dict[str, Any],
) -> str:
    raw_container = containers.get(container_id)
    if isinstance(raw_container, dict):
        metadata = raw_container.get("metadata")
        if isinstance(metadata, dict):
            label = metadata.get("label")
            if isinstance(label, str) and label:
                return label

    aliases = []
    for alias, resolved in bindings.items():
        if resolved != container_id or not isinstance(alias, str):
            continue
        if alias == container_id or "::" in alias:
            continue
        aliases.append(alias)
    if aliases:
        aliases.sort(key=lambda item: (item.startswith(("tube::", "well::", "surface::", "chamber::")), len(item), item))
        return aliases[0]
    return container_id


def _qc_results(measurements: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in measurements:
        if not isinstance(m, dict):
            continue
        method = str(m.get("method", ""))
        if method == "UV":
            out.append(
                {
                    "item": f"{m.get('sample', 'sample')} UV",
                    "concentration_estimate": m.get("concentration_estimate"),
                    "a260_estimate": m.get("a260_estimate"),
                }
            )
        elif method == "Fluorescence":
            out.append(
                {
                    "item": f"{m.get('sample', 'sample')} qPCR",
                    "ct_estimate": m.get("ct_estimate"),
                    "template_total": m.get("template_total"),
                }
            )
        else:
            out.append({"item": f"{m.get('sample', 'sample')} {method}".strip(), "value": m})
    return out


def _is_user_output_name(name: str) -> bool:
    token = name.lower()
    markers = ("solution", "well", "plate", "cdna", "rna", "dna", "pellet")
    return any(m in token for m in markers)


def _merge_row_with_state(
    row: dict[str, Any],
    raw_container: Any,
    *,
    content_registry: dict[str, Any],
) -> dict[str, Any]:
    out = dict(row)
    out.update(_derived_container_state(raw_container, content_registry=content_registry))
    return out


def _derived_container_state(raw_container: Any, *, content_registry: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw_container, dict):
        return {
            "mass_mg": None,
            "primary_component": None,
        }
    components = raw_container.get("components")
    if not isinstance(components, dict):
        components = {}
    primary_component, _ = _select_primary_component(
        components,
        content_registry=content_registry,
    )
    return {
        "mass_mg": round(float(raw_container.get("mass_mg", 0.0)), 3),
        "primary_component": primary_component,
    }


def _select_primary_component(
    components: dict[str, Any],
    *,
    content_registry: dict[str, Any],
) -> tuple[str | None, float | None]:
    if not components:
        return None, None

    candidates: list[tuple[str, float, bool]] = []
    for name, amount in components.items():
        amount_f = float(amount)
        meta = content_registry.get(name)
        meta = meta if isinstance(meta, dict) else {}
        kind = str(meta.get("content_kind", "")).lower()
        content_type = str(meta.get("content_type", "")).lower()
        is_background = kind == ContentKind.BUFFER.value or content_type == ContentType.DILUENT.value
        candidates.append((str(name), amount_f, is_background))

    preferred = [(name, amount) for name, amount, is_background in candidates if not is_background]
    selected = preferred if preferred else [(name, amount) for name, amount, _ in candidates]
    return max(selected, key=lambda item: item[1])


def _container_usage_summary(*, plan: Any, final_material_state: dict[str, Any] | None) -> dict[str, Any]:
    allocated = 0
    kind_counts: dict[str, int] = {}
    for protocol in getattr(plan, "plans", []):
        for step in getattr(protocol, "steps", []):
            if getattr(step, "op", "") != "AllocContainer":
                continue
            allocated += 1
            kind = _arg_string_from_plan(getattr(step, "args", {}).get("kind")) or "unknown"
            kind_counts[kind] = kind_counts.get(kind, 0) + 1

    touched_names: list[str] = []
    if isinstance(final_material_state, dict):
        containers = final_material_state.get("containers", {})
        if isinstance(containers, dict):
            touched_names = sorted(name for name in containers.keys() if "::" not in name)

    return {
        "allocated_count": allocated,
        "touched_count": len(touched_names),
        "container_kinds": [
            {"kind": kind, "count": count}
            for kind, count in sorted(kind_counts.items(), key=lambda item: item[0])
        ],
        "touched_names": touched_names[:50],
    }


def _instrument_usage_summary(*, plan: Any) -> dict[str, Any]:
    tool_counts: dict[str, int] = {}
    device_counts: dict[str, int] = {}
    for protocol in getattr(plan, "plans", []):
        for step in getattr(protocol, "steps", []):
            args = getattr(step, "args", {})
            if not isinstance(args, dict):
                continue
            program = args.get("program")
            if isinstance(program, dict):
                device = _program_arg_string(program, "device")
                if device:
                    device_counts[device] = device_counts.get(device, 0) + 1
            device = _arg_string_from_plan(args.get("device"))
            if device:
                device_counts[device] = device_counts.get(device, 0) + 1

    return {
        "tools": [
            {"name": name, "count": count}
            for name, count in sorted(tool_counts.items(), key=lambda item: item[0])
        ],
        "devices": [
            {"name": name, "count": count}
            for name, count in sorted(device_counts.items(), key=lambda item: item[0])
        ],
    }


def _program_arg_string(program: Any, name: str) -> str | None:
    if not isinstance(program, dict):
        return None
    args = program.get("args")
    if not isinstance(args, list):
        return None
    for arg in args:
        if not isinstance(arg, dict):
            continue
        if arg.get("name") != name:
            continue
        return _arg_string_from_plan(arg.get("value"))
    return None


def _program_tool_name(program: Any) -> str | None:
    if not isinstance(program, dict):
        return None
    if program.get("kind") != "IRCall":
        return None
    name = program.get("name")
    if not isinstance(name, str):
        return None
    return program_tool_label(name)
