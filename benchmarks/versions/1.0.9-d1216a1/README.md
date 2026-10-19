# Benchmark 1.0.9

Release evaluation dated 2026-10-19 for Culsma 1.0.9, implementation
`d1216a16f7adaa41ac0aac763a60c84bb7be3f64`. Python 3.12.8 and Lark 1.3.1.

This snapshot retains the same seven modules, two composites, 173 source steps
and counting rule as the [1.0.7 paper snapshot](../../README.md#paper-results-107-section-35).
Module 07 S37 uses whole-plate TAP with GENTLE. Its program inputs are identical
to the [development evaluation](../1.0.9-dev-ca7a098/README.md); this run verifies
the versioned 1.0.9 package metadata and implementation together.

## Recorded result

<!-- benchmark-table:start -->
Evaluated with Culsma 1.0.9.

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

All seven modules cover 161/161 source steps; the two composites bring the total
to **173/173 (100%)**. The nine entry programs complete **2700/2700** execution
steps, with zero failed or skipped steps and zero runtime diagnostics.
Module 07 covers **42/42**, including TAP between stop solution and readout.

Execution counts differ from 1.0.7 by two carrier assignments, 22 MutationGroup
control nodes, and one TAP action; these do not increase the source inventory.
Coverage measures source–program correspondence and software execution, not
biological outcomes or physical execution.

[Manifest](manifest.json) retains runtime/dependency versions, all 22 input hashes,
expected counts and the procedural baseline. [Summary](summary.json),
[table](table.md) and each entry's `results/` retain the recorded outputs and
comparison evidence. Earlier version records remain unchanged.

## Reproduce

From the repository root with Python 3.12.8 and Lark 1.3.1:

```sh
git clone . /tmp/culsma-benchmark-runtime-1.0.9
git -C /tmp/culsma-benchmark-runtime-1.0.9 checkout --detach d1216a16f7adaa41ac0aac763a60c84bb7be3f64
python benchmarks/reproduce.py \
  --manifest benchmarks/versions/1.0.9-d1216a1/manifest.json \
  --runtime-repo /tmp/culsma-benchmark-runtime-1.0.9 \
  --output benchmarks/local-results/1.0.9-reproduction
```

Use a fresh checkout and output directory. The runner verifies the exact runtime
commit, clean source, dependency versions, input hashes and expected results.
