"""Join observations to material lineage in both raw execution records."""

import argparse
import json
from collections import defaultdict
from pathlib import Path



def read(directory, name):
    return json.loads((directory / name).read_text())


def only(items):
    item, = items
    return item


def culsma_result(directory):
    run = read(directory, "run.json")
    output = read(directory, "output.json")
    assert run["ok"] and output["ok"] and not run["diagnostics"]
    artifacts = run["state"]["artifacts"]
    material = artifacts["material_state"]
    stocks = material["bindings"]
    containers = material["containers"]
    observations = output["returns"]["entry"]["value"]["observation_ids"]
    completions = [e for e in run["events"] if e["kind"] == "STEP_COMPLETED"]
    separation = only(e for e in completions
                      if e["payload"].get("material_delta", {}).get("op") == "sep")
    partition = separation["payload"]["material_delta"]
    roles = partition["partition"]["slot_contract"]
    assert partition["source"] == stocks["lysate"]
    assert partition["partition"]["ratios_by_component"] == {
        "GFP_CELL_DEBRIS": {"0": 0.0, "1": 1.0},
        "LYSATE_LIQUID": {"0": 1.0, "1": 0.0},
    }

    transfers = defaultdict(list)
    for event in completions:
        mutation = event["payload"].get("material_delta", {})
        for transfer in mutation.get("sources", []):
            if transfer["source"] != mutation["target"]:
                transfers[mutation["target"]].append((event, transfer))

    def trace(container):
        if container == stocks["buffer"]:
            return [("buffer", "assay buffer", container, [])]
        paths = []
        for event, move in transfers[container]:
            source = move["source"]
            if "selected_slot" in move:
                assert source == partition["source"] and event["seq"] > separation["seq"]
                paths.append((roles[move["selected_slot"]], "GFP lysate",
                              source, [event["seq"], separation["seq"]]))
            else:
                for role, label, root, events in trace(source):
                    paths.append((role, label, root, [event["seq"], *events]))
        return paths

    wells = {}
    for identity in observations:
        data = artifacts["data_objects"][identity]
        assert data["contract_kind"] == "fluorescence"
        container = data["resolved_sample"]
        state = containers[container]
        well = state["metadata"]["label"].removeprefix("Assay plate_")
        assert well not in wells
        wells[well] = {
            "observation": identity, "container": container,
            "fluorescence": data["result"]["signal"], "volume_uL": state["volume_uL"],
            "lineage": [
                {"fraction": role, "input": label, "input_id": root, "event_sequence": events}
                for role, label, root, events in trace(container)
            ],
        }
    remaining = {label: containers[stocks[key]]["volume_uL"]
                 for label, key in (("supernatant", "lysate"), ("resuspended pellet", "resuspended"),
                                    ("assay buffer", "buffer"))}
    return {"wells": wells, "remaining_uL": remaining}


def labop_result(directory):
    import xarray as xr
    status = read(directory, "run-status.json")
    assert status["completed_normally"] and not status["issues"]
    assert not status["validation_errors"] and not status["validation_warnings"]
    assert set(status["fraction_outputs"]) == {"supernatant", "pellet"}
    graph = xr.Dataset.from_dict(read(directory, "sample_graph.json"))
    readings = xr.Dataset.from_dict(read(directory, "readings.json"))[status["fluorescence_data"]]
    assert readings.sizes["container"] == 1

    parents = defaultdict(list)
    fraction_edges = {}
    input_nodes = {}
    for edge in graph.edges.to_numpy():
        source, target, label = edge.tolist()
        parents[target].append((source, label))
        if label.startswith("ClarifyLysate:"):
            fraction = label.split(":")[1].split("@")[0]
            fraction_edges[(source, target)] = fraction
        if label.startswith("Provision("):
            stock = "assay buffer" if ", Assay buffer)" in label else "GFP lysate"
            assert stock not in input_nodes.values()
            input_nodes[target] = stock

    assert set(input_nodes.values()) == {"GFP lysate", "assay buffer"}
    assert sorted(fraction_edges.values()) == ["pellet", "supernatant"]
    assert all(input_nodes[source] == "GFP lysate" for source, _ in fraction_edges)

    def trace(sample_id, fraction=None):
        if sample_id in input_nodes:
            stock = input_nodes[sample_id]
            return [{
                "fraction": fraction or "buffer", "input": stock, "input_id": sample_id,
                "sample_path": [sample_id], "edge_labels": [],
            }]
        paths = []
        for source, label in parents[sample_id]:
            role = fraction_edges.get((source, sample_id), fraction)
            for path in trace(source, role):
                path["sample_path"].insert(0, sample_id)
                path["edge_labels"].insert(0, label)
                paths.append(path)
        return paths

    def latest(container, well):
        states = graph.sel(container=container, location=well).sortby("tick")
        tick = states.sample_location.dropna("tick").tick[-1].item()
        return states.sel(tick=tick)

    wells = {}
    container = readings.container.item()
    for well in readings.location.to_numpy().tolist():
        state = latest(container, well)
        sample_id = state.sample_location.item()
        wells[well] = {
            "observation": readings.name, "container": container, "sample_id": sample_id,
            "fluorescence": readings.sel(container=container, location=well).item(),
            "volume_uL": state.contents.astype(float).sum().item(),
            "lineage": trace(sample_id),
        }
    spec_uri = container.rsplit("/", 1)[0]
    remaining = {
        label: latest(f"{spec_uri}/{tube}", "A1").contents.astype(float).sum().item()
        for label, tube in (("supernatant", "lysate_tube"), ("resuspended pellet", "pellet_tube"),
                            ("assay buffer", "buffer_tube"))
    }
    return {"wells": wells, "remaining_uL": remaining}


def check(result, expected):
    wells = result["wells"]
    assert wells.keys() == expected["wells"].keys(), wells.keys()
    assert result["remaining_uL"] == expected["remaining_uL"], result["remaining_uL"]
    for well, target in expected["wells"].items():
        observed = wells[well]
        assert observed["fluorescence"] is None, observed
        assert observed["volume_uL"] == target["volume_uL"], observed
        lineage = {(path["fraction"], path["input"]) for path in observed["lineage"]}
        assert lineage == {tuple(pair) for pair in target["lineage"]}, observed
    source_ids = {path["input_id"] for well in wells.values() for path in well["lineage"]
                  if path["input"] == "GFP lysate"}
    assert len(source_ids) == 1, source_ids


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("culsma", type=Path)
    parser.add_argument("labop", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    expected = read(Path(__file__).parent, "expected.json")
    results = {"Culsma": culsma_result(args.culsma), "LabOP": labop_result(args.labop)}
    for result in results.values():
        check(result, expected)
    args.output.write_text(json.dumps({"pass": True, **results}, indent=2) + "\n")
    print("Both runs match all common well, lineage, volume and missing-signal checks.")
