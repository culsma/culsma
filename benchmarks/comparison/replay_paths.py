"""Package-relative evidence and configurable, untracked replay environments."""
import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
REPOSITORY = PACKAGE.parents[1]
LOCAL_RESULTS = PACKAGE.parent / "local-results"
RUNTIME = Path(os.environ.get("COMPARISON_RUNTIME_DIR",
                              LOCAL_RESULTS / "comparison-runtime")).expanduser().resolve()
REPLAY_OUTPUT = LOCAL_RESULTS / "comparison-replay"


def result_path(relative):
    return Path(os.environ.get("COMPARISON_RESULTS_DIR", PACKAGE / "results")) / relative
