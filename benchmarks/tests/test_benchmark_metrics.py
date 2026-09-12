"""Real-frontend regression tests for the Cases 00/04 metrics pilot.

Run with CULSMA_TEST_PYTHON pointing to a Culsma 1.0.7rc1 environment.
No reviewed annotations or frozen paper totals are used as test inputs.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "benchmark_metrics.py"
SPEC = importlib.util.spec_from_file_location("benchmark_metrics", SCRIPT)
metrics = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = metrics
SPEC.loader.exec_module(metrics)
CASE = SCRIPT.parent.parent / "cases" / "00"
PLATE_CASE = SCRIPT.parent.parent / "cases" / "04"


def fixture_config(case):
    return metrics.read_json(Path(__file__).parent / "fixtures" / ("legacy-profile-" + case.name + ".json"))


def capture_fixture(case, python, destination):
    # Historical extractor profiles belong to tests, not the public case inputs.
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        shutil.copyfile(case / "protocol.culs", root / "protocol.culs")
        metrics.write_json(root / "case.json", fixture_config(case))
        return metrics.capture(root / "case.json", python, destination)


class InterpreterPathTests(unittest.TestCase):
    def test_capture_keeps_venv_symlink_for_probe_and_execution(self):
        # Real symlink and interpreter startup, without depending on installed Culsma.
        # The stub CLI identifies the process that actually produced the artifacts.
        import subprocess
        import sys
        import venv
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            env_root = root / "venv with spaces"
            venv.EnvBuilder(with_pip=False, symlinks=True).create(env_root)
            python = env_root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if not python.is_symlink():
                self.skipTest("This platform did not create a symlinked venv interpreter")
            self.assertNotEqual(str(python), str(python.resolve()))
            site = Path(subprocess.check_output(
                [str(python), "-I", "-c",
                 "import sysconfig;print(sysconfig.get_path('purelib'))"], text=True).strip())
            package = site / "culsma"
            package.mkdir()
            (package / "__init__.py").write_text("")
            (package / "cli.py").write_text(
                "import json,sys\nfrom pathlib import Path\n"
                "out=Path(sys.argv[sys.argv.index('--artifacts-dir')+1]);out.mkdir()\n"
                "identity={'executable':sys.executable,'prefix':sys.prefix,'module':__file__}\n"
                f"for name in {metrics.ARTIFACT_NAMES!r}:\n"
                " (out/(name+'.json')).write_text(json.dumps(identity))\n")
            for package_name, version in (("culsma", "1.0.7rc1"), ("lark", "1.3.1")):
                info = site / f"{package_name}-{version}.dist-info"
                info.mkdir()
                (info / "METADATA").write_text(
                    f"Metadata-Version: 2.1\nName: {package_name}\nVersion: {version}\n")
            for label, supplied in (("absolute", str(python)),
                                    ("relative", os.path.relpath(python))):
                with self.subTest(path=label):
                    bundle = capture_fixture(CASE, supplied, root / label)
                    receipt = metrics.read_json(bundle / "receipt.json")
                    actual = metrics.read_json(bundle / "artifacts/result.json")
                    self.assertEqual(receipt["command"][0], str(python))
                    self.assertEqual(receipt["environment"]["executable"], str(python))
                    self.assertEqual(actual["executable"], str(python))
                    self.assertEqual(actual["prefix"], str(env_root))
                    self.assertEqual(receipt["environment"]["prefix"], actual["prefix"])
                    self.assertTrue(actual["module"].startswith(str(site)))
                    self.assertTrue(receipt["environment"]["culsma_file"].startswith(str(site)))

class Case00Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        python = os.environ.get("CULSMA_TEST_PYTHON")
        if not python:
            raise unittest.SkipTest("Set CULSMA_TEST_PYTHON to a Culsma 1.0.7rc1 Python executable")
        cls.python = python
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.bundle = capture_fixture(CASE, python, cls.root / "input")
        cls.outputs = metrics.Extractor(cls.bundle).derive()

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(dir=self.root))
        self.addCleanup(shutil.rmtree, self.work)

    def variant(self, old, new):
        source = (CASE / "protocol.culs").read_text()
        self.assertEqual(source.count(old), 1)
        source = source.replace(old, new)
        (self.work / "protocol.culs").write_text(source)
        config = fixture_config(CASE)
        config["source_sha256"] = metrics.digest(self.work / "protocol.culs")
        metrics.write_json(self.work / "case.json", config)
        return metrics.capture(self.work / "case.json", self.python, self.work / "input")

    def test_case00_explicit_rule_examples(self):
        d = self.outputs["action_descriptors.json"]
        self.assertEqual(d["source_steps"], 7)
        # Expectations follow the new rule table, not old annotations.
        expected = [
            {"object": 5, "operation": 1},
            {"object": 1, "operation": 1, "schedule": 1},
            {"object": 1, "operation": 1, "environment": 1},
            {"object": 1, "operation": 1, "environment": 1, "program": 1},
            {"object": 2, "operation": 1},
            {"object": 2, "operation": 1},
            {"object": 2, "operation": 1},
        ]
        for row, counts in zip(d["rows"], expected):
            self.assertEqual(dict(metrics.Counter(e["category"] for e in row["descriptors"])), counts)
        self.assertEqual(d["descriptor_items"], sum(sum(x.values()) for x in expected))
        first_objects = {e["label"] for e in d["rows"][0]["descriptors"] if e["category"] == "object"}
        self.assertIn("clarified_lysate", first_objects)
        self.assertIn("debris_waste", first_objects)

    def test_loop_has_one_static_transfer_and_ten_completed_uses(self):
        d = self.outputs["action_descriptors.json"]["rows"][1]
        self.assertEqual(sum(x["label"] == "transfer" for x in d["descriptors"]), 1)
        continuity = self.outputs["material_state_continuity.json"]
        lysis = next(r for r in continuity["rows"] if r["members"][0]["name"] == "lysis_tube")
        step_ids = {event["step_id"] for use in lysis["uses"]["S2"] for event in use["execution"]}
        self.assertEqual(len(step_ids), 10)
        self.assertEqual(lysis["used_in"], ["S2", "S3", "S4", "S5", "S6"])
        self.assertEqual(continuity["reused_objects"], 3)
        self.assertEqual(continuity["later_use_links"], 8)
        self.assertEqual((continuity["active_steps"], continuity["completed_steps"]), (27, 27))

    def test_every_json_pointer_resolves(self):
        def resolve(data, pointer):
            for part in pointer.split("/")[1:]:
                key = part.replace("~1", "/").replace("~0", "~")
                data = data[int(key)] if isinstance(data, list) else data[key]
            return data
        for result in self.outputs.values():
            for _, node in metrics.nodes(result):
                if "file" in node and "json_pointer" in node:
                    resolve(metrics.read_json(self.bundle / node["file"]), node["json_pointer"])

    def test_result_records_are_preserved(self):
        trace = self.outputs["result_traceability.json"]
        raw = metrics.read_json(self.bundle / "artifacts/result.json")
        self.assertEqual(trace["reagent_records"], 2)
        self.assertEqual(trace["touched_containers"], 5)
        self.assertEqual(trace["final_material_states"], 3)
        self.assertEqual([r["record"] for r in trace["reagent_consumption"]],
                         raw["materials"]["reagent_consumption"])
        self.assertEqual([r["record"] for r in trace["final_products"]],
                         raw["materials"]["final_products"])
        self.assertEqual([r["name"] for r in trace["touched_names"]],
                         raw["resource_summary"]["containers"]["touched_names"])
        self.assertFalse(trace["container_identity"]["available"])

    def test_duplicate_names_preserve_multiplicity_and_order(self):
        extractor = metrics.Extractor(self.bundle)
        containers = extractor.data["result"]["resource_summary"]["containers"]
        containers["touched_names"] = ["same", "same", "other"]
        containers["touched_count"] = 3
        output = extractor.traceability()
        self.assertEqual(output["touched_containers"], 3)
        self.assertEqual([r["name"] for r in output["touched_names"]], ["same", "same", "other"])
        containers["touched_count"] = 2
        with self.assertRaisesRegex(metrics.EvidenceError, "count mismatch"):
            extractor.traceability()

    def test_changed_parameter_same_count_changes_details(self):
        bundle = self.variant("clarified_volume = 100uL", "clarified_volume = 90uL")
        changed = metrics.Extractor(bundle).derive()
        original = self.outputs["action_descriptors.json"]
        revised = changed["action_descriptors.json"]
        self.assertEqual(original["descriptor_items"], revised["descriptor_items"])
        self.assertNotEqual(original["rows"][4], revised["rows"][4])
        self.assertEqual(revised["parameters"]["clarified_volume"]["value"]["value"], 90.0)
        finals = changed["result_traceability.json"]["final_products"]
        clarified = next(r["record"] for r in finals if r["record"]["name"] == "ClarifiedLysate")
        self.assertEqual(clarified["volume_uL"], 90.0)

    def test_rename_updates_objects_without_changing_totals(self):
        # Test input preparation is allowed to edit code; extractor never does.
        source = (CASE / "protocol.culs").read_text().replace("debris_waste", "pellet_discard")
        (self.work / "protocol.culs").write_text(source)
        config = fixture_config(CASE)
        config["source_sha256"] = metrics.digest(self.work / "protocol.culs")
        metrics.write_json(self.work / "case.json", config)
        bundle = metrics.capture(self.work / "case.json", self.python, self.work / "input")
        changed = metrics.Extractor(bundle).derive()
        reuse = changed["material_state_continuity.json"]
        self.assertEqual(reuse["reused_objects"], 3)
        self.assertEqual(reuse["later_use_links"], 8)
        names = {r["members"][0]["name"] for r in reuse["rows"]}
        self.assertIn("pellet_discard", names)
        self.assertNotIn("debris_waste", names)

    def test_missing_internal_marker_fails_without_outputs(self):
        bundle = self.variant("// Source step S6:", "// Routing:")
        with self.assertRaisesRegex(metrics.EvidenceError, "STEP_MARKER"):
            metrics.extract(bundle, self.work / "results")
        self.assertFalse((self.work / "results").exists())

    def test_missing_final_marker_fails(self):
        bundle = self.variant("// Source step S7:", "// Readout:")
        with self.assertRaisesRegex(metrics.EvidenceError, "STEP_MARKER"):
            metrics.Extractor(bundle)

    def test_duplicate_and_ranged_markers_fail(self):
        for replacement in ("// Source step S5:", "// Source steps S5–S6:"):
            # Reuse valid compiler artifacts and isolate just the comment-scanner unit.
            extractor = metrics.Extractor(self.bundle)
            extractor.source = extractor.source.replace("// Source step S6:", replacement)
            with self.assertRaisesRegex(metrics.EvidenceError, "STEP_MARKER"):
                extractor.step_map()

    def test_rejects_legacy_receipt_and_mismatched_interpreter(self):
        bundle = self.work / "input"
        shutil.copytree(self.bundle, bundle)
        receipt = metrics.read_json(bundle / "receipt.json")
        for change, message in (({"schema": "patterns-metrics-input-v1"}, "INPUT_SCHEMA"),
                                ({"command": ["/different/python"]}, "INPUT_INTERPRETER")):
            metrics.write_json(bundle / "receipt.json", dict(receipt, **change))
            with self.assertRaisesRegex(metrics.EvidenceError, message):
                metrics.extract(bundle, self.work / "results")
            self.assertFalse((self.work / "results").exists())

    def test_changed_source_rejects_old_artifacts(self):
        bundle = self.work / "input"
        shutil.copytree(self.bundle, bundle)
        with (bundle / "protocol.culs").open("a") as handle:
            handle.write("\n// new comment\n")
        with self.assertRaisesRegex(metrics.EvidenceError, "INPUT_HASH"):
            metrics.extract(bundle, self.work / "results")
        self.assertFalse((self.work / "results").exists())

    def test_changed_artifact_rejects_unchanged_receipt(self):
        bundle = self.work / "input"
        shutil.copytree(self.bundle, bundle)
        path = bundle / "artifacts/result.json"
        data = metrics.read_json(path)
        data["resource_summary"]["containers"]["touched_count"] += 1
        metrics.write_json(path, data)
        with self.assertRaisesRegex(metrics.EvidenceError, "INPUT_HASH"):
            metrics.Extractor(bundle)

    def test_unsupported_alias_does_not_silently_drop(self):
        bundle = self.variant(
            '  let lysis_tube = tube(label = "LysisTube", capacity = 1.5mL);',
            '  let lysis_tube = tube(label = "LysisTube", capacity = 1.5mL);\n'
            '  let same_tube = lysis_tube;')
        with self.assertRaisesRegex(metrics.EvidenceError, "UNSUPPORTED_DECLARATION"):
            metrics.extract(bundle, self.work / "results")
        self.assertFalse((self.work / "results").exists())

    def test_same_bundle_reextracts_identically_and_rejects_overwrite(self):
        a, b = self.work / "a", self.work / "b"
        metrics.extract(self.bundle, a)
        metrics.extract(self.bundle, b)
        self.assertEqual(set(p.name for p in a.iterdir()), set(metrics.FILES))
        for name in metrics.FILES:
            self.assertEqual((a / name).read_bytes(), (b / name).read_bytes())
        before = {p.name: p.read_bytes() for p in a.iterdir()}
        with self.assertRaisesRegex(metrics.EvidenceError, "OUTPUT_EXISTS"):
            metrics.extract(self.bundle, a)
        self.assertEqual(before, {p.name: p.read_bytes() for p in a.iterdir()})

    def test_write_failure_leaves_no_partial_case(self):
        original = metrics.write_json
        def fail_second(path, value):
            if Path(path).name == "material_state_continuity.json":
                raise OSError("simulated disk failure")
            return original(path, value)
        with patch.object(metrics, "write_json", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "disk failure"):
                metrics.write_outputs(self.outputs, self.work / "results")
        self.assertFalse((self.work / "results").exists())
        self.assertEqual(list(self.work.iterdir()), [])

    def test_extraction_never_reads_old_annotations(self):
        # Even invalid annotations cannot influence generation.
        for name in ("action_descriptors.json", "object_reuse.json"):
            (self.bundle / name).write_text("not json")
        try:
            actual = metrics.Extractor(self.bundle).derive()
            self.assertEqual(actual, self.outputs)
        finally:
            for name in ("action_descriptors.json", "object_reuse.json"):
                (self.bundle / name).unlink()

class GroupSelectionTests(unittest.TestCase):
    def setUp(self):
        self.objects = {m: {"introduced_at": "S1"} for m in "ABC"}
        self.uses = {m: {"S2": []} for m in "ABC"}
        self.order = {"S1": 0, "S2": 1, "S3": 2}

    def group(self, members, name=None, intro="S1"):
        return {"members": list(members), "introduced_at": intro,
                "source_object": name or members}

    def select(self, candidates):
        return metrics.select_groups(self.objects, self.uses, candidates, self.order)

    def test_rejects_all_qualified_overlaps_independent_of_order(self):
        candidates = [self.group("AB"), self.group("BC")]
        a, audit = self.select(candidates)
        b, other_audit = self.select(list(reversed(candidates)))
        self.assertEqual(a, b)
        self.assertEqual(audit, other_audit)
        self.assertEqual([r["members"] for r in a], [["A"], ["B"], ["C"]])
        self.assertEqual([r["status"] for r in audit], ["overlap", "overlap"])

    def test_ineligible_overlap_does_not_disqualify_valid_group(self):
        self.uses["C"]["S3"] = []
        rows, audit = self.select([self.group("AB"), self.group("BC")])
        self.assertEqual([r["members"] for r in rows], [["A", "B"], ["C"]])
        self.assertEqual(audit[0]["status"], "retained")
        self.assertEqual(audit[1]["status"], "different_introduction_or_uses")

    def test_normalizes_same_members_before_overlap_check(self):
        rows, audit = self.select([self.group("AB", "first"), self.group("BA", "alias")])
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["status"], "retained")
        self.assertEqual(len(rows[0]["bases"]), 2)
        self.assertEqual([r["members"] for r in rows], [["A", "B"], ["C"]])

    def test_different_introduction_or_late_group_stays_separate(self):
        for unequal_intro in (False, True):
            with self.subTest(unequal_intro=unequal_intro):
                if unequal_intro:
                    self.objects["B"]["introduced_at"] = "S2"
                rows, audit = self.select([self.group("AB", intro="S2")])
                self.assertEqual(len(rows), 3)
                self.assertEqual(audit[0]["status"], "different_introduction_or_uses")


class Case04Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python = os.environ.get("CULSMA_TEST_PYTHON")
        if not cls.python:
            raise unittest.SkipTest("Set CULSMA_TEST_PYTHON to a Culsma 1.0.7rc1 Python executable")
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.bundle = capture_fixture(PLATE_CASE, cls.python, cls.root / "input")
        cls.extractor = metrics.PlateExtractor(cls.bundle)
        cls.outputs = cls.extractor.derive()

    def test_bound_entry_and_complete_execution(self):
        x = self.extractor
        self.assertEqual(x.entry_binding, "sandwich_elisa_result")
        self.assertEqual(x.covered_plan_ids, {s["step_id"] for _, s, _ in x.plan})
        out = self.outputs["material_state_continuity.json"]
        self.assertEqual((out["active_steps"], out["completed_steps"]), (778, 778))
        self.assertEqual(metrics.extract(self.bundle, self.root / "results"), self.outputs)

    def test_source_construct_categories_and_loop_deduplication(self):
        d = self.outputs["action_descriptors.json"]
        self.assertEqual(d["source_steps"], 10)
        by_step = {r["step"]: r for r in d["rows"]}
        self.assertEqual(by_step["S1"]["descriptor_items"], 28)  # Plate, six groups, 21 tubes.
        self.assertEqual(metrics.Counter(x["category"] for x in by_step["S2"]["descriptors"]),
                         {"constraint": 1, "environment": 1, "object": 2, "operation": 2})
        # Different iterator spellings do not create duplicate program/partition settings.
        for step in ("S3", "S4", "S6", "S7", "S8"):
            labels = metrics.Counter(x["label"] for x in by_step[step]["descriptors"])
            self.assertEqual(labels["filtration_program"], 1)
            self.assertEqual(labels["partition"], 1)
            self.assertEqual(labels["schedule"], 2)
        last = metrics.Counter(x["category"] for x in by_step["S10"]["descriptors"])
        self.assertEqual(last, {"object": 3, "schema": 1, "operation": 1})
        schema = next(x for x in by_step["S10"]["descriptors"] if x["category"] == "schema")
        self.assertIn("fields", str(schema))
        self.assertEqual(sum(x["label"] == "agit" for x in by_step["S9"]["descriptors"]), 1)

    def test_full_group_and_loop_index_use_actual_members(self):
        x = self.extractor
        wells = {oid: obj for oid, obj in x.objects.items() if obj["kind"] == "well"}
        hold_members, index_members = {}, {}
        op = {ps["step_id"]: ps["op"] for _, ps, _ in x.plan}
        for mid in wells:
            for step, uses in x.runtime_uses[mid].items():
                for use in uses:
                    for evidence in use["execution"]:
                        sid = evidence["step_id"]
                        if step == "S2" and op[sid] == "env_hold":
                            hold_members.setdefault(sid, set()).add(mid)
                        if step == "S3" and "/source" in use["source_reference"]["json_pointer"]:
                            index_members.setdefault(sid, set()).add(mid)
        self.assertEqual(len(hold_members), 1)
        self.assertEqual(next(iter(hold_members.values())), set(wells))
        self.assertEqual(len(index_members), 64)  # 16 coating + 3 x 16 wash aspirations.
        self.assertTrue(all(len(members) == 1 for members in index_members.values()))
        self.assertEqual(set.union(*index_members.values()), set(wells))

    def test_direct_and_range_selectors_preserve_member_scope(self):
        x = self.extractor
        direct, blank = set(), set()
        plate = x.symbols["elisa_plate"]
        blanks = x.symbols["blank_wells"]
        for mid, by_step in x.runtime_uses.items():
            for use in by_step.get("S5", []):
                if use["source_object"] == plate:
                    ref = use["source_reference"]
                    node = resolve_pointer(x.data["ast"], ref["json_pointer"])
                    if metrics.plain(node.get("regions")) == [{"start": "A1", "end": None}]:
                        direct.add(x.objects[mid]["name"])
                if use["source_object"] == blanks:
                    blank.add(x.objects[mid]["name"])
        self.assertEqual(direct, {"A1"})
        self.assertEqual(blank, {"E2", "F2", "G2", "H2"})

    def test_overlapping_groups_split_without_double_counting(self):
        r = self.outputs["material_state_continuity.json"]
        self.assertEqual(len(r["grouping_audit"]), 6)
        self.assertTrue(all(g["status"] == "overlap" for g in r["grouping_audit"]))
        self.assertTrue(all(len(row["members"]) == 1 for row in r["rows"]))
        self.assertEqual(r["reused_objects"], 37)  # 16 wells + 21 tubes.
        self.assertEqual(r["later_use_links"], 173)
        self.assertEqual(sum(row["later_use_links"] for row in r["rows"]
                             if row["members"][0]["kind"] == "well"), 16 * 9)

    def test_all_evidence_pointers_and_source_spans_match(self):
        data = {self.extractor.paths[k]: v for k, v in self.extractor.data.items()}
        for result in self.outputs.values():
            for _, node in metrics.nodes(result):
                if "file" in node and "json_pointer" in node:
                    actual = resolve_pointer(data[node["file"]], node["json_pointer"])
                    if "source_span" in node:
                        self.assertEqual(actual["span"], node["source_span"])

    def test_unknown_actual_member_fails_instead_of_using_whole_group(self):
        x = metrics.PlateExtractor(self.bundle)
        hold = next(ps for _, ps, _ in x.plan if ps["op"] == "env_hold")
        hold["gate"]["env_targets"][0]["name"] = "not_a_known_member"
        with self.assertRaisesRegex(metrics.EvidenceError, "REFERENCE_MEMBERS: unknown binding"):
            x.derive()

    def test_settings_keep_distinct_selector_associations(self):
        x = self.extractor
        targets = [n for _, n in metrics.nodes(x.protocol)
                   if "regions" in n and n["span"]["line"] > 50]
        self.assertNotEqual(x.associations([targets[0]]), x.associations([targets[1]]))

    def test_raw_results_and_grouped_readout_identity(self):
        t = self.outputs["result_traceability.json"]
        result = self.extractor.data["result"]
        for key in ("reagent_consumption", "final_products"):
            self.assertEqual([r["record"] for r in t[key]], result["materials"][key])
        self.assertEqual([r["name"] for r in t["touched_names"]],
                         result["resource_summary"]["containers"]["touched_names"])
        readout = self.extractor.objects[self.extractor.symbols["elisa_result"]]
        self.assertEqual(len(readout["runtime_identity"]["item_ids"]), 16)
        self.assertIn("data_group_id", readout["runtime_identity"])
        self.assertEqual((t["reagent_records"], t["touched_containers"], t["final_material_states"]),
                         (20, 37, 17))

    def test_single_index_changes_member_later_use_sets(self):
        # A small real-frontend case distinguishes index[0] from a whole-group use.
        root = self.root / "subset"
        root.mkdir()
        (root / "protocol.culs").write_text('''protocol Subset {
  // Source step S1: Setup.
  let p = plate(label = "P", format = "96well", carrier_id = "P", capacity = 500uL);
  let g = p[A1:A2];
  let r = tube(label = "R", capacity = 1mL, load = [content(kind = chemical, type = solvent, code = "R"):500uL]);
  // Source step S2: Only index zero.
  g[0] << [r:100uL];
  // Source step S3: Both wells.
  g << [r:10uL];
}
Subset();
''')
        config = fixture_config(PLATE_CASE)
        config.update(protocol="Subset", expected_steps=["S1", "S2", "S3"],
                      source_sha256=metrics.digest(root / "protocol.culs"))
        metrics.write_json(root / "case.json", config)
        bundle = metrics.capture(root / "case.json", self.python, root / "input")
        x = metrics.PlateExtractor(bundle)
        output = x.derive()["material_state_continuity.json"]
        rows = {row["members"][0]["name"]: row for row in output["rows"]}
        self.assertEqual(rows["A1"]["used_in"], ["S2", "S3"])
        self.assertEqual(rows["A2"]["used_in"], ["S3"])
        self.assertEqual(output["grouping_audit"][0]["status"], "different_introduction_or_uses")
        self.assertEqual((output["reused_objects"], output["later_use_links"]), (3, 5))

        # Change only the actual selection and recapture: a valid group now remains.
        source = root / "protocol.culs"
        source.write_text(source.read_text().replace("g[0] <<", "g <<"))
        config["source_sha256"] = metrics.digest(source)
        metrics.write_json(root / "case.json", config)
        whole = metrics.capture(root / "case.json", self.python, root / "whole-input")
        grouped = metrics.PlateExtractor(whole).derive()["material_state_continuity.json"]
        self.assertEqual(grouped["grouping_audit"][0]["status"], "retained")
        self.assertEqual((grouped["reused_objects"], grouped["later_use_links"]), (2, 4))
        group = next(row for row in grouped["rows"] if len(row["members"]) == 2)
        self.assertEqual({m["name"] for m in group["members"]}, {"A1", "A2"})


def resolve_pointer(data, pointer):
    for part in pointer.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


if __name__ == "__main__":
    unittest.main()
