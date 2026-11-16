"""Check whether BPL consumes procedure semantics beyond a HumanStep label.

Vary the callee body/return while preserving call sites, inspect public CLI
plans and human instructions, then run non-strict and strict simulations.
"""
import json
import os
from pathlib import Path
import subprocess

PACKAGE = Path(__file__).resolve().parent
from replay_paths import RUNTIME
CLI = RUNTIME / 'bpl-env/bin/bplc'
from replay_paths import result_path
OUT = result_path("l2/bpl-consumption")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    inputs = OUT / "inputs"
    inputs.mkdir(exist_ok=True)
    base = (PACKAGE / "cases/l2/bpl/composition.bpl").read_text()
    direct = (PACKAGE / "cases/l2/bpl/direct.bpl").read_text()
    cases = {"base": base,
             "body_20": base.replace("volume: 10 uL", "volume: 20 uL"),
             "return_target": base.replace("return StockTube", "return TargetTube"),
             "direct_10": direct,
             "direct_20": direct.replace("volume: 10 uL", "volume: 20 uL")}
    report = {"bpl_commit": "4e505740f5025d59ba655c6c955f83876f753007", "cases": {}}
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)

    def run(label, args):
        command = [str(CLI), *map(str, args)]
        result = subprocess.run(command, cwd=OUT, env=env, capture_output=True, text=True, timeout=90)
        (OUT / (label + ".stdout.txt")).write_text(result.stdout)
        (OUT / (label + ".stderr.txt")).write_text(result.stderr)
        return {"command": command, "returncode": result.returncode}

    for name, source in cases.items():
        path = inputs / (name + ".bpl")
        path.write_text(source)
        plan = OUT / (name + "-plan.json")
        row = {"lower": run(name + "-lower", ["lower", path, "--target", "human", "--out", plan, "--json-errors"]),
               "compose": run(name + "-compose", ["compose", path, "--target", "human", "--out", OUT / (name + ".md"), "--json-errors"])}
        if row["lower"]["returncode"] == 0:
            row["operations"] = [{k: step[k] for k in ("primitive_type", "primitive", "dependencies", "source_intent")}
                                 for step in json.loads(plan.read_text())["steps"]]
        report["cases"][name] = row
        (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        print(name, "lower", row["lower"]["returncode"], "compose", row["compose"]["returncode"], flush=True)
    report["simulations"] = {}
    for name, strict in [("base", False), ("base", True), ("direct_10", False)]:
        label = name + ("-strict" if strict else "-simulate")
        args = ["simulate", inputs / (name + ".bpl"), "--trace", OUT / (label + "-trace.json"), "--json-errors"]
        if strict:
            args.append("--strict")
        report["simulations"][label] = run(label, args)
        (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        print(label, report["simulations"][label]["returncode"], flush=True)
    rows = report["cases"]
    report["body_change_leaves_operations_identical"] = rows["base"]["operations"] == rows["body_20"]["operations"]
    report["return_change_leaves_operations_identical"] = rows["base"]["operations"] == rows["return_target"]["operations"]
    report["direct_volume_change_changes_operations"] = rows["direct_10"]["operations"] != rows["direct_20"]["operations"]
    (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
