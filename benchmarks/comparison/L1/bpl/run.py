"""Exercise BPL L1 through the installed, unmodified bplc public CLI.

No execution, binding, lowering, or CLI modules are patched. This invokes no
hardware or LLM service. Run after installing the pinned BPL source snapshot.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile

PACKAGE = Path(__file__).resolve().parent
RUNTIME = Path(os.environ["COMPARISON_RUNTIME_DIR"])
PIN = "4e505740f5025d59ba655c6c955f83876f753007"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=RUNTIME / 'bpl-source')
    parser.add_argument("--cli", type=Path, default=Path(sys.executable).with_name("bplc"))
    parser.add_argument("--out", type=Path, default=PACKAGE)
    parser.add_argument("--cases-dir", type=Path, default=PACKAGE)
    parser.add_argument("--skip-upstream-readme", action="store_true")
    parser.add_argument("--case-files", nargs="+")
    parser.add_argument("--report", default="results.json")
    args = parser.parse_args()
    args.cli = args.cli.resolve()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    # Avoid inheriting another environment's source or package overrides.
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)

    def run(label, command):
        result = subprocess.run(command, cwd=out, env=env, capture_output=True,
                                text=True, timeout=90)
        (out / (label + ".stdout.txt")).write_text(result.stdout)
        (out / (label + ".stderr.txt")).write_text(result.stderr)
        return {"command": list(map(str, command)), "working_directory": str(out),
                "returncode": result.returncode,
                "stdout": label + ".stdout.txt", "stderr": label + ".stderr.txt"}

    # Retain the complete upstream README code block, rather than silently
    # repairing or minimizing the official example.
    readme = args.source / "README.md"
    blocks = re.findall(r"```[^\n]*\n(.*?)```", readme.read_text(), re.S)
    official = next(b for b in blocks if "protocol PrepareLBMedia(" in b)
    official_path = out / "upstream_readme.bpl"
    if not args.skip_upstream_readme:
        official_path.write_text(official)
    evidence_sources = ["README.md", "pyproject.toml", "docs/BPL_Syntax_Reference.md",
                        "bpl/orchestrator.py", "bpl/cli/main.py", "bpl/grammar/bpl.lark"]
    report = {"upstream_commit": PIN, "python": sys.version,
              "platform": platform.platform(), "source_sha256": {
                  p: digest(args.source / p) for p in evidence_sources},
              "cases": {}}
    archive = args.source.parent / "bpl-source-4e505740.tar.gz"
    if archive.exists():
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            for name, sha in report["source_sha256"].items():
                member = next(m for m in members if m.name.endswith("/" + name))
                if hashlib.sha256(tar.extractfile(member).read()).hexdigest() != sha:
                    raise ValueError("Source differs from retained archive: " + name)
        report["source_archive"] = {"filename": archive.name, "sha256": digest(archive),
                                    "audited_files_match_archive": True}
    report["dependency_check"] = run("pip-check", [sys.executable, "-m", "pip", "check"])
    report["environment"] = run("pip-freeze", [sys.executable, "-m", "pip", "freeze", "--all"])
    report["cli_help"] = run("cli-help", [str(args.cli), "--help"])
    cases = [PACKAGE / name for name in args.case_files] if args.case_files else sorted(args.cases_dir.resolve().glob("*.bpl"))
    if not args.skip_upstream_readme:
        cases.append(official_path)
    for path in cases:
        name = path.stem.removeprefix("endpoint_")
        row = {"input": os.path.relpath(path, PACKAGE), "sha256": digest(path)}
        row["parse"] = run(name + "-parse", [str(args.cli), "parse", str(path),
                              "--with-spans", "--out", str(out / (name + "-ast.json")), "--json-errors"])
        row["check"] = run(name + "-check", [str(args.cli), "check", str(path), "--json-errors"])
        row["lower"] = {}
        for target in ("human", "simulation"):
            plan_path = out / (name + "-" + target + "-plan.json")
            # A failed rerun must not leave a stale plan masquerading as output.
            if plan_path.exists():
                plan_path.unlink()
            result = run(name + "-lower-" + target, [str(args.cli), "lower", str(path),
                             "--target", target, "--out", str(plan_path), "--json-errors"])
            if result["returncode"] == 0 and plan_path.exists():
                steps = json.loads(plan_path.read_text())["steps"]
                result["steps"] = [{k: s[k] for k in ("primitive_type", "primitive", "source_intent")}
                                   for s in steps]
            row["lower"][target] = result
        report["cases"][name] = row
        (out / args.report).write_text(json.dumps(report, indent=2) + "\n")
        print(name, "parse=", row["parse"]["returncode"], "check=", row["check"]["returncode"],
              "lower=", {t: {"returncode": r["returncode"],
                            "primitives": [s["primitive_type"] for s in r.get("steps", [])]}
                          for t, r in row["lower"].items()}, flush=True)


if __name__ == "__main__":
    main()
