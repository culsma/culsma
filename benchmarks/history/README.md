# Benchmark version history

The benchmark is maintained as a work in progress. Each recorded evaluation
pairs specific input programs with a specific runtime, preserving its results
as the implementation and collection evolve.

| Runtime | Status of evaluation | Input snapshot | Completed programs | Record |
| --- | --- | --- | ---: | --- |
| 1.0.6 (`0a5393c`) | Retrospective run on 21 September 2026 against the released version | `ba46a8d` | 1/8 | [Results and compatibility boundaries](1.0.6/README.md) |
| 1.0.7 development (`42b562b`, metadata `1.0.7rc3`) | Fixed paper evaluation; final 1.0.7 release pending | `ba46a8d` | 8/8 | [Paper snapshot](../README.md#paper-evaluation-snapshot) |

Both rows use the same eight programs and the same structural correspondence
rule: **164/166 source steps**. Execution compatibility differs. The historical
run is not an original release-time measurement and does not measure all
procedures that could have been written for the older release.

## Work toward the next snapshot

- Surface spreading has an implemented `spread` constraint in the 1.0.7
  development runtime. The updated Module 02 program has been checked at
  12/12 source steps and 71/71 execution steps; the fixed paper snapshot still
  contains the earlier program. Incorporating this change requires a new input
  snapshot, a complete benchmark run and synchronized manuscript results.
- Plate tap-mixing in Module 07 remains an explicit gap.
- Final 1.0.7 release identity and the next benchmark snapshot remain to be
  aligned; neither is presented here as already released.

## Add a historical evaluation

Create `history/<version>/manifest.json` with the exact runtime commit, input
package commit, dependency version and evaluation date. Use the shared
[history runner](reproduce.py), preserve its outputs under that record, and
explain the observed failures alongside the generated table. Program failures
are evidence; infrastructure or identity errors must be resolved before
publishing a completed evaluation.

Use the same input snapshot and counting rule for direct comparisons. If a
program needs rewriting, record it as a separate adapted evaluation with its
own input hashes. Keep retrospective runs distinguishable from results
recorded when a version was released. Existing records and paper citations
remain available through their immutable Git commits.
