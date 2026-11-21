"""Observe native GFP output-to-transfer references in the serialized model."""
import json
from pathlib import Path
import sys

from rdflib import Graph, Namespace, RDF


def observe(directory):
    graph = Graph().parse(directory / 'protocol.ttl', format='turtle')
    uml = Namespace('http://bioprotocols.org/uml#')
    sbol = Namespace('http://sbols.org/v3#')
    references = []

    def destinations(node, edges, visited):
        # Fork nodes preserve the output reference when it has several users.
        if node in visited:
            return
        if (node, RDF.type, uml.ForkNode) not in graph:
            yield node, edges
            return
        for edge in graph.subjects(uml.source, node):
            if (edge, RDF.type, uml.ObjectFlow) in graph:
                yield from destinations(graph.value(edge, uml.target),
                                        edges + [str(edge)], visited | {node})

    for edge in graph.subjects(RDF.type, uml.ObjectFlow):
        source = graph.value(edge, uml.source)
        target = graph.value(edge, uml.target)
        if (source, RDF.type, uml.OutputPin) not in graph:
            continue
        if str(graph.value(source, sbol.name)) != 'samples':
            continue
        for producer in graph.subjects(uml.output, source):
            for pin, edges in destinations(target, [str(edge)], set()):
                for consumer in graph.subjects(uml.input, pin):
                    behavior = str(graph.value(consumer, uml.behavior))
                    if behavior.endswith('/Transfer'):
                        references.append({
                            'producer_behavior': str(graph.value(producer, uml.behavior)),
                            'output_pin': str(source), 'input_pin': str(pin),
                            'consumer': str(consumer), 'edges': edges})
    result = json.loads((directory / 'results.json').read_text())
    return {
        'references': sorted(references, key=lambda row: row['edges']),
        'samples_outputs_used_by_transfer': {
            name: any(r['producer_behavior'].endswith('/' + name) for r in references)
            for name in ('EmptyContainer', 'PlateCoordinates')},
        'completed_normally': result['completed_normally'],
        'validation_errors': result['validation_errors'],
        'well_volumes_uL': result['well_volumes_uL']}


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(json.dumps(observe(Path(sys.argv[1])), indent=2) + '\n')
