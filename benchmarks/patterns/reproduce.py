#!/usr/bin/env python3
"""Run the frozen corpus and derive tables from runtime/annotation records."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
FIELDS = (
    "source_steps", "descriptor_items", "reused_objects", "later_use_links",
    "active_steps", "completed_steps", "reagent_records", "touched_containers",
    "final_material_states",
)


def read_json(path):
    path = Path(path)
    if not path.exists() and path.with_suffix(path.suffix + ".gz").exists():
        path = path.with_suffix(path.suffix + ".gz")
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def case_dir(case):
    return ROOT / ("worked-example" if case == "00" else "cases") / case


def annotation_counts(directory):
    steps = read_json(directory / "source.steps.json")["steps"]
    ids = [s["id"] for s in steps]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{directory.name}: duplicate source step IDs")
    descriptors = read_json(directory / "action_descriptors.json")["rows"]
    if sorted(r["step"] for r in descriptors) != sorted(ids):
        raise ValueError(f"{directory.name}: descriptor rows do not match source steps")
    objects = read_json(directory / "object_reuse.json")["rows"]
    links = 0
    for row in objects:
        intro, uses = row["introduced_at"], row["used_in"]
        if intro not in ids or any(s not in ids for s in uses):
            raise ValueError(f"{directory.name}: unknown object-reuse step")
        if intro in uses or len(uses) != len(set(uses)) or not uses:
            raise ValueError(f"{directory.name}: invalid later-use list: {row['object']}")
        links += len(uses)
    return dict(source_steps=len(steps),
                descriptor_items=sum(len(r["descriptors"]) for r in descriptors),
                reused_objects=len(objects), later_use_links=links)


def runtime_counts(output):
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
                final_material_states=len(materials["final_products"]))


def total(rows):
    return {k: sum(row[k] for case, row in rows.items() if case != "00") for k in FIELDS}


def record_projection(output):
    """Compare full material rows and returns, not just their lengths."""
    r = output["report"]
    # Object key ordering is irrelevant; preserve duplicate rows using a sorted list.
    def rows(values):
        return sorted(json.dumps(v, sort_keys=True, separators=(",", ":")) for v in values)
    return {
        "consumption": rows(r["materials"]["reagent_consumption"]),
        "final_materials": rows(r["materials"]["final_products"]),
        "touched_names": sorted(r["resource_summary"]["containers"]["touched_names"]),
        "returns": output["returns"],
    }


def derive(results):
    return {case: {**annotation_counts(case_dir(case)),
                   **runtime_counts(read_json(results / case / "output.json"))}
            for case in read_json(ROOT / "manifest.json")["case_ids"]}


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


def compare(rows, results):
    expected = read_json(ROOT / "expected" / "tables.json")
    differences = []
    for case, row in rows.items():
        for field, value in row.items():
            wanted = expected["cases"][case][field]
            if value != wanted:
                differences.append(f"Case {case} {field}: observed {value}, expected {wanted}")
        baseline = ROOT / "expected" / "runtime" / case / "output.json.gz"
        if baseline.exists():
            actual_record = record_projection(read_json(results / case / "output.json"))
            expected_record = record_projection(read_json(baseline))
            for field in actual_record:
                if actual_record[field] != expected_record[field]:
                    differences.append(f"Case {case}: {field} records differ (see raw output.json)")
        else:
            differences.append(f"Case {case}: missing frozen runtime baseline")
    for field, value in total(rows).items():
        if value != expected["totals"][field]:
            differences.append(f"Total {field}: observed {value}, expected {expected['totals'][field]}")
    return differences


def check_files():
    checksums = read_json(ROOT / "checksums.json")
    differences = [name for name, digest in checksums.items()
                   if not (ROOT / name).is_file() or sha256(ROOT / name) != digest]
    if differences:
        raise ValueError("snapshot files missing/changed: " + ", ".join(differences))
    print(f"Verified {len(checksums)} snapshot files", flush=True)


def check_environment():
    manifest = read_json(ROOT / "manifest.json")
    baseline = manifest["environment"]
    supported = manifest["supported_python_series"]
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
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    failures = []
    for case in read_json(ROOT / "manifest.json")["case_ids"]:
        dest = results / case
        dest.mkdir()
        artifacts = dest / "artifacts"
        # -I avoids user-site packages and PYTHONPATH overrides.
        command = [sys.executable, "-I", "-m", "culsma.cli", "run",
                   "protocol.culs", "--json",
                   "--output", str(dest / "output.json"), "--artifacts-dir", str(artifacts)]
        with (dest / "stdout.txt").open("w") as out, (dest / "stderr.txt").open("w") as err:
            proc = subprocess.run(command, cwd=case_dir(case), env=env, stdout=out, stderr=err)
        write_json(dest / "invocation.json", {"command": command, "exit_code": proc.returncode})
        print(f"Case {case}: exit {proc.returncode}", flush=True)
        if proc.returncode:
            failures.append(case)
        # Preserve every emitted artifact; lossless gzip avoids multi-GB bundles.
        for path in sorted(artifacts.glob("*.json")):
            with path.open("rb") as src, path.with_suffix(".json.gz").open("wb") as target:
                with gzip.GzipFile(fileobj=target, mode="wb", mtime=0) as gz:
                    import shutil
                    shutil.copyfileobj(src, gz)
            path.unlink()  # only this run's freshly generated, now compressed copy
    if failures:
        raise ValueError("execution failed for: " + ", ".join(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("all", "summarize", "check-files"))
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    try:
        check_files()
        if args.command == "check-files":
            return 0
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
