#!/usr/bin/env python3
"""Build an immutable, versioned summary of benchmark coverage records."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

SCHEMA = "benchmark-coverage-snapshot-v1"
GAP = re.compile(r"^[ \t]*//[ \t]+Language gap S([1-9]\d*):[ \t]+(.+?)\s*$")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def language_gaps(program, total_steps):
    gaps = []
    seen = set()
    for line_number, line in enumerate(program.splitlines(), 1):
        match = GAP.fullmatch(line)
        if not match:
            continue
        step = int(match.group(1))
        if total_steps is not None and step > total_steps:
            raise ValueError(
                f"{line_number}: language gap refers to missing source step S{step}"
            )
        if step in seen:
            raise ValueError(
                f"{line_number}: duplicate language gap for source step S{step}"
            )
        seen.add(step)
        gaps.append({"step": step, "summary": " ".join(match.group(2).split())})
    return gaps


def case_entry(case_dir):
    source_path = case_dir / "source.md"
    program_path = case_dir / "protocol.culs"
    coverage_path = case_dir / "coverage.json"
    for path in (source_path, program_path, coverage_path):
        if not path.is_file():
            raise ValueError(f"{case_dir.name}: missing {path.name}")

    source = source_path.read_bytes()
    program = program_path.read_bytes()
    record = read_json(coverage_path)
    if record.get("schema") != "source-coverage-v2":
        raise ValueError(f"{case_dir.name}: unsupported coverage schema")
    if record.get("metric") != "source_step_correspondence":
        raise ValueError(f"{case_dir.name}: unsupported coverage metric")
    if record.get("case_id") != case_dir.name:
        raise ValueError(f"{case_dir.name}: coverage case_id does not match directory")
    if record.get("source_sha256") != digest(source):
        raise ValueError(f"{case_dir.name}: stale source_sha256")
    if record.get("program_sha256") != digest(program):
        raise ValueError(f"{case_dir.name}: stale program_sha256")

    total = record.get("total_steps")
    matched = record.get("matched_steps")
    correspondence_status = record.get("status")
    counts_available = isinstance(total, int) and isinstance(matched, int)
    unavailable_error = (
        correspondence_status == "error"
        and total is None
        and matched is None
    )
    if not (
        (counts_available and 0 <= matched <= total)
        or unavailable_error
    ):
        raise ValueError(f"{case_dir.name}: invalid step totals")
    gaps = language_gaps(program.decode("utf-8"), total)
    display_status = (
        correspondence_status
        if correspondence_status in {"incomplete", "error"}
        else "language_gap"
        if gaps
        else "covered"
    )
    relative = case_dir.relative_to(case_dir.parents[1]).as_posix()
    return {
        "case_id": case_dir.name,
        "status": display_status,
        "correspondence": {
            "matched_steps": matched,
            "total_steps": total,
            "coverage_percent": record.get("coverage_percent"),
            "status": correspondence_status,
            "issues": record.get("issues", []),
        },
        "language_gaps": gaps,
        "language_version": record.get("language_version"),
        "implementation": record.get("implementation"),
        "evidence": {
            "source_sha256": record["source_sha256"],
            "program_sha256": record["program_sha256"],
            "source": f"{relative}/source.md",
            "program": f"{relative}/protocol.culs",
            "coverage": f"{relative}/coverage.json",
        },
    }


def issue_map(case):
    return {
        (issue.get("step"), issue["reason"]): {
            "case_id": case["case_id"],
            **issue,
        }
        for issue in case["correspondence"]["issues"]
    }


def gap_map(case):
    return {
        gap["step"]: {"case_id": case["case_id"], **gap}
        for gap in case["language_gaps"]
    }


def changes(cases, previous):
    current_by_id = {case["case_id"]: case for case in cases}
    if previous is None:
        return {
            "compared_to": None,
            "comparable_cases": [],
            "source_changed_cases": [],
            "added_cases": sorted(current_by_id),
            "removed_cases": [],
            "resolved_correspondence_issues": [],
            "introduced_correspondence_issues": [],
            "resolved_language_gaps": [],
            "introduced_language_gaps": [],
            "updated_language_gaps": [],
        }

    if previous.get("schema") != SCHEMA:
        raise ValueError("previous snapshot uses an unsupported schema")
    previous_by_id = {case["case_id"]: case for case in previous["cases"]}
    shared = sorted(set(current_by_id) & set(previous_by_id))
    comparable = []
    source_changed = []
    resolved_issues = []
    introduced_issues = []
    resolved_gaps = []
    introduced_gaps = []
    updated_gaps = []

    for case_id in shared:
        current = current_by_id[case_id]
        old = previous_by_id[case_id]
        if (
            current["evidence"]["source_sha256"]
            != old["evidence"]["source_sha256"]
        ):
            source_changed.append(case_id)
            continue
        comparable.append(case_id)
        old_issues = issue_map(old)
        new_issues = issue_map(current)
        resolved_issues.extend(
            old_issues[key]
            for key in sorted(old_issues.keys() - new_issues.keys(), key=str)
        )
        introduced_issues.extend(
            new_issues[key]
            for key in sorted(new_issues.keys() - old_issues.keys(), key=str)
        )

        old_gaps = gap_map(old)
        new_gaps = gap_map(current)
        resolved_gaps.extend(
            old_gaps[key] for key in sorted(old_gaps.keys() - new_gaps.keys())
        )
        introduced_gaps.extend(
            new_gaps[key] for key in sorted(new_gaps.keys() - old_gaps.keys())
        )
        for step in sorted(old_gaps.keys() & new_gaps.keys()):
            if old_gaps[step]["summary"] != new_gaps[step]["summary"]:
                updated_gaps.append(
                    {
                        "case_id": case_id,
                        "step": step,
                        "previous_summary": old_gaps[step]["summary"],
                        "summary": new_gaps[step]["summary"],
                    }
                )

    return {
        "compared_to": previous["benchmark_version"],
        "comparable_cases": comparable,
        "source_changed_cases": source_changed,
        "added_cases": sorted(set(current_by_id) - set(previous_by_id)),
        "removed_cases": sorted(set(previous_by_id) - set(current_by_id)),
        "resolved_correspondence_issues": resolved_issues,
        "introduced_correspondence_issues": introduced_issues,
        "resolved_language_gaps": resolved_gaps,
        "introduced_language_gaps": introduced_gaps,
        "updated_language_gaps": updated_gaps,
    }


def build(cases_root, benchmark_version, benchmark_revision, released_at, previous=None):
    if not re.fullmatch(r"[0-9a-f]{40}", benchmark_revision):
        raise ValueError("benchmark revision must be a full 40-character Git commit")
    case_dirs = sorted(
        path
        for path in cases_root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    )
    if not case_dirs:
        raise ValueError("no benchmark cases found")
    cases = [case_entry(path) for path in case_dirs]

    language_versions = {case["language_version"] for case in cases}
    implementations = {case["implementation"] for case in cases}
    if None in language_versions or len(language_versions) != 1:
        raise ValueError("all cases must use one recorded language version")
    if None in implementations or len(implementations) != 1:
        raise ValueError("all cases must use one recorded implementation revision")

    unavailable_counts = sum(
        case["correspondence"]["total_steps"] is None for case in cases
    )
    total_steps = sum(
        case["correspondence"]["total_steps"] or 0 for case in cases
    )
    matched_steps = sum(
        case["correspondence"]["matched_steps"] or 0 for case in cases
    )
    return {
        "schema": SCHEMA,
        "benchmark_version": benchmark_version,
        "benchmark_revision": benchmark_revision,
        "released_at": released_at,
        "language_version": next(iter(language_versions)),
        "implementation": next(iter(implementations)),
        "totals": {
            "cases": len(cases),
            "covered_cases": sum(case["status"] == "covered" for case in cases),
            "cases_with_language_gaps": sum(
                case["status"] == "language_gap" for case in cases
            ),
            "incomplete_cases": sum(
                case["status"] == "incomplete" for case in cases
            ),
            "error_cases": sum(case["status"] == "error" for case in cases),
            "cases_with_unavailable_counts": unavailable_counts,
            "matched_steps": matched_steps,
            "total_steps": total_steps,
            "step_correspondence_percent": (
                None
                if unavailable_counts or not total_steps
                else round(100 * matched_steps / total_steps, 6)
            ),
            "open_correspondence_issues": sum(
                len(case["correspondence"]["issues"]) for case in cases
            ),
            "open_language_gaps": sum(
                len(case["language_gaps"]) for case in cases
            ),
        },
        "cases": cases,
        "changes": changes(cases, previous),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-root", required=True, type=Path)
    parser.add_argument("--benchmark-version", required=True)
    parser.add_argument("--benchmark-revision", required=True)
    parser.add_argument("--released-at", required=True)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output already exists; snapshots are immutable")
    try:
        previous = read_json(args.previous) if args.previous else None
        snapshot = build(
            args.cases_root,
            args.benchmark_version,
            args.benchmark_revision,
            args.released_at,
            previous,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        print(args.out)
        totals = snapshot["totals"]
        print(
            f'{totals["matched_steps"]}/{totals["total_steps"]}; '
            f'gaps={totals["open_language_gaps"]}; '
            f'issues={totals["open_correspondence_issues"]}'
        )
        return 0
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
