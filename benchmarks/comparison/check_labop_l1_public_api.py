"""Check L1 against upstream subprotocol usage and the official harness.

Only output paths and Graphviz rendering are redirected. No LabOP binding,
token propagation, execution or material handlers are replaced.
"""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import labop
from labop.execution.harness import ProtocolHarness, ProtocolExecutionNTuples
from gfp_labop import save_dot
from labop_l1_counterexample import build, run

from replay_paths import PACKAGE, RUNTIME, result_path
OUT = result_path("l1/public-api-audit")
SOURCE = RUNTIME / 'labop-source'


def upstream_test():
    spec = importlib.util.spec_from_file_location(
        "pinned_test_subprotocols", SOURCE / "test/test_subprotocols.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def redirected_harness(*args, **kwargs):
        kwargs["base_dir"] = str(OUT / "upstream-test")
        return ProtocolHarness(*args, **kwargs)
    suite = unittest.TestSuite([module.TestSubprotocols("test_subexecutions")])
    stream = io.StringIO()
    with patch("labop.execution.harness.ProtocolHarness", redirected_harness), \
         patch("graphviz.Digraph.render", save_dot):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (OUT / "upstream-test.txt").write_text(stream.getvalue())
    return {"tests_run": result.testsRun, "success": result.wasSuccessful(),
            "failures": len(result.failures), "errors": len(result.errors)}


def through_harness():
    captured = {}
    def entry_point(doc, protocol):
        values = build("subprotocol", parent=protocol, doc=doc)
        captured["calls"] = values[3]
        return values[0]
    harness = ProtocolHarness(
        namespace="https://example.org/l1-api-audit/",
        protocol_name="parameter_reuse", base_dir=str(OUT / "harness"),
        execution_id="reuse_execution", entry_point=entry_point,
    )
    with patch("graphviz.Digraph.render", save_dot):
        harness.run()
    artifact = next(iter(harness.artifacts_of_type(ProtocolExecutionNTuples)))
    execution = artifact.execution
    transfers = []
    for record in execution.executions:
        if isinstance(record, labop.CallBehaviorExecution) and str(record.get_behavior().identity).endswith("/Transfer"):
            transfers.append(record.parameter_value_map()["amount"].value)
    return {"planned_calls": len(captured["calls"]),
            "completed_normally": execution.completed_normally,
            "executed_transfer_amounts_ul": transfers,
            "issues": {str(k): list(map(str, v)) for k, v in artifact.execution_engine.issues.items()}}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"upstream_subprotocol_test": upstream_test()}
    (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    report["counterexample_official_harness"] = through_harness()
    (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    report["counterexample_explicit_order"] = run("subprotocol_explicit", OUT / "explicit-order")
    (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
