"""Check the unchanged magnetic example and inventory the pinned LabOP library.

This is a Culsma execution check plus a LabOP source audit, not a matched
magnetic execution or a proof that LabOP extensions cannot represent the task.
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path



def audit_library(source):
    from rdflib import Graph, Namespace, RDF
    uml = Namespace("http://bioprotocols.org/uml#")
    sbol = Namespace("http://sbols.org/v3#")
    labop = Namespace("http://bioprotocols.org/labop#")
    primitives, hashes = [], {}
    for path in sorted((source / "labop/lib").glob("*.ttl")):
        hashes[str(path.relative_to(source))] = hashlib.sha256(path.read_bytes()).hexdigest()
        graph = Graph().parse(path, format="turtle")
        for primitive in sorted(graph.subjects(RDF.type, labop.Primitive)):
            parameters = []
            for ordered in graph.objects(primitive, uml.ownedParameter):
                parameter = graph.value(ordered, uml.propertyValue)
                parameters.append({
                    "index": int(graph.value(ordered, uml.indexValue)),
                    "name": str(graph.value(parameter, sbol.name)),
                    "direction": str(graph.value(parameter, uml.direction)).split("#")[-1],
                    "type": str(graph.value(parameter, uml.type)),
                })
            primitives.append({
                "identity": str(primitive),
                "library": path.stem,
                "name": str(graph.value(primitive, sbol.displayId)),
                "description": str(graph.value(primitive, sbol.description)),
                "parameters": sorted(parameters, key=lambda item: item["index"]),
            })
    handlers = {}
    for filename, target in (("behavior_dynamics.py", "handlers"),
                             ("primitive_execution.py", "primitive_to_output_function")):
        path = source / "labop/execution" / filename
        hashes[str(path.relative_to(source))] = hashlib.sha256(path.read_bytes()).hexdigest()
        matches = []
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
                continue
            if any((isinstance(t, ast.Name) and t.id == target) or
                   (isinstance(t, ast.Attribute) and t.attr == target) for t in node.targets):
                matches.append({ast.literal_eval(k): ast.unparse(v)
                                for k, v in zip(node.value.keys, node.value.values)})
        assert len(matches) == 1, (filename, matches)
        handlers[target] = matches[0]
    return {"primitive_count": len(primitives), "primitives": primitives,
            "default_handlers": handlers, "source_sha256": hashes}


def check_execution(directory):
    run = json.loads((directory / "run.json").read_text())
    output = json.loads((directory / "output.json").read_text())
    assert run["ok"] and output["ok"] and not run["diagnostics"]
    events = [e for e in run["events"] if e["kind"] == "STEP_COMPLETED"
              and e["payload"].get("material_delta", {}).get("op") == "sep"]
    assert len(events) == 1
    event = events[0]
    delta = event["payload"]["material_delta"]
    assert delta["program_kind"] == "magnetic_program"
    assert delta["partition"]["slot_contract"] == {"0": "bound", "1": "flowthrough"}
    expected = {
        "bound": {"MAGNETIC_BEADS": (10, "mg", "mass"),
                  "TARGET_PROTEIN": (0.001, "mg", "mass"), "BUFFER": (0, "uL", "volume")},
        "flowthrough": {"MAGNETIC_BEADS": (0, "mg", "mass"),
                        "TARGET_PROTEIN": (0, "mg", "mass"), "BUFFER": (100, "uL", "volume")},
    }
    fractions = {}
    for slot, role in delta["partition"]["slot_contract"].items():
        identifier = delta["slots"][slot]
        state = event["payload"]["material_state_snapshot"]["containers"][identifier]
        entries = {e["entry_id"]: e for e in state["component_entries"]}
        for component, (value, unit, dimension) in expected[role].items():
            assert entries[component]["quantity"] == {
                "value": value, "unit": unit, "dimension": dimension}
        fractions[role] = {"container_id": identifier, "component_entries": entries,
                           "aggregate_volume_uL": state["volume_uL"],
                           "aggregate_mass_mg": state["mass_mg"]}
    target = fractions["bound"]["component_entries"]["TARGET_PROTEIN"]
    beads = fractions["bound"]["component_entries"]["MAGNETIC_BEADS"]
    assert target["relation"] == "bead_bound"
    assert target["association_target_kind"] == "component_entry"
    assert target["associated_with"] == beads["entry_id"]
    assert target["material_state_source"] == "author_transition"
    returned = output["returns"]["entry"]["value"]
    assert returned["member_count"] == 2
    assert [m["id"] for m in returned["members"]] == [delta["slots"]["0"], delta["slots"]["1"]]
    return {"typed_quantities_and_association_passed": True, "separation_event": event["seq"],
            "source": delta["source"], "fractions": fractions,
            "scope": "Declared allocation and association, without downstream operations or hardware.",
            "aggregate_limitation": "The pinned runtime also reports 10.001 uL for the bound "
                "fraction and 100 mg for flowthrough via cross-dimension aggregate projections. "
                "These are not physical volume/density predictions and are excluded from the "
                "verified outcomes; this check uses dimensioned component quantities."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("culsma_output", type=Path)
    parser.add_argument("labop_source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = {"comparison_kind": "Culsma execution and LabOP library/source audit",
              "culsma": check_execution(args.culsma_output),
              "labop": audit_library(args.labop_source),
              "limitation": "No extended LabOP magnetic implementation was executed. "
                  "Library inventory does not establish a limit on LabOP expressiveness."}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("Magnetic typed quantities, component association and returned identities verified.")
    print(f"Inventoried {result['labop']['primitive_count']} LabOP primitive declarations.")
