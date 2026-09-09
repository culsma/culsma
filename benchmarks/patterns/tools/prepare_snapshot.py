#!/usr/bin/env python3
"""Maintainer-only snapshot assembly; never generates or edits website pages.

Usage: python tools/prepare_snapshot.py --paper DIR --artifacts DIR --wheels DIR
       python tools/prepare_snapshot.py --freeze-results DIR
       python tools/prepare_snapshot.py --seal
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "0a5393c33151663566fe3d81d4fe01f29f98e274"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def seal():
    paths = [p for p in ROOT.rglob("*") if p.is_file()
             and not any(x in (".venv", "results", "dist", "__pycache__") for x in p.relative_to(ROOT).parts)
             and p.name != "checksums.json"]
    write(ROOT / "checksums.json", {str(p.relative_to(ROOT)): digest(p) for p in sorted(paths)})


def assemble(args):
    if (ROOT / "manifest.json").exists():
        raise ValueError("snapshot exists; review changes explicitly instead of overwriting it")
    ids = [f"{i:02d}" for i in range(15)]
    case_metadata = {}
    for case in ids:
        src = args.artifacts / case
        dest = ROOT / ("worked-example" if case == "00" else "cases") / case
        dest.mkdir(parents=True, exist_ok=True)
        filenames = {"source.md", "source.steps.json", "action_descriptors.json", "object_reuse.json"}
        if (src / "alignment.json").exists():
            filenames.add("alignment.json")
        filenames |= {p.name for p in src.glob("*.culs")}
        if (src / "record.md").exists():
            filenames.add("record.md")
        for name in sorted(filenames):
            if (dest / name).exists() and digest(src / name) != digest(dest / name):
                raise ValueError(f"refusing to overwrite changed snapshot input: {dest / name}")
            shutil.copyfile(src / name, dest / name)
        evidence = json.loads((src / "evidence.json").read_text())
        case_metadata[case] = {key: evidence[key] for key in ("title", "source_class", "provider", "boundaries") if key in evidence}
        case_metadata[case]["upstream_path"] = f"docs/public/papers/patterns-benchmark/artifacts/cases/{case}"

    tex = (args.paper / "sections/08_controlled_convergence.tex").read_text()
    expected = {case: {} for case in ids}
    tables = [
        ("tab:semantic-capture-corpus-counts", ("source_steps", "descriptor_items")),
        ("tab:executable-continuity-corpus-counts", ("reused_objects", "later_use_links", "completed_steps", "active_steps")),
        ("tab:run-record-content-corpus-counts", ("reagent_records", "touched_containers", "final_material_states")),
    ]
    excerpts = []
    totals = {}
    for label, fields in tables:
        block = next(b for b in re.findall(r"\\begin\{table\}.*?\\end\{table\}", tex, re.S) if f"\\label{{{label}}}" in b)
        excerpts.append(block)
        found = []
        for match in re.finditer(r"^(\d{2})\s*&\s*(.+?)\\\\", block, re.M):
            case = match[1]
            values = [int(n) for n in re.findall(r"\d+", match[2])]
            if len(values) != len(fields):
                raise ValueError(f"invalid table row: {match[0]}")
            expected[case].update(zip(fields, values))
            found.append(case)
        if found != ids[1:]:
            raise ValueError(f"incomplete manuscript table {label}")
        total_line = next(line for line in block.splitlines() if r"\textbf{Total}" in line)
        totals.update(zip(fields, map(int, re.findall(r"\d+", total_line))))
    # Worked-example values transcribed from its three tables and explanatory text.
    expected["00"] = dict(source_steps=7, descriptor_items=23, reused_objects=3,
                          later_use_links=8, active_steps=27, completed_steps=27,
                          reagent_records=2, touched_containers=5, final_material_states=3)
    write(ROOT / "expected/tables.json", {"cases": expected, "totals": totals})
    (ROOT / "expected/manuscript-tables.tex").write_text("\n\n".join(excerpts) + "\n")
    vendor = ROOT / "vendor"
    vendor.mkdir()
    requirements = []
    for name, version in (("culsma", "1.0.6"), ("lark", "1.3.1")):
        wheel = args.wheels / f"{name}-{version}-py3-none-any.whl"
        shutil.copyfile(wheel, vendor / wheel.name)
        requirements.append(f"{name}=={version} --hash=sha256:{digest(wheel)}")
    (ROOT / "requirements.lock").write_text("\n".join(requirements) + "\n")
    # Verify the public wheel's executable sources against the recorded Git object.
    verified = 0
    if args.implementation:
        with zipfile.ZipFile(vendor / "culsma-1.0.6-py3-none-any.whl") as wheel:
            wheel_paths = {name for name in wheel.namelist() if name.startswith("culsma/") and not name.endswith("/")}
            tracked = subprocess.check_output(["git", "-C", str(args.implementation), "ls-tree", "-r", "--name-only", COMMIT, "src/culsma"], text=True).splitlines()
            for name in tracked:
                if name.endswith((".py", ".culs", ".lark")) and name.removeprefix("src/") not in wheel_paths:
                    raise ValueError(f"wheel missing source: {name}")
            for name in sorted(wheel_paths):
                content = subprocess.check_output(["git", "-C", str(args.implementation), "show", f"{COMMIT}:src/{name}"])
                if content != wheel.read(name):
                    raise ValueError(f"wheel differs from recorded commit: {name}")
                verified += 1
    docs_head = subprocess.check_output(["git", "-C", str(args.artifacts), "rev-parse", "HEAD"], text=True).strip()
    write(ROOT / "manifest.json", {
        "snapshot_id": "patterns-benchmark-2026-09-09", "status": "local submission candidate; not yet archived",
        "environment": {"python": "3.12.8", "culsma": "1.0.6", "lark": "1.3.1"},
        "environment_note": "Original baseline environment; Python patch version is recorded, not an exact runtime requirement. Package versions remain pinned.",
        "supported_python_series": ["3.11", "3.12", "3.13"],
        "recommended_python_series": "3.13",
        "implementation_release_url": "https://github.com/culsma/culsma/releases/tag/v1.0.6",
        "implementation_release_status": "published stable release (2026-09-07)",
        "implementation_commit": COMMIT, "wheel_source_files_verified": verified,
        "docs_commit": docs_head, "input_policy": "Exact working-tree artifact copies; checksums identify the actual inputs",
        "driver": "StubDriver", "inventory_reconciliation": False,
        "case_ids": ids, "formal_case_ids": ids[1:], "cases": case_metadata,
        "manuscript_section_sha256": digest(args.paper / "sections/08_controlled_convergence.tex"),
    })
    seal()


def freeze(results):
    spec = importlib.util.spec_from_file_location("reproduce", ROOT / "reproduce.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = module.derive(results)
    expected = module.read_json(ROOT / "expected/tables.json")
    if rows != expected["cases"] or module.total(rows) != expected["totals"]:
        raise ValueError("refusing to freeze: derived counts differ from manuscript")
    dest = ROOT / "expected/runtime"
    dest.mkdir(exist_ok=False)
    for case in rows:
        target = dest / case
        target.mkdir()
        (target / "output.json.gz").write_bytes(gzip.compress((results / case / "output.json").read_bytes(), mtime=0))
        shutil.copyfile(results / case / "artifacts/run.json.gz", target / "run.json.gz")
    (ROOT / "expected/tables.md").write_text(module.render_tables(rows))
    seal()


def record_protocols(repository):
    """Record exact provenance; normalization is only for locating Case 05's pair."""
    manifest = json.loads((ROOT / "manifest.json").read_text())
    originals = list((repository / "protocols").rglob("protocol.culs"))
    def spelling(text):
        return text.replace("CentrifugeProgramOutput.PELLET", "pellet").replace("MaterialRelation.CELL_BOUND", "cell_bound")
    for case, metadata in manifest["cases"].items():
        packaged = ROOT / ("worked-example" if case == "00" else "cases") / case / "protocol.culs"
        candidates = [p for p in originals if spelling(p.read_text()) == spelling(packaged.read_text())]
        if len(candidates) != 1:
            raise ValueError(f"ambiguous/missing protocol provenance for {case}")
        original = candidates[0]
        metadata["protocol_repository_path"] = str(original.relative_to(repository))
        metadata["protocol_repository_sha256"] = digest(original)
        metadata["program_byte_identical_to_protocol_repository"] = digest(original) == digest(packaged)
        metadata["source_byte_identical_to_protocol_repository"] = digest(original.with_name("source.md")) == digest(packaged.with_name("source.md"))
    manifest["protocols_commit"] = subprocess.check_output(["git", "-C", str(repository), "rev-parse", "HEAD"], text=True).strip()
    write(ROOT / "manifest.json", manifest)
    seal()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path)
    parser.add_argument("--wheels", type=Path)
    parser.add_argument("--implementation", type=Path)
    parser.add_argument("--paper", type=Path, help="Maintainer-only manuscript source for creating a new snapshot")
    parser.add_argument("--freeze-results", type=Path)
    parser.add_argument("--record-protocols", type=Path)
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    if args.seal:
        seal()
    elif args.record_protocols:
        record_protocols(args.record_protocols)
    elif args.freeze_results:
        freeze(args.freeze_results)
    elif args.artifacts and args.wheels and args.paper:
        assemble(args)
    else:
        parser.error("supply --paper, --artifacts and --wheels, --record-protocols, --freeze-results, or --seal")
