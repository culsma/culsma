# Reproduce the Patterns benchmark

This directory contains the 14 workflows evaluated in the paper and the
separate worked example (00), with their source files and expected results.

## Read the files

| Path | Purpose |
| --- | --- |
| `cases/01/` through `cases/14/` | The 14 benchmark cases. |
| `cases/00/` | Worked example, excluded from corpus totals. |
| `reproduce.py` | Run, extract metrics, and compare with the paper tables. |
| `tools/` | Extraction scripts. |
| `expected/` | `tables.json` for automatic comparison; `tables.md` for reading the same totals. |
| `tests/` | Regression tests; not required to run the benchmark. |
| `requirements.lock` | Exact dependency versions and installation-package hashes. |
| `SOURCES.md` | Source provenance and complete case references. |

Every case has the same six files:

| File | Contents |
| --- | --- |
| `protocol.culs` | Executable Culsma program. |
| `source.md` | Original experimental description. |
| `source.steps.json` | Reviewed step titles and inputs/outputs for navigation; not a counting input. |
| `action_descriptors.json` | Section 3.2: per-step descriptors and evidence. |
| `material_state_continuity.json` | Section 3.3: objects, later uses and execution completion. |
| `result_traceability.json` | Section 3.4: consumption, touched containers and final material states. |

The supplied JSON files are expected results. The scripts regenerate them from
source and fresh CLI exports without reading them as counting inputs.
No per-case configuration or compressed archive is needed.

## Install the matching environment

This working candidate requires **Culsma 1.0.7rc1**, Lark 1.3.1 and Python
3.11–3.13 (validated with 3.12.8). The implementation is an internal prerelease:
public end-to-end installation remains pending a release decision. No wheel
is bundled or redistributed here.

With authorized access, obtain `culsma-1.0.7rc1-py3-none-any.whl` from
`internal-1.0.7rc1` and put it in a local wheel directory. Its SHA-256 is
`ba049c3217e45d500dbf1cf848667ab268a218f7373a20bc90b884a88fa7cffe`.
From this directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --find-links /path/to/authorized/wheels --require-hashes -r requirements.lock
```

On Windows, use `.venv/Scripts/python.exe`. Python hosts the installed Culsma
CLI and runs the metric scripts; the extractor does not import language internals.

## Run and compare

```sh
.venv/bin/python reproduce.py all --results results/my-run
```

The runner discovers the two-digit subdirectories of `cases/` in numeric order,
requires a `protocol.culs` in each, invokes the installed Culsma CLI and extracts
three metric files per case. No separately maintained case list is read.
Use a new results directory each time. Allow several minutes and a few GB
for intermediate exports. External inventory reconciliation is not enabled.

New metric files appear in `results/my-run/<case>/evaluation/`.
The adjacent `input/` holds the source copy, AST/IR/Plan/Run/Result/Output JSON
and automatically generated capture metadata. These are local reproduction
evidence, not additional committed case files.

At the run root, `tables.json` and `tables.md` contain regenerated tables;
`comparison.json` records differences. Comparison checks all nine counts
against `expected/tables.json`, plus complete material and return records
against each supplied `result_traceability.json` and the new raw output.
A mismatch or failed run gives a nonzero exit status.
The discovered case set must also match the expected table: missing or extra
cases fail comparison. Case 00 stays outside corpus totals regardless of its
directory location.

Both capture and the runner read dependency versions from `requirements.lock`
and verify the installed versions. Actual Python, Culsma and Lark versions are
recorded with the run. The runner accepts stable Python 3.11–3.13. Source and
artifact hashes are generated automatically in the capture receipt and checked
when extracting; there is no separate file-hash list to maintain at the root.

Recompute comparisons without rerunning Culsma:

```sh
.venv/bin/python reproduce.py summarize --results results/my-run
```

Check the supplied JSON against the tables without installing Culsma:

```sh
python3 reproduce.py check-baseline
```

Run one case and generate its three files:

```sh
.venv/bin/python tools/benchmark_metrics.py capture --source cases/01/protocol.culs --python .venv/bin/python --bundle results/single/01/input
.venv/bin/python tools/benchmark_metrics.py extract --bundle results/single/01/input --out results/single/01/evaluation
```

## How the metrics are extracted

The entry and call relationships come from exported AST JSON. Numbered
`// Source step S<n>:` comments may occur in main or subprotocols. Local
markers take precedence; otherwise a subprotocol inherits the calling step.
Initial main-protocol declarations belong to S1. An unmarked batch wrapper
with one distinct protocol callee inherits that callee's step scope. Missing
S1, gaps, malformed/ranged markers and ambiguous mappings fail. Without a
separate step list, an entirely deleted final marker cannot be detected solely
from remaining source; expected tables provide an independent comparison.

The fixed `patterns-metrics-nested-v9` rules deduplicate identical descriptors
within a step. Loop iterations do not multiply static descriptors; distinct
explicit calls retain their object context. Groups require program-defined
membership, a common introduction step and identical later-use steps;
overlapping eligible groups are split. Later uses are compared by source-step
number, while runtime events establish actual use. Traceability counts preserve
distinct records even when display names repeat.

The committed baseline for the 14 cases totals 208 source steps, 3929 descriptors, 299 reused objects,
680 later-use links and 4672/4672 completed/active steps. Section 3.4 totals
are 229 reagent records, 633 touched-container records and 482 final states.
These describe modeled execution, not biological validation or device execution.
Static compatibility warnings are distinct from runtime diagnostics.
Capture paths/hashes and evidence-list ordering may differ between runs without
changing metric content.

### Final-state scope

New extractions count nonempty physical containers directly from
`run.json` at `/state/artifacts/material_state/containers`, including residual
source stocks, assay containers and waste. Each `final_material_records` entry
preserves the runtime container ID, full material state and a JSON pointer.
Empty containers and internal fraction handles (`::`) are excluded; event
snapshots are not accumulated. Positive quantities use a tolerance of `1e-9`.
The runtime's narrower `final_products` summary remains available separately
under its original name and is not the basis of the revised final-state count.

All 15 cases have been rerun with this scope. Cases 01–14 contain 482 final
material records in total, compared with 287 records in the former summary-only
scope. Case 00 remains separate with three records. Descriptor and continuity
counts are unchanged. The case JSONs and expected tables use the revised scope.

## Maintainer checks

```sh
CULSMA_TEST_PYTHON="$PWD/.venv/bin/python" .venv/bin/python -m unittest discover -s tests -q
```

Integration tests skip without an implementation interpreter; a skipped run
is not full validation. Historical profile inputs in `tests/fixtures/` are
test-only; production capture reads `protocol.culs` directly.

After a program change, regenerate its metrics and review differences before
updating expected results. Do not change expected results just to make a failing
comparison pass. Programs and sources are maintained here; the website and
manuscript are publication copies. Public releases should identify the Git
commit/tag used so readers can obtain the same files.
