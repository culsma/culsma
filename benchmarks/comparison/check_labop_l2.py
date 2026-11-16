"""L2: connect a producer protocol's output to a consumer protocol's input.

Pinned LabOP software execution only; no operation handlers are changed.
Only Graphviz rendering is redirected to retained DOT source.
"""
import hashlib
import json
import math
import traceback
from pathlib import Path
from unittest.mock import patch

import labop
import sbol3
from labop.execution.execution_engine import ExecutionEngine
from gfp_labop import save_dot
from labop_l1_counterexample import SAMPLE, MICROLITRE, PIN

PACKAGE = Path(__file__).resolve().parent
from replay_paths import result_path
OUT = result_path("l2/labop")


def run(mode):
    out = OUT / mode
    out.mkdir(parents=True, exist_ok=True)
    parent, doc = labop.Protocol.initialize_protocol(
        "main", "L2 output to input", "https://example.org/l2/" + mode + "/")
    buffer = sbol3.Component("buffer", [sbol3.SBO_FUNCTIONAL_ENTITY])
    doc.add(buffer)
    specs = {}

    def container(protocol, name):
        spec = labop.ContainerSpec(name + "_spec", queryString="cont:MicrofugeTube1.5mL")
        specs[name] = str(spec.identity)
        array = labop.SampleArray(name=name, container_type=spec)
        array.empty(geometry="A1")
        doc.add(spec)
        return protocol.primitive_step("EmptyContainer", specification=spec,
                                       sample_array=array).output_pin("samples")

    target = container(parent, "target")
    if mode == "direct":
        prepared = container(parent, "prepared")
        parent.primitive_step("Provision", resource=buffer, destination=prepared,
                              amount=sbol3.Measure(100, MICROLITRE))
        parent.primitive_step("Transfer", source=prepared, destination=target,
                              amount=sbol3.Measure(10, MICROLITRE))
    else:
        producer = labop.Protocol.create_protocol("PrepareSample", "PrepareSample")
        consumer = labop.Protocol.create_protocol("TakeAliquot", "TakeAliquot")
        doc.add([producer, consumer])
        prepared = container(producer, "prepared")
        producer.primitive_step("Provision", resource=buffer, destination=prepared,
                                amount=sbol3.Measure(100, MICROLITRE))
        producer.designate_output("sample", SAMPLE, source=prepared)
        sample_in = consumer.input_value("sample", SAMPLE)
        destination_in = consumer.input_value("destination", SAMPLE)
        consumer.primitive_step("Transfer", source=sample_in, destination=destination_in,
                                amount=sbol3.Measure(10, MICROLITRE))
        first = parent.primitive_step(producer)
        parent.primitive_step(consumer, sample=first.output_pin("sample"), destination=target)
        if mode == "composition_explicit_final":
            producer.order(producer.get_last_step(), producer.final())
            consumer.order(consumer.get_last_step(), consumer.final())
            parent.order(parent.get_last_step(), parent.final())

    validation = doc.validate()
    doc.write(str(out / "protocol.ttl"), sbol3.TURTLE)
    report = {"mode": mode, "validation_errors": list(map(str, validation.errors)),
              "validation_warnings": list(map(str, validation.warnings))}
    engine = ExecutionEngine(out_dir=str(out), use_ordinal_time=True, failsafe=False)
    try:
        with patch("graphviz.Digraph.render", save_dot):
            execution = engine.execute(parent, sbol3.Agent("software_runner"),
                                       id="execution", parameter_values=[])
        report["completed_normally"] = execution.completed_normally
        doc.write(str(out / "execution.ttl"), sbol3.TURTLE)
        records = []
        for record in execution.executions:
            if isinstance(record, labop.CallBehaviorExecution):
                values = record.parameter_value_map()
                records.append({"behavior": str(record.get_behavior().identity),
                    "node": str(record.get_node().identity), "parameters": {
                        k: ({"value": v.value, "unit": str(v.unit)} if isinstance(v, sbol3.Measure)
                            else str(v.identity) if hasattr(v, "identity") else str(v))
                        for k, v in values.items()}})
        report["call_records"] = records
        graph = engine.prov_observer.graph
        (out / "sample_graph.json").write_text(json.dumps(graph.to_dict(), default=str))
        report["latest_recorded_buffer_ul"] = {}
        for name, identity in specs.items():
            values = graph["contents"].sel(container=identity, location="A1",
                     reagent=str(buffer.identity)).sortby("tick", ascending=False).values.flatten()
            report["latest_recorded_buffer_ul"][name] = next(
                (float(x) for x in values if math.isfinite(float(x))), None)
    except Exception as exc:
        report["observation_error" if "completed_normally" in report else "execution_error"] = {
            "type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
        doc.write(str(out / "partial-execution.ttl"), sbol3.TURTLE)
        report["partial_call_parameters"] = [{
            "behavior": str(record.get_behavior().identity),
            "parameters": [{"name": pv.get_name(), "value": str(pv.value.get_value())}
                           for pv in record.get_call().parameter_values]}
            for record in engine.ex.executions if isinstance(record, labop.CallBehaviorExecution)]
    report["issues"] = {str(k): list(map(str, v)) for k, v in engine.issues.items()}
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    report = {"labop_commit": PIN, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "expected_buffer_ul": {"prepared": 90, "target": 10},
              "results": {mode: run(mode) for mode in
                          ("direct", "composition", "composition_explicit_final")}}
    (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
