# Patterns workflow benchmark

This directory is the canonical public benchmark for Section 3.5 of
*Culsma: An Executable Specification Language for Laboratory Protocols*.
GitHub holds the source procedures, Culsma programs, coverage rules, and
reproduction instructions together. Documentation sites may link here; they
are not a second version of the benchmark.

## Collection and paper results

| Module | Coverage | Version |
| --- | ---: | --- |
| [01: Cell transfection](modules/01-cell-transfection/) | 100% | 1.0.7 |
| [02: Selective plating and colony isolation](modules/02-selective-plating-candidate-colony-isolation/) | 91.7% | 1.0.7 |
| [03: Cell lysate preparation](modules/03-cell-lysate-preparation/) | 100% | 1.0.7 |
| [04: Suspension-cell staining](modules/04-suspension-cell-staining/) | 100% | 1.0.7 |
| [05: Magnetic-bead immunoprecipitation](modules/05-magnetic-bead-immunoprecipitation/) | 100% | 1.0.7 |
| [06: Western blot](modules/06-western-blot/) | 100% | 1.0.7 |
| [07: Sandwich ELISA](modules/07-sandwich-elisa/) | 97.6% | 1.0.7 |
| [Composite 01: Flow-cytometry immunophenotyping](composites/01-flow-cytometry-immunophenotyping/) | 100% | 1.0.7 |

The seven modules cover 159/161 numbered source steps (98.76%). Including the
five-step composite gives 164/166 (98.80%). The composite imports Module 04
through `libraries/Module04.culs`; its five steps describe the composition,
not another count of the module's source instructions.

All eight entry programs complete under deterministic software execution:
2,406/2,406 generated steps, with no failed or skipped steps and no runtime
diagnostics. Generated execution steps and numbered source steps are different
denominators; execution counts are not the coverage metric.

The two unmatched source steps are Module 02 S5 (spreading an inoculum on agar)
and Module 07 S37 (tap-mixing a plate). They remain visible in the source and
annotations. Reproducing these two gaps is a successful comparison with the
paper; the runner does not require every artifact to have 100% coverage.

## Files and interpretation

Each linked directory contains `source.md`, a `protocol.culs` entry program,
and `coverage.json`. Module 04 also contains its reusable `module.culs`.
Source descriptions retain their references and contextual notes. The checker
matches complete numbered source instructions to unique annotations with an
associated statement across the artifact's program files. A reference-only
placeholder does not count.

Coverage measures structural correspondence, not full semantic fidelity,
biological success, or physical execution. For example, a transfer can represent
the main action while a finer instruction such as dropwise delivery remains
only in an annotation. Calculated material states follow the declared inputs
and material rules; readout records do not establish measured signals.

## Fixed versions

[`patterns-manifest.json`](patterns-manifest.json) records the paper inputs,
expected coverage and execution counts, and SHA-256 hashes for source files,
programs, the shared library, and the checker.

- Benchmark input snapshot: `e65e56cfe4de10b21d890fe2724210dfde1c9c84`.
- Runtime implementation: `42b562bce488d25bdc00af82c62fdb5d4cc52b8b`.
- Paper table version: `1.0.7` (release family).
- Actual package metadata at the runtime commit: `1.0.7rc3`.
- Dependency: Lark `1.3.1`; Python 3.12 was used for the preparation check.

The older artifact-local `coverage.json` files retain the original manually
supplied `1.0.7rc2` label. The implementation hash is unchanged. Fresh outputs
record the actual runtime version, `1.0.7rc3`; the table retains `1.0.7`.
Use the commit below, not a similarly named installed package, to reproduce
this snapshot. The benchmark source and runtime are pinned separately.

## Reproduce from GitHub

Run from a new working directory with Git and Python 3.12 installed:

```sh
git clone --branch codex/benchmark-publication https://github.com/culsma/culsma.git culsma-benchmark
git clone https://github.com/culsma/culsma.git culsma-runtime
git -C culsma-runtime checkout 42b562bce488d25bdc00af82c62fdb5d4cc52b8b
python3.12 -m venv .venv
.venv/bin/python -m pip install lark==1.3.1
.venv/bin/python culsma-benchmark/benchmarks/reproduce_modular.py \
  --runtime-repo culsma-runtime --output results/patterns-run-01
```

On Windows use `.venv/Scripts/python.exe`. No private wheel or document-site
export is required. The runner imports Culsma directly from the pinned runtime
checkout, verifies its identity and dependencies, checks every benchmark input
hash, and uses the same interpreter for all runs. Existing output directories
are rejected; use a new path for each run.

The command returns zero only when all eight coverage records (including the
two expected gaps) and execution counts match the paper and every run has zero
failed steps, skipped steps, and diagnostics. Input changes, version mismatches,
or result mismatches give a nonzero exit status. Runtime validation failures
are retained in the run outputs.

Outputs include:

- `table.md`: the three-column table used in Section 3.5.
- `summary.json`: aggregate coverage, per-artifact comparisons, versions,
  manifest/runner/input hashes, and hashes of generated output files.
- `<modules-or-composites>/<name>/coverage.json`: freshly computed coverage.
- `run.json`: execution report with completion and diagnostic counts.
- `results.json`: material, resource, and return records from the compact CLI.
- Captured console output and error logs.

The execution report and compact results are exported in two deterministic
invocations because the CLI exposes them as separate output modes. The runner
compares structural coverage and execution status/counts; it preserves material
and observation results for inspection without treating them as independent
experimental validation.

[`evidence/patterns/summary.json`](evidence/patterns/summary.json) and
[`evidence/patterns/table.md`](evidence/patterns/table.md) retain the checked
preparation result. Complete run reports and compact results are alongside them.
Future changes must regenerate and review this evidence, then update the
paper's cited revision deliberately.

## Separate material

The four manuscript illustrations are checked separately and are not included
in this benchmark denominator. `cases/00/` is the separate lysate-clarification
correspondence example. Older `cases/01/`–`cases/14/`, metrics, and baselines
belong to a previous evaluation design, documented in
[README.legacy.md](README.legacy.md); they are not the Section 3.5 benchmark.
