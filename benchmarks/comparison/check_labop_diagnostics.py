"""Probe positive LabOP diagnostics, without executing a protocol or instrument.

Run with the existing labop environment. Preserve all cases, including any
construction exceptions or missing diagnostics; do not select only successes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import traceback

import labop
import sbol3


def issue_record(issue):
    return {"object_id": str(issue.object_id) if issue.object_id else None,
            "rule_id": str(issue.rule_id) if issue.rule_id else None,
            "message": str(issue.message), "rendered": str(issue)}


def check_case(name):
    om = "http://www.ontology-of-units-of-measure.org/resource/om-2/"
    stage = "model_construction"
    try:
        protocol, document = labop.Protocol.initialize_protocol(
            name, name, "https://example.org/diagnostic_check/")
        sample = protocol.input_value("sample", "http://bioprotocols.org/labop#SampleArray")
        duration = sbol3.Measure(10, None if name == "missing_measure_unit" else om + "minute-Time")
        spin = protocol.primitive_step("Spin", location=sample, duration=duration,
            acceleration=sbol3.Measure(12000 * 9.80665, om + "metrePerSecond-TimeSquared"))
        if name == "incoming_edge_to_initial":
            protocol.order(spin, protocol.initial())
        stage = "document_validation"
        report = document.validate()
        return {"case": name, "entry_point": "document.validate()", "stage": stage,
                "protocol_execution_stage": "before_execution",
                "host_script_stage": "during_execution",
                "errors": [issue_record(e) for e in report.errors],
                "warnings": [issue_record(w) for w in report.warnings]}
    except Exception as error:
        return {"case": name, "stage": stage, "exception_type": type(error).__name__,
                "message": str(error), "traceback": traceback.format_exc()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    labop.import_library("plate_handling")
    cases = [check_case(name) for name in
             ("valid", "missing_measure_unit", "incoming_edge_to_initial")]
    paths = [Path(__file__).resolve(), Path(labop.__file__).parent / "lib/plate_handling.ttl",
             Path(sbol3.__file__).parent / "om_unit.py",
             Path(sbol3.__file__).parent / "validation.py"]
    result = {
        "python": sys.version,
        "labop_commit": "2e2bd88150c71a440771fd369f40295dfd622324",
        "pin_source": "Existing environment prepared for the retained comparison; not a fresh complete installation audit.",
        "scope": "Standard Spin model; no extension, protocol execution, or hardware.",
        "expectations": {"valid": "No errors or warnings",
                         "missing_measure_unit": "Reject a Measure with no required unit",
                         "incoming_edge_to_initial": "Reject an incoming control edge to InitialNode"},
        "sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    for case in cases:
        print(case["case"], json.dumps(case.get("errors", case), ensure_ascii=False))


if __name__ == "__main__":
    main()
