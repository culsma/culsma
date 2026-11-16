# GFP fraction-to-observation comparison

Updated 14 November 2026. Responds to Reviewer 2, request 4: put two fractions
in separate wells, associate observations with their fractions, and identify
additional code or conventions. This is one task, not an independent score
for every M/L criterion. Culsma and extended LabOP use the retained executions;
BPL was newly run on the same material requirements, with an explicitly
incomplete diagnostic projection after a documented-syntax failure.

## Reporting decision: released results first, extensions separately

Both LabOP routes are reported. The released run is primary for M3; the
extension is evidence for L4 and for the extra code requested by Reviewer 2.
The No for released integrated material semantics and the Yes for extension
integration remain unchanged. Neither means that all LabOP programs fail.

The [released program](gfp_labop.py) and [results](results/gfp-labop-native/results.json)
show that the prefix and the location-based continuation validate and execute.
The continuation produces three 20-uL wells and observation coordinates. A2's
material ledger contains only buffer, but its provenance graph still has a
path through the original tube's history to the lysate. It therefore lacks a
computed pellet and cellular quantity, not all provenance. Missing `Spin`
output queries are recorded as authoring-time failures separately from runs.

The table below reports the explicitly labelled extended LabOP route; it
must be read alongside these primary released results. The extended volume
and fraction-ancestry checks pass, but cellular accounting remains absent.
The [second-opinion record](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/labop_gfp_extension_second_opinion.zh.md)
retains the discussion and the accepted reporting decision.

## Task and support routes

The common requirements are 160 uL of GFP lysate, a stipulated partition into
liquid supernatant and a zero-liquid pellet, 20 uL supernatant in assay A1,
40 uL buffer to resuspend the pellet and 20 uL of suspension in A2, and 20 uL
buffer in A3. Buffer starts at 100 uL. Observation records should identify the
fractions and original sources; no system is required to invent fluorescence
measurements. Cell accounting additionally uses the declared 100000 cellular
units and complete partition assumptions, not measured biological recovery.

- **Culsma 1.0.7:** [program](gfp.culs), [run](results/culsma/run.json),
  [shared volume/ancestry results](results/comparison.json),
  [material-ledger interpretation](material-evolution-evidence.md).
  Uses the released separation and material implementation.
- **LabOP 1.0a2, released library:** the standard `Spin` has no fraction output
  definitions or default material updater; see the retained
  [mechanism audit](material-evolution-evidence.md) and the newly executed
  [released-only checks](results/gfp-labop-native/results.json).
- **LabOP, extended:** [extended program](gfp_labop_extended.py), [added primitive and updater](fractionation.py),
  [shared volume/ancestry results](results/comparison.json). `ClarifyLysate`
  supplies two outputs, `compute_output` returns their collection tokens, and
  `FractionationUpdater` creates fraction-to-parent edges. Standard transfer
  arithmetic and measurement records then support the retained case. The
  evaluation checker joins the final well states to the observation coordinates.
- **BPL `4e505740`:** [documented source](cases/gfp/gfp_documented.bpl),
  [diagnostic projection](cases/gfp/gfp.bpl), [runner](gfp_bpl.py),
  [results](results/gfp-bpl/results.json). No BPL implementation was patched.
  [Source verification](results/gfp-bpl/source-verification.json) confirms all
  99 checked implementation files against the retained source archive.

## Before/after separation states used in the main-text table

The main-text separation table stops **before any transfer or resuspension**.
Its right column uses common schematic notation for the before/after material
states, not native serialization or a verbatim program return value. It does
not use the final A2 aliquot. `liquid` and `cells` abbreviate the corresponding
component quantities (BPL cells are input metadata); the fraction nesting
represents computed partitions, not just the existence of two components.

- **Culsma:** `results/culsma/run.json`, event `seq=20`, records the input
  container with 160 uL liquid and 100000 cells, in a suspension relation and
  without a partitioned contents state. After separation, event `seq=22`,
  `payload.material_state_snapshot.contents_states` for the container resolved
  by `bindings.lysate`. The state is `partitioned`. Part `0` has
  `LYSATE_LIQUID = 160 uL` and `GFP_CELL_DEBRIS = 0 cells`; part `1` has
  `LYSATE_LIQUID = 0 uL` and `GFP_CELL_DEBRIS = 100000 cells`, from each part's
  `component_quantities`. These are the program's `lysate.contents[0]` and
  `lysate.contents[1]`, under the declared complete-partition rules.
- **LabOP:** `results/gfp-labop-native/spin_prefix/sample_graph.json`, latest
  recorded tick `1`, container `lysate_tube`, location `A1`: the sole reagent
  `lysate_liquid` has contents `160.0` uL. The only graph edge is Provision;
  Spin adds no material update. The adjacent `results.json` confirms that
  Spin executed and the prefix completed normally. This Provision state remains
  the latest material state both before and after Spin. The table shortens the
  reagent URI and omits array axes, rather than inventing a fraction record.
- **BPL:** `results/gfp-bpl/gfp-default-states.json`, stage `step_0001`,
  `contents["sources:A1"]`, is identical to its initial state. The table
  uses `liquid` for its liquid component volume and `cells` for `properties.declared_cells`;
  the latter is input metadata, not computed cellular partitioning.
  `gfp-default-trace.json` records `unsupported_no_op` for this step and equal
  before/after state hashes. `lysate` is a display label for `sources:A1`;
  the source statement retains the actual address.

## Observed comparison

| Requirement in this task | Culsma, released | LabOP, with explicit extension | BPL, evaluated source/plan/simulator route |
| --- | --- | --- | --- |
| Separately identified fractions with a defined relation to the lysate | Yes: released `sep` outputs | Yes: added `ClarifyLysate` outputs and updater; unavailable from standard `Spin` alone | No on this route: the operator's supernatant selection is only a source comment/convention; `centrifuge` becomes an unsupported simulation step |
| Expected liquid volumes | Yes: A1/A2/A3 = 20/20/20 uL; remaining = 140/20/40 uL | Yes: same results | Yes in the reduced optical-syntax projection: same six volumes, despite skipped operations |
| Declared cellular quantity propagated through pellet resuspension and aliquoting | Yes under the partition assumption: 50000 cellular units in A2 and 50000 in the remaining suspension | No: the added volume/ancestry updater does not implement solid-component counts | No on this route: seeded components are not carried to destination wells; all three assay component lists are empty |
| Per-well observation records linked to the expected fractions and sources | Yes: three observation references with missing signal values | Yes: three observation coordinates joined to the sample graph, including the independent blank | No on this route: `measure` becomes an unsupported simulation step and creates no per-well observation records |
| Actual fluorescence signal produced | Not part of this software task; values remain missing | Not part of this software task; values remain missing | No observation output on this route; not a claim that real fluorescence should be simulated |

The two LabOP separation gaps (fraction outputs and their material/ancestry
updates) are parts of the same M3 support boundary, not two independent
failures of entity identity. M1 remains supported; LabOP's successful extension
supports L4. The solid-component calculation gap remains after this particular
extension. GFP does not exercise parameterized subprotocol calls, return-to-input
procedure composition, or runtime branches, so it cannot decide L1--L3.
The separate invalid-duration probe informs M2; the valid GFP run is not a
negative dimensional-consistency test. No new L5 or D1 verdict is inferred.

## BPL authoring and execution evidence

1. The documented optical property form from `docs/BPL_Syntax_Reference.md`
   section 5.5, `Fluorescence { excitation: 488 nm, emission: 510 nm }`, fails
   `bplc check` at the opening brace (`SYNTAX_UNEXPECTED_CHARACTER`, exit 10).
   The [exact diagnostic](results/gfp-bpl/gfp_documented-check.stdout.txt) is
   retained. The source expresses all the requested operations but cannot
   enter the evaluated lowering route in that form.
2. The diagnostic projection retains `property: Fluorescence` but omits the
   unsupported wavelength literal. It is **not an exact optical equivalent**.
   It passes `check` and lowers through the public CLI. The runner confirms
   that the primitive fields in the API plan used for simulation match the
   [CLI plan](results/gfp-bpl/gfp-plan.json). Human instructions are also
   [retained](results/gfp-bpl/gfp-human.md).
3. To avoid making up a fraction-output API, the source follows the documented
   centrifuge-then-transfer pattern (syntax reference's protein
   purification example): collect the 160-uL supernatant into a separate source
   location, keep the nominal pellet in the original tube, then resuspend it.
   Source comments explain that selecting supernatant is an operator convention;
   it is not a computed partition. This container choice differs from LabOP's
   pellet-collection tube but preserves the intended material task.
4. Initial stocks are supplied through `Simulator(deck_state=...)` and
   `VirtualContents.add_volume`, with the same declared liquid amounts. The
   zero-volume cellular component carries `declared_cells` only as opaque
   metadata; it is not claimed as an implemented cell-count type. Nothing is
   injected after initialization. Step callbacks only record snapshots.
5. Default simulation finishes with the correct liquid totals and **three
   explicit warnings/no-ops**: centrifugation, mixing, and measurement. Their
   before/after state hashes are unchanged. The full
   [trace](results/gfp-bpl/gfp-default-trace.json) and
   [states](results/gfp-bpl/gfp-default-states.json) show no computed fraction
   state or measurement record. Transfer traces retain physical endpoints, so
   we do not claim there are no references or no location history.
6. Strict simulation rejects `human_step` before executing the plan. The
   [transfer-only control](cases/gfp/gfp_transfers_only.bpl) completes without
   unsupported steps and produces the same liquid totals. This confirms that
   the numerical success comes from transfer arithmetic, not from executing
   the omitted experimental operations.

The inspected mechanism explains these observations: `orchestrator.py`
`_emit_call_statement` specializes transfer/wait and falls back to `HumanStep`
for these centrifuge/mix/measure calls. `Simulator._execute_primitive` reports
unsupported no-ops; `_exec_aspirate` passes volume to the pipette and
`_exec_dispense` adds volume without a component payload. Separate `Centrifuge`
and `ReadFluorescence` IR classes exist; this finding concerns the documented
source-to-plan/simulator route, not the absence of those classes or the ability
of a person to carry out generated instructions.

## Reproduction

From the manuscript root, with the existing pinned BPL environment:

```sh
benchmarks/local-results/comparison-runtime/bpl-env/bin/python benchmarks/comparison/gfp_bpl.py
```

Use `--output PATH` to retain a new run separately. The existing
`reproduce_comparison.py --system bpl` command also includes this witness.
Outputs include exact CLI commands and diagnostics, plans, generated human
instructions, initial/final state snapshots, and default/strict traces.
The Culsma and released-only LabOP runs use the system-selecting runner.
The historical extended LabOP run uses `gfp_labop_extended.py OUTPUT`; the
new native witness does not overwrite its results.
