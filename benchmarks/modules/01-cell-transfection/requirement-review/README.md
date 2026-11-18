# Module 01 transfer requirements

The parent directory contains the submitted program and its frozen source. The revised protocol in this directory adds a scoped delivery requirement at S10 and S11. Both programs use the same numbered source, linked here as `source.md`. The historical inventory is evaluated from the parent directory.

The checker runs both programs with Culsma 1.0.7. It verifies the volume moved, destination, driver requirement, remaining source volumes and structural correspondence. A third run configures the software driver without dropwise support and checks that it rejects S10 before either transfer. The observed results are in [results.json](results.json).

From the benchmark repository root, with Python 3.12 and Lark 1.3.1, point `PYTHONPATH` at the `src` directory of Culsma revision `5364676bc2437b4981a00ce0133c730af243e469` or its code-identical release tag `v1.0.7`:

```sh
PYTHONPATH=/path/to/culsma-1.0.7/src python benchmarks/modules/01-cell-transfection/requirement-review/reproduce.py
```

The checker verifies runtime source files against the pinned Git revision and writes its JSON report to standard output. All three runs use the software-only StubDriver.
