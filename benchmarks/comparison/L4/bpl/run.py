import hashlib, importlib, json
from pathlib import Path
module = importlib.import_module('bpl.simulation.simulator')
source = Path(module.__file__)
text = source.read_text()
checks = {token: token in text for token in ['def add_step_callback', '_step_callbacks']}
Path("results.json").write_text(json.dumps({"method":"source_inspection", "source":str(source), "sha256":hashlib.sha256(source.read_bytes()).hexdigest(), "interfaces":checks, "interface_found":all(checks.values())},indent=2)+"\n")
