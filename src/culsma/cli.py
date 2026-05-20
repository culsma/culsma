"""CLI for end-to-end execution kernel pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from culsma.frontend.resolver import resolve_files
from culsma.pipeline.compile import compile_ast
from culsma.driver.stub import StubDriver
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.runtime.replay import replay_events
from culsma.runtime.executor import run
from culsma.runtime.state import init_state
from culsma.runtime.user_result import build_user_result
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def _json_text(payload: Any) -> str:
    return json.dumps(_to_jsonable(payload), ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(payload), encoding="utf-8")


def _protocol_returns_from_state(state: Any) -> dict[str, Any]:
    artifacts = getattr(state, "artifacts", {})
    if not isinstance(artifacts, dict):
        return {}
    outputs = artifacts.get("protocol_outputs")
    if not isinstance(outputs, dict):
        return {}
    return {str(name): payload for name, payload in outputs.items() if isinstance(payload, dict)}


def build_run_output(*, ok: bool, returns: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "culsma_run_output_v1",
        "ok": ok,
        "returns": returns,
        "report": report,
    }


def _format_number(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return str(value)
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.6f}".rstrip("0").rstrip(".")


def _format_container_state(value: dict[str, Any], *, indent: str = "  ") -> list[str]:
    label = value.get("label") or value.get("id") or "container"
    container_kind = value.get("container_kind") or value.get("kind") or "container"
    lines = [f"{indent}{label} ({container_kind})"]
    container_id = value.get("id")
    if isinstance(container_id, str) and container_id != label:
        lines.append(f"{indent}  id: {container_id}")
    if "volume_uL" in value:
        lines.append(f"{indent}  volume: {_format_number(value.get('volume_uL'))} uL")
    if "mass_mg" in value:
        lines.append(f"{indent}  mass: {_format_number(value.get('mass_mg'))} mg")
    components = value.get("components")
    if isinstance(components, dict) and components:
        lines.append(f"{indent}  components:")
        for name, amount in sorted(components.items()):
            lines.append(f"{indent}    {name}: {_format_number(amount)}")
    return lines


def _format_return_value(value: Any, *, indent: str = "  ") -> list[str]:
    if isinstance(value, dict) and value.get("kind") == "container_ref":
        return _format_container_state(value, indent=indent)
    if isinstance(value, dict) and value.get("kind") == "IRQuantity":
        return [f"{indent}{_format_number(value.get('value'))} {value.get('unit')}"]
    if isinstance(value, list):
        if not value:
            return [f"{indent}[]"]
        lines = [f"{indent}["]
        for item in value:
            rendered = _format_return_value(item, indent=indent + "  ")
            if len(rendered) == 1:
                lines.append(f"{rendered[0]},")
            else:
                lines.extend(rendered)
        lines.append(f"{indent}]")
        return lines
    if isinstance(value, dict):
        lines = [f"{indent}{value.get('kind', 'object')}"]
        for key, item in sorted(value.items()):
            if key == "kind":
                continue
            if isinstance(item, (dict, list)):
                lines.append(f"{indent}  {key}: {json.dumps(_to_jsonable(item), ensure_ascii=True, sort_keys=True)}")
            else:
                lines.append(f"{indent}  {key}: {item}")
        return lines
    return [f"{indent}{value}"]


def format_terminal_result(bundle: dict[str, Any]) -> str:
    """Render a compact, human-readable result for the default CLI path."""
    result = bundle.get("result", {})
    execution = result.get("execution", {}) if isinstance(result, dict) else {}
    ok = bool(execution.get("ok"))
    outputs = bundle.get("returns", {})
    outputs = outputs if isinstance(outputs, dict) else {}

    names = list(outputs.keys())
    title = names[0] if len(names) == 1 else "Culsma run"
    lines = [f"{title} {'ok' if ok else 'failed'}"]

    if outputs:
        lines.append("")
        lines.append("return:")
        for protocol_name, payload in outputs.items():
            if len(outputs) > 1:
                lines.append(f"  {protocol_name}:")
                indent = "    "
            else:
                indent = "  "
            if not isinstance(payload, dict):
                lines.append(f"{indent}{payload}")
                continue
            if "bindings" in payload and isinstance(payload["bindings"], dict):
                for name, value in payload["bindings"].items():
                    lines.append(f"{indent}{name}:")
                    lines.extend(_format_return_value(value, indent=indent + "  "))
            elif "value" in payload:
                lines.extend(_format_return_value(payload["value"], indent=indent))
            else:
                lines.append(f"{indent}(no explicit return value)")
    else:
        final_products = []
        if isinstance(result, dict):
            materials = result.get("materials", {})
            if isinstance(materials, dict) and isinstance(materials.get("final_products"), list):
                final_products = materials["final_products"]
        if final_products:
            lines.append("")
            lines.append("final products:")
            for item in final_products:
                if not isinstance(item, dict):
                    continue
                label = item.get("name", "product")
                lines.append(f"  {label}")
                if "volume_uL" in item:
                    lines.append(f"    volume: {_format_number(item.get('volume_uL'))} uL")
                component = item.get("primary_component")
                if isinstance(component, str):
                    lines.append(f"    primary_component: {component}")

    lines.append("")
    lines.append(
        "execution: "
        f"{_format_number(execution.get('completed_steps', 0))}/"
        f"{_format_number(execution.get('total_steps', 0))} steps completed, "
        f"{_format_number(execution.get('diagnostic_count', 0))} diagnostics"
    )
    alerts = result.get("alerts", []) if isinstance(result, dict) else []
    if isinstance(alerts, list) and alerts:
        lines.append("alerts:")
        for alert in alerts[:5]:
            lines.append(f"  {alert}")
    return "\n".join(lines) + "\n"


def _load_initial_material_state(material_state_path: Path | None) -> dict[str, Any]:
    if material_state_path is None:
        return {"containers": {}}
    payload = json.loads(material_state_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("containers"), dict):
        return payload
    return {"containers": {}}


def execute_pipeline(
    input_paths: list[Path],
    fail_ops: set[str] | None = None,
    material_state_path: Path | None = None,
    inventory_check: bool = False,
    library_roots: list[Path] | None = None,
) -> dict[str, Any]:
    frontend = resolve_files(input_paths, library_roots=library_roots or ())
    compile_result = compile_ast(frontend.prepared_program)
    ir = compile_result.ir

    initial_material_state = _load_initial_material_state(material_state_path)
    initial_containers = initial_material_state.get("containers", {})
    initial_defined_names = set(initial_containers.keys()) if isinstance(initial_containers, dict) else set()

    sem = validate(
        ir,
        analysis=compile_result.analysis,
        initial_defined_names=initial_defined_names,
        enforce_binding=inventory_check,
    )

    typ = typecheck(sem.ir)

    plan = lower_ir_to_plan(typ.ir)

    state = init_state(plan)
    state.artifacts["material_state"] = deepcopy(initial_material_state)
    if isinstance(state.artifacts["material_state"], dict):
        state.artifacts["material_state"]["_inventory_check"] = bool(inventory_check)

    can_run = sem.ok and typ.ok
    if can_run:
        run_result = run(plan=plan, driver=StubDriver(fail_ops=fail_ops or set()), state=state)
    else:
        run_result = SimpleNamespace(ok=False, diagnostics=[], state=state, events=[])

    user_result = (
        run_result.user_result
        if can_run and getattr(run_result, "user_result", None) is not None
        else build_user_result(
            ok=run_result.ok,
            diagnostics=list(run_result.diagnostics),
            state=run_result.state,
            events=list(run_result.events),
            plan=plan,
            initial_material_state=initial_material_state,
        )
    )
    run_payload = {
        "ok": run_result.ok,
        "diagnostics": [d.to_dict() for d in run_result.diagnostics],
        "state": run_result.state.to_dict(),
        "events": [e.to_dict() for e in run_result.events],
        "user_result": user_result,
    }
    returns = _protocol_returns_from_state(run_result.state)
    output = build_run_output(ok=run_result.ok, returns=returns, report=user_result)

    summary = {
        "inputs": [str(p) for p in input_paths],
        "semantic_error_count": sum(1 for d in sem.diagnostics if d.severity == "error"),
        "type_error_count": sum(1 for d in typ.diagnostics if d.severity == "error"),
        "plan_diagnostic_count": len(plan.diagnostics),
        "runtime_diagnostic_count": len(run_result.diagnostics),
        "runtime_ok": run_result.ok,
        "total_steps": len(run_result.state.step_status),
        "completed_steps": sum(1 for s in run_result.state.step_status.values() if s == "completed"),
        "failed_steps": sum(1 for s in run_result.state.step_status.values() if s == "failed"),
        "skipped_steps": sum(1 for s in run_result.state.step_status.values() if s == "skipped"),
        "user_result_available": True,
    }
    return {
        "ast": frontend.parsed_program,
        "ir": ir.to_dict(),
        "validate": [d.to_dict() for d in sem.diagnostics],
        "typecheck": [d.to_dict() for d in typ.diagnostics],
        "plan": plan.to_dict(),
        "run": run_payload,
        "returns": returns,
        "output": output,
        "result": user_result,
        "summary": summary,
    }


def write_run_artifacts(bundle: dict[str, Any], outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    _write_json(outdir / "summary.json", bundle["summary"])
    _write_json(outdir / "ast.json", bundle["ast"])
    _write_json(outdir / "ir.json", bundle["ir"])
    _write_json(outdir / "validate.json", bundle["validate"])
    _write_json(outdir / "typecheck.json", bundle["typecheck"])
    _write_json(outdir / "plan.json", bundle["plan"])
    _write_json(outdir / "run.json", bundle["run"])
    _write_json(outdir / "output.json", bundle["output"])
    _write_json(outdir / "result.json", bundle["result"])


def _argv_for_parser(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    commands = {"run", "replay"}
    first = argv[0]
    if first not in commands and not first.startswith("-"):
        return ["run", *argv]
    return argv


def main() -> None:
    parser = argparse.ArgumentParser(description="Culsma execution kernel CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run end-to-end kernel pipeline on one or more .culs files")
    run_cmd.add_argument(
        "paths",
        nargs="*",
        help="Path to .culs protocol file (repeatable for multi-file merge)",
    )
    run_cmd.add_argument(
        "--input",
        action="append",
        default=[],
        help="Path to .culs protocol file (repeatable for multi-file merge)",
    )
    run_cmd.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable run output JSON instead of the default terminal summary.",
    )
    run_cmd.add_argument(
        "--output",
        default=None,
        help="Optional path for machine-readable run output JSON.",
    )
    run_cmd.add_argument(
        "--artifacts-dir",
        default=None,
        help="Optional directory for debug and intermediate JSON artifacts.",
    )
    run_cmd.add_argument(
        "--fail-op",
        action="append",
        default=[],
        help="Stub driver: mark operation as failed (repeatable)",
    )
    run_cmd.add_argument(
        "--material-state-json",
        default=None,
        help="Optional path to initial material_state JSON payload",
    )
    run_cmd.add_argument(
        "--inventory-check",
        action="store_true",
        help="Enable strict inventory validation (bindings and insufficient-material failures).",
    )
    run_cmd.add_argument(
        "--library-root",
        action="append",
        default=[],
        help="Optional directory containing importable library .culs modules (repeatable).",
    )

    replay_cmd = sub.add_parser("replay", help="Replay state from a run artifact JSON")
    replay_cmd.add_argument("--run-json", required=True, help="Path to an explicit run.json artifact")
    replay_cmd.add_argument("--out", required=True, help="Output JSON path for reconstructed state")

    args = parser.parse_args(_argv_for_parser(sys.argv[1:]))
    if args.command == "run":
        input_values = [*args.input, *args.paths]
        if not input_values:
            parser.error("run requires at least one input path")
        bundle = execute_pipeline(
            input_paths=[Path(p) for p in input_values],
            fail_ops=set(args.fail_op),
            material_state_path=Path(args.material_state_json) if args.material_state_json else None,
            inventory_check=bool(args.inventory_check),
            library_roots=[Path(p) for p in args.library_root],
        )
        if args.output:
            _write_json(Path(args.output), bundle["output"])
        else:
            if args.json:
                print(_json_text(bundle["output"]), end="")
            else:
                print(format_terminal_result(bundle), end="")
        if args.artifacts_dir:
            write_run_artifacts(bundle, Path(args.artifacts_dir))
        return

    if args.command == "replay":
        run_json = json.loads(Path(args.run_json).read_text(encoding="utf-8"))
        reconstructed = replay_events(run_json.get("events", []))
        _write_json(Path(args.out), reconstructed.to_dict())
        summary = {
            "run_json": args.run_json,
            "out": args.out,
            "event_count": len(run_json.get("events", [])),
            "step_count": len(reconstructed.step_status),
        }
        print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))
        return


if __name__ == "__main__":
    main()
