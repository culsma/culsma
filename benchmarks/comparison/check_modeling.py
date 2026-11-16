"""Construct, validate, serialize and reread scoped LabOP M witnesses.

Uses the retained LabOP environment. No protocol execution or device access.
Run: benchmarks/local-results/comparison-runtime/labop-env/bin/python \
  benchmarks/comparison/check_modeling.py \
  --output benchmarks/comparison/results/modeling
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import traceback

import labop
import labop_time as labopt
import sbol3
import uml
from rdflib import Graph, URIRef
from rdflib.compare import isomorphic

OM = "http://www.ontology-of-units-of-measure.org/resource/om-2/"
NS = "https://example.org/modeling-check/"
SAMPLE = "http://bioprotocols.org/labop#SampleArray"


def measure(value, unit="microlitre"):
    return sbol3.Measure(value, OM + unit)


def container(protocol, document, identifier):
    spec = labop.ContainerSpec(identifier, queryString="cont:MicrofugeTube1.5mL")
    document.add(spec)
    samples = labop.SampleArray(name="same description", container_type=spec)
    samples.empty(geometry="A1")
    return protocol.primitive_step(
        "EmptyContainer", specification=spec, sample_array=samples
    ).output_pin("samples")


def base():
    protocol, document = labop.Protocol.initialize_protocol("protocol", "M witness", NS)
    a = container(protocol, document, "tube_a")
    b = container(protocol, document, "tube_b")
    return protocol, document, a, b


def build(name):
    protocol, document, a, b = base()
    ids = {"a": a.identity, "b": b.identity, "protocol": protocol.identity}
    if name in ("entities", "quantity", "timing"):
        first = protocol.primitive_step("Transfer", source=a, destination=b, amount=measure(20))
        second = protocol.primitive_step("Transfer", source=b, destination=a, amount=measure(20))
        ids.update(first=first.identity, second=second.identity)
        if name == "timing":
            requirement = labopt.duration(first, [10, 20], units=OM + "second-Time")
            bundle = labopt.TimeConstraints("constraints", constraints=[labopt.And([requirement])],
                                          protocols=[protocol])
            document.add(bundle)
            ids["requirement"] = requirement.identity
    elif name == "products":
        operation = labop.Primitive("TwoProducts")
        operation.description = "Two separately referenceable material-product outputs; no execution handler."
        operation.add_output("supernatant", SAMPLE)
        operation.add_output("pellet", SAMPLE)
        document.add(operation)
        split = protocol.primitive_step(operation)
        first = protocol.primitive_step("Transfer", source=split.output_pin("supernatant"),
                                        destination=a, amount=measure(20))
        second = protocol.primitive_step("Transfer", source=split.output_pin("pellet"),
                                         destination=b, amount=measure(20))
        ids.update(first=first.identity, second=second.identity,
                   supernatant=split.output_pin("supernatant").identity,
                   pellet=split.output_pin("pellet").identity)
    elif name in ("complex", "unspecified_association"):
        # The control does not assert dissociation: SBOL uses open-world semantics.
        # Both documents contain the same components and the same 20 uL input.
        protein = sbol3.Component("protein", sbol3.SBO_PROTEIN)
        ligand = sbol3.Component("ligand", sbol3.SBO_SIMPLE_CHEMICAL)
        kind = (sbol3.SBO_NON_COVALENT_COMPLEX if name == "complex"
                else sbol3.SBO_FUNCTIONAL_ENTITY)
        material = sbol3.Component("material", kind,
                                  features=[sbol3.SubComponent(protein), sbol3.SubComponent(ligand)])
        document.add([protein, ligand, material])
        provision = protocol.primitive_step("Provision", resource=material,
                                             destination=a, amount=measure(20))
        ids.update(material=material.identity, provision=provision.identity)
    else:
        raise ValueError(name)
    protocol.order(protocol.get_last_step(), protocol.final())
    return document, ids


def edges(document, target):
    protocol = document.find(NS + "protocol")
    def origins(node_id, visited):
        if node_id in visited:
            raise ValueError("Cycle in reference path")
        values = []
        for edge in protocol.edges:
            if isinstance(edge, uml.ObjectFlow) and str(edge.target) == node_id:
                source = edge.source.lookup()
                if isinstance(source, uml.ForkNode):
                    values.extend(origins(source.identity, visited | {node_id}))
                else:
                    values.append(str(edge.source))
        return values
    return sorted(origins(target, set()))


def inspect(document, ids, name):
    facts = {"container_output_ids": [ids["a"], ids["b"]]}
    if name in ("entities", "quantity", "timing", "products"):
        first, second = document.find(ids["first"]), document.find(ids["second"])
        facts["source_flows"] = [edges(document, first.input_pin("source").identity),
                                 edges(document, second.input_pin("source").identity)]
        facts["amount"] = {"value": first.input_pin("amount").value.value.value,
                           "unit": str(first.input_pin("amount").value.value.unit)}
        expected = [ids["supernatant"], ids["pellet"]] if name == "products" else [ids["a"], ids["b"]]
        assert facts["source_flows"] == [[expected[0]], [expected[1]]], facts
        assert expected[0] != expected[1]
        assert facts["amount"] == {"value": 20, "unit": OM + "microlitre"}
    if name == "timing":
        requirement = document.find(ids["requirement"])
        facts["constraint_targets"] = [str(x.property_value) for x in requirement.constrained_elements]
        facts["interval"] = [requirement.specification.min.expr.expr.value,
                             requirement.specification.max.expr.expr.value]
        facts["interval_units"] = [str(requirement.specification.min.expr.expr.unit),
                                   str(requirement.specification.max.expr.expr.unit)]
        assert facts["constraint_targets"] == [ids["first"]]
        assert ids["second"] not in facts["constraint_targets"]
        assert facts["interval"] == [10, 20]
        assert facts["interval_units"] == [OM + "second-Time"] * 2
    if name in ("complex", "unspecified_association"):
        material = document.find(ids["material"])
        provision = document.find(ids["provision"])
        facts.update(material_types=sorted(str(t) for t in material.types),
                     constituents=sorted(str(f.instance_of) for f in material.features),
                     protocol_resource=str(provision.input_pin("resource").value.value))
        expected_type = sbol3.SBO_NON_COVALENT_COMPLEX if name == "complex" else sbol3.SBO_FUNCTIONAL_ENTITY
        assert facts["material_types"] == [expected_type]
        assert facts["constituents"] == [NS + "ligand", NS + "protein"]
        assert facts["protocol_resource"] == ids["material"]
    return facts


def validation(document):
    report = document.validate()
    return {"errors": [str(x) for x in report.errors], "warnings": [str(x) for x in report.warnings]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for library in ("sample_arrays", "liquid_handling"):
        labop.import_library(library)
    import tyto
    ontology_file = Path(tyto.__file__).parent / "ontologies/om-2.0.rdf"
    ontology = Graph().parse(str(ontology_file))
    base_unit = ontology.value(URIRef(OM + "microlitre"), URIRef(OM + "hasUnit"))
    dimension = ontology.value(base_unit, URIRef(OM + "hasDimension"))
    assert str(base_unit) == OM + "litre", base_unit
    assert str(dimension) == OM + "volume-Dimension", dimension
    cases = []
    for name in ("entities", "products", "quantity", "complex", "unspecified_association", "timing"):
        result = {"case": name}
        try:
            document, ids = build(name)
            result["validation"] = validation(document)
            path = args.output / (name + ".ttl")
            document.write(str(path), sbol3.TURTLE)
            result["before"] = inspect(document, ids, name)
            reread = sbol3.Document()
            reread.read(str(path))
            result["reread_validation"] = validation(reread)
            result["after"] = inspect(reread, ids, name)
            original_graph = Graph().parse(str(path), format="turtle")
            read_graph = Graph().parse(data=reread.write_string(sbol3.TURTLE), format="turtle")
            result["graph_isomorphic"] = isomorphic(original_graph, read_graph)
            result["passed"] = (result["before"] == result["after"] and result["graph_isomorphic"]
                                and not result["validation"]["errors"]
                                and not result["reread_validation"]["errors"])
        except Exception:
            result.update(passed=False, exception=traceback.format_exc())
        cases.append(result)
        print(name, result["passed"], result.get("exception", ""), flush=True)
    roots = {"labop": Path(labop.__file__).parent, "uml": Path(uml.__file__).parent,
             "sbol3": Path(sbol3.__file__).parent, "labop_time": Path(labopt.__file__).parent}
    files = {"observer": Path(__file__), "tyto/ontologies/om-2.0.rdf": ontology_file}
    for package, rels in {
        "labop": ["lib/liquid_handling.ttl", "lib/sample_arrays.ttl"],
        "uml": ["inner/uml.ttl", "activity.py", "behavior.py", "action.py"],
        "sbol3": ["component.py", "subcomponent.py", "om_unit.py", "constants.py"],
        "labop_time": ["__init__.py", "labop_time.ttl"],
    }.items():
        files.update({package + "/" + rel: roots[package] / rel for rel in rels})
    report = {"scope": "Model construction, validation and RDF roundtrip; no protocol execution or physical experiment.",
              "labop_commit": "2e2bd88150c71a440771fd369f40295dfd622324",
              "pin_source": "Retained environment; selected installed files hashed, not a complete fresh installation audit.",
              "python": sys.version,
              "volume_definition": {"unit": OM + "microlitre", "base_unit": str(base_unit),
                                    "dimension": str(dimension)},
              "versions": {p: importlib.metadata.version(p) for p in ("labop", "sbol3", "tyto")},
              "sha256": {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in files.items()},
              "cases": cases}
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if not all(case["passed"] for case in cases):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
