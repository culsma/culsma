
import json, sys
from pathlib import Path
from culsma.parser.parser import parse
from culsma.frontend.resolver import resolve_program
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.typecheck import typecheck
src = Path(sys.argv[1]).read_text()
assert src.count("duration = 10min") == 1
rows = []
for name, source in [("valid", src), ("wrong_duration_unit", src.replace("duration = 10min", "duration = 10uL"))]:
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    result = typecheck(compiled.ir, analysis=compiled.analysis)
    rows.append({"case": name, "accepted": result.ok,
                 "diagnostics": [{"code": d.code, "span": str(d.span)} for d in result.diagnostics]})
print("RESULT_JSON=" + json.dumps({"python": sys.version, "cases": rows}))
