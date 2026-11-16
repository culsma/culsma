"""L1 parameterized procedure reuse on the pinned Culsma, LabOP and BPL routes.

Software only. Defines Aliquot once, calls it with 10 and 20 uL, and records
binding/lowering or execution evidence. Run using the Culsma environment.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from check_duration_units import ENV, PACKAGE, probe

OUT = PACKAGE / "results/l1"


def assess(report):
    """Judge the retained witness, not the existence of syntax or API methods."""
    output = OUT / "culsma/output.json"
    if output.exists():
        products = json.loads(output.read_text())["report"]["materials"]["final_products"]
        volumes = {p["name"]: p["volume_uL"] for p in products}
        report["culsma"]["destination_volumes_ul"] = volumes
        report["culsma"]["meets_reuse_witness"] = (
            report["culsma"]["returncode"] == 0 and volumes == {"first": 10, "second": 20}
        )
    primitives = report["bpl"]["primitives"]
    report["bpl"]["meets_reuse_witness"] = (
        [p["class"] for p in primitives] == ["Aspirate", "Dispense", "Aspirate", "Dispense"]
        and [p["fields"].get("volume_ul") for p in primitives] == [10, 10, 20, 20]
    )
    if all(p["class"] == "HumanStep" for p in primitives):
        report["bpl"]["reason"] = "Both user-procedure calls remain HumanStep text; the declared body is not instantiated."
    for mode in ["literal", "input_flow"]:
        row = report["labop_" + mode]
        transfers = row.get("executed_transfers", [])
        row["meets_reuse_witness"] = (
            row.get("completed_normally", False)
            and [t["amount"] for t in transfers] == [10, 20]
            and len({t["destination"] for t in transfers}) == 2
        )
    return report

CULSMA_SOURCE = '''protocol Aliquot(source, destination, amount) {
 destination << [source:amount];
}
let stock = tube(label = "stock", capacity = 1.5mL, load = [
 content(kind = ContentKind.FORMULATION, type = ContentType.BUFFER, code = "BUFFER"):100uL]);
let first = tube(label = "first", capacity = 1.5mL);
let second = tube(label = "second", capacity = 1.5mL);
Aliquot(source = stock, destination = first, amount = 10uL);
Aliquot(source = stock, destination = second, amount = 20uL);
return second;
'''

BPL_SOURCE = '''protocol Main {
 aliquot(source: "plate_1:A1", destination: "plate_1:A2", amount: 10 uL)
 aliquot(source: "plate_1:A1", destination: "plate_1:A3", amount: 20 uL)
}
protocol aliquot(source, destination, amount: Volume) {
 transfer(from: source, to: destination, volume: amount)
}
'''

BPL = r'''
import json, sys
from pathlib import Path
from dataclasses import asdict
from bpl.parser import BPLParser
from bpl.orchestrator import run_semantic_gate, lower_program_to_plan
path=Path(sys.argv[1])
program=BPLParser().parse(path.read_text(), filename=str(path))
diagnostics=run_semantic_gate(program,path)
plan=lower_program_to_plan(program,path,"simulation")
print("RESULT_JSON="+json.dumps({
 "protocols": [{"name": d.name, "parameters": [p.name for p in d.parameters]} for d in program.declarations],
 "diagnostics": [d.to_dict() for d in diagnostics],
 "primitives": [{"class":type(s.primitive).__name__,"fields":asdict(s.primitive)} for s in plan.steps.values()],
},default=str))
'''

LABOP = r'''
import json, sys
from pathlib import Path
from unittest.mock import patch
import labop, sbol3
from uml import LiteralIdentified
from labop.execution.execution_engine import ExecutionEngine
from gfp_labop import save_dot
out=Path(sys.argv[1]); out.mkdir(parents=True,exist_ok=True)
parent,doc=labop.Protocol.initialize_protocol("main","L1 reuse","https://example.org/l1/")
sub=labop.Protocol.create_protocol("Aliquot","Aliquot")
doc.add(sub)
sample="http://bioprotocols.org/labop#SampleArray"
src=sub.input_value("source",sample)
dst=sub.input_value("destination",sample)
amount=sub.input_value("amount",sbol3.OM_MEASURE)
sub.primitive_step("Transfer",source=src,destination=dst,amount=amount)
om="http://www.ontology-of-units-of-measure.org/resource/om-2/"
def container(name):
 spec=labop.ContainerSpec(name+"_spec",queryString="cont:MicrofugeTube1.5mL")
 array=labop.SampleArray(name=name,container_type=spec)
 array.empty(geometry="A1")
 doc.add(spec)
 return parent.primitive_step("EmptyContainer",specification=spec,sample_array=array).output_pin("samples")
stock=container("stock"); first=container("first"); second=container("second")
resource=sbol3.Component("buffer",[sbol3.SBO_FUNCTIONAL_ENTITY]);doc.add(resource)
parent.primitive_step("Provision",resource=resource,destination=stock,amount=sbol3.Measure(100,om+"microlitre"))
mode=sys.argv[2]
arguments=[sbol3.Measure(value,om+"microlitre") for value in [10,20]]
parameter_values=[]
if mode=="input_flow":
 nodes=[]
 for index,value in enumerate(arguments):
  name="amount_"+str(index)
  nodes.append(parent.input_value(name,sbol3.OM_MEASURE))
  parameter_values.append(labop.ParameterValue(parameter=parent.get_input(name),value=LiteralIdentified(value=value)))
 arguments=nodes
calls=[parent.primitive_step(sub,source=stock,destination=dest,amount=value) for dest,value in zip([first,second],arguments)]
validation=doc.validate()
engine=ExecutionEngine(out_dir=str(out),use_ordinal_time=True,failsafe=False)
report={"mode":mode,"validation_errors":list(map(str,validation.errors)),"calls":[{"id":str(c.identity),"behavior":str(c.behavior)} for c in calls]}
doc.write(str(out/"protocol.ttl"),sbol3.TURTLE)
try:
 with patch("graphviz.Digraph.render",save_dot):
  execution=engine.execute(parent,sbol3.Agent("software_runner"),id="l1_execution",parameter_values=parameter_values)
 report["completed_normally"]=execution.completed_normally
 report["executed_transfers"]=[]
 for record in execution.executions:
  if isinstance(record,labop.CallBehaviorExecution):
   call=record.call.lookup()
   if str(record.get_behavior().identity).endswith("/Transfer"):
    values=call.parameter_value_map()
    report["executed_transfers"].append({"amount":values["amount"].value,"unit":str(values["amount"].unit),"source":str(values["source"].identity),"destination":str(values["destination"].identity)})
 report["issues"]={str(k):list(map(str,v)) for k,v in engine.issues.items()}
 doc.write(str(out/"execution.ttl"),sbol3.TURTLE)
 (out/"sample_graph.json").write_text(json.dumps(engine.prov_observer.graph.to_dict(),default=str))
except Exception as exc:
 report["evidence_collection_error" if "completed_normally" in report else "execution_error"]={"type":type(exc).__name__,"message":str(exc)}
print("RESULT_JSON="+json.dumps(report,default=str))
'''

if __name__ == "__main__":
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"reuse.culs").write_text(CULSMA_SOURCE)
    (OUT/"reuse.bpl").write_text(BPL_SOURCE)
    env=dict(os.environ,PYTHONPATH=str(ENV/"culsma-source/src"))
    c=subprocess.run([str(ENV/"culsma-env/bin/python"),"-m","culsma.cli","run",str(OUT/"reuse.culs"),"--output",str(OUT/"culsma/output.json"),"--artifacts-dir",str(OUT/"culsma")],env=env,capture_output=True,text=True,timeout=90)
    (OUT/"culsma-log.txt").write_text(c.stdout+c.stderr)
    report={"culsma":{"returncode":c.returncode,"log":c.stdout+c.stderr}}
    summary=OUT/"culsma/summary.json"
    if summary.exists(): report["culsma"]["summary"]=json.loads(summary.read_text())
    (OUT/"results.json").write_text(json.dumps(report,indent=2)+"\n")
    report["bpl"]=probe(ENV/"bpl-env/bin/python",BPL,OUT/"reuse.bpl")
    (OUT/"results.json").write_text(json.dumps(report,indent=2)+"\n")
    for mode in ["literal","input_flow"]:
        report["labop_"+mode]=probe(ENV/"labop-env/bin/python",LABOP,OUT/("labop_"+mode),mode,extra_env={"PYTHONPATH":str(PACKAGE)})
        (OUT/"results.json").write_text(json.dumps(report,indent=2)+"\n")
    report=assess(report)
    (OUT/"results.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
