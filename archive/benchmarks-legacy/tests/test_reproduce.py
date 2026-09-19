import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reproduce", ROOT / "reproduce.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def runtime_fixture(case):
    """Minimal CLI-shaped fixture built from the plain published metric records."""
    c = r.read_json(r.case_dir(case) / "material_state_continuity.json")
    t = r.read_json(r.case_dir(case) / "result_traceability.json")
    return {"ok": True, "returns": t["formal_returns"]["value"], "report": {
        "execution": copy.deepcopy(c["execution"]), "external_inventory": {"checked": False},
        "resource_summary": {"containers": {"touched_count": t["touched_containers"],
            "touched_names": [x["name"] for x in t["touched_names"]]}},
        "materials": {"has_material_state": True,
            "reagent_consumption": [x["record"] for x in t["reagent_consumption"]],
            "final_products": [x["record"] for x in t["final_products"]]}}}


class ReproductionTests(unittest.TestCase):
    def test_plain_case_metrics_reproduce_manuscript_counts(self):
        rows = r.derive()
        expected = r.read_json(ROOT / "expected/tables.json")
        self.assertEqual(rows, expected["cases"])
        self.assertEqual(r.total(rows), expected["totals"])
        self.assertEqual(r.compare(rows), [])

    def test_worked_example_never_enters_totals(self):
        rows = {"00": dict.fromkeys(r.FIELDS, 999), "01": dict.fromkeys(r.FIELDS, 1)}
        self.assertEqual(r.total(rows), dict.fromkeys(r.FIELDS, 1))

    def test_generated_entries_not_unchecked_cached_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            for name in ("action_descriptors.json", "material_state_continuity.json", "result_traceability.json"):
                r.write_json(dest / name, r.read_json(ROOT / "cases/00" / name))
            counts = r.generated_counts(dest)
            self.assertEqual(counts["descriptor_items"], 25)
            obj = r.read_json(dest / "action_descriptors.json")
            obj["descriptor_items"] = 999
            r.write_json(dest / "action_descriptors.json", obj)
            with self.assertRaises(ValueError):
                r.generated_counts(dest)

    def test_invalid_reuse_link_is_not_silently_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            for name in ("action_descriptors.json", "material_state_continuity.json", "result_traceability.json"):
                r.write_json(dest / name, r.read_json(ROOT / "cases/00" / name))
            obj = r.read_json(dest / "material_state_continuity.json")
            obj["rows"][0]["used_in"][0] = obj["rows"][0]["introduced_at"]
            r.write_json(dest / "material_state_continuity.json", obj)
            with self.assertRaises(ValueError):
                r.generated_counts(dest)

    def test_completed_versus_total_excludes_skipped(self):
        output = runtime_fixture("01")
        self.assertEqual(r.runtime_counts(output)["active_steps"], 611)
        self.assertEqual(output["report"]["execution"]["total_steps"], 657)

    def test_failed_or_incomplete_execution_rejected(self):
        original = runtime_fixture("00")
        for field, value in (("diagnostic_count", 1), ("failed_steps", 1), ("completed_steps", 0)):
            output = copy.deepcopy(original)
            output["report"]["execution"][field] = value
            with self.assertRaises(ValueError):
                r.runtime_counts(output)

    def test_duplicate_display_names_are_distinct_records(self):
        output = runtime_fixture("01")
        names = output["report"]["resource_summary"]["containers"]["touched_names"]
        self.assertGreater(len(names), len(set(names)))
        self.assertEqual(r.runtime_counts(output)["touched_containers"], len(names))

    def test_quantity_change_detected_even_with_same_counts(self):
        original = runtime_fixture("00")
        changed = copy.deepcopy(original)
        changed["report"]["materials"]["final_products"][0]["volume_uL"] += 1
        self.assertEqual(r.runtime_counts(original), r.runtime_counts(changed))
        self.assertNotEqual(r.record_projection(original), r.record_projection(changed))

    def test_missing_runtime_field_fails(self):
        output = runtime_fixture("00")
        del output["report"]["materials"]["final_products"]
        with self.assertRaises(KeyError):
            r.runtime_counts(output)

    def test_changed_descriptor_causes_count_difference(self):
        rows = r.derive()
        rows["01"]["descriptor_items"] += 1
        differences = r.compare(rows)
        self.assertTrue(any("Case 01 descriptor_items" in d for d in differences))

    def test_case_discovery_is_sorted_and_rejects_missing_program(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            for name in ("02", "00", "01"):
                case = dest / "cases" / name
                case.mkdir(parents=True)
                (case / "protocol.culs").write_text("Main();")
            with patch.object(r, "ROOT", dest):
                self.assertEqual(r.discover_cases(), ["00", "01", "02"])
                (dest / "cases/03").mkdir()
                with self.assertRaisesRegex(ValueError, "missing protocol.culs"):
                    r.discover_cases()

    def test_case_set_must_match_expected_tables(self):
        rows = r.derive()
        del rows["00"]
        with self.assertRaisesRegex(ValueError, "case set differs"):
            r.compare(rows)

    def test_dependency_lock_is_the_version_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "requirements.lock"
            path.write_text((ROOT / "requirements.lock").read_text().replace("1.0.7rc1", "1.0.8"))
            self.assertEqual(r.locked_versions(path)["culsma"], "1.0.8")
            path.write_text("culsma>=1.0.7\n")
            with self.assertRaisesRegex(ValueError, "DEPENDENCY_LOCK"):
                r.locked_versions(path)

    def test_supported_python_patch_versions_are_accepted(self):
        for version in ("3.11.11", "3.12.8", "3.12.11", "3.13.1"):
            with self.subTest(version=version), patch.object(r.platform, "python_version", return_value=version), \
                 patch.object(r.importlib.metadata, "version", side_effect=lambda n: {"culsma": "1.0.7rc1", "lark": "1.3.1"}[n]):
                self.assertEqual(r.check_environment()["python"], version)

    def test_unverified_python_series_are_rejected(self):
        for version in ("3.10.16", "3.14.0"):
            with self.subTest(version=version), patch.object(r.platform, "python_version", return_value=version), \
                 patch.object(r.importlib.metadata, "version", side_effect=lambda n: {"culsma": "1.0.7rc1", "lark": "1.3.1"}[n]):
                with self.assertRaisesRegex(ValueError, "unsupported Python"):
                    r.check_environment()

    def test_python_prerelease_is_rejected(self):
        from types import SimpleNamespace
        with patch.object(r.platform, "python_version", return_value="3.13.0rc1"), \
             patch.object(r.sys, "version_info", SimpleNamespace(releaselevel="candidate")), \
             patch.object(r.importlib.metadata, "version", side_effect=lambda n: {"culsma": "1.0.7rc1", "lark": "1.3.1"}[n]):
            with self.assertRaisesRegex(ValueError, "unsupported Python"):
                r.check_environment()

    def test_dependencies_still_require_exact_versions(self):
        for versions in ({"culsma": "1.0.5", "lark": "1.3.1"}, {"culsma": "1.0.7rc1", "lark": "1.2.2"}):
            with self.subTest(versions=versions), patch.object(r.platform, "python_version", return_value="3.13.1"), \
                 patch.object(r.importlib.metadata, "version", side_effect=versions.__getitem__):
                with self.assertRaisesRegex(ValueError, "package version mismatch"):
                    r.check_environment()

    def test_plain_trace_projection_matches_runtime_records(self):
        for case in ("00", "01", "05"):
            trace = r.read_json(r.case_dir(case) / "result_traceability.json")
            run = {"ok": True, "state": {"artifacts": {"material_state": {"containers": {
                row["container_id"]: row["record"]["material_state"]
                for row in trace["final_material_records"]}}}}}
            self.assertEqual(r.trace_projection(trace), r.record_projection(runtime_fixture(case), run))
            changed = copy.deepcopy(trace)
            changed["final_material_records"][0]["record"]["volume_uL"] += 1
            self.assertNotEqual(r.trace_projection(changed), r.trace_projection(trace))

    def test_delivery_has_no_archives_or_duplicate_reuse_files(self):
        for removed in ("manifest.json", "checksums.json", "references.bib", "tools/prepare_snapshot.py"):
            self.assertFalse((ROOT / removed).exists())
        for case in r.discover_cases():
            self.assertEqual({p.name for p in r.case_dir(case).iterdir()}, {
                "protocol.culs", "source.md", "source.steps.json",
                "action_descriptors.json", "material_state_continuity.json",
                "result_traceability.json"})
        self.assertFalse((ROOT / "patterns").exists())
        self.assertFalse((ROOT / "docs").exists())
        self.assertEqual({p.name for p in (ROOT / "expected").iterdir()},
                         {"tables.json", "tables.md"})

    def test_real_case_discovery(self):
        self.assertEqual(r.discover_cases(), [f"{i:02}" for i in range(15)])


if __name__ == "__main__":
    unittest.main()
