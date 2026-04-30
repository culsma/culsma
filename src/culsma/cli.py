"""CLI for end-to-end execution kernel pipeline."""

from __future__ import annotations

import argparse
import json
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

    can_run = len(sem.diagnostics) == 0 and len(typ.diagnostics) == 0
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

    summary = {
        "inputs": [str(p) for p in input_paths],
        "semantic_error_count": len(sem.diagnostics),
        "type_error_count": len(typ.diagnostics),
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
    _write_json(outdir / "result.json", bundle["result"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Culsma execution kernel CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run end-to-end kernel pipeline on one or more .culs files")
    run_cmd.add_argument(
        "--input",
        required=True,
        action="append",
        help="Path to .culs protocol file (repeatable for multi-file merge)",
    )
    run_cmd.add_argument(
        "--output",
        default=None,
        help="Optional path for the primary run result JSON; stdout is used when omitted.",
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

    args = parser.parse_args()
    if args.command == "run":
        bundle = execute_pipeline(
            input_paths=[Path(p) for p in args.input],
            fail_ops=set(args.fail_op),
            material_state_path=Path(args.material_state_json) if args.material_state_json else None,
            inventory_check=bool(args.inventory_check),
            library_roots=[Path(p) for p in args.library_root],
        )
        if args.output:
            _write_json(Path(args.output), bundle["result"])
        else:
            print(_json_text(bundle["result"]), end="")
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
