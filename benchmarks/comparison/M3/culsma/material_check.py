import json
from pathlib import Path
def check_execution(directory):
    run = json.loads((directory / "magnetic_run.json").read_text())
    output = json.loads((directory / "magnetic_output.json").read_text())
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
    Path("material-audit.json").write_text(json.dumps(check_execution(Path.cwd()),indent=2)+"\n")
