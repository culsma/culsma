# Culsma 1.0.7 evaluation

Actual runtime: `1.0.7`, commit `5364676bc2437b4981a00ce0133c730af243e469`.
Counting rule: `modular-source-step-correspondence-v2`.

Original workflows: 172/173.
Module 11: 21/21, reported separately.

All evaluated entry programs completed; execution events reproduce the final
material state. See [summary.json](summary.json) and [table.md](table.md).

The manifest identifies the Git revision of the evaluated program inputs.
The runner recovers those files from Git, without maintaining a second program tree.

From the repository root, replace these results with:

```sh
python benchmarks/evaluate.py --version 1.0.7 --replace
```
