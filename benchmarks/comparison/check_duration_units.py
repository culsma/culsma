"""Reproduce a pre-run duration-dimension check in the existing pinned environments.

Run from any directory with Python 3. Writes only the specified JSON report;
does not execute protocols or control instruments. Environments are prepared
by reproduce.sh. This is an evaluation observer, not a system extension.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


from replay_paths import PACKAGE, REPOSITORY as ROOT, RUNTIME as ENV

CULSMA_CHECK = r'''
import json, sys
from pathlib import Path
from culsma.parser.parser import parse
from culsma.frontend.resolver import resolve_program
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.typecheck import typecheck
src = Path(sys.argv[1]).read_text()
assert src.count("duration = 10min") == 1
rows = []
for name, source in [("valid", src), ("wrong_duration_unit", src.replace("duration = 10min", "duration = 10uL"))]:
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    result = typecheck(compiled.ir, analysis=compiled.analysis)
    rows.append({"case": name, "accepted": result.ok,
                 "diagnostics": [{"code": d.code, "span": str(d.span)} for d in result.diagnostics]})
print("RESULT_JSON=" + json.dumps({"python": sys.version, "cases": rows}))
'''

LABOP_CHECK = r'''
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
'''


def probe(python, code, *args, extra_env=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    completed = subprocess.run([str(python), "-u", "-c", code, *map(str, args)],
                               env=env, text=True, capture_output=True, timeout=180, check=True)
    lines = completed.stdout.splitlines()
    result = json.loads(next(line.removeprefix("RESULT_JSON=") for line in lines
                             if line.startswith("RESULT_JSON=")))
    result["stdout"] = [line for line in lines if not line.startswith("RESULT_JSON=")]
    result["stderr"] = completed.stderr
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    culsma = probe(ENV / "culsma-env/bin/python", CULSMA_CHECK, PACKAGE / "gfp.culs",
                   extra_env={"PYTHONPATH": str(ENV / "culsma-source/src")})
    labop = probe(ENV / "labop-env/bin/python", LABOP_CHECK)
    paths = [Path(__file__).resolve(), PACKAGE / "gfp.culs", PACKAGE / "labop-requirements.txt",
             ENV / "culsma-source/src/culsma/pipeline/typecheck/expressions.py",
             ENV / "labop-env/lib/python3.11/site-packages/labop/lib/plate_handling.ttl"]
    report = {
        "scope": "Pre-run checks only; Culsma GFP typecheck versus standard LabOP Spin document.validate; no protocol execution.",
        "expected_rule": "Duration must have a time dimension; 10 min is valid and 10 microlitres is invalid.",
        "version_pins": {"culsma": "5364676bc2437b4981a00ce0133c730af243e469",
                         "labop": "2e2bd88150c71a440771fd369f40295dfd622324"},
        "sha256": {os.path.relpath(path, ROOT): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
        "culsma": culsma, "labop": labop,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    for system in ("culsma", "labop"):
        print(system, [(case["case"], case["accepted"]) for case in report[system]["cases"]])


if __name__ == "__main__":
    main()
