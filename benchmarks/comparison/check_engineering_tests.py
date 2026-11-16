"""Run one unmodified upstream test module per pinned comparison system.

Uses the source directories and isolated environments under benchmarks/local-results/comparison-runtime.
Install pytest==8.4.2 in those environments first. This is a sample, not a full
test-suite or coverage assessment, and it does not operate instruments.
"""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import tarfile

from replay_paths import RUNTIME as BASE
OUT = Path(__file__).resolve().parent / "results/engineering"
CASES = {
    "culsma": ("tests/test_pipeline_scope.py", "src"),
    "labop": ("test/test_validation.py", "."),
    "bpl": ("tests/phase2_state/test_state_model.py", "."),
}


def run(name):
    test, import_root = CASES[name]
    cwd = BASE / f"{name}-source"
    env = os.environ.copy()
    env.update(PYTHONPATH=str(cwd / import_root),
               PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONDONTWRITEBYTECODE="1")
    command = [str(BASE / f"{name}-env/bin/python"), "-m", "pytest", "-q",
               "-o", "addopts=", "-p", "no:cacheprovider", test]
    result = subprocess.run(command, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=45)
    (OUT / f"{name}-test.txt").write_text(result.stdout)
    return name, {"command": command, "cwd": str(cwd),
                  "PYTHONPATH": env["PYTHONPATH"], "returncode": result.returncode,
                  "output": result.stdout}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    # The original source setup extracted only src/ for Culsma.
    target = BASE / "culsma-source" / CASES["culsma"][0]
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(Path(__file__).parent / "sources/culsma-5364676b.tar.gz") as archive:
        target.write_bytes(archive.extractfile("culsma/" + CASES["culsma"][0]).read())
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = dict(pool.map(run, CASES))
    (OUT / "test-runs.json").write_text(json.dumps(results, indent=2) + "\n")
    for name, result in results.items():
        print(name, "exit", result["returncode"], result["output"][-1200:])
