import ast, hashlib, json, os
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

if __name__ == "__main__":
    source = Path(os.environ["COMPARISON_RUNTIME_DIR"]) / "labop-source"
    Path("material-audit.json").write_text(json.dumps(audit_library(source),indent=2)+"\n")
