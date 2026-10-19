# Patterns workflow benchmark

This is the canonical public benchmark for Section 3.5 of
*Culsma: An Executable Specification Language for Laboratory Protocols*.
It contains seven experimental modules and two composite workflows. Source
procedures, programs, results, and reproduction instructions are maintained
here together; no documentation-site export is needed.

## Results by version

Each recorded version keeps its program inputs, pinned runtime, manifest,
aggregate summary and per-artifact results. The root snapshot below is the
fixed paper evaluation; newer runs are added under `versions/`.

| Version | Status | Seven modules | All nine entries | Completed execution steps | Records |
| --- | --- | ---: | ---: | ---: | --- |
| 1.0.7 | Paper evaluation | 160/161 | 172/173 | 2675/2675 | [Manifest](manifest.json), [results](summary.json) |
| 1.0.9-dev | Unreleased; runtime `ca7a098` | 161/161 | 173/173 | 2700/2700 | [Snapshot](versions/1.0.9-dev-ca7a098/README.md), [results](versions/1.0.9-dev-ca7a098/summary.json) |

The development snapshot resolves Module 07 S37 with a whole-plate TAP and an
independent GENTLE requirement. Its complete nine-entry rerun has no failures,
skips or runtime diagnostics. It is a development evaluation, not a 1.0.9
release: package metadata at its pinned runtime still reports 1.0.8. No 1.0.8
benchmark result is inferred from that metadata.

## Paper results (1.0.7, Section 3.5)

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

## Known gaps and extension targets

The results above describe the fixed evaluated version, not an exhaustive
inventory of laboratory operations. The collection can grow as additional
workflows are added; compare versions using the same source inventory and
coverage rules when assessing improvements in operation support.

| Source step | Gap in 1.0.7 | Status in 1.0.9-dev |
| --- | --- | --- |
| [Module 07 S37](modules/07-sandwich-elisa/source.md) | Gentle plate tapping to mix the stopped reaction has no executable action in the paper program. | Resolved by `AgitationMode.TAP` with GENTLE in the [versioned ELISA program](versions/1.0.9-dev-ca7a098/modules/07-sandwich-elisa/protocol.culs); 42/42 source steps, with TAP after stopping and before readout. |

The recorded development run and agitation regressions verify language and
simulated execution support. The published 1.0.7 program, manifest and results
retain their original 41/42 ELISA result; the new snapshot records 42/42.
Successful software execution alone does not demonstrate physical performance.
Module 02 remains 12/12 and still requires an
operator-supplied mapping from selected observation rows to colony material
references; structural correspondence does not establish that automatic link.

## Directory and execution entry points

| Path | Contents |
| --- | --- |
| [`modules/`](modules/) | Seven numbered benchmark modules and manuscript `example-00`–`example-04`; programs and results are kept together in each directory. |
| [`composites/`](composites/) | Two composite workflows, each with its source, entry program, and results. |
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
Paths resolve relative to the composite file, independently of the working
directory. No import search-path configuration or wrapper files are required.
With Culsma 1.0.7 installed, both entry programs can run directly from the
repository root:

```sh
culsma benchmarks/composites/01-flow-cytometry-immunophenotyping/protocol.culs
culsma benchmarks/composites/02-magnetic-bead-ip-western-blot/protocol.culs
```

Each source procedure retains its references and context in `source.md`.

## Reproduce

With Git and Python 3.12 installed, run from a new working directory:

```sh
git clone https://github.com/culsma/culsma.git culsma-benchmark
git clone https://github.com/culsma/culsma.git culsma-runtime
git -C culsma-runtime checkout 5364676bc2437b4981a00ce0133c730af243e469
python3.12 -m venv .venv
.venv/bin/python -m pip install lark==1.3.1
.venv/bin/python culsma-benchmark/benchmarks/reproduce.py \
  --runtime-repo culsma-runtime --output results/patterns-run-01
```

For the exact paper snapshot, also check out the benchmark-package commit
cited in the paper before running. On Windows use `.venv/Scripts/python.exe`.
The runner imports the pinned runtime directly; no private wheel is required.
Use a new output directory for every run. For local work inside this repository,
use `benchmarks/local-results/<run-name>/`, which is ignored by Git.

The input snapshot is `f7b744e8efbafd9176a5b4fa07761358a4aee214`; the runtime
is `5364676bc2437b4981a00ce0133c730af243e469`. The paper's benchmark version is
**1.0.7**; package metadata at the pinned runtime is **1.0.7**. Release tag
`v1.0.7` contains the same implementation source as this evaluated runtime;
the benchmark package additionally includes the later composite and example updates. The recorded evaluation environment is Python 3.12.8
with Lark 1.3.1.

A zero exit status requires the pinned runtime and input hashes, matching
coverage counts and gap records, and successful completion of all nine
programs with the expected execution counts and zero failures, skips, or
runtime diagnostics. Reproducing the remaining known gap is a successful comparison.
The checker and its counting rule are included in the single script.

To reproduce a different recorded version, select its manifest with
`--manifest`. Inputs resolve relative to that manifest, and its runtime commit
and dependency versions are checked before execution. For the development
snapshot, use a separate runtime checkout containing commit
`ca7a0984d0b5b0d47a63c39725d8f70529961687` (see the snapshot's
[reproduction command](versions/1.0.9-dev-ca7a098/README.md#reproduce)).
The default command above continues to reproduce the 1.0.7 paper snapshot.

Each output directory mirrors the module/composite layout, with `summary.json`,
`table.md`, and per-artifact `results/coverage.json`, `results/run.json`, and
`results/results.json`. Nonempty console/error logs
are retained when present. Report and compact-result exports use separate
deterministic CLI invocations. Input, script, environment, and output identities
are recorded. The automatic comparison checks coverage and execution counts;
material and observation records are preserved for inspection, not treated as
independent experimental validation. No second copy of coverage is stored in
the source directories.

## Maintain the benchmark and paper together

1. Add a new `versions/<version>-<runtime-commit>/` snapshot for each evaluated
   release or development revision. Retain previous records. Copy the complete
   source inventory and program dependencies, then revise the intended program
   steps with their complete annotations and references.
2. Freeze its manifest with runtime commit, actual package/dependency versions,
   expected coverage and execution counts, remaining gaps and input hashes.
   Explain intentional execution-count changes; do not replace expectations
   merely to make a failing comparison pass.
3. Run all nine entries into a fresh output directory with `--manifest`.
   `--update-readme` refreshes only the selected snapshot's marked table after
   every comparison passes. Keep its summary, table and per-artifact results
   together with those inputs.
4. Add the reviewed result to the version index above and commit the snapshot
   and runner changes together. Keep development results labeled as unreleased.
   A manuscript evaluation changes only when its paper table and Methods are
   deliberately advanced to the newly cited benchmark package commit.

Historical Cases 00–14 and their original tools are preserved outside this
active directory in [`archive/benchmarks-legacy/`](../archive/benchmarks-legacy/).
They are excluded from this runner and the paper's current coverage totals.
## Manuscript examples

The examples share the module layout but are not part of the Section 3.5
coverage denominator. Their `protocol.culs` files reproduce the paper listings;
`results/` retains their checked states, observations, reports, and raw outputs.

| Directory | Manuscript location | Focus |
| --- | --- | --- |
| `modules/example-00/` | Introduction | Lysate clarification and fluorescence observation |
| `modules/example-01/` | Section 3.1 | PCR composition and applied conditions |
| `modules/example-02/` | Section 3.2 | Staining, washing, and flow-cytometry observation |
| `modules/example-03/` | Section 3.3 | Magnetic separation and component relationships |
| `modules/example-04/` | Section 3.4 | Ordered fractions and parameterized plate analysis |

Install the pinned runtime CLI in the environment above:

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

When editing a manuscript listing, synchronize the corresponding `protocol.culs`
and checker, rerun, and replace its recorded results. Keep coverage unchanged
unless the separately enumerated benchmark source inventory changes.
