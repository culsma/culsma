"""Evaluate shared benchmark programs with a pinned Culsma runtime.

Only results and their manifests live under evaluations/. Historical input
revisions are recovered from Git; they are not maintained as program copies.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

from reproduce import assess, RULES

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def git_files(commit, paths):
    archive = subprocess.check_output(["git", "-C", str(REPO), "archive", commit, *paths])
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        return {m.name: bundle.extractfile(m).read() for m in bundle.getmembers() if m.isfile()}


def materialize(files, target):
    """Use a reproducibility cache inside this repository, never a checkout."""
    target.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != content:
            path.write_bytes(content)
    return target


def verify_inputs(inputs, manifest):
    actual = {str(p.relative_to(inputs)) for entry in manifest["artifacts"]
              for p in (inputs / entry["path"]).iterdir() if p.suffix in {".culs", ".md"}}
    if actual != set(manifest["input_sha256"]):
        raise ValueError("Benchmark input inventory changed")
    for name, expected in manifest["input_sha256"].items():
        if digest(inputs / name) != expected:
            raise ValueError(f"Input changed: {name}")


def prepare_inputs(manifest):
    commit = manifest.get("benchmark_commit")
    if not commit:
        inputs = ROOT
    else:
        paths = ["benchmarks/" + name for name in manifest["input_sha256"]]
        files = git_files(commit, paths)
        inputs = materialize(files, ROOT / "local-results" / "inputs" / commit) / "benchmarks"
    verify_inputs(inputs, manifest)
    return inputs


def prepare_runtime(manifest):
    commit = manifest["runtime_commit"]
    files = git_files(commit, ["src", "pyproject.toml"])
    # The cache is disposable: remove stale Python modules before reconstruction.
    target = ROOT / "local-results" / "runtimes" / commit
    if target.exists():
        shutil.rmtree(target)
    return materialize(files, target)


def group_totals(rows):
    totals = {}
    for row in rows:
        group = totals.setdefault(row["group"], {"matched_steps": 0, "total_steps": 0})
        group["matched_steps"] += row["coverage"]["matched_steps"]
        group["total_steps"] += row["coverage"]["total_steps"]
    return totals


def evaluate(manifest_path, output, replace=False):
    manifest = json.loads(manifest_path.read_text())
    inputs = prepare_inputs(manifest)
    runtime = prepare_runtime(manifest)
    env = dict(os.environ, PYTHONPATH=str(runtime / "src"), PYTHONNOUSERSITE="1",
               PYTHONDONTWRITEBYTECODE="1")
    versions = json.loads(subprocess.check_output([
        sys.executable, "-c", "import json,culsma,lark; print(json.dumps([culsma.__version__,lark.__version__]))"
    ], env=env, cwd=runtime, text=True))
    if versions != [manifest["runtime_version"], manifest["lark_version"]]:
        raise ValueError(f"Runtime/dependency mismatch: {versions}")
    if output.exists():
        if not replace or output.resolve() != manifest_path.parent.resolve():
            raise FileExistsError("Use a new output directory, or --replace for this evaluation directory")
        # Preserve the manifest and documentation; only replace recorded outputs.
        for name in ("modules", "composites"):
            if (output / name).exists():
                shutil.rmtree(output / name)
        for name in ("summary.json", "table.md"):
            (output / name).unlink(missing_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    if output.resolve() != manifest_path.parent.resolve():
        shutil.copy2(manifest_path, output / "manifest.json")
    rows = []
    for entry in manifest["artifacts"]:
        case, target = inputs / entry["path"], output / entry["path"]
        coverage = assess(case, manifest["runtime_commit"], manifest["runtime_version"])
        write_json(target / "coverage.json", coverage)
        process = subprocess.run([sys.executable, str(ROOT / "evaluate_case.py"),
                                  str(case / "protocol.culs"), str(target)],
                                 env=env, cwd=runtime, capture_output=True, text=True)
        for stream in ("stdout", "stderr"):
            value = getattr(process, stream)
            if value.strip():
                (target / (stream + ".txt")).write_text(value)
        result_path = target / "execution.json"
        if result_path.exists():
            result = json.loads(result_path.read_text())
        else:
            result = {"accepted": False, "software_pass": False, "execution": None,
                      "exception": "Runtime worker did not produce an execution record"}
        if process.returncode:
            result["software_pass"] = False
        row = {"artifact": entry["path"], "name": entry["name"], "group": entry["group"],
               "coverage": coverage, **result}
        rows.append(row)
        print(f"{entry['path']}: {coverage['matched_steps']}/{coverage['total_steps']}; "
              f"{'PASS' if result['software_pass'] else 'FAIL'}", flush=True)
    summary = {"schema": "benchmark-evaluation-v1", "version": manifest["version"],
               "runtime_commit": manifest["runtime_commit"], "runtime_version": versions[0],
               "python": platform.python_version(), "lark_version": versions[1], "rules": RULES,
               "benchmark_commit": manifest.get("benchmark_commit"),
               "input_sha256": manifest["input_sha256"], "groups": group_totals(rows),
               "artifacts": rows, "all_software_pass": all(r["software_pass"] for r in rows),
               "manifest_sha256": digest(manifest_path),
               "runner_sha256": {name: digest(ROOT / name) for name in
                                  ("evaluate.py", "evaluate_case.py", "reproduce.py")},
               "output_sha256": {str(p.relative_to(output)): digest(p)
                                 for folder in ("modules", "composites")
                                 for p in sorted((output / folder).rglob("*")) if p.is_file()}}
    write_json(output / "summary.json", summary)
    lines = ["| Workflow | Source steps | Software execution |", "| --- | ---: | --- |"]
    for row in rows:
        c = row["coverage"]
        lines.append(f"| {row['name']} | {c['matched_steps']}/{c['total_steps']} | "
                     f"{'pass' if row['software_pass'] else 'failed'} |")
    (output / "table.md").write_text("\n".join(lines) + "\n")
    return 0 if summary["all_software_pass"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, choices=("1.0.7", "1.0.9", "1.0.11"))
    parser.add_argument("--output", type=Path, help="Optional separate replay output directory")
    parser.add_argument("--replace", action="store_true", help="Update this version's recorded results in place")
    args = parser.parse_args()
    manifest = ROOT / "evaluations" / args.version / "manifest.json"
    output = args.output.resolve() if args.output else manifest.parent
    return evaluate(manifest, output, args.replace)


if __name__ == "__main__":
    raise SystemExit(main())
