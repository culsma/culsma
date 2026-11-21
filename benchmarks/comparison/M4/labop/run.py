
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
