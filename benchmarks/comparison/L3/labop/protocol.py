"""Exercise released LabOP decision/cyclic control flow with test input values.

The predicate callback supplies runtime Boolean inputs, following the upstream
test_decision_nodes.py mechanism. It is a fixture, not a real measurement or
a released bounded-loop counter. No routing/engine code is modified.
"""
import hashlib
import json
import math
from pathlib import Path
import traceback
from unittest.mock import patch

import labop
import sbol3
import uml
from labop.execution.execution_engine import ExecutionEngine
from evaluate import save_dot

OUT = Path(__file__).resolve().parent


def run_case(kind, values):
    name = kind + "_" + (str(values[0]).lower() if "branch" in kind else str(len(values)-1))
    out = OUT / name
    out.mkdir(parents=True, exist_ok=True)
    protocol, doc = labop.Protocol.initialize_protocol("main", "L3 control",
                                                       "https://example.org/l3/"+kind+"/")
    fixture = {"values": None, "consumed": []}
    predicate = labop.Primitive("TestPredicate")
    predicate.add_output("return", "http://www.w3.org/2001/XMLSchema#boolean")
    doc.add(predicate)

    def output(inputs, parameter, sample_format, record_hash, engine=None):
        index = len(fixture["consumed"])
        if index >= len(fixture["values"]):
            raise RuntimeError("Predicate consumed more values than supplied")
        value = fixture["values"][index]
        fixture["consumed"].append(value)
        return value
    predicate.compute_output = output

    def marker(name):
        primitive = labop.Primitive(name)
        doc.add(primitive)
        return protocol.execute_primitive(primitive)

    specs = {}
    if "branch" in kind:
        if kind == "material_branch":
            microlitre = "http://www.ontology-of-units-of-measure.org/resource/om-2/microlitre"
            def tube(name):
                spec = labop.ContainerSpec(name+"_spec",queryString="cont:MicrofugeTube1.5mL")
                specs[name] = str(spec.identity)
                array = labop.SampleArray(name=name,container_type=spec)
                array.empty(geometry="A1")
                doc.add(spec)
                return protocol.primitive_step("EmptyContainer",specification=spec,sample_array=array).output_pin("samples")
            stock, target, alternative = tube("stock"), tube("target"), tube("alternative")
            buffer = sbol3.Component("buffer",[sbol3.SBO_FUNCTIONAL_ENTITY]); doc.add(buffer)
            incoming = protocol.primitive_step("Provision",resource=buffer,destination=stock,
                                               amount=sbol3.Measure(100,microlitre))
            true_step = protocol.execute_primitive("Transfer",source=stock,destination=target,amount=sbol3.Measure(10,microlitre))
            false_step = protocol.execute_primitive("Transfer",source=stock,destination=alternative,amount=sbol3.Measure(20,microlitre))
        else:
            true_step, false_step = marker("TrueBranch"), marker("FalseBranch")
            incoming = protocol.initial()
        protocol.make_decision_node(incoming, decision_input_behavior=predicate,
                                    outgoing_targets=[(True,true_step),(False,false_step)])
        protocol.order(true_step, protocol.final())
        protocol.order(false_step, protocol.final())
    else:
        merge = uml.MergeNode()
        protocol.nodes.append(merge)
        body = marker("LoopBody")
        protocol.order(protocol.initial(), merge)
        protocol.make_decision_node(merge, decision_input_behavior=predicate,
                                    outgoing_targets=[(True,body),(False,protocol.final())])
        protocol.order(body, merge)

    # Set the fixture only after constructing and serializing the model.
    validation = doc.validate()
    doc.write(str(out/"protocol.ttl"),sbol3.TURTLE)
    model_hash = hashlib.sha256((out/"protocol.ttl").read_bytes()).hexdigest()
    fixture["values"] = values
    report = {"kind":kind,"runtime_values":values,"model_sha256":model_hash,
              "validation_errors":list(map(str,validation.errors)),
              "validation_warnings":list(map(str,validation.warnings))}
    # The upstream marker test disables standard primitive output handlers.
    # Material checks require those handlers for EmptyContainer and sample data.
    report["use_defined_primitives"] = kind == "material_branch"
    engine = ExecutionEngine(out_dir=str(out), use_ordinal_time=True,
                             use_defined_primitives=report["use_defined_primitives"], failsafe=False)
    try:
        with patch("graphviz.Digraph.render",save_dot):
            ex = engine.execute(protocol,sbol3.Agent("software_runner"),id="execution",parameter_values=[])
        report["completed_normally"] = ex.completed_normally
    except Exception as exc:
        report["execution_error"] = {"type":type(exc).__name__,"message":str(exc),
                                     "traceback":traceback.format_exc()}
    report["consumed_values"] = fixture["consumed"]
    report["calls"] = [str(r.get_behavior().identity).rsplit("/",1)[-1]
                       for r in engine.ex.executions if isinstance(r,labop.CallBehaviorExecution)]
    report["issues"] = {str(k):list(map(str,v)) for k,v in engine.issues.items()}
    if specs and "execution_error" not in report:
        graph = engine.prov_observer.graph
        (out/"sample_graph.json").write_text(json.dumps(graph.to_dict(),default=str))
        report["volumes_ul"] = {}
        for name,identity in specs.items():
            amounts = graph['contents'].sel(container=identity,location='A1',reagent=str(buffer.identity)).sortby('tick',ascending=False).values.flatten()
            report["volumes_ul"][name] = next((float(x) for x in amounts if math.isfinite(float(x))),None)
    doc.write(str(out/"execution.ttl"),sbol3.TURTLE)
    (out/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    return report


if __name__ == "__main__":
    report = {"labop_commit":"2e2bd88150c71a440771fd369f40295dfd622324","cases":[]}
    for kind, values in [("branch",[True]),("branch",[False]),
                         ("cycle",[True,True,False]),("cycle",[True,True,True,False]),
                         ("material_branch",[True]),("material_branch",[False])]:
        result = run_case(kind,values)
        report["cases"].append(result)
        (OUT/"results.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(result),flush=True)
