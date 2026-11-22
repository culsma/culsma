# Culsma workflow benchmark

Source procedures, Culsma programs and recorded source-step coverage across versions.

| Workflow | 1.0.7 | 1.0.9 | 1.0.11 |
| --- | ---: | ---: | ---: |
| [Module 01: Cell transfection](modules/01-cell-transfection/source.md) | 13/13 | 13/13 | 13/13 |
| [Module 02: Selective plating and colony isolation](modules/02-selective-plating-candidate-colony-isolation/source.md) | 12/12 | 12/12 | 12/12 |
| [Module 03: Cell lysate preparation](modules/03-cell-lysate-preparation/source.md) | 10/10 | 10/10 | 10/10 |
| [Module 04: Suspension-cell staining](modules/04-suspension-cell-staining/source.md) | 29/29 | 29/29 | 29/29 |
| [Module 05: Magnetic-bead immunoprecipitation](modules/05-magnetic-bead-immunoprecipitation/source.md) | 23/23 | 23/23 | 23/23 |
| [Module 06: Western blot](modules/06-western-blot/source.md) | 32/32 | 32/32 | 32/32 |
| [Module 07: Sandwich ELISA](modules/07-sandwich-elisa/source.md) | 41/42 | 42/42 | 42/42 |
| [Composite 01: Flow-cytometry immunophenotyping](composites/01-flow-cytometry-immunophenotyping/source.md) | 5/5 | 5/5 | 5/5 |
| [Composite 02: Magnetic-bead IP with Western blot](composites/02-magnetic-bead-ip-western-blot/source.md) | 7/7 | 7/7 | 7/7 |
| [Module 08: Qubit 1X dsDNA HS quantification](modules/08-qubit-dsdna-hs/source.md) | — | 13/13 | 13/13 |
| [Module 09: Double-sided SPRI selection](modules/09-double-sided-spri/source.md) | — | 21/21 | 21/21 |
| [Composite 03: Qubit quantification and double-sided SPRI selection](composites/03-qubit-double-sided-spri/source.md) | — | 3/3 | 3/3 |
| [Module 11: PBMC stimulation, staining and flow acquisition](modules/11-pbmc-hia-staining-flow/source.md) | 21/21 | 21/21 | 21/21 |

Coverage is matched / total numbered source steps. **—** means not evaluated in that
version. Composite rows count their own steps, not the steps of reused modules.
Coverage measures source–program correspondence, not experimental success.
The shared counting script does not count steps marked `COVERAGE GAP` as
matched. Module 01 declares `with constraint(dropwise)` on S10 and S11,
using support already present in Culsma 1.0.7. Programs are maintained only in
`modules/` and `composites/`; version-specific results live in `evaluations/`.
The 1.0.7 record uses the program revision identified in its manifest, which
predates Module 07's plate-tapping implementation. Git retains those inputs;
there are no maintained version-specific program copies.

The [concentration accounting case](concentration/README.md) separately checks
optional concentration initialization, mixing, splitting, dilution and exact
per-solute accounting in the local implementation. It is not included in these
historical workflow coverage totals.

The [whole-blood LPS stimulation and RBC lysis example](automation/README.md)
demonstrates continuous execution with the Opentrons simulator driver and checks
how the driver handles unmet device requirements.

The original seven modules and two composites cover **172/173** steps in 1.0.7
and **173/173** in 1.0.9. The three added entries cover **37/37** in 1.0.9 and
are recorded separately.

Module 11 reports the procedure supplied by a neighboring laboratory.
Its [1.0.7 coverage](evaluations/1.0.7/modules/11-pbmc-hia-staining-flow/coverage.json)
is reported separately from the original 172/173. The [numbered source procedure](modules/11-pbmc-hia-staining-flow/source.md)
and [evaluated program](modules/11-pbmc-hia-staining-flow/protocol.culs) are retained together.

## Cross-system comparison

The [Culsma, LabOP and BPL comparison](comparison/README.md) contains the
input programs and results organized by M1–M4 and L1–L4, with one folder per
language inside each case. Follow that README to prepare the pinned environments,
then run `python3 benchmarks/comparison/evaluate.py` to reproduce the comparison. Criterion explanations are in the manuscript supplement;
these results do not contribute to workflow source-step coverage totals.

## Evaluate

Use Python 3.12 with Lark 1.3.1. From the repository root:

```sh
python benchmarks/evaluate.py --version 1.0.7 --replace
python benchmarks/evaluate.py --version 1.0.9 --replace
python benchmarks/evaluate.py --version 1.0.11 --replace
```

Each command replaces that version's results in `evaluations/<version>/`.
To check without replacing published records, use `--output` with a new
results directory instead of `--replace`.

The runner verifies the manifest's input hashes and reconstructs the pinned
runtime directly from this repository's Git objects. Its disposable caches
stay in ignored `local-results/`; they are not maintained program variants.
For 1.0.7 it also recovers the recorded benchmark input revision from Git.
The 1.0.9 and 1.0.11 evaluations use the current shared modules and composites,
including the corrected dropwise transfers and the explicit plate-tapping step.
The 1.0.11 evaluation is prepared for the 1.0.11 release. Its manifest records
the exact runtime commit used for the retained run. Before publication, update
the 1.0.11 manifest to the final release implementation and verified input hashes,
then rerun the evaluation. The `--version` option selects an evaluation manifest;
it does not automatically select a newer runtime.

Each evaluation records input hashes, runtime commit, actual package version,
counting rule, diagnostics, material results, and execution-event replay checks.
Source-step correspondence and successful software execution are separate
results. Unsupported programs are recorded as failures, not rewritten for a
runtime. Original, added, and externally supplied workflows have separate totals.

## Records

- **1.0.7:** [manifest](evaluations/1.0.7/manifest.json), [results](evaluations/1.0.7/summary.json).
- **1.0.9:** [manifest](evaluations/1.0.9/manifest.json), [results](evaluations/1.0.9/summary.json).
- **1.0.11:** [manifest](evaluations/1.0.11/manifest.json), [results](evaluations/1.0.11/summary.json).

The original collection covers 172/173 steps in the 1.0.7 evaluation and
173/173 in the 1.0.9 and 1.0.11 evaluations. The Qubit/SPRI additions cover
37/37 in each later evaluation. Module 11 covers 21/21 separately in all three.
The same v2 counting rule is used throughout. These records do not establish
experimental success, numerical fidelity, or equivalence of every computed
result across versions.

The worked examples in `modules/example-*` have separate material-state checks
and do not enter the coverage totals. Their checking commands remain
`check_manuscript_examples.py` and `check_introduction_example.py`.
