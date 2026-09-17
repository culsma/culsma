import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "build_coverage_snapshot", ROOT / "tools" / "build_coverage_snapshot.py"
)
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


def sha(data):
    return hashlib.sha256(data.encode()).hexdigest()


def write_case(
    root, case_id, source, program, *, matched, issues, version="1.0.7"
):
    directory = root / case_id
    directory.mkdir()
    (directory / "source.md").write_text(source)
    (directory / "protocol.culs").write_text(program)
    total = source.count("\n") - 1
    record = {
        "schema": "source-coverage-v2",
        "rules": "steps-section-correspondence-v2",
        "metric": "source_step_correspondence",
        "case_id": case_id,
        "implementation": "a" * 40,
        "language_version": version,
        "source_sha256": sha(source),
        "program_sha256": sha(program),
        "total_steps": total,
        "matched_steps": matched,
        "coverage_percent": 100 * matched / total,
        "status": "pass" if not issues else "incomplete",
        "issues": issues,
    }
    (directory / "coverage.json").write_text(json.dumps(record))
    return directory


class CoverageSnapshotTests(unittest.TestCase):
    def test_snapshot_separates_correspondence_from_declared_language_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = "## Steps\n1. Read the result.\n"
            program = (
                "protocol Main() {\n"
                "// Source step S1: Read the result.\n"
                "// Language gap S1: Result rows cannot become material references.\n"
                "return sample;\n}\n"
            )
            write_case(root, "01-example", source, program, matched=1, issues=[])
            result = snapshot.build(root, "b1", "b" * 40, "2026-09-16")
            self.assertEqual(
                result["totals"]["step_correspondence_percent"], 100
            )
            self.assertEqual(result["totals"]["open_language_gaps"], 1)
            self.assertEqual(result["cases"][0]["status"], "language_gap")

    def test_comparison_reports_resolved_issues_and_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = "## Steps\n1. Spread the sample.\n"
            old_root = base / "old"
            new_root = base / "new"
            old_root.mkdir()
            new_root.mkdir()
            old_program = (
                "protocol Main() {\n"
                "// Source step S1: Spread the sample.\n"
                "// Language gap S1: Surface spreading is not expressible.\n"
                "}\n"
            )
            new_program = (
                "protocol Main() {\n"
                "// Source step S1: Spread the sample.\n"
                "plate << [sample:100uL] with constraint(spread);\n"
                "}\n"
            )
            write_case(
                old_root,
                "01-spread",
                source,
                old_program,
                matched=0,
                issues=[{"step": 1, "reason": "no_code_region"}],
            )
            write_case(
                new_root,
                "01-spread",
                source,
                new_program,
                matched=1,
                issues=[],
                version="1.0.8",
            )
            previous = snapshot.build(
                old_root, "b1", "b" * 40, "2026-09-15"
            )
            current = snapshot.build(
                new_root, "b2", "c" * 40, "2026-09-16", previous
            )
            changes = current["changes"]
            self.assertEqual(
                changes["resolved_correspondence_issues"][0]["step"], 1
            )
            self.assertEqual(changes["resolved_language_gaps"][0]["step"], 1)
            self.assertEqual(changes["comparable_cases"], ["01-spread"])

    def test_changed_source_is_not_compared_as_language_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            old_root = base / "old"
            new_root = base / "new"
            old_root.mkdir()
            new_root.mkdir()
            write_case(
                old_root,
                "01-example",
                "## Steps\n1. Hold.\n",
                "protocol Main() {\n// Source step S1: Hold.\nreturn sample;\n}\n",
                matched=1,
                issues=[],
            )
            write_case(
                new_root,
                "01-example",
                "## Steps\n1. Hold longer.\n",
                (
                    "protocol Main() {\n"
                    "// Source step S1: Hold longer.\n"
                    "return sample;\n}\n"
                ),
                matched=1,
                issues=[],
                version="1.0.8",
            )
            previous = snapshot.build(
                old_root, "b1", "b" * 40, "2026-09-15"
            )
            current = snapshot.build(
                new_root, "b2", "c" * 40, "2026-09-16", previous
            )
            self.assertEqual(
                current["changes"]["source_changed_cases"], ["01-example"]
            )
            self.assertEqual(current["changes"]["comparable_cases"], [])

    def test_stale_case_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = write_case(
                root,
                "01-example",
                "## Steps\n1. Hold.\n",
                "protocol Main() {\n// Source step S1: Hold.\nreturn sample;\n}\n",
                matched=1,
                issues=[],
            )
            (directory / "protocol.culs").write_text("changed")
            with self.assertRaisesRegex(ValueError, "stale program_sha256"):
                snapshot.build(root, "b1", "b" * 40, "2026-09-16")

    def test_error_status_remains_distinct_from_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = write_case(
                root,
                "01-example",
                "## Steps\n1. Hold.\n",
                "protocol Main() {\n// Source step S1: Hold.\n}\n",
                matched=0,
                issues=[{"step": None, "reason": "check_error"}],
            )
            record_path = directory / "coverage.json"
            record = json.loads(record_path.read_text())
            record["status"] = "error"
            record["total_steps"] = None
            record["matched_steps"] = None
            record["coverage_percent"] = None
            record_path.write_text(json.dumps(record))
            result = snapshot.build(root, "b1", "b" * 40, "2026-09-16")
            self.assertEqual(result["cases"][0]["status"], "error")
            self.assertEqual(result["totals"]["error_cases"], 1)
            self.assertEqual(result["totals"]["incomplete_cases"], 0)
            self.assertIsNone(result["totals"]["step_correspondence_percent"])


if __name__ == "__main__":
    unittest.main()
