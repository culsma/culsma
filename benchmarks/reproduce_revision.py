"""Run a frozen revision benchmark inventory through the compiler/runtime API."""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO / "src"))

import culsma
import lark
from reproduce import assess
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_files
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.entrypoints import resolve_entry
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.runtime.replay import replay_events
from culsma.runtime.results import build_results


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def verify_manifest(manifest_path):
    manifest = json.loads(manifest_path.read_text())
    for name, expected in manifest["input_sha256"].items():
        actual = hashlib.sha256((manifest_path.parent / name).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Input changed: {name}")
    runner_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if runner_hash != manifest["runner_sha256"]:
        raise ValueError("Runner changed")
    if hashlib.sha256((ROOT / "reproduce.py").read_bytes()).hexdigest() != manifest["coverage_runner_sha256"]:
        raise ValueError("Coverage rule changed")
    if (culsma.__version__, lark.__version__) != (manifest["runtime_version"], manifest["lark_version"]):
        raise ValueError("Runtime/dependency version changed")
    changed = subprocess.check_output([
        "git", "-C", str(REPO), "diff", "--name-only", manifest["runtime_commit"],
        "--", "src", "pyproject.toml"], text=True).splitlines()
    unused_cli = {"src/culsma/cli.py", "src/culsma/__main__.py"}
    if set(changed) - unused_cli:
        raise ValueError(f"Compiler/runtime differs from pinned commit: {changed}")
    untracked = subprocess.check_output([
        "git", "-C", str(REPO), "ls-files", "--others", "--exclude-standard", "--", "src"],
        text=True).splitlines()
    if untracked:
        raise ValueError(f"Untracked runtime source: {untracked}")
    return manifest, sorted(set(changed) & unused_cli)


def execute_case(program, target):
    frontend = resolve_files([program])
    compiled = compile_ast(frontend.prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    typed = typecheck(semantic.ir, analysis=compiled.analysis)
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis,
                            entry_resolution=resolve_entry(typed.ir))
    diagnostics = {"semantic": [d.to_dict() for d in semantic.diagnostics],
                   "typecheck": [d.to_dict() for d in typed.diagnostics],
                   "plan": [d.to_dict() for d in plan.diagnostics]}
    accepted = semantic.ok and typed.ok and not any(d.severity == "error" for d in plan.diagnostics)
    if not accepted:
        write_json(target / "diagnostics.json", diagnostics)
        return {"accepted": False, "software_pass": False, "execution": None, "diagnostics": diagnostics}
    result = run(plan=plan, driver=StubDriver())
    diagnostics["runtime"] = [d.to_dict() for d in result.diagnostics]
    write_json(target / "diagnostics.json", diagnostics)
    replay_equal = replay_events(result.events).artifacts["material_state"] == result.state.artifacts["material_state"]
    returns = result.state.artifacts.get("protocol_outputs", {})
    write_json(target / "run.json", {"ok": result.ok, "report": result.user_result, "returns": returns})
    write_json(target / "results.json", build_results(state=result.state, returns=returns, plan=plan,
                                                       material_accounting=result.material_accounting))
    execution = result.user_result["execution"]
    passed = result.ok and replay_equal and execution["completed_steps"] == execution["total_steps"] and all(
        execution[k] == 0 for k in ("failed_steps", "skipped_steps", "diagnostic_count"))
    return {"accepted": True, "software_pass": passed, "execution": execution,
            "event_replay_equal": replay_equal, "diagnostics": diagnostics}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New results directory")
    args = parser.parse_args()
    manifest, unused_cli = verify_manifest(args.manifest)
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for entry in manifest["artifacts"]:
        case = args.manifest.parent / entry["path"]
        target = args.output / entry["path"] / "results"
        coverage = assess(case, manifest["runtime_commit"], manifest["runtime_version"])
        write_json(target / "coverage.json", coverage)
        try:
            result = execute_case(case / "protocol.culs", target)
        except Exception as error:
            result = {"accepted": False, "software_pass": False, "execution": None,
                      "exception": str(error), "traceback": traceback.format_exc()}
            write_json(target / "error.json", result)
        row = {"artifact": entry["path"], "name": entry["name"], "coverage": coverage, **result}
        rows.append(row)
        print(f"{entry['path']}: {coverage['matched_steps']}/{coverage['total_steps']}; "
              f"{'PASS' if result['software_pass'] else 'FAIL'} {result['execution']}", flush=True)
        gc.collect()
    summary = {"schema": "revision-benchmark-run-v1", "runtime_commit": manifest["runtime_commit"],
               "runtime_version": culsma.__version__, "python": platform.python_version(),
               "lark": lark.__version__, "execution_api": "compiler/runtime with StubDriver",
               "unused_cli_differences": unused_cli, "artifacts": rows,
               "all_software_pass": all(r["software_pass"] for r in rows),
               "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
               "output_sha256": {str(p.relative_to(args.output)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(args.output.rglob("*")) if p.is_file()}}
    write_json(args.output / "summary.json", summary)
    if not summary["all_software_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
