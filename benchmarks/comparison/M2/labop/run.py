
import json, sys
import labop, sbol3
labop.import_library("plate_handling")
om = "http://www.ontology-of-units-of-measure.org/resource/om-2/"
rows = []
for name, unit in [("valid", "minute-Time"), ("wrong_duration_unit", "microlitre")]:
    protocol, document = labop.Protocol.initialize_protocol(name, name, "https://example.org/unit_check/")
    sample = protocol.input_value("sample", "http://bioprotocols.org/labop#SampleArray")
    protocol.primitive_step("Spin", location=sample,
        duration=sbol3.Measure(10, om + unit),
        acceleration=sbol3.Measure(12000 * 9.80665, om + "metrePerSecond-TimeSquared"))
    result = document.validate()
    rows.append({"case": name, "accepted": not bool(result.errors),
                 "errors": [str(e) for e in result.errors],
                 "warnings": [str(w) for w in result.warnings]})
print("RESULT_JSON=" + json.dumps({"python": sys.version, "cases": rows}))
