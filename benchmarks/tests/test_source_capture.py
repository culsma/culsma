"""Source-only capture: no maintained per-case metric configuration."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import benchmark_metrics as metrics


class ScopeTests(unittest.TestCase):
    def scope(self, definitions, entry="Main", setup=False):
        # Small exported-AST fixtures; source text contains only comment content.
        text, protocols = "", []
        for name, comments, callees in definitions:
            start = len(text)
            text += "\n".join(comments) + "\n"
            protocols.append(dict(name=name, span=dict(start=start, end=len(text)),
                                  statements=[dict(name=n, args=[]) for n in callees]))
        statements = [dict(name="answer", value=dict(name=entry, args=[]))]
        if setup:
            statements.insert(0, dict(name="sample", value=dict(name="well", args=[])))
        return metrics.discover_scope(text, dict(protocols=protocols, statements=statements))

    def test_entry_binding_and_global_setup(self):
        result = self.scope([("Main", ["// Source step S1: setup"], [])], setup=True)
        self.assertEqual(result, dict(protocol="Main", step_protocol="Main", expected_steps=["S1"]))

    def test_unmarked_batch_wrapper_and_unreachable_labels(self):
        result = self.scope([("Main", [], ["Child", "Child"]),
                             ("Child", ["// Source step S1: act"], []),
                             ("Unused", ["// Source step S99: ignored"], [])])
        self.assertEqual(result["step_protocol"], "Child")
        self.assertEqual(result["expected_steps"], ["S1"])

    def test_nested_repeated_calls_and_nonmonotonic_markers(self):
        result = self.scope([("Main", ["// Source step S3: later"], ["Child", "Child"]),
                             ("Child", ["// Source step S2: second", "// Source step S1: first"], [])])
        self.assertEqual(result["step_protocol"], "Main")
        self.assertEqual(result["expected_steps"], ["S1", "S2", "S3"])

    def test_missing_invalid_and_ranged_markers_fail(self):
        for comments in ([], ["// Source step S2: missing first"],
                         ["// Source step S1: one", "// Source step S3: missing middle"],
                         ["// Source step S1-S3: range"], ["// Source step S0: zero"]):
            with self.subTest(comments=comments), self.assertRaises(metrics.EvidenceError):
                self.scope([("Main", comments, [])])

    def test_recursion_fails(self):
        with self.assertRaisesRegex(metrics.EvidenceError, "RECURSIVE_CALL"):
            self.scope([("Main", ["// Source step S1: recurse"], ["Main"])])

    def test_multiple_entry_calls_fail(self):
        with self.assertRaisesRegex(metrics.EvidenceError, "UNSUPPORTED_ENTRY"):
            metrics.discover_scope("", dict(protocols=[dict(name="Main")],
                                           statements=[dict(name="Main", args=[])] * 2))

    def test_scope_discovers_markers_across_captured_sources(self):
        sources = {
            "/capture/protocol.culs": "// Source step S1: root\n",
            "/capture/helper.culs": "// Source step S2: helper\n",
        }
        ast = {
            "protocols": [
                {"name": "Main", "source_path": "/capture/protocol.culs",
                 "span": {"start": 0, "end": len(sources["/capture/protocol.culs"])},
                 "statements": [{"name": "Helper", "args": []}]},
                {"name": "Helper", "source_path": "/capture/helper.culs",
                 "span": {"start": 0, "end": len(sources["/capture/helper.culs"])},
                 "statements": []},
            ],
            "statements": [{"name": "result", "value": {"name": "Main", "args": []}}],
        }
        result = metrics.discover_scope(sources, ast)
        self.assertEqual(result["expected_steps"], ["S1", "S2"])


class DependencyCaptureTests(unittest.TestCase):
    def test_collects_recursive_includes_and_library_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case"
            library = root / "library"
            (case / "parts").mkdir(parents=True)
            library.mkdir()
            (case / "protocol.culs").write_text(
                'include "parts/helper.culs";\nimport Shared;\n', encoding="utf-8"
            )
            (case / "parts" / "helper.culs").write_text("protocol Helper {}\n", encoding="utf-8")
            (library / "Shared.culs").write_text("protocol SharedProtocol {}\n", encoding="utf-8")

            captured = metrics._capture_sources(case / "protocol.culs", [library])

            self.assertEqual(
                set(captured),
                {Path("protocol.culs"), Path("parts/helper.culs"), Path("libraries/0/Shared.culs")},
            )

    def test_include_cannot_escape_source_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "case"
            case.mkdir()
            (root / "outside.culs").write_text("protocol Outside {}\n", encoding="utf-8")
            (case / "protocol.culs").write_text('include "../outside.culs";\n', encoding="utf-8")

            with self.assertRaisesRegex(metrics.EvidenceError, "escapes"):
                metrics._capture_sources(case / "protocol.culs", [])


class SourceCaptureTests(unittest.TestCase):
    def test_real_source_capture_and_three_outputs_without_config(self):
        python = os.environ.get("CULSMA_TEST_PYTHON")
        if not python:
            self.skipTest("Set CULSMA_TEST_PYTHON for source capture integration")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "01"
            case.mkdir()
            source = case / "protocol.culs"
            source.write_text('''protocol Main {
  repeat i in schedule(start = 1, end = 2, step = 1) { Child(); }
}
protocol Child {
  // Source step S1: declare materials.
  let a = tube(label = "A", capacity = 1mL, load = [content(kind = chemical, type = solvent, code = "A"):500uL]);
  let b = tube(label = "B", capacity = 1mL);
  // Source step S2: transfer.
  b << [a:100uL];
}
Main();
''')
            bundle = metrics.capture(source, python, root / "input")
            generated = metrics.read_json(bundle / "case.json")
            self.assertEqual(generated["step_protocol"], "Child")
            self.assertEqual(generated["expected_steps"], ["S1", "S2"])
            self.assertEqual(list(case.iterdir()), [source])
            outputs = metrics.extract(bundle, root / "evaluation")
            self.assertEqual(set(outputs), set(metrics.FILES))
            self.assertEqual(outputs["action_descriptors.json"]["source_steps"], 2)

    def test_real_source_capture_with_include_preserves_dependency_evidence(self):
        python = os.environ.get("CULSMA_TEST_PYTHON")
        if not python:
            self.skipTest("Set CULSMA_TEST_PYTHON for source capture integration")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "02"
            case.mkdir()
            source = case / "protocol.culs"
            source.write_text('''include "helper.culs";
protocol Main {
  // Source step S1: allocate through a dependency protocol.
  Helper();
}
Main();
''', encoding="utf-8")
            (case / "helper.culs").write_text('''protocol Helper {
  let a = tube(label = "A", capacity = 1mL);
}
''', encoding="utf-8")

            bundle = metrics.capture(source, python, root / "input")
            receipt = metrics.read_json(bundle / "receipt.json")
            self.assertIn("helper.culs", receipt["files"])
            outputs = metrics.extract(bundle, root / "evaluation")
            self.assertIn('"source_file":"helper.culs"', metrics.canonical(outputs))
