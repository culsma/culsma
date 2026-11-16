"""Count static test definitions in the three pinned source archives.

Counts test_*.py files under test/ or tests/ and module/class-level test_*
functions/methods. Parameterized cases are not expanded; skipped tests remain
definitions. Counts are not executed-case counts, coverage, or quality scores.
"""
import ast
import json
from pathlib import Path
import tarfile

BASE = Path(__file__).resolve().parent


def definitions(body, prefix=""):
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                yield {"name": prefix + node.name, "line": node.lineno,
                       "decorators": [ast.unparse(d) for d in node.decorator_list]}
        elif isinstance(node, ast.ClassDef):
            yield from definitions(node.body, prefix + node.name + ".")


if __name__ == "__main__":
    manifest = json.loads((BASE / "sources/manifest.json").read_text())
    report = {"method": __doc__.strip(), "systems": {}}
    for system, meta in manifest.items():
        files = []
        with tarfile.open(BASE / "sources" / meta["archive"]) as archive:
            for member in archive.getmembers():
                path = member.name.partition("/")[2]
                if (member.isfile() and path.startswith(("tests/", "test/"))
                        and Path(path).name.startswith("test_") and path.endswith(".py")):
                    tree = ast.parse(archive.extractfile(member).read(), filename=path)
                    items = list(definitions(tree.body))
                    files.append({"path": path, "definition_count": len(items),
                                  "definitions": items})
        report["systems"][system] = {
            "commit": meta["commit"], "test_file_count": len(files),
            "test_definition_count": sum(f["definition_count"] for f in files),
            "files": files,
        }
        print(system, len(files), report["systems"][system]["test_definition_count"])
    output = BASE / "results/engineering/test-inventory.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
