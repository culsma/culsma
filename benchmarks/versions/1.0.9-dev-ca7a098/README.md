# Benchmark 1.0.9-dev

This unreleased development evaluation uses the same seven modules, two
composites, 173 numbered source steps and counting rule as the 1.0.7 paper
snapshot. Only Module 07's program changes: S37 now requests whole-plate TAP
with an independent GENTLE requirement, between stop-solution addition and
readout. The source procedures and all other program inputs are unchanged.

## Recorded result

<!-- benchmark-table:start -->
Evaluated with Culsma 1.0.9-dev.

| Module | Source steps | Coverage |
| --- | ---: | ---: |
| Module 01: Cell transfection | 13/13 | 100% |
| Module 02: Selective plating and colony isolation | 12/12 | 100% |
| Module 03: Cell lysate preparation | 10/10 | 100% |
| Module 04: Suspension-cell staining | 29/29 | 100% |
| Module 05: Magnetic-bead immunoprecipitation | 23/23 | 100% |
| Module 06: Western blot | 32/32 | 100% |
| Module 07: Sandwich ELISA | 42/42 | 100% |
| Composite 01: Flow-cytometry immunophenotyping | 5/5 | 100% |
| Composite 02: Magnetic-bead IP with Western blot | 7/7 | 100% |
<!-- benchmark-table:end -->

The seven modules cover **161/161** source steps; including the two composites,
the total is **173/173 (100%)**. All nine programs complete **2700/2700**
execution steps with no failures, skips or runtime diagnostics. ELISA completes
834/834 execution steps and covers 42/42 source steps.

Compared with 1.0.7, execution adds two plate-identity assignments (Module 01
and Module 07), 22 MutationGroup control nodes (Module 07), and one TAP action.
These explain the increase from 2675 to 2700 execution steps; internal nodes
and expanded iterations do not add numbered source steps. TAP regression tests
also verify action order and 16 independent wells retaining 150 uL each.

## Version and provenance

| Record | Identity |
| --- | --- |
| Evaluation date | 2026-10-19 |
| Benchmark label | 1.0.9-dev, unreleased |
| Runtime commit | `ca7a0984d0b5b0d47a63c39725d8f70529961687` |
| Runtime package metadata | 1.0.8 (not a separate evaluation of the released 1.0.8 implementation) |
| Python / Lark | 3.12.8 / 1.3.1 |
| Procedural source baseline | `f7b744e8efbafd9176a5b4fa07761358a4aee214` |
| Benchmark starting checkout | `ca7a0984d0b5b0d47a63c39725d8f70529961687`; the ELISA TAP adaptation is frozen by the input hashes |

[Manifest](manifest.json) pins the runtime, dependencies, all 22 input hashes
and expected counts. [Summary](summary.json) records the actual run and
output identities; [table](table.md) and the per-artifact `results/` directories
retain coverage and execution records. `matches_manifest` compares this run to
its development expectations; it does not claim to reproduce the paper's
1.0.7 result. The [paper snapshot](../../README.md#paper-results-107-section-35)
retains 172/173 and its original ELISA gap.

## Reproduce

From the repository root, using Python 3.12.8 with Lark 1.3.1, create a separate
runtime checkout containing the local development commit:

```sh
git clone . /tmp/culsma-benchmark-runtime-1.0.9-dev
git -C /tmp/culsma-benchmark-runtime-1.0.9-dev checkout --detach ca7a0984d0b5b0d47a63c39725d8f70529961687
python benchmarks/reproduce.py \
  --manifest benchmarks/versions/1.0.9-dev-ca7a098/manifest.json \
  --runtime-repo /tmp/culsma-benchmark-runtime-1.0.9-dev \
  --output benchmarks/local-results/1.0.9-dev-reproduction
```

Use a fresh runtime checkout and output directory. The version label does not
replace the actual package version or pinned implementation commit. Later
release evaluations get their own records rather than overwriting this run.
Coverage measures structural source–program correspondence and software
execution, not laboratory success or physical homogenization.
