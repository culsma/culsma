# Culsma 1.0.6 — retrospective compatibility evaluation

Evaluated on **21 September 2026** using released tag `v1.0.6`, commit
`0a5393c33151663566fe3d81d4fe01f29f98e274`, Python 3.12.8 and Lark 1.3.1.
The input programs are the unchanged benchmark snapshot
[`ba46a8d`](https://github.com/culsma/culsma/tree/ba46a8d892ad800f0fb474a398438787535f0ff7/benchmarks).

This is a new retrospective run of later-authored programs against an older
release, not a benchmark recorded at the time of the 1.0.6 release. No syntax
was rewritten to make the programs compatible with 1.0.6.

## Results

**1 of 8 programs completed.** Module 02 completed 71/71 execution steps with
zero runtime diagnostics; its older material taxonomy produced compile-time
compatibility warnings, preserved in the diagnostic record.

| Module | Source steps | Structural coverage | Execution on 1.0.6 |
| --- | ---: | ---: | --- |
| Module 01: Cell transfection | 13/13 | 100% | Failed |
| Module 02: Selective plating and colony isolation | 11/12 | 91.7% | Completed |
| Module 03: Cell lysate preparation | 10/10 | 100% | Failed |
| Module 04: Suspension-cell staining | 29/29 | 100% | Failed |
| Module 05: Magnetic-bead immunoprecipitation | 23/23 | 100% | Failed |
| Module 06: Western blot | 32/32 | 100% | Failed |
| Module 07: Sandwich ELISA | 41/42 | 97.6% | Failed |
| Composite 01: Flow-cytometry immunophenotyping | 5/5 | 100% | Failed |

Structural coverage remains **164/166 (98.80%)** because it checks the same
source annotations and code regions, independently of runtime acceptance.
It is not a percentage of steps that 1.0.6 can execute. A failed program is
not assigned zero source coverage or a fabricated partial support score.

## Observed compatibility boundaries

| Programs | Observed first blocking condition |
| --- | --- |
| Modules 01, 04, 06, 07 | Material enum declarations are rejected by validation/type checking (`SEM_INVALID_CONTENT_TYPE_FORMAT`, `TYPE_CONTENT_KIND_NOT_TEXT`, `TYPE_CONTENT_TYPE_NOT_TEXT`). |
| Modules 03, 05 | Parsing stops at the `materials.replace(...)` form. |
| Composite 01 | Parsing stops at the named arguments of the imported protocol call used as an expression. |

These are the failures observed with unchanged input programs. Earlier failures
can hide later ones, and this evaluation does not show whether alternative
1.0.6-compatible programs could express the same procedures.
The corresponding fixed development runtime `42b562b` completes all eight
programs in the paper snapshot. This comparison demonstrates compatibility
changes for these programs, not an overall ranking of language capabilities.

## Reproduce and inspect

From a full checkout of the benchmark publication branch, create a separate
runtime checkout and use Python 3.12 with `lark==1.3.1`:

```sh
git clone https://github.com/culsma/culsma.git culsma-runtime-1.0.6
git -C culsma-runtime-1.0.6 checkout 0a5393c33151663566fe3d81d4fe01f29f98e274
python3.12 -m venv .venv
.venv/bin/python -m pip install lark==1.3.1
.venv/bin/python benchmarks/history/reproduce.py \
  --runtime-repo culsma-runtime-1.0.6 \
  --output /tmp/culsma-history-1.0.6-new-run
```

Use a new output directory. The runner verifies runtime identity, dependency
versions and every frozen input hash. It records all eight outcomes even when
individual programs fail. Exit zero means the evaluation completed, not that
all programs passed; inspect `completed_programs` and per-program outcomes.

- [Evaluation manifest](manifest.json)
- [Machine-readable summary](results/summary.json)
- [Generated table](results/table.md)
- [Module evidence](results/modules/): coverage records, available run reports,
  phase diagnostics, and parser error logs.
- [Composite evidence](results/composites/)

The historical CLI does not expose the newer compact `--results` export;
this evaluation uses its supported `--output` and diagnostic-artifact options.
The raw report can omit validation failures from its runtime diagnostic count,
so phase diagnostics are retained separately.

[Back to version history](../README.md) · [Current paper snapshot](../../README.md)
