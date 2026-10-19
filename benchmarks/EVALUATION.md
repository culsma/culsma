# Benchmark evaluation and reproduction

[Coverage overview](README.md) · [Reproduce](#reproduce) · [Worked examples](#worked-examples)

## Counting source steps

Coverage counts numbered source instructions matched to annotated program statements,
including statements in reusable module files. Composite coverage counts only its own
numbered steps; reused module steps are counted under the modules. Loop iterations
do not increase source-step coverage. This measures structural correspondence, not
complete experimental semantics or biological or hardware validation.

## Historical results (1.0.7)

The root manifest, programs and recorded results preserve the 1.0.7 baseline.
New evaluations are stored separately under `versions/`.

<!-- paper-table:start -->
Evaluated with Culsma 1.0.7.

| Module | Source steps | Coverage |
| --- | ---: | ---: |
| Module 01: Cell transfection | 13/13 | 100% |
| Module 02: Selective plating and colony isolation | 12/12 | 100% |
| Module 03: Cell lysate preparation | 10/10 | 100% |
| Module 04: Suspension-cell staining | 29/29 | 100% |
| Module 05: Magnetic-bead immunoprecipitation | 23/23 | 100% |
| Module 06: Western blot | 32/32 | 100% |
| Module 07: Sandwich ELISA | 41/42 | 97.6% |
| Composite 01: Flow-cytometry immunophenotyping | 5/5 | 100% |
| Composite 02: Magnetic-bead IP with Western blot | 7/7 | 100% |
<!-- paper-table:end -->

The seven modules cover **160/161** numbered source steps (99.38%). Including
the two composites gives **172/173** (99.42%). All nine entry programs complete:
**2675/2675** generated execution steps, with no failed or skipped steps and
no runtime diagnostics. Source steps and execution steps are different
counts; expanded loop iterations do not increase source-step coverage.

The uncovered step is Module 07 S37 (tap-mixing a plate). Module 02 now
represents surface spreading with `constraint(spread, aseptic)`. Coverage
measures structural source–program correspondence, not complete semantic
fidelity, biological success, or hardware execution. In particular, a transfer
may match a source step while a finer detail such as dropwise delivery remains
only in its annotation.


## Additional workflows

The Qubit-to-SPRI submission adds two modules and one composite, evaluated with
Culsma 1.0.9 at `e96c97ebe8211d0c92880887db7e58703c693cad`. These entries use
the same source-step correspondence rule and `reproduce.py` as the baseline set.

<!-- benchmark-table:start -->
Evaluated with Culsma 1.0.9.

| Module | Source steps | Coverage |
| --- | ---: | ---: |
| Module 08: Qubit 1X dsDNA HS quantification | 13/13 | 100% |
| Module 09: Double-sided SPRI selection | 21/21 | 100% |
| Composite 03: Qubit quantification and double-sided SPRI selection | 3/3 | 100% |
<!-- benchmark-table:end -->

The submitted module procedures cover **34/34 source steps (100%)**:
Qubit **13/13** and SPRI **21/21**. Qubit S8–S10 correspond jointly to the
calibration procedure's declared readout structure and ordered standard
measurements. These matches describe structural correspondence; they do not
establish every detail or physical endpoint. The separate three-step composite
source summarizes input setup and module handoff. Including it gives
**37/37 (100%)** across the three new entries.

All three entry programs complete: **35/35**, **56/56**, and **86/86** execution
steps respectively (**177/177** across the three runs), with zero failed or
skipped steps and zero runtime diagnostics. The composite retains six
nonblocking deprecated-return warnings. Its material check verifies the same
51 uL DNA tube, the 1 uL Qubit aliquot, and the final 50 uL eluate. Stub
concentration remains unset, and DNA masses remain unknown.

The [manifest](qubit-spri-manifest.json) freezes all three source inventories,
program hashes, runtime and expected results. The [summary](qubit-spri-summary.json),
[coverage table](qubit-spri-table.md), each entry's `results/`, and the composite
[verification](composites/03-qubit-double-sided-spri/results/verification.json)
retain the evidence. The [original submission](composites/03-qubit-double-sided-spri/submission/)
preserves all 11 files and the author's integrity manifest unchanged. The module
sources retain the submitted 13 and 21 numbered steps; the composite source is
an explicitly identified editorial summary of their handoff.

To reproduce these entries with a clean runtime checkout at the pinned commit:

```sh
python benchmarks/reproduce.py \
  --manifest benchmarks/qubit-spri-manifest.json \
  --runtime-repo /path/to/culsma-runtime \
  --output benchmarks/local-results/qubit-spri-reproduction
```

A passing comparison reproduces all numbered source-step matches and the
expected execution results. This additional inventory is recorded separately
from the nine-entry baseline and versioned snapshots, preserving their denominators.

## Known gaps and extension targets

The results above describe the fixed evaluated version, not an exhaustive
inventory of laboratory operations. The collection can grow as additional
workflows are added; compare versions using the same source inventory and
coverage rules when assessing improvements in operation support.

| Source step | Gap in 1.0.7 | Status in 1.0.9 |
| --- | --- | --- |
| [Module 07 S37](modules/07-sandwich-elisa/source.md) | Gentle plate tapping to mix the stopped reaction has no executable action in the 1.0.7 program. | Resolved by `AgitationMode.TAP` with GENTLE in the [versioned ELISA program](versions/1.0.9-d1216a1/modules/07-sandwich-elisa/protocol.culs); 42/42 source steps, with TAP after stopping and before readout. |

The recorded release run and agitation regressions verify language and
simulated execution support. The published 1.0.7 program, manifest and results
retain their original 41/42 ELISA result; the new snapshot records 42/42.
Successful software execution alone does not demonstrate physical performance.
Module 02 remains 12/12 and still requires an
operator-supplied mapping from selected observation rows to colony material
references; structural correspondence does not establish that automatic link.

## Directory and execution entry points

| Path | Contents |
| --- | --- |
| [`modules/`](modules/) | Benchmark modules and worked examples `example-00`–`example-04`; the baseline inventory uses modules 01–07, and the additional Qubit/SPRI inventory uses 08–09. |
| [`composites/`](composites/) | Composite workflows, each with its source, entry program, and results; the baseline inventory uses entries 01–02. |
| [`reproduce.py`](reproduce.py) | Coverage and execution checks for the seven benchmark modules and two composites. |
| [`check_manuscript_examples.py`](check_manuscript_examples.py) | Material-state and result checks for Examples 01–04. |
| [`check_introduction_example.py`](check_introduction_example.py) | Checks for introductory Example 00. |
| [`manifest.json`](manifest.json) | Fixed versions, input hashes, expected counts and known gaps. |
| [`summary.json`](summary.json) | Aggregate benchmark results; per-artifact records are in each artifact's `results/`. |
| [`versions/`](versions/) | Additional version snapshots, each with its own inputs, manifest, summary, coverage table and per-artifact results. |
| [`examples-summary.json`](examples-summary.json) | Aggregate checks for Examples 01–04, excluded from coverage totals. |

Composite entry programs use explicit, source-relative `include` paths to load
reusable module definitions. Composite 01 includes Module 04's `Module04.culs`;
Composite 02 includes Module 05's `Module05.culs` and Module 06's `two-lane-gfp.culs`.
Composite 03 includes the reusable definitions from Modules 08 and 09.
Paths resolve relative to the composite file, independently of the working
directory. No import search-path configuration or wrapper files are required.
With Culsma 1.0.7 installed, the two baseline entry programs can run directly from the
repository root:

```sh
culsma benchmarks/composites/01-flow-cytometry-immunophenotyping/protocol.culs
culsma benchmarks/composites/02-magnetic-bead-ip-western-blot/protocol.culs
```

Composite 03 requires Culsma 1.0.9 for non-fractionating centrifuge agitation:

```sh
culsma benchmarks/composites/03-qubit-double-sided-spri/protocol.culs
```

Each source procedure retains its references and context in `source.md`.

## Reproduce

### Current release (1.0.9)

With Python 3.12.8 installed, use separate benchmark and runtime checkouts:

```sh
git clone https://github.com/culsma/culsma.git culsma-benchmark
git clone https://github.com/culsma/culsma.git culsma-runtime
git -C culsma-runtime checkout --detach d1216a16f7adaa41ac0aac763a60c84bb7be3f64
python3.12 -m venv .venv
.venv/bin/python -m pip install lark==1.3.1
.venv/bin/python culsma-benchmark/benchmarks/reproduce.py \
  --manifest culsma-benchmark/benchmarks/versions/1.0.9-d1216a1/manifest.json \
  --runtime-repo culsma-runtime --output results/benchmark-1.0.9
```

The selected manifest determines the inputs, runtime and expected results.
The runner verifies the pinned runtime, dependency versions and input hashes
before comparing coverage and execution counts. On Windows use
`.venv/Scripts/python.exe`. Use a fresh output directory for each run.

### Historical baseline (1.0.7)

To reproduce the historical evaluation, use a fresh working directory and the
same Python 3.12.8 / Lark 1.3.1 environment:

```sh
git clone https://github.com/culsma/culsma.git culsma-benchmark
git -C culsma-benchmark checkout --detach a76a98b98dab5e8edd76eefbb7dc5cc7ac447a64
git clone https://github.com/culsma/culsma.git culsma-runtime
git -C culsma-runtime checkout --detach 5364676bc2437b4981a00ce0133c730af243e469
python3.12 -m venv .venv
.venv/bin/python -m pip install lark==1.3.1
.venv/bin/python culsma-benchmark/benchmarks/reproduce.py \
  --runtime-repo culsma-runtime --output results/benchmark-1.0.7
```

The input snapshot is `f7b744e8efbafd9176a5b4fa07761358a4aee214`; the runtime
is `5364676bc2437b4981a00ce0133c730af243e469`. Package metadata is **1.0.7**.
Release tag `v1.0.7` contains the same implementation source; the benchmark
package also includes later composite and example updates.

Reproducing the recorded 1.0.7 gap is a successful comparison. A zero exit
status requires matching coverage, gaps and execution counts, with no failures,
skips or runtime diagnostics. Running the current runner without `--manifest`
still selects this historical baseline; use the explicit manifest above for 1.0.9.

### Recorded outputs

Each output directory mirrors the module/composite layout, with `summary.json`,
`table.md`, and per-artifact `results/coverage.json`, `results/run.json`, and
`results/results.json`. Nonempty console/error logs are retained when present.
Input, script, environment and output identities are recorded. Material and
observation records are preserved for inspection, not treated as independent
experimental validation. Local runs can use `benchmarks/local-results/`, which
is ignored by Git.

## Maintaining versioned evaluations

1. Store each new release evaluation under `versions/<version>-<runtime-commit>/`.
   Retain previous inputs and results, including complete program dependencies.
2. Freeze its manifest with runtime and dependency versions, expected counts,
   remaining gaps and input hashes. Explain intentional execution-count changes;
   do not change expectations merely to make a failing comparison pass.
3. Run the selected inventory into a fresh directory with `--manifest`.
   `--update-readme` refreshes only that inventory's marked table after all
   comparisons pass. Keep the summary, table and per-artifact results together.
4. Add the verified release to the version index. Keep additional workflow
   inventories separate, and cite a fixed snapshot when reporting results.

Historical Cases 00–14 and their original tools are preserved in
[`archive/benchmarks-legacy/`](../archive/benchmarks-legacy/) and excluded from
the current benchmark totals.

## Worked examples

The worked examples have separate state and result checks and are excluded
from benchmark coverage totals. Their `protocol.culs` files and `results/`
retain the programs, checked states, observations, reports and raw outputs.

| Directory | Focus |
| --- | --- |
| `modules/example-00/` | Lysate clarification and fluorescence observation |
| `modules/example-01/` | PCR composition and applied conditions |
| `modules/example-02/` | Staining, washing, and flow-cytometry observation |
| `modules/example-03/` | Magnetic separation and component relationships |
| `modules/example-04/` | Ordered fractions and parameterized plate analysis |

These examples retain their 1.0.7 runtime. Use the historical reproduction
environment described above, then install its pinned CLI:

```sh
.venv/bin/python -m pip install -e culsma-runtime
.venv/bin/python culsma-benchmark/benchmarks/check_manuscript_examples.py \
  --culsma-repo culsma-runtime --culsma-cli .venv/bin/culsma \
  --output results/examples-run-01 --tex-output-dir results/examples-run-01/listings
.venv/bin/python culsma-benchmark/benchmarks/check_introduction_example.py \
  --culsma-cli .venv/bin/culsma \
  --output results/examples-run-01/modules/example-00/results \
  --tex-output-dir results/examples-run-01/listings
```

The four-example checker emits `examples-summary.json` and per-example results
under `modules/example-01` through `example-04`. The introductory checker keeps
its summary alongside its outputs. Unset observation fields remain unset;
these software runs do not supply laboratory measurements. Its display maps
the observation subject to its declared container label; raw output and the
mapping are retained. These commands generate TeX listings without compiling
the manuscript PDF.

When updating a worked example, synchronize the corresponding `protocol.culs`
and checker, rerun, and replace its recorded results. Keep coverage unchanged
unless the separately enumerated benchmark source inventory changes.
