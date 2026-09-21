# Patterns workflow benchmark

This is the canonical public benchmark for Section 3.5 of
*Culsma: An Executable Specification Language for Laboratory Protocols*.
It contains seven experimental modules and one composite workflow. Source
procedures, programs, results, and reproduction instructions are maintained
here together; no documentation-site export is needed.

## Evaluation overview

This collection is a work in progress. The paper cites a fixed evaluation;
historical runs and subsequent improvements are tracked separately.

| Evaluation | Runtime status | Completed programs | Details |
| --- | --- | ---: | --- |
| Paper snapshot | 1.0.7 development; package metadata 1.0.7rc3, final release pending | 8/8 | [Coverage and results](#paper-evaluation-snapshot) |
| 1.0.6 retrospective run | Released 1.0.6 tested against the same programs | 1/8 | [Historical results](history/1.0.6/README.md) |

[Version history and ongoing work](history/README.md) records what changed,
what remains open, and how to reproduce each evaluation.

## Paper evaluation snapshot

<!-- paper-table:start -->
Evaluated with Culsma 1.0.7.

| Module | Source steps | Coverage |
| --- | ---: | ---: |
| Module 01: Cell transfection | 13/13 | 100% |
| Module 02: Selective plating and colony isolation | 11/12 | 91.7% |
| Module 03: Cell lysate preparation | 10/10 | 100% |
| Module 04: Suspension-cell staining | 29/29 | 100% |
| Module 05: Magnetic-bead immunoprecipitation | 23/23 | 100% |
| Module 06: Western blot | 32/32 | 100% |
| Module 07: Sandwich ELISA | 41/42 | 97.6% |
| Composite 01: Flow-cytometry immunophenotyping | 5/5 | 100% |
<!-- paper-table:end -->

The seven modules cover **159/161** numbered source steps (98.76%). Including
the composite gives **164/166** (98.80%). All eight entry programs complete:
**2406/2406** generated execution steps, with no failed or skipped steps and
no runtime diagnostics. Source steps and execution steps are different
counts; expanded loop iterations do not increase source-step coverage.

The two uncovered steps are Module 02 S5 (spreading inoculum on agar) and
Module 07 S37 (tap-mixing a plate). These remain explicit gaps in this fixed input snapshot. Surface spreading
has since been represented in an updated Module 02 program; see the
[development status](history/README.md#work-toward-the-next-snapshot). Coverage
measures structural source–program correspondence, not complete semantic
fidelity, biological success, or hardware execution. In particular, a transfer
may match a source step while a finer detail such as dropwise delivery remains
only in its annotation.

## Known gaps and extension targets

The results above describe the fixed evaluated version, not an exhaustive
inventory of laboratory operations. The collection can grow as additional
workflows are added; compare versions using the same source inventory and
coverage rules when assessing improvements in operation support.

| Source step | Gap in the paper snapshot | Development status and next verification |
| --- | --- | --- |
| [Module 02 S5](modules/02-selective-plating-candidate-colony-isolation/source.md) | Evenly spreading each inoculum across agar with a sterile spreading tool is retained as an annotation; the preceding transfer does not represent surface spreading. | `spread` is implemented in the development runtime. The updated Module 02 has checked at 12/12 and runs 71/71; adoption into a new paper snapshot and full-suite regeneration remain pending. |
| [Module 07 S37](modules/07-sandwich-elisa/source.md) | Gentle plate tapping to mix the stopped reaction has no verified action in the evaluated program. | Define plate tap-mixing and its target and requirements, then provide execution support. Verify that it occurs after stopping the reaction and before readout, without substituting a different mixing method. |

Surface spreading is an implemented change awaiting snapshot synchronization;
plate tap-mixing remains an extension target. Language representation and execution
support need to be assessed together. Keep the original numbered source steps
and gap records until support is implemented and checked. A later result should
record the revised program/runtime versions and rerun coverage and execution;
successful software execution alone does not demonstrate physical performance.
The current values (11/12 for Module 02 and 41/42 for Module 07) remain unchanged.

## Directory and execution entry points

| Path | Contents |
| --- | --- |
| [`modules/`](modules/) | Seven modules; each has `source.md` and a `protocol.culs` entry program. |
| [`composites/`](composites/) | One composite, also with `source.md` and a `protocol.culs` entry. |
| [`worked_examples/`](worked_examples/) | Four manuscript examples, independent checker, and recorded results; excluded from coverage totals. |
| [`libraries/`](libraries/) | Import entry for Module 04, reused by the composite. |
| [`reproduce.py`](reproduce.py) | Single script for coverage, execution, comparison, and table generation. |
| [`manifest.json`](manifest.json) | Fixed versions, source hashes, expected counts and known gaps. |
| [`history/`](history/) | Version index, retrospective evaluations, diagnostic records and reproduction script. |
| [`results/`](results/) | One checked set of coverage, execution, and material/observation results. |

Module 04 also contains its reusable `module.culs`. Its `protocol.culs` runs
that module independently. The composite imports the same definition through
`libraries/Module04.culs`; it does not copy the staining procedure.
Each `source.md` retains the procedure's source references and context.

## Reproduce

With Git and Python 3.12 installed, run from a new working directory:

```sh
git clone --branch codex/benchmark-publication https://github.com/culsma/culsma.git culsma-benchmark
git clone https://github.com/culsma/culsma.git culsma-runtime
git -C culsma-runtime checkout 42b562bce488d25bdc00af82c62fdb5d4cc52b8b
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

The input snapshot is `e65e56cfe4de10b21d890fe2724210dfde1c9c84`; the runtime
is `42b562bce488d25bdc00af82c62fdb5d4cc52b8b`. The paper's benchmark version is
**1.0.7**; package metadata at the pinned runtime is **1.0.7rc3**. The manifest
and generated summary retain that distinction. The preparation environment is
Python 3.12.8 with Lark 1.3.1.

A zero exit status requires the pinned runtime and input hashes, matching
coverage counts and gap records, and successful completion of all eight
programs with the expected execution counts and zero failures, skips, or
runtime diagnostics. Reproducing the two known gaps is a successful comparison.
The checker and its counting rule are included in the single script.

Each output directory contains `summary.json`, `table.md`, and per-artifact
`coverage.json`, `run.json`, and `results.json`. Nonempty console/error logs
are retained when present. Report and compact-result exports use separate
deterministic CLI invocations. Input, script, environment, and output identities
are recorded. The automatic comparison checks coverage and execution counts;
material and observation records are preserved for inspection, not treated as
independent experimental validation. No second copy of coverage is stored in
the source directories.

## Maintain the benchmark and paper together

1. Revise source procedures and programs together. Keep complete source-step
   annotations and source references; retain gaps explicitly.
2. Review the expected counts, gap records, input hashes, and runtime identity
   in `manifest.json`. Update them only for an intended, reviewed change;
   do not replace expectations merely to make a failing comparison pass.
3. Run `reproduce.py` into a new directory. Add `--update-readme` to regenerate
   the marked three-column table above after all comparisons pass. The same
   table is written to `table.md`, using the paper's module names and rounding,
   with one version label for the entire run.
4. Review the resulting records. When advancing to a new runtime version,
   rerun the full collection and archive the previous complete `results/` set
   under `archive/benchmark-results/<version>-<commit>/` before replacing it.
   Update the aggregate figures above and the paper's table and Methods
   if the evidence changes. Commit inputs, manifest, README, and results
   together, and cite the new package commit in the paper.

Historical Cases 00–14 and their original tools are preserved outside this
active directory in [`archive/benchmarks-legacy/`](../archive/benchmarks-legacy/).
They are excluded from this runner and the paper's current coverage totals.
The four manuscript illustrations and their independent reproduction script are
provided in [`worked_examples/`](worked_examples/). They are evaluated separately
and do not contribute to the coverage totals above.
