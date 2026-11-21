"""Run the GFP fractionation task with the LabOP reference execution engine."""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

import labop
import sbol3
from labop.execution.execution_engine import ExecutionEngine

from fractionation import FractionationUpdater, define_fractionation

OM = "http://www.ontology-of-units-of-measure.org/resource/om-2/"
NAMESPACE = "https://example.org/gfp-comparison/"
DATASET = "http://bioprotocols.org/labop#Dataset"


def measure(amount, unit):
    return sbol3.Measure(amount, OM + unit)


def build_protocol():
    protocol, document = labop.Protocol.initialize_protocol(
        "gfp_comparison", "GFP clarification and fluorescence", NAMESPACE
    )

    def container(identifier, name, kind, geometry):
        spec = labop.ContainerSpec(identifier, name=name, queryString=kind)
        samples = labop.SampleArray(name=name, container_type=spec)
        samples.empty(geometry=geometry)
        document.add(spec)
        return protocol.primitive_step(
            "EmptyContainer", specification=spec, sample_array=samples
        ).output_pin("samples")

    def supply(identifier, description, destination, amount):
        resource = sbol3.Component(identifier, [sbol3.SBO_FUNCTIONAL_ENTITY], name=description)
        document.add(resource)
        protocol.primitive_step(
            "Provision", resource=resource, destination=destination,
            amount=measure(amount, "microlitre"),
        )

    def select(plate, coordinates):
        return protocol.primitive_step(
            "PlateCoordinates", source=plate, coordinates=coordinates
        ).output_pin("samples")

    def transfer(source, destination, amount):
        protocol.primitive_step(
            "Transfer", source=source, destination=destination,
            amount=measure(amount, "microlitre"),
        )

    tube = "cont:MicrofugeTube1.5mL"
    lysate = container("lysate_tube", "GFP lysate", tube, "A1")
    pellet_tube = container("pellet_tube", "Pellet collection tube", tube, "A1")
    buffer = container("buffer_tube", "Assay buffer", tube, "A1")
    assay = container("assay_plate", "Assay plate", "cont:Plate96Well", "A1:H12")
    supply("lysate_liquid", "GFP lysate with 100000 suspended cellular units", lysate, 160)
    supply("assay_buffer", "Assay buffer", buffer, 100)

    fractionation = define_fractionation(document)
    spin = protocol.primitive_step(
        fractionation, lysate=lysate, pellet_tube=pellet_tube,
        duration=measure(10, "minute-Time"),
        acceleration=measure(12000 * 9.80665, "metrePerSecond-TimeSquared"),
        temperature=measure(22, "degreeCelsius"),
    )
    supernatant = spin.output_pin("supernatant")
    pellet = spin.output_pin("pellet")
    transfer(supernatant, select(assay, "A1"), 20)
    transfer(buffer, pellet, 40)
    protocol.primitive_step(
        "PipetteMix", samples=pellet, amount=measure(32, "microlitre"),
        cycleCount=measure(1, "one"),
    )
    transfer(pellet, select(assay, "A2"), 20)
    transfer(buffer, select(assay, "A3"), 20)
    reading = protocol.primitive_step(
        "MeasureFluorescence", samples=select(assay, "A1:A3"),
        excitationWavelength=measure(488, "nanometre"),
        emissionWavelength=measure(510, "nanometre"),
        emissionBandpassWidth=measure(20, "nanometre"),
    )
    output = protocol.designate_output("fluorescence", DATASET, reading.output_pin("measurements"))
    protocol.order(output, protocol.final())
    return protocol, document, fractionation, spin


def save_dot(graph, filename, **kwargs):
    """Keep the upstream DOT source without requiring a Graphviz executable."""
    path = Path(filename).with_suffix(".dot")
    path.write_text(graph.source, encoding="utf-8")
    return str(path)


def write_dataset(path, dataset):
    # Convert xarray's NaN markers to JSON nulls while preserving dimensions.
    data = json.loads(json.dumps(dataset.to_dict()), parse_constant=lambda token: None)
    path.write_text(json.dumps(data, separators=(",", ":")) + "\n")


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    protocol, document, fractionation, spin = build_protocol()
    document.write(str(output / "protocol.ttl"), sbol3.TURTLE)
    validation = document.validate()
    print("Document validation errors:", list(map(str, validation.errors)))
    print("Document validation warnings:", list(map(str, validation.warnings)))
    if validation.errors:
        raise ValueError("LabOP protocol document failed validation")

    engine = ExecutionEngine(out_dir=str(output), use_ordinal_time=True, failsafe=False)
    engine.prov_observer.handlers[fractionation.identity] = FractionationUpdater
    with patch("graphviz.Digraph.render", save_dot):
        execution = engine.execute(
            protocol, sbol3.Agent("software_runner"), id="gfp_execution", parameter_values=[]
        )
    document.write(str(output / "execution.ttl"), sbol3.TURTLE)
    reading = labop.ParameterValue.parameter_value_map(execution.parameter_values)["fluorescence"]
    write_dataset(output / "readings.json", reading.to_dataset())
    write_dataset(output / "sample_graph.json", engine.prov_observer.graph)
    (output / "run-status.json").write_text(json.dumps({
        "validation_errors": list(map(str, validation.errors)),
        "validation_warnings": list(map(str, validation.warnings)),
        "completed_normally": execution.completed_normally,
        "issues": list(map(str, engine.issues["gfp_execution"])),
        "fraction_outputs": [pin.name for pin in spin.outputs],
        "fluorescence_data": reading.data.identity,
    }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
