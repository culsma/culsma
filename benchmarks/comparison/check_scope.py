"""Record Culsma source binding and LabOP model-boundary witnesses.

Uses the existing pinned environments. No protocol or device is executed.
"""
import json
from check_duration_units import ENV, PACKAGE, probe

CULSMA = r'''
import json
from culsma.parser.parser import parse
from culsma.frontend.resolver import resolve_program
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.validate import validate
source = """protocol Prepare {
 let local = tube(label = "local", capacity = 1.5mL);
 return local;
}
let first = Prepare();
let second = Prepare();
"""
rows = []
for name, text in [("returned_local", source),
                   ("local_outside_protocol", source + "first << [local:20uL];\n")]:
    compiled = compile_ast(resolve_program(parse(text)).prepared_program)
    result = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    rows.append({"case": name, "source": text,
                 "diagnostics": [{"code": d.code, "span": str(d.span)} for d in result.diagnostics]})
print("RESULT_JSON=" + json.dumps({"cases": rows}))
'''

LABOP = r'''
import json
import labop, sbol3
sbol3.set_namespace("https://example.org/scope/")
document = sbol3.Document()
parent = labop.Protocol("parent")
other = labop.Protocol("other")
document.add([parent, other])
def builder_local_scope(protocol):
    local = protocol.input_value("sample", "http://bioprotocols.org/labop#SampleArray")
    return local
ref = builder_local_scope(parent)
target = other.input_value("target", "http://bioprotocols.org/labop#SampleArray")
try:
    other.use_value(ref, target)
    rejection = None
except ValueError as exc:
    rejection = str(exc)
print("RESULT_JSON=" + json.dumps({
    "owner": str(ref.get_toplevel().identity),
    "python_helper_name_in_rdf": "builder_local_scope" in document.write_string(sbol3.TURTLE),
    "cross_activity_rejection": rejection,
}))
'''

if __name__ == "__main__":
    result = {
        "culsma": probe(ENV / "culsma-env/bin/python", CULSMA,
                        extra_env={"PYTHONPATH": str(ENV / "culsma-source/src")}),
        "labop": probe(ENV / "labop-env/bin/python", LABOP),
    }
    output = PACKAGE / "results" / "scope-mechanisms.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(output)
