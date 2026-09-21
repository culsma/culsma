#!/usr/bin/env python3
"""Run the frozen corpus and derive tables with the fixed automatic metrics extractor."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from benchmark_metrics import locked_versions, final_material_records

SUPPORTED_PYTHON_SERIES = ("3.11", "3.12", "3.13")
FIELDS = (
    "source_steps", "descriptor_items", "reused_objects", "later_use_links",
    "active_steps", "completed_steps", "reagent_records", "touched_containers",
    "final_material_states",
)


def read_json(path):
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def discover_cases():
    cases = []
    for path in sorted((ROOT / "cases").iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        if not re.fullmatch(r"[0-9]{2}", path.name):
            raise ValueError(f"invalid case directory: {path.name}")
        if not (path / "protocol.culs").is_file():
            raise ValueError(f"Case {path.name}: missing protocol.culs")
        cases.append(path.name)
    if not cases:
        raise ValueError("no case directories found")
    return cases


def case_dir(case):
    return ROOT / "cases" / case


def generated_counts(directory):
    """Validate and aggregate the three automatically extracted metric files."""
    d = read_json(directory / "action_descriptors.json")
    c = read_json(directory / "material_state_continuity.json")
    t = read_json(directory / "result_traceability.json")
    if len({x["extraction_id"] for x in (d,c,t)}) != 1:
        raise ValueError("mixed extraction identities")
    if d["descriptor_items"] != sum(len(row["descriptors"]) for row in d["rows"]):
        raise ValueError("descriptor count differs from generated entries")
    if c["reused_objects"] != len(c["rows"]) or c["later_use_links"] != sum(len(row["used_in"]) for row in c["rows"]):
        raise ValueError("continuity count differs from generated relations")
    steps = {row["step"] for row in d["rows"]}
    if d["source_steps"] != len(steps) or len(steps) != len(d["rows"]):
        raise ValueError("source-step count differs from unique rows")
    for row in c["rows"]:
        intro, uses = row["introduced_at"], row["used_in"]
        if intro not in steps or not uses or len(uses) != len(set(uses)) or any(
            step not in steps or int(step[1:]) <= int(intro[1:]) for step in uses
        ):
            raise ValueError("invalid later-use relation")
    finals = t["final_material_records"] if "final_material_records" in t else t["final_products"]
    if t["reagent_records"] != len(t["reagent_consumption"]) or t["touched_containers"] != len(t["touched_names"]) or t["final_material_states"] != len(finals):
        raise ValueError("traceability count differs from generated records")
    return {key: value for data in (d,c,t) for key,value in data.items() if key in FIELDS}


def runtime_counts(output, run=None):
    report = output["report"]
    execution = report["execution"]
    if not output["ok"] or not execution["ok"] or execution["failed_steps"] or execution["diagnostic_count"]:
        raise ValueError(f"runtime did not pass cleanly: {execution}")
    active = execution["total_steps"] - execution["skipped_steps"]
    if active != execution["completed_steps"] or active < 0:
        raise ValueError(f"incomplete active path: {execution}")
    if report["external_inventory"]["checked"]:
        raise ValueError("This snapshot uses no external inventory reconciliation")
    containers = report["resource_summary"]["containers"]
    if containers["touched_count"] != len(containers["touched_names"]):
        raise ValueError("touched-container count/list mismatch")
    materials = report["materials"]
    if not materials["has_material_state"]:
        raise ValueError("runtime material state missing")
    # Count report rows, not unique display names. Distinct allocations may share a name.
    return dict(active_steps=active, completed_steps=execution["completed_steps"],
                reagent_records=len(materials["reagent_consumption"]),
                touched_containers=len(containers["touched_names"]),
                final_material_states=len(final_material_records(run)) if run is not None
                else len(materials["final_products"]))


def total(rows):
    return {k: sum(row[k] for case, row in rows.items() if case != "00") for k in FIELDS}


def record_projection(output, run=None):
    """Compare full material rows and returns, not just their lengths."""
    r = output["report"]
    # Object key ordering is irrelevant; preserve duplicate rows using a sorted list.
    def rows(values):
        return sorted(json.dumps(v, sort_keys=True, separators=(",", ":")) for v in values)
    return {
        "consumption": rows(r["materials"]["reagent_consumption"]),
        "final_materials": rows([x["record"] for x in final_material_records(run)]) if run is not None
        else rows(r["materials"]["final_products"]),
        "touched_names": sorted(r["resource_summary"]["containers"]["touched_names"]),
        "returns": output["returns"],
    }


def derive(results=None):
    rows = {}
    for case in discover_cases():
        row = generated_counts(case_dir(case) if results is None else results / case / "evaluation")
        if results is not None:
            trace = read_json(results / case / "evaluation/result_traceability.json")
            run = read_json(results / case / "input/artifacts/run.json") if "final_material_records" in trace else None
            runtime = runtime_counts(read_json(results / case / "input/artifacts/output.json"), run)
            if any(row[k] != v for k,v in runtime.items()):
                raise ValueError(f"Case {case}: generated metrics and runtime disagree")
        rows[case] = row
    return rows


def render_tables(rows):
    text = ["# Recomputed benchmark tables", "", "Case 00 is reported separately and excluded from every total.", ""]
    tables = [
        ("Structured experimental detail", FIELDS[:2]),
        ("Material-state continuity", FIELDS[2:6]),
        ("Result traceability", FIELDS[6:]),
    ]
    totals = total(rows)
    for title, fields in tables:
        text += [f"## {title}", "", "| Case | " + " | ".join(fields) + " |",
                 "| --- | " + " | ".join("---:" for _ in fields) + " |"]
        for case, row in rows.items():
            if case != "00":
                text.append(f"| {case} | " + " | ".join(str(row[k]) for k in fields) + " |")
        text += ["| Total | " + " | ".join(str(totals[k]) for k in fields) + " |", "",
                 "Worked example 00: " + ", ".join(f"{k}={rows['00'][k]}" for k in fields) + ".", ""]
    return "\n".join(text)


def trace_projection(trace):
    """Compare full result records from the plain section-3.4 metric file."""
    def records(values):
        return sorted(json.dumps(v["record"], sort_keys=True, separators=(",", ":")) for v in values)
    return {"consumption": records(trace["reagent_consumption"]),
            "final_materials": records(trace["final_material_records"] if "final_material_records" in trace else trace["final_products"]),
            "touched_names": sorted(v["name"] for v in trace["touched_names"]),
            "returns": trace["formal_returns"]["value"]}


def compare(rows, results=None):
    expected = read_json(ROOT / "expected" / "tables.json")
    if set(rows) != set(expected["cases"]):
        raise ValueError("case set differs from expected tables: "
                         f"missing={sorted(set(expected['cases']) - set(rows))}, "
                         f"extra={sorted(set(rows) - set(expected['cases']))}")
    differences = []
    for case, row in rows.items():
        for field, value in row.items():
            wanted = expected["cases"][case][field]
            if value != wanted:
                differences.append(f"Case {case} {field}: observed {value}, expected {wanted}")
        baseline = read_json(case_dir(case) / "result_traceability.json")
        actual = baseline if results is None else read_json(results / case / "evaluation/result_traceability.json")
        actual_record, expected_record = trace_projection(actual), trace_projection(baseline)
        for field in actual_record:
            if actual_record[field] != expected_record[field]:
                differences.append(f"Case {case}: {field} records differ (see result_traceability.json)")
        if results is not None:
            run = read_json(results / case / "input/artifacts/run.json") if "final_material_records" in actual else None
            runtime_record = record_projection(read_json(results / case / "input/artifacts/output.json"), run)
            if actual_record != runtime_record:
                differences.append(f"Case {case}: extracted traceability differs from raw runtime records")
    for field, value in total(rows).items():
        if value != expected["totals"][field]:
            differences.append(f"Total {field}: observed {value}, expected {expected['totals'][field]}")
    return differences


def check_environment():
    baseline = locked_versions(ROOT / "requirements.lock")
    supported = SUPPORTED_PYTHON_SERIES
    observed = {"python": platform.python_version(),
                **{name: importlib.metadata.version(name) for name in ("culsma", "lark")}}
    series = ".".join(observed["python"].split(".")[:2])
    if series not in supported or sys.version_info.releaselevel != "final":
        raise ValueError(f"unsupported Python {observed['python']}; use a stable release of "
                         + ", ".join(supported))
    mismatches = {name: observed[name] for name in ("culsma", "lark")
                  if observed[name] != baseline[name]}
    if mismatches:
        raise ValueError(f"package version mismatch: {mismatches}; required "
                         f"culsma={baseline['culsma']}, lark={baseline['lark']}")
    return observed


def run_all(results):
    environment = check_environment()
    results.mkdir(parents=True, exist_ok=False)
    write_json(results / "environment.json", environment)
    script = ROOT / "tools" / "benchmark_metrics.py"
    for case in discover_cases():
        dest = results / case
        commands = [
            [sys.executable, str(script), "capture", "--source", str(case_dir(case)/"protocol.culs"),
             "--python", sys.executable, "--bundle", str(dest/"input")],
            [sys.executable, str(script), "extract", "--bundle", str(dest/"input"), "--out", str(dest/"evaluation")],
        ]
        for command in commands:
            subprocess.run(command, check=True)
        print(f"Case {case}: captured and automatically extracted", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("all", "summarize", "check-baseline"))
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    try:
        if args.command == "check-baseline":
            differences = compare(derive())
            print("\n".join(differences) if differences else "PASS: per-case plain JSON counts match the expected tables.")
            return 1 if differences else 0
        results = args.results.resolve()
        if args.command == "all":
            run_all(results)
        rows = derive(results)
        write_json(results / "tables.json", {"cases": rows, "totals": total(rows)})
        (results / "tables.md").write_text(render_tables(rows), encoding="utf-8")
        differences = compare(rows, results)
        write_json(results / "comparison.json", {"match": not differences, "differences": differences})
        print("\n".join(differences) if differences else "PASS: all case counts, totals and frozen material/return records match.")
        return 1 if differences else 0
    except (ValueError, KeyError, FileNotFoundError, FileExistsError, importlib.metadata.PackageNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
