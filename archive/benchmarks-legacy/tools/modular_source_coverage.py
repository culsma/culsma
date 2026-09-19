#!/usr/bin/env python3
"""Measure numbered source-step correspondence in a modular benchmark artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


RULES = "modular-source-step-correspondence-v1"
SOURCE_MARKER = re.compile(r"^\s*//\s+Source step S([1-9]\d*):\s+(.+)$")
DIRECT_ALIAS = re.compile(r"^let\s+[A-Za-z_]\w*\s*=\s*[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\s*;$")
WRAPPER = re.compile(r"^(?:with\b|repeat\b|if\b|else\b)")


def normalize(value: str) -> str:
    return " ".join(value.split())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_source_steps(path: Path) -> dict[int, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [index for index, line in enumerate(lines) if line == "## Steps"]
    if len(starts) != 1:
        raise ValueError("source must contain exactly one ## Steps section")
    rows: dict[int, str] = {}
    for line in lines[starts[0] + 1 :]:
        if line.startswith("## "):
            break
        match = re.fullmatch(r"([1-9]\d*)\.\s+(.+)", line)
        if match:
            rows[int(match.group(1))] = normalize(match.group(2))
        elif line.strip():
            if not rows:
                raise ValueError("text precedes the first numbered source step")
            rows[max(rows)] += " " + normalize(line)
    if list(rows) != list(range(1, len(rows) + 1)):
        raise ValueError("source steps must be consecutive from 1")
    return rows


def meaningful_region(lines: list[str], marker_index: int) -> bool:
    saw_gap = False
    for raw in lines[marker_index + 1 :]:
        if SOURCE_MARKER.match(raw):
            if saw_gap:
                return False
            continue
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("//"):
            saw_gap = saw_gap or "COVERAGE GAP:" in stripped
            continue
        if stripped in {"{", "}", "};"} or WRAPPER.match(stripped):
            continue
        if DIRECT_ALIAS.fullmatch(stripped):
            return False
        return True
    return False


def assess(
    artifact_dir: Path,
    implementation: str | None,
    language_version: str | None,
) -> dict[str, object]:
    source_path = artifact_dir / "source.md"
    program_paths = sorted(artifact_dir.glob("*.culs"))
    if not program_paths:
        raise ValueError("artifact contains no .culs program files")
    expected = read_source_steps(source_path)
    occurrences: dict[int, list[dict[str, object]]] = {}
    for program_path in program_paths:
        lines = program_path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            match = SOURCE_MARKER.match(line)
            if not match:
                continue
            step = int(match.group(1))
            occurrences.setdefault(step, []).append(
                {
                    "file": program_path.name,
                    "line": index + 1,
                    "text": normalize(match.group(2)),
                    "has_code_region": meaningful_region(lines, index),
                }
            )

    steps = []
    for step, source_text in expected.items():
        found = occurrences.get(step, [])
        if not found:
            status = "missing_comment"
        elif len(found) != 1:
            status = "duplicate_comment"
        elif found[0]["text"] != source_text:
            status = "text_mismatch"
        elif not found[0]["has_code_region"]:
            status = "no_code_region"
        else:
            status = "matched"
        steps.append(
            {
                "step": step,
                "status": status,
                "source_text": source_text,
                "occurrences": found,
            }
        )
    unknown = sorted(set(occurrences) - set(expected))
    matched = sum(row["status"] == "matched" for row in steps)
    total = len(steps)
    issues = [
        {"step": row["step"], "reason": row["status"]}
        for row in steps
        if row["status"] != "matched"
    ] + [{"step": step, "reason": "unexpected_comment"} for step in unknown]
    return {
        "schema": "modular-source-coverage-v1",
        "rules": RULES,
        "metric": "source_step_correspondence",
        "artifact": artifact_dir.name,
        "implementation": implementation,
        "language_version": language_version,
        "source_sha256": digest(source_path),
        "program_sha256": {path.name: digest(path) for path in program_paths},
        "total_steps": total,
        "matched_steps": matched,
        "coverage_percent": round(100 * matched / total, 6),
        "status": "pass" if matched == total and not unknown else "incomplete",
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument("--implementation")
    parser.add_argument("--language-version")
    args = parser.parse_args()
    report = assess(args.artifact_dir, args.implementation, args.language_version)
    output = args.artifact_dir / "coverage.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"{output}: {report['matched_steps']}/{report['total_steps']} ({report['coverage_percent']}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
