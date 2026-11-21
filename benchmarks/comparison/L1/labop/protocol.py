"""Reproduce LabOP L1 argument propagation, with a direct-Transfer control.

Run with the pinned labop-env Python. No instruments or custom operation
handlers are used. Graphviz rendering is replaced only to retain DOT files.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from unittest.mock import patch

import labop
import sbol3
from uml import ActivityParameterNode
from labop.execution.execution_engine import ExecutionEngine

from evaluate import save_dot

SAMPLE = "http://bioprotocols.org/labop#SampleArray"
MICROLITRE = "http://www.ontology-of-units-of-measure.org/resource/om-2/microlitre"
PIN = "2e2bd88150c71a440771fd369f40295dfd622324"


def build(mode, parent=None, doc=None):
    if parent is None:
        parent, doc = labop.Protocol.initialize_protocol(
            "main", "L1 reproduction", f"https://example.org/l1-reproduction/{mode}/"
        )

    # Define one parameterized procedure containing one Transfer.
    sub = labop.Protocol.create_protocol("Aliquot", "Aliquot")
    doc.add(sub)
    source = sub.input_value("source", SAMPLE)
    destination = sub.input_value("destination", SAMPLE)
    amount = sub.input_value("amount", sbol3.OM_MEASURE)
    sub.primitive_step("Transfer", source=source, destination=destination, amount=amount)

    # Prepare the same initial state in both variants.
    specs = {}
    def empty_tube(name):
        spec = labop.ContainerSpec(name + "_spec", queryString="cont:MicrofugeTube1.5mL")
        specs[name] = str(spec.identity)
        samples = labop.SampleArray(name=name, container_type=spec)
        samples.empty(geometry="A1")
        doc.add(spec)
        return parent.primitive_step(
            "EmptyContainer", specification=spec, sample_array=samples
        ).output_pin("samples")

    stock, first, second = empty_tube("stock"), empty_tube("first"), empty_tube("second")
    buffer = sbol3.Component("buffer", [sbol3.SBO_FUNCTIONAL_ENTITY])
    doc.add(buffer)
    parent.primitive_step(
        "Provision", resource=buffer, destination=stock,
        amount=sbol3.Measure(100, MICROLITRE),
    )

    if mode == "subprotocol_explicit":
        # Public lower-level authoring path used in the upstream pH example.
        call_1 = parent.execute_primitive(
            sub, source=stock, destination=first,
            amount=sbol3.Measure(10, MICROLITRE),
        )
        call_2 = parent.execute_primitive(
            sub, source=stock, destination=second,
            amount=sbol3.Measure(20, MICROLITRE),
        )
        parent.order(parent.get_last_step(), call_1)
        parent.order(call_1, call_2)
        parent.order(call_2, parent.final())
        sub.order(sub.get_last_step(), sub.final())
    elif mode == "subprotocol":
        # The counterexample: two calls to the SAME procedure definition.
        call_1 = parent.primitive_step(
            sub, source=stock, destination=first,
            amount=sbol3.Measure(10, MICROLITRE),
        )
        call_2 = parent.primitive_step(
            sub, source=stock, destination=second,
            amount=sbol3.Measure(20, MICROLITRE),
        )
    else:
        # Positive control: identical transfers without a procedure boundary.
        call_1 = parent.primitive_step(
            "Transfer", source=stock, destination=first,
            amount=sbol3.Measure(10, MICROLITRE),
        )
        call_2 = parent.primitive_step(
            "Transfer", source=stock, destination=second,
            amount=sbol3.Measure(20, MICROLITRE),
        )
    return parent, doc, sub, [call_1, call_2], specs, buffer


def run(mode, output):
    output.mkdir(parents=True, exist_ok=True)
    parent, doc, sub, calls, specs, buffer = build(mode)
    validation = doc.validate()
    engine = ExecutionEngine(out_dir=str(output), use_ordinal_time=True, failsafe=False)
    doc.write(str(output / "protocol.ttl"), sbol3.TURTLE)
    with patch("graphviz.Digraph.render", save_dot):
        execution = engine.execute(
            parent, sbol3.Agent("software_runner"), id="execution", parameter_values=[]
        )
    doc.write(str(output / "execution.ttl"), sbol3.TURTLE)

    call_ids = {str(c.identity): index + 1 for index, c in enumerate(calls)}
    entered_calls, transfers, child_inputs = [], [], []
    for record in execution.executions:
        node = record.get_node()
        if isinstance(node, ActivityParameterNode) and node.get_toplevel() is sub:
            child_inputs.append(node.get_parameter().name)
        if not isinstance(record, labop.CallBehaviorExecution):
            continue
        values = record.parameter_value_map()
        if str(node.identity) in call_ids:
            entered_calls.append({
                "call": call_ids[str(node.identity)],
                "amount_ul": values["amount"].value,
            })
        if str(record.get_behavior().identity).endswith("/Transfer"):
            transfers.append({
                "amount_ul": values["amount"].value,
                "unit": str(values["amount"].unit),
                "destination": str(values["destination"].identity),
            })

    graph = engine.prov_observer.graph
    (output / "sample_graph.json").write_text(json.dumps(graph.to_dict(), default=str))
    latest = {}
    for name, identity in specs.items():
        amounts = graph["contents"].sel(
            container=identity, location="A1", reagent=str(buffer.identity)
        ).sortby("tick", ascending=False).values.flatten()
        latest[name] = next((float(x) for x in amounts if math.isfinite(float(x))), None)

    result = {
        "mode": mode,
        "validation_errors": list(map(str, validation.errors)),
        "validation_warnings": list(map(str, validation.warnings)),
        "planned_calls": len(calls),
        "entered_calls": entered_calls,
        "executed_child_inputs": sorted(set(child_inputs)),
        "executed_transfers": transfers,
        "completed_normally": execution.completed_normally,
        "issues": {str(k): list(map(str, v)) for k, v in engine.issues.items()},
        "latest_recorded_buffer_ul": latest,
        "null_means": "No finite buffer quantity recorded; null is not converted to zero.",
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    results = {mode: run(mode, args.output / mode) for mode in ("subprotocol", "direct")}
    # Check the observer and setup using a successful direct-operation control.
    assert [t["amount_ul"] for t in results["direct"]["executed_transfers"]] == [10, 20]
    assert results["direct"]["latest_recorded_buffer_ul"] == {"stock": 70, "first": 10, "second": 20}
    report = {
        "labop_commit": PIN,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "expected_buffer_ul": {"stock": 70, "first": 10, "second": 20},
        "results": results,
    }
    (args.output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
