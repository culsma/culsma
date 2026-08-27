"""Derived user-facing run summary for runtime results."""

from __future__ import annotations

from typing import Any

from culsma.pipeline.content_vocab import ContentKind, ContentType
from culsma.pipeline.program_registry import program_tool_label
from culsma.runtime.material.accounting import MaterialAccounting, MaterialAccountingRecorder
from culsma.runtime.material.ledger import container_count_cells
from culsma.runtime.report import (
    ContainerKindCount,
    ContainerResourceSummary,
    ExecutionSummary,
    FinalProductRow,
    InputInventoryRow,
    IntermediateMaterialRow,
    InstrumentSummary,
    LabReport,
    MaterialsReport,
    NamedCount,
    ProcessSummary,
    QcResult,
    ReagentConsumptionRow,
    ResourceSummary,
)


def build_user_result(
    *,
    ok: bool,
    diagnostics: list[Any],
    state: Any,
    events: list[Any],
    plan: Any,
    initial_material_state: dict[str, Any] | None,
    material_accounting: MaterialAccounting | None = None,
) -> dict[str, Any]:
    """Compatibility adapter for callers that already hold runtime inputs."""
    if material_accounting is None:
        return build_unexecuted_report(
            ok=ok,
            diagnostics=diagnostics,
            state=state,
            plan=plan,
            initial_material_state=initial_material_state,
        )
    return ReportBuilder().build(
        ok=ok,
        diagnostics=diagnostics,
        state=state,
        plan=plan,
        initial_material_state=initial_material_state,
        material_accounting=material_accounting,
    ).to_dict()


def build_unexecuted_report(
    *,
    ok: bool,
    diagnostics: list[Any],
    state: Any,
    plan: Any,
    initial_material_state: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the stable report shape when frontend errors prevented execution."""
    accounting = MaterialAccountingRecorder().initialize(initial_material_state)
    return ReportBuilder().build(
        ok=ok,
        diagnostics=diagnostics,
        state=state,
        plan=plan,
        initial_material_state=initial_material_state,
        material_accounting=accounting,
    ).to_dict()


class ReportBuilder:
    def build(
        self,
        *,
        ok: bool,
        diagnostics: list[Any],
        state: Any,
        plan: Any,
        initial_material_state: dict[str, Any] | None,
        material_accounting: MaterialAccounting,
    ) -> LabReport:
        return _build_report(
            ok=ok,
            diagnostics=diagnostics,
            state=state,
            plan=plan,
            initial_material_state=initial_material_state,
            material_accounting=material_accounting,
        )


def _build_report(
    *,
    ok: bool,
    diagnostics: list[Any],
    state: Any,
    plan: Any,
    initial_material_state: dict[str, Any] | None,
    material_accounting: MaterialAccounting,
) -> LabReport:
    execution = ExecutionSummary(
        ok=ok,
        diagnostic_count=len(diagnostics),
        total_steps=len(state.step_status),
        completed_steps=sum(1 for s in state.step_status.values() if s == "completed"),
        failed_steps=sum(1 for s in state.step_status.values() if s == "failed"),
        skipped_steps=sum(1 for s in state.step_status.values() if s == "skipped"),
    )

    final_material_state = getattr(state, "artifacts", {}).get("material_state")
    if not isinstance(final_material_state, dict):
        return LabReport(
            execution=execution,
            headline=_headline(execution),
            materials=MaterialsReport(has_material_state=False),
            qc_results=[],
            resource_summary=ResourceSummary(
                containers=_container_usage_summary(plan=plan, final_material_state=None),
                instruments=_instrument_usage_summary(plan=plan),
            ),
            process_summary=ProcessSummary(),
            alerts=_alerts(diagnostics),
        )

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
            "count_cells": round(after["count_cells"] - before["count_cells"], 6),
        }
        container_stats[name] = {
            "before": before,
            "after": after,
            "delta": delta,
            "final_raw": final_containers.get(name),
        }

    measurements = final_material_state.get("measurements", [])
    measurements = measurements if isinstance(measurements, list) else []
    calculations = _extract_calculation_summary(plan=plan, state=state)
    artifacts = getattr(state, "artifacts", None)
    if isinstance(artifacts, dict):
        data_objects = artifacts.get("data_objects", {})
        if isinstance(data_objects, dict):
            calculations = ProcessSummary(
                mutation_steps=calculations.mutation_steps,
                separation_steps=calculations.separation_steps,
                environment_steps=calculations.environment_steps,
                readout_steps=max(calculations.readout_steps, len(data_objects)),
            )
    roles = _collect_container_roles(plan=plan, final_material_state=final_material_state)
    input_inventory = _input_inventory(material_accounting)
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
    reagent_consumption = _reagent_consumption(material_accounting, roles=roles)
    qc_results = _qc_results(measurements)
    alerts = _alerts(diagnostics)

    return LabReport(
        execution=execution,
        headline=_headline(execution),
        materials=MaterialsReport(
            has_material_state=True,
            input_inventory=input_inventory,
            final_products=final_products,
            intermediate_materials=intermediate_materials,
            reagent_consumption=reagent_consumption,
        ),
        qc_results=qc_results,
        resource_summary=ResourceSummary(
            containers=_container_usage_summary(plan=plan, final_material_state=final_material_state),
            instruments=_instrument_usage_summary(plan=plan),
        ),
        process_summary=calculations,
        alerts=alerts,
    )


def _container_metrics(raw: Any) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {"volume_uL": 0.0, "mass_mg": 0.0, "components_total": 0.0, "count_cells": 0.0}
    comp = raw.get("components", {})
    if isinstance(comp, dict):
        comp_total = sum(float(v) for v in comp.values())
    else:
        comp_total = 0.0
    return {
        "volume_uL": float(raw.get("volume_uL", 0.0)),
        "mass_mg": float(raw.get("mass_mg", 0.0)),
        "components_total": float(comp_total),
        "count_cells": container_count_cells(raw),
    }


def _has_material(metrics: dict[str, float]) -> bool:
    return (
        metrics["volume_uL"] > 1e-12
        or metrics["mass_mg"] > 1e-12
        or metrics["components_total"] > 1e-12
        or metrics["count_cells"] > 1e-12
    )


def _extract_calculation_summary(*, plan: Any, state: Any) -> ProcessSummary:
    mutation_steps = 0
    separation_steps = 0
    environment_steps = 0
    readout_steps = 0
    statuses = getattr(state, "step_status", {})
    statuses = statuses if isinstance(statuses, dict) else {}
    for protocol in getattr(plan, "plans", []):
        for step in getattr(protocol, "steps", []):
            if statuses.get(getattr(step, "step_id", "")) != "completed":
                continue
            op = str(getattr(step, "op", ""))
            if op == "Mutation":
                mutation_steps += 1
            elif op == "sep":
                separation_steps += 1
            elif op == "env_hold":
                environment_steps += 1
            elif op in {"img", "ecp", "phy"}:
                readout_steps += 1
    return ProcessSummary(
        mutation_steps=mutation_steps,
        separation_steps=separation_steps,
        environment_steps=environment_steps,
        readout_steps=readout_steps,
    )


def _headline(execution: ExecutionSummary) -> str:
    if execution.ok:
        return "Experiment completed successfully with no runtime errors."
    return "Experiment did not complete successfully; review alerts for blocking issues."


def _alerts(diagnostics: list[Any]) -> list[str]:
    if not diagnostics:
        return []
    return [f"{d.code}: {d.message}" for d in diagnostics]


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
) -> list[FinalProductRow]:
    measured_names = {
        str(m.get("sample"))
        for m in measurements
        if isinstance(m, dict) and isinstance(m.get("sample"), str)
    }
    rows: list[FinalProductRow] = []
    for name, data in container_stats.items():
        after = data["after"]
        delta = data["delta"]
        if after["volume_uL"] <= 1e-9 and after["mass_mg"] <= 1e-9 and after["count_cells"] <= 1e-9:
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
            or delta["count_cells"] > 1e-9
            or name in measured_names
        ):
            continue
        if not (name_roles & {"dest", "mix_target", "sample"} or name in measured_names):
            continue
        mass_mg, primary_component = _derived_container_state(
            data.get("final_raw"),
            content_registry=content_registry,
        )
        rows.append(
            FinalProductRow(
                name=name,
                volume_uL=round(after["volume_uL"], 3),
                volume_mL=round(after["volume_uL"] / 1000.0, 6),
                mass_mg=mass_mg,
                primary_component=primary_component,
                count_cells=round(after["count_cells"], 3),
            )
        )
    rows.sort(key=lambda x: x.volume_uL, reverse=True)
    return rows


def _input_inventory(accounting: MaterialAccounting) -> list[InputInventoryRow]:
    totals: dict[str, tuple[float, float, float]] = {}
    for lot in accounting.list_input_lots():
        volume_uL, mass_mg, count_cells = totals.get(lot.name, (0.0, 0.0, 0.0))
        totals[lot.name] = (
            volume_uL + lot.initial.volume_uL,
            mass_mg + lot.initial.mass_mg,
            count_cells + lot.initial.count_cells,
        )
    rows = [
        InputInventoryRow(
            name=name,
            initial_uL=round(volume_uL, 3),
            initial_mL=round(volume_uL / 1000.0, 6),
            initial_mg=round(mass_mg, 3),
            initial_cells=round(count_cells, 3),
        )
        for name, (volume_uL, mass_mg, count_cells) in totals.items()
    ]
    rows.sort(key=lambda row: (-row.initial_uL, -row.initial_mg, -row.initial_cells, row.name))
    return rows


def _intermediate_materials(
    *,
    container_stats: dict[str, dict[str, Any]],
    roles: dict[str, set[str]],
    final_products: list[FinalProductRow],
    content_registry: dict[str, Any],
) -> list[IntermediateMaterialRow]:
    final_names = {x.name for x in final_products}
    rows: list[IntermediateMaterialRow] = []
    for name, data in container_stats.items():
        if name in final_names or "::" in name:
            continue
        after = data["after"]
        if after["volume_uL"] <= 1e-9 and after["count_cells"] <= 1e-9:
            continue
        name_roles = roles.get(name, set())
        is_process_container = bool(name_roles & {"dest", "mix_target"}) and not _is_user_output_name(name)
        if not is_process_container:
            continue
        mass_mg, primary_component = _derived_container_state(
            data.get("final_raw"),
            content_registry=content_registry,
        )
        rows.append(
            IntermediateMaterialRow(
                name=name,
                final_uL=round(after["volume_uL"], 3),
                final_mL=round(after["volume_uL"] / 1000.0, 6),
                mass_mg=mass_mg,
                primary_component=primary_component,
                count_cells=round(after["count_cells"], 3),
            )
        )
    rows.sort(key=lambda x: x.final_uL, reverse=True)
    return rows


def _reagent_consumption(
    accounting: MaterialAccounting,
    *,
    roles: dict[str, set[str]],
) -> list[ReagentConsumptionRow]:
    consumed = accounting.consumption_by_input()
    totals: dict[str, tuple[float, float, float, set[str]]] = {}
    for lot in accounting.list_input_lots():
        quantity = consumed.get(lot.lot_id)
        if quantity is None or (
            quantity.volume_uL <= 1e-9
            and quantity.mass_mg <= 1e-9
            and quantity.count_cells <= 1e-9
        ):
            continue
        volume_uL, mass_mg, count_cells, row_roles = totals.get(lot.name, (0.0, 0.0, 0.0, set()))
        totals[lot.name] = (
            volume_uL + quantity.volume_uL,
            mass_mg + quantity.mass_mg,
            count_cells + quantity.count_cells,
            row_roles | roles.get(lot.container_id, set()),
        )
    rows = [
        ReagentConsumptionRow(
            name=name,
            roles=sorted(row_roles),
            consumed_uL=round(volume_uL, 3) if volume_uL > 1e-9 else None,
            consumed_mL=round(volume_uL / 1000.0, 6) if volume_uL > 1e-9 else None,
            consumed_mg=round(mass_mg, 3) if mass_mg > 1e-9 else None,
            consumed_cells=round(count_cells, 3) if count_cells > 1e-9 else None,
        )
        for name, (volume_uL, mass_mg, count_cells, row_roles) in totals.items()
    ]
    rows.sort(
        key=lambda row: (
            -(row.consumed_uL or 0.0),
            -(row.consumed_mg or 0.0),
            -(row.consumed_cells or 0.0),
            row.name,
        )
    )
    return rows


def _qc_results(measurements: list[Any]) -> list[QcResult]:
    out: list[QcResult] = []
    for m in measurements:
        if not isinstance(m, dict):
            continue
        method = str(m.get("method", ""))
        if method == "UV":
            out.append(
                QcResult(
                    item=f"{m.get('sample', 'sample')} UV",
                    values={
                        "concentration_estimate": m.get("concentration_estimate"),
                        "a260_estimate": m.get("a260_estimate"),
                    },
                )
            )
        elif method == "Fluorescence":
            out.append(
                QcResult(
                    item=f"{m.get('sample', 'sample')} qPCR",
                    values={
                        "ct_estimate": m.get("ct_estimate"),
                        "template_total": m.get("template_total"),
                    },
                )
            )
        else:
            out.append(
                QcResult(
                    item=f"{m.get('sample', 'sample')} {method}".strip(),
                    values={"value": m},
                )
            )
    return out


def _is_user_output_name(name: str) -> bool:
    token = name.lower()
    markers = ("solution", "well", "plate", "cdna", "rna", "dna", "pellet")
    return any(m in token for m in markers)


def _derived_container_state(
    raw_container: Any,
    *,
    content_registry: dict[str, Any],
) -> tuple[float | None, str | None]:
    if not isinstance(raw_container, dict):
        return None, None
    components = raw_container.get("components")
    if not isinstance(components, dict):
        components = {}
    primary_component, _ = _select_primary_component(
        components,
        content_registry=content_registry,
    )
    return round(float(raw_container.get("mass_mg", 0.0)), 3), primary_component


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
        if amount_f <= 1e-9:
            continue
        meta = content_registry.get(name)
        meta = meta if isinstance(meta, dict) else {}
        kind = str(meta.get("content_kind", "")).lower()
        content_type = str(meta.get("content_type", "")).lower()
        attrs = meta.get("content_attrs")
        attrs = attrs if isinstance(attrs, dict) else {}
        role = str(attrs.get("role", "") or "").lower()
        is_background = (
            (kind == ContentKind.FORMULATION.value and content_type == ContentType.BUFFER.value)
            or (kind == ContentKind.CHEMICAL.value and content_type == ContentType.SOLVENT.value and role == "carrier")
        )
        candidates.append((str(name), amount_f, is_background))

    if not candidates:
        return None, None
    preferred = [(name, amount) for name, amount, is_background in candidates if not is_background]
    selected = preferred if preferred else [(name, amount) for name, amount, _ in candidates]
    return max(selected, key=lambda item: item[1])


def _container_usage_summary(*, plan: Any, final_material_state: dict[str, Any] | None) -> ContainerResourceSummary:
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

    return ContainerResourceSummary(
        allocated_count=allocated,
        touched_count=len(touched_names),
        container_kinds=[
            ContainerKindCount(kind=kind, count=count)
            for kind, count in sorted(kind_counts.items(), key=lambda item: item[0])
        ],
        touched_names=touched_names,
    )


def _instrument_usage_summary(*, plan: Any) -> InstrumentSummary:
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

    return InstrumentSummary(
        tools=[
            NamedCount(name=name, count=count)
            for name, count in sorted(tool_counts.items(), key=lambda item: item[0])
        ],
        devices=[
            NamedCount(name=name, count=count)
            for name, count in sorted(device_counts.items(), key=lambda item: item[0])
        ],
    )


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
