# Culsma 1.0.11 evaluation

Release target: **Culsma 1.0.11**.
Recorded runtime commit: `b27f9f8d2460d65379ece299245a2d399cf7aeec`.
Before publication, update the manifest to the final 1.0.11 implementation and
verified input hashes, then rerun the evaluation to refresh these records.
Counting rule: `modular-source-step-correspondence-v2`.

Original workflows: 173/173.
Qubit/SPRI additions: 37/37.
Module 11: 21/21, reported separately.

All evaluated entry programs completed; execution events reproduce the final
material state. See [summary.json](summary.json) and [table.md](table.md).

The manifest identifies the hashes of the shared files in `../../modules/`
and `../../composites/`. No program copies are stored in this directory.

From the repository root, rerun using the runtime and inputs pinned in the
manifest and replace these results with:

```sh
python benchmarks/evaluate.py --version 1.0.11 --replace
```
