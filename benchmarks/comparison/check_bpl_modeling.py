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

ROOT = Path(__file__).resolve().parent
from replay_paths import result_path
OUT = result_path("bpl-modeling")
OUT.mkdir(parents=True, exist_ok=True)
parser = BPLParser()
cases = {
    "duration_valid": "protocol Test {\n wait(duration: 10 min)\n}\n",
    "duration_wrong_dimension": "protocol Test {\n wait(duration: 10 uL)\n}\n",
    "volume_wrong_dimension": 'protocol Test {\n transfer(from: "plate_1:A1", to: "plate_1:A2", volume: 10 min)\n}\n',
    "local_binding": "protocol Test {\n let delay = 10 min\n wait(duration: delay)\n}\n",
    "unbound_name": "protocol Test {\n wait(duration: missing)\n}\n",
    "nested_local": "protocol Test {\n sequence {\n let delay = 10 min\n wait(duration: delay)\n }\n wait(duration: delay)\n}\n",
    "transfer": 'protocol Test {\n transfer(from: "plate_1:A1", to: "plate_1:A2", volume: 20 uL)\n}\n',
    "named_entities": "labware TubeA {\n footprint: Custom\n well_volume: 1500 uL\n}\nlabware TubeB {\n footprint: Custom\n well_volume: 1500 uL\n}\nprotocol Test {\n transfer(from: TubeA, to: TubeB, volume: 20 uL)\n}\n",
    "centrifuge": 'protocol Test {\n centrifuge(target: "plate_1:A1", speed: 12000, duration: 10 min)\n}\n',
}
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
    path = OUT / f"{name}.bpl"
    path.write_text(source)
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

# Seed the simulator through its public state API: this is a runtime-component
# witness, not a claim that reagent declarations initialize this state in the CLI.
deck = create_deck_with_labware([("plate_1", LabwareType.PLATE_96, "1")])
src = deck.get_well_contents("plate_1", "A1")
dst = deck.get_well_contents("plate_1", "A2")
src.add_volume(100, Component(name="buffer", volume_ul=100))
result = Simulator(deck_state=deck).simulate(plans["transfer"])
report["transfer_simulation"] = {
    "success": result.success, "errors": result.validation_errors,
    "source_volume_ul": src.volume_ul, "destination_volume_ul": dst.volume_ul,
    "source_components": [asdict(c) for c in src.components],
    "destination_components": [asdict(c) for c in dst.components],
}

assert not report["cases"]["duration_valid"]["diagnostics"]
assert report["cases"]["duration_valid"]["primitives"][0]["fields"]["duration_s"] == 600
assert result.success and src.volume_ul == 80 and dst.volume_ul == 20
destination = OUT / "results.json"
destination.write_text(json.dumps(report, indent=2, default=str) + "\n")
print(destination)
for name, item in report["cases"].items():
    print(name, "diagnostics=", len(item["diagnostics"]), "primitives=", item["primitives"])
print("transfer_simulation", report["transfer_simulation"])
