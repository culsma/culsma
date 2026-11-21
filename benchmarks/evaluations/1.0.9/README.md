# Culsma 1.0.9 evaluation

Actual runtime: `1.0.9`, commit `e96c97ebe8211d0c92880887db7e58703c693cad`.
Counting rule: `modular-source-step-correspondence-v2`.

Original workflows: 173/173.
Qubit/SPRI additions: 37/37.
Module 11: 21/21, reported separately.

All evaluated entry programs completed; execution events reproduce the final
material state. See [summary.json](summary.json) and [table.md](table.md).

The manifest identifies the hashes of the shared files in `../../modules/`
and `../../composites/`. No program copies are stored in this directory.

From the repository root, replace these results with:

```sh
python benchmarks/evaluate.py --version 1.0.9 --replace
```
