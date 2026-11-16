# Culsma, LabOP and BPL comparison

Current three-system discussion: [document index](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/README.md)
and [working table](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/comparison_table_working.md).
This directory collects Culsma, LabOP and BPL programs, mechanism audits,
reproduction commands and recorded results. It was migrated from the manuscript repository on 16 November 2026.
`migration_manifest.json` records its origin commit and the hashes of frozen
inputs, results, sources and backups. Previously recorded logs,
RDF and JSON are retained unchanged, including historical absolute paths.
Pinned upstream source archives are retained in `sources/`; installed runtimes
remain in `benchmarks/local-results/comparison-runtime/`.
The comparisons are separate from the workflow source-step coverage totals.
The supplementary PDF and criterion definitions remain in the manuscript repository.

Installed environments and generated replay outputs are ignored by Git.
To reuse an already prepared runtime, set `COMPARISON_RUNTIME_DIR` to its
absolute directory; every active replay helper uses this same setting. Otherwise
`setup_replay.py` creates the default runtime location shown above. Virtual
environments are not copied or moved, because their installed launchers contain
absolute paths. Historical records and backups retain the original paths;
commands in this README are the current entry points.

## One-command replay

From the Culsma repository root, using Python 3.9 or newer as the coordinator:

```bash
python3 benchmarks/comparison/reproduce_comparison.py --system bpl
python3 benchmarks/comparison/reproduce_comparison.py --system labop
python3 benchmarks/comparison/reproduce_comparison.py --system culsma
python3 benchmarks/comparison/reproduce_comparison.py --system all
```

System names are case-insensitive. Each run creates a new directory under
`benchmarks/local-results/comparison-replay/` and prints the path to `summary.md`. An optional
`--output PATH` must name a **new** directory. Previously retained results are
never overwritten. Individual-system runs require only that system's runtime.
All execution is software execution: no instruments, hardware drivers or LLM
services are contacted. Runtime observation fixtures are identified in the L3 audit.

The current suite covers the retained **M1–M4 and L1–L3** findings, direct-operation
controls, official upstream examples, the GFP tasks (released LabOP mechanisms by default; the historical
extended LabOP execution has a separate entry point), and Culsma magnetic material accounting. Historical
exploratory scripts remain available but are superseded by the canonical paths
in this runner. L4 and unassessed implementation/continuity checks are not
silently counted as No.

The manuscript witnesses are replayed directly:

- Culsma M1 checks the GFP trace's separate `lysate.contents[0/1]` transfers.
- Culsma M3 checks the initial 100000 cellular units, the partitioned pellet,
  and the final two 50000-unit portions, including count units. State checks cover
  the separation update from suspension to pellet, not subsequent resuspension.
- LabOP M1 checks native GFP RDF output references (including forked object flows)
  from `EmptyContainer` and `PlateCoordinates` into transfers, with execution results.
- BPL M4 runs `cases/m4/bpl/m4_let_10.bpl` and `m4_let_20.bpl`, byte-identical
  copies of the witnesses retained in `results/bpl-m4/`, through public CLI
  check, validate and lower commands. It retains complete messages and checks
  exit status 11 and `SEMANTIC_MISSING_VOLUME` for both programs.

The magnetic witness remains an additional M3 check. Old exploratory `wait`
checks may still be collected, but do not determine the current BPL M4 result.

Each directory contains:

- `summary.md` and `summary.json`: scoped judgments, observed values and exact
  predicates; each row links conceptually to its named mechanism audit.
- `commands.json` under each system: commands, working directory, exit status;
  `logs/`: complete stdout/stderr; raw protocol models, plans, traces, quantities
  and generated instructions under the corresponding check directories.
- `source-verification.json`: archive checksums and byte-level comparison of
  installed implementation files with the bundled source (including the upstream
  packaging exclusion for LabOP's `attic`). Dependency versions are recorded by
  `pip freeze`; this is not a wheel-level dependency integrity audit.
- `observer-source/`: the exact comparison scripts, input programs, expected
  observations and interpretation notes, with `observer-sha256.json`.
- `artifacts-sha256.json`: hashes of all resulting evidence files.

**Interpretation:** `replay_expectations.json` freezes the reviewed evidence
predicates, independently of each new execution. The runner reads new raw results
and checks these predicates before reporting the associated Yes/No. A reproduced
No is a successful reproduction of the documented negative witness; it does not
make the command fail. Missing evidence, unexpected observations or infrastructure
failures produce NE and a nonzero exit status, requiring review. A changed result
is never automatically reclassified as lack of capability. These are scoped
mechanism findings supported by executable witnesses, not a universal automated
proof of a language's capabilities. `freeze_replay_expectations.py` is a
maintainer-only generator from reviewed historical records, **never** invoked by
the replay command.

### Preparing a new machine

On a new checkout, use each recorded interpreter to prepare its runtime once.
An existing runtime can instead be selected with `COMPARISON_RUNTIME_DIR`:

```bash
/path/to/python3.12.8 benchmarks/comparison/setup_replay.py --system culsma
/path/to/python3.11.11 benchmarks/comparison/setup_replay.py --system labop
/path/to/python3.13.1 benchmarks/comparison/setup_replay.py --system bpl
```

`setup_replay.py` verifies and extracts the bundled source archive, creates an
isolated environment and installs the recorded dependencies. It refuses to
overwrite existing source/environment directories. Dependencies still require
package-index/network access; this is not an offline wheel bundle. Installation
logs are retained in `benchmarks/local-results/comparison-runtime/`. The source pins, archive origins,
checksums and Python versions are in [sources/manifest.json](sources/manifest.json).
The archives preserve upstream license files. The Culsma archive contains the
pinned `src`, `tests`, project metadata, README and license; LabOP and BPL archives
contain the full upstream snapshots.

## Example catalog

| Topic | Runnable entry or source | Retained evidence |
|---|---|---|
| L1: focused LabOP subprotocol/direct-transfer contrast | [labop_l1_counterexample.py](labop_l1_counterexample.py) | [comparison](results/l1/labop-reproduction/comparison.json) |
| L1: LabOP official API, upstream test and harness | [check_labop_l1_public_api.py](check_labop_l1_public_api.py) | [API audit](results/l1/public-api-audit/results.json) |
| L1: BPL official CLI, defaults, function calls and direct control | [check_bpl_l1.py](check_bpl_l1.py), [BPL cases](cases/l1/bpl/README.md) | [CLI results](results/l1/bpl-cli/results.json), [interpretation](bpl-l1-evidence.md) |
| L1: BPL caller-local containers and parameter-free calls | [Endpoint-binding cases](cases/l1/bpl_endpoint_binding/README.md) | [Follow-up results](results/l1/bpl-endpoint-binding/results.json) |
| L1: three-system initial witness, including Culsma execution | [check_l1.py](check_l1.py), [Culsma source](results/l1/reuse.culs) | [shared results](results/l1/results.json), [mechanisms](l1-mechanism-evidence.md) |
| L2: producer output to consumer input | [Culsma source](cases/l2/composition.culs), [LabOP runner](check_labop_l2.py), [BPL source](cases/l2/bpl/composition.bpl) | [Mechanism audit and retained results](l2-mechanism-evidence.md) |
| L3: repetition and conditional routing | [Culsma runner](check_culsma_l3.py), [LabOP runner](check_labop_l3.py), [BPL loop](cases/l3/bpl/loop_3.bpl) | [Control-flow mechanisms and results](l3-mechanism-evidence.md) |
| Working upstream routes versus L1/L2 failures | [check_upstream_examples.py](check_upstream_examples.py) | [Official examples, test results and limits](upstream-examples-evidence.md) |
| M1 and earlier model representation checks | [check_modeling.py](check_modeling.py) | [modeling evidence](modeling-evidence.md) |
| M2: duration dimensions | [check_duration_units.py](check_duration_units.py) | [results](results/duration-unit-check.json) |
| M3: GFP fraction-to-readout workflow | [gfp.culs](gfp.culs), [native LabOP runner](gfp_labop.py) | [native results](results/gfp-labop-native/results.json), [material mechanisms](material-evolution-evidence.md) |
| GFP: BPL authoring and software route, with three-system interpretation | [BPL sources and control](cases/gfp/), [runner](gfp_bpl.py) | [results](results/gfp-bpl/results.json), [comparison and reproduction](gfp-three-system-evidence.md) |
| M3: magnetic component allocation | [magnetic.culs](magnetic.culs), [check_magnetic.py](check_magnetic.py) | [results and limitations](results/magnetic-comparison.json) |
| M4: scope and binding | [check_scope.py](check_scope.py) | [results](results/scope-mechanisms.json) |
| BPL M1–M4 | [check_bpl_modeling.py](check_bpl_modeling.py) | [audit](bpl-modeling-evidence.md), [results](results/bpl-modeling/results.json) |
| BPL M4: documented local-volume bindings | [10 µL source](results/bpl-m4/m4_let_10.bpl), [20 µL source](results/bpl-m4/m4_let_20.bpl) | [original CLI report](results/bpl-m4/result.json), [provenance](results/bpl-m4/README.md) |
| Positive LabOP validation diagnostics | [check_labop_diagnostics.py](check_labop_diagnostics.py) | [results](results/labop-diagnostics.json) |

No hardware is operated by these checks. The primary GFP LabOP runner uses
released primitives without fraction handlers. The separately retained
[gfp_labop_extended.py](gfp_labop_extended.py) adds fraction handling; the L1 LabOP examples use unmodified binding and
execution mechanisms. These routes must not be conflated. The focused L1
reports take precedence over the initial shared witness when discussing
official-API verification.

## GFP released versus extended LabOP routes

The primary entry point is now `gfp_labop.py`. It records two distinct checks:
`Spin` output lookup/prefix execution and a location-based continuation using
only released operations. Missing fraction outputs are authoring evidence;
normal execution without a material update is recorded as such, not forced
into an execution exception.

```sh
benchmarks/local-results/comparison-runtime/labop-env/bin/python benchmarks/comparison/gfp_labop.py benchmarks/comparison/results/gfp-labop-native
```

The complete previous extended witness and results are preserved in
[the checksummed backup](backups/gfp-labop-extended-2026-11-14/README.md).
Its standalone entry point is `gfp_labop_extended.py`; `fractionation.py`
remains its explicit added implementation. `reproduce.sh` is the historical
extended-pair replay, clearly labelled as such. Default `--system labop`
replays the native witness and does not import the added separation code.
The replay summary reports M3 No for the released GFP material behavior,
with scope explicitly distinguishing successful execution from the missing
separation-material update. L4 Yes rests separately on the extended execution.
The original `results/labop/` and `results/comparison.json` remain historical
**extended** results and have not been replaced by native outputs.

See [the second-opinion brief](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/labop_gfp_extension_second_opinion.zh.md)
for the question of extension legitimacy, evidence, and fair comparison scope.

## Comparison criteria and evidence

The [L1 mechanism audit](l1-mechanism-evidence.md) now records parameter binding,
procedure instantiation and software execution, including the LabOP
model-support/execution distinction and BPL’s unexpanded procedure calls.

The current M4 scope/binding interpretation and probes are recorded in the
[scope mechanism audit](scope-mechanism-evidence.md). The earlier temporal and
handling-constraint examples below remain historical evidence, not the current
M4 criterion. The [BPL M1–M4 audit](bpl-modeling-evidence.md) supplies pinned
source analysis and executable witnesses for the current discussion table.

The [M1–M4 modeling examples](modeling-evidence.md) now include executed
construction, validation and RDF roundtrip checks for LabOP containers, product
references, quantities, SBOL complex descriptions and scoped duration constraints.
These are model checks, not laboratory-protocol execution results.
The [remaining table examples](table-example-evidence.md) identify inspected
language mechanisms, generator interfaces, and retained implementation
results, with outstanding checks stated separately.

The current manuscript reports eight criteria: M1–M4 and L1–L4, with scoped
Yes/No judgments. The unified runner checks the retained M1–M4/L1–L3 witnesses
and two additional GFP records (23 rows across three systems); L4 extension
mechanisms are documented separately. The older task registry, engineering
checks and F/A/B/C mappings below are historical records, not additional
criteria in the current table. NE in replay output flags evidence requiring
review rather than assigning a new capability judgment.

[The source evidence index](framework-evidence.md) retains pinned source
locations, conceptual origins, and the earlier F/A/B/C mappings for history.
The current comparison distinguishes matched GFP executions, Culsma magnetic
execution with a LabOP source audit, Culsma PCR variants, and a pinned BPL
mechanism audit. [M1 definitions and mechanism evidence](m1-mechanism-evidence.md)
and [M2 quantities and units](m2-mechanism-evidence.md) record the agreed scoped
three-system results; BPL M1–M4 and L1–L3 now have scoped findings, while
unassessed checks remain pending. The
[duration-unit validation probe](check_duration_units.py) and its
[report](results/duration-unit-check.json) distinguish M2 representation from
parameter checking in the historical numbering. The [positive LabOP diagnostic probes](diagnostic-evidence.md)
also show detected missing-unit and invalid-control-flow faults, with model-URI
diagnostics; they do not establish BPL or Culsma results for those fault families.
[Architecture discussion notes](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/comparison_language_architecture_notes.zh.md)
retain the rationale and planned manuscript explanation order. The earlier LabOP overdraw pilot is a different workflow, not a matched
fault-detection comparison. Magnetic aggregate failures remain visible below
and in the active I2 decision record.

## Reuse of experimental operations: magnetic-bead capture

[magnetic.culs](magnetic.culs) is the unchanged complete magnetic-bead example
from the manuscript, including its stated post-binding input and complete
retention assumptions. It uses the same `sep` operation as centrifugation,
configured with a magnetic program, component allocations and a relationship
transition. No new Culsma operation or runtime implementation was added.

[check_magnetic.py](check_magnetic.py) verifies the executed dimensioned
component ledger: bound contains 10 mg beads and 0.001 mg target protein,
flowthrough contains 100 µL buffer, and the target's `bead_bound` relationship
identifies the bead component. Both returned container IDs resolve to these
states. The [checked results and LabOP inventory](results/magnetic-comparison.json)
include all 52 bundled LabOP primitive declarations with their parameters,
descriptions and default output/provenance handler registrations. `Spin` and
`Filter` expose no fraction outputs; this pinned library contains no magnetic
separation primitive. Its default provenance handlers do not supply this
example's component allocation and bead-association calculation. This is an
execution check on Culsma and a source audit on LabOP, not a matched magnetic
execution. No extended LabOP magnetic implementation was run.

This distinction concerns reusable **experimental operation contracts**.
LabOP's UML activity model also remains stable when library primitives are
added, as explained in §5.3 of the [original paper](https://doi.org/10.1145/3604568).
A reusable separation primitive, data convention and execution implementation
could be added to LabOP. The audit does not show that each new technique must
have its own primitive, or that LabOP cannot represent this example. Culsma
also requires method-specific configuration and scientific-model support;
these examples demonstrate reuse within the evaluated cases, not universal
closure of the operation set.

**Numerical scope.** The pinned Culsma runtime's dimensioned component entries
pass these checks. Its aggregate fields also report 10.001 µL for the bound
fraction and 100 mg for flowthrough via cross-dimension projections. These
values are not validated physical quantities and must not be used to claim
correct bulk-volume or density calculation. They remain visible in the
[raw execution](results/magnetic-culsma/run.json),
[returned output](results/magnetic-culsma/output.json) and check result.
This example ends at the returned fractions; downstream transfer and observation
linkage is evaluated separately in the GFP workflow below.

## Matched fraction-to-readout executions

This software benchmark accompanies Results §3.7 and the corresponding
Discussion. It applies the same stipulated partition and liquid volumes in
both implementations. The starting lysate has 160 µL of liquid and 100,000
suspended cellular units. Centrifugation at 12,000 × g and 22 °C for 10 min
assigns all the liquid to the supernatant and all the cellular material to
the pellet. The pellet contributes zero liquid volume. Transfer 20 µL of
supernatant to A1, resuspend the collected pellet in 40 µL of the common
100 µL assay-buffer stock with one 32 µL pipette mix, and transfer 20 µL of
suspension to A2. Transfer 20 µL of buffer to A3 for the blank.

The common outcomes in [expected.json](expected.json) are 20 µL in each well,
the ancestry shown below, and final source volumes of 140 µL supernatant,
20 µL pellet suspension and 40 µL assay buffer. Both software paths leave the
signals empty. The LabOP call supplies nominal excitation, emission and
bandpass metadata for its measurement primitive. Optical settings, physical
mixing, biological yield and instrument performance are outside the comparison.

| Observation | Fraction and original material verified in both runs |
| --- | --- |
| A1 | Supernatant from the original GFP lysate |
| A2 | Pellet from the same GFP lysate, plus assay buffer |
| A3 | Assay buffer only |

## Implementations and joins

- [gfp.culs](gfp.culs) uses the built-in centrifugation rule to partition
  liquid and cellular contents. The run records the separation source, slots
  and partition rule. The transfer records carry the source slot or container
  and destination. The returned observation IDs resolve to per-well records
  whose subject IDs join to those transfers.
- [gfp_labop_extended.py](gfp_labop_extended.py), the historical extended route, uses standard sample arrays, provisioning,
  well selection, transfers, pipette mixing and fluorescence data collection.
  The evaluated library's [Spin definition](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop/lib/plate_handling.py)
  takes a location, duration and acceleration. It exposes no fraction outputs.
  [fractionation.py](fractionation.py) defines a primitive with two output
  pins and binds them to the appropriate collections. Its graph updater runs
  through the existing [provenance observer](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop/execution/behavior_dynamics.py).
  It versions the source state as supernatant, creates a pellet state in
  the collection tube and connects both states to the pre-separation sample.
  Standard transfer updates then propagate those connections. The pellet is
  represented by a sample-state ID with zero initial liquid volume. The
  LabOP graph tracks liquid volume and pellet ancestry. The cellular count
  is declared as input metadata and is quantified only by Culsma.
- [check.py](check.py) starts from the returned observations. For LabOP it
  joins dataset coordinates to the latest well state, because the
  fluorescence operation follows all material changes and is the last
  operation in this workflow. It traverses the sample graph back to the
  provisioned sample states. For Culsma it traverses transfer and separation
  events by container and slot ID. Both use the same expected well volumes,
  source volumes, lineage and missing-signal checks. The comparison
  evaluates the named workflows and software versions.

## Reproduce

The recorded runs used Culsma 1.0.7
(`5364676bc2437b4981a00ce0133c730af243e469`, Python 3.12.8, Lark 1.3.1)
and LabOP 1.0a2
(`2e2bd88150c71a440771fd369f40295dfd622324`, Python 3.11.11).
Use Git repositories containing those commits and the two Python executables.
The runner reads each commit with `git archive` and uses clean environments
under `benchmarks/local-results/comparison-runtime/`. If that directory
already exists, move it before rerunning. Dependencies require package and
archive access on initial setup. The lock records each runtime package
version and uses commit URLs plus archive SHA-256 digests for the two
GitHub-hosted transitive dependencies. The LabOP runner saves DOT source
without calling an external renderer.

```sh
bash benchmarks/comparison/reproduce.sh \
  /path/to/Culsma /path/to/labop /path/to/python3.12.8 /path/to/python3.11.11
```

The [common check output](results/comparison.json) contains the actual
observation and input IDs, event numbers or sample-graph edges for each
path, and volume checks. The recorded [environment](results/versions.txt)
includes input SHA-256 digests. The raw [Culsma execution](results/culsma/run.json)
and [program output](results/culsma/output.json) are preserved alongside the
LabOP [protocol](results/labop/protocol.ttl),
[execution](results/labop/execution.ttl), [sample graph](results/labop/sample_graph.json),
and [fluorescence dataset](results/labop/readings.json).
LabOP's [run status](results/labop/run-status.json) records successful
execution, no engine issues and no document-validation warnings or errors.
The [execution log](results/labop/execution-log.txt) separately retains warnings
from the optional backend specialization when it has no handler for a step.
The output directory from the replay also contains Culsma's complete
intermediate artifacts and the LabOP graph snapshots.

The earlier normal, swapped-well and overdraw runs used a handoff-based
LabOP program. They remain in the [revision pilot](https://github.com/culsma/paper-patterns/blob/58a9031/revision/2026-11-09/labop-comparison/README.md).
The manuscript uses the native LabOP route for material findings; the extended
implementation above is retained separately as extension evidence under L4.

## Engineering comparison (I1–I4)

[Engineering audit](engineering-evidence.md) records Testing, Implementation structure, Documentation, and Ongoing maintenance for the pinned systems. [Sample upstream-test runner](check_engineering_tests.py) and [retained records](results/engineering) support the current working table. These engineering criteria do not reuse the former execution-oriented I numbering.
