"""Execute one benchmark with the runtime selected by evaluate.py."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import traceback

import culsma
import lark
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
    parser.add_argument("program", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    try:
        result = execute_case(args.program, args.target)
    except Exception as error:
        result = {"accepted": False, "software_pass": False, "execution": None,
                  "exception": str(error), "traceback": traceback.format_exc()}
        write_json(args.target / "error.json", result)
    result["runtime_version"] = culsma.__version__
    result["lark_version"] = lark.__version__
    write_json(args.target / "execution.json", result)
    return 0 if result["software_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
