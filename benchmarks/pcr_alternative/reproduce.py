"""Reproduce the controlled PCR variant with the manuscript's frozen runtime.

Only software execution is performed. Runtime sources and full run records
stay under the manuscript repository's output directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import tarfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMMIT = "5364676bc2437b4981a00ce0133c730af243e469"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--culsma-repo", required=True, type=Path)
    args = parser.parse_args()
    output = ROOT / "output/pcr-alternative"
    runtime = output / "runtime" / COMMIT
    runtime.mkdir(parents=True, exist_ok=True)
    archive = subprocess.check_output([
        "git", "-C", str(args.culsma_repo), "archive", COMMIT,
        "src", "pyproject.toml",
    ])
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(runtime, filter="data")
    sys.path.insert(0, str(runtime / "src"))
    import lark
    from culsma.parser.parser import parse
    from culsma.frontend.resolver import resolve_program
    from culsma.pipeline.compile import compile_ast
    from culsma.pipeline.validate import validate
    from culsma.pipeline.typecheck import typecheck
    from culsma.pipeline.plan import lower_ir_to_plan
    from culsma.runtime.executor import run
    from culsma.driver.stub import StubDriver

    expected = json.loads((HERE / "expected.json").read_text())
    sources = {name: (HERE / f"{name}.culs").read_text()
               for name in ("original", "normal", "overdraw")}
    assert sources["original"].count("[template,") == 1
    assert sources["normal"] == sources["original"].replace(
        "[template, forward, reverse, master_mix, water]",
        "[template:1uL, forward:2.5uL, reverse:2.5uL, master_mix:25uL, water:19uL]",
    )
    assert sources["overdraw"] == sources["normal"].replace("[template:1uL,", "[template:2uL,")
    summary = {
        "implementation_commit": COMMIT,
        "python": platform.python_version(), "lark": lark.__version__,
        "execution_mode": "software reference execution with StubDriver; no hardware",
        "runtime_archive_sha256": hashlib.sha256(archive).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "expected_sha256": hashlib.sha256((HERE / "expected.json").read_bytes()).hexdigest(),
        "cases": {},
    }
    for name, source in sources.items():
        compiled = compile_ast(resolve_program(parse(source)).prepared_program)
        valid = validate(compiled.ir, analysis=compiled.analysis)
        assert valid.ok, [d.to_dict() for d in valid.diagnostics]
        typed = typecheck(valid.ir, analysis=compiled.analysis)
        assert typed.ok, [d.to_dict() for d in typed.diagnostics]
        plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
        assert not plan.diagnostics, [d.to_dict() for d in plan.diagnostics]
        result = run(plan=plan, driver=StubDriver())
        state = result.state.to_dict()
        events = [e.to_dict() for e in result.events]
        diagnostics = [d.to_dict() for d in result.diagnostics]
        save(output / name / "run.json", {
            "ok": result.ok, "diagnostics": diagnostics, "events": events,
            "state": state, "user_result": result.user_result,
        })
        save(output / name / "plan.json", plan.to_dict())
        trace = []
        for event in events:
            if event["kind"] != "STEP_COMPLETED":
                continue
            if event["payload"].get("driver_payload", {}).get("op") != "env_hold":
                continue
            env = event["payload"]["gate"]["env"]
            duration = env["duration"]
            assert env["thermal"]["unit"] == "C"
            assert duration["unit"] in ("s", "min")
            trace.append({
                "ordinal": len(trace) + 1, "event_seq": event["seq"],
                "step_id": event["step_id"], "source_line": event["span"]["line"],
                "temperature_C": env["thermal"]["value"],
                "duration_s": duration["value"] * (60 if duration["unit"] == "min" else 1),
            })
        containers = state["artifacts"]["material_state"]["containers"]
        by_label = {c["metadata"]["label"]: c for c in containers.values()}
        product = by_label["PCR reaction"]
        case = {
            "input_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "validation_passed": valid.ok, "typecheck_passed": typed.ok,
            "plan_diagnostics": [], "runtime_ok": result.ok,
            "step_status_counts": dict(Counter(state["step_status"].values())),
            "reaction_volume_uL": product["volume_uL"],
            "components_uL": product["components"],
            "template_remaining_uL": by_label["Template"]["volume_uL"],
            "completed_thermal_steps": len(trace), "diagnostics": diagnostics,
        }
        if name in ("original", "normal"):
            assert result.ok and not diagnostics
            assert product["volume_uL"] == expected["normal"]["reaction_volume_uL"]
            assert product["components"] == expected["normal"]["components_uL"]
            assert [{k: t[k] for k in ("temperature_C", "duration_s")} for t in trace] == expected["normal"]["thermal_sequence"]
        else:
            e = expected["overdraw"]
            assert result.ok == e["runtime_ok"]
            assert e["required_diagnostic"] in [d["code"] for d in diagnostics]
            for key in ("reaction_volume_uL", "template_remaining_uL", "completed_thermal_steps"):
                assert case[key] == e[key], (key, case[key], e[key])
            assert not any(event["kind"] == "STEP_STARTED" and event["payload"].get("op") == "env_hold" for event in events)
            material_error = next(d for d in diagnostics if d["code"] == e["required_diagnostic"])
            assert "template:2uL" in source.splitlines()[material_error["span"]["line"] - 1]
        summary["cases"][name] = case
        save(HERE / "results" / f"{name}.thermal-trace.json", trace)
    save(HERE / "results/summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
