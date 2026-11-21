"""Small mechanism witnesses for the pinned BPL snapshot; no BPL code patches.

Requires Python >=3.13, lark==1.3.1, and the BPL source on PYTHONPATH.
Results describe the inspected source-to-plan and simulation routes only.
"""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform

import lark
import bpl
from bpl.parser import BPLParser
from bpl.orchestrator import run_semantic_gate, lower_program_to_plan
from bpl.simulation.simulator import Simulator
from bpl.simulation.virtual_deck import (
    Component, LabwareType, create_deck_with_labware,
)

OUT = Path(__file__).resolve().parent
OUT.mkdir(parents=True, exist_ok=True)
parser = BPLParser()
cases = {name: (OUT / filename).read_text() for name, filename in {'named_entities': 'protocol.bpl'}.items()}
report = {
    "source_commit": "4e505740f5025d59ba655c6c955f83876f753007",
    "python": platform.python_version(), "lark": lark.__version__, "cases": {},
}
source_root = Path(bpl.__file__).resolve().parent
report["source_sha256"] = {
    name: hashlib.sha256((source_root / name).read_bytes()).hexdigest()
    for name in ("orchestrator.py", "grammar/bpl.lark", "types/unit_engine.py",
                 "lowering/plan_ir.py", "simulation/simulator.py",
                 "simulation/virtual_deck.py")
}
plans = {}
for name, source in cases.items():
    path = OUT / {'named_entities': 'protocol.bpl'}[name]
    program = parser.parse(source, filename=str(path))
    diagnostics = run_semantic_gate(program, path)
    plan = lower_program_to_plan(program, path, "simulation")
    plans[name] = plan
    report["cases"][name] = {
        "source": source,
        "declaration_types": [type(d).__name__ for d in program.declarations],
        "diagnostics": [d.to_dict() for d in diagnostics],
        "primitives": [{"class": type(s.primitive).__name__,
                        "fields": asdict(s.primitive)} for s in plan.steps.values()],
    }

destination = OUT / "results.json"
destination.write_text(json.dumps(report, indent=2, default=str) + "\n")
print(destination)
for name, item in report["cases"].items():
    print(name, "diagnostics=", len(item["diagnostics"]), "primitives=", item["primitives"])

