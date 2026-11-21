
import json
from culsma.parser.parser import parse
from culsma.frontend.resolver import resolve_program
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.validate import validate
from pathlib import Path
source = Path("protocol.culs").read_text()
rows = []
for name, text in [("returned_local", source),
                   ("local_outside_protocol", source + "first << [local:20uL];\n")]:
    compiled = compile_ast(resolve_program(parse(text)).prepared_program)
    result = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    rows.append({"case": name, "source": text,
                 "diagnostics": [{"code": d.code, "span": str(d.span)} for d in result.diagnostics]})
print("RESULT_JSON=" + json.dumps({"cases": rows}))
