# Material evolution and accounting: revised M3 evidence

12 November 2026. Source inspection and reinspection of retained results; no new execution. Active table: [working comparison](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/comparison_table_working.md).

## Decision and scope

| Evaluated capability | Culsma 1.0.7 | LabOP 1.0a2 |
|---|---|---|
| Released material mechanisms carry the specified clarification/separation-and-transfer path from input components through product states and quantities | Yes, under the stipulated partition rules and for the inspected component ledger | No, standard Spin has no default material-state updater |

Culsma pin: `5364676bc2437b4981a00ce0133c730af243e469`. LabOP pin: `2e2bd88150c71a440771fd369f40295dfd622324`. The subsequent [BPL audit](bpl-modeling-evidence.md) assesses this criterion on its pinned transfer/simulation route.

## Culsma mechanism and retained witness

The pinned `runtime/material/ledger.py` maintains material records; `component_entries.py` stores component references, dimensioned quantities, relations, and their sources. `separation.py` applies resolved component effects to output entries, and `separation_fate.py` defines operation/output and material-fate contracts. `accounting.py` separately records input lots and movements. Their presence is source evidence, not a claim that every path or field has passed a test.

[gfp.culs](gfp.culs) uses released separation and transfer constructs without an author `transition(...)`. In [the retained run](results/culsma/run.json), event 22 records 160 uL of liquid and 100000 cellular units in the modeled pellet. Event 36 records 140 uL in the supernatant and 20 uL in A1; A2 and the remaining resuspension each have 50000 cellular units and 20 uL buffer. These are calculations under the stated complete-partition model, not predictions of measured separation efficiency. The inspected output retains a pellet relation after resuspension; this audit does not certify all subsequent physical-state meanings.

The separate magnetic run's component quantities are dimensioned, but its mixed-dimension aggregate projections have known errors. Those errors remain reported under I2. The scoped M3 Yes does not certify every aggregate or arbitrary transformation.

## LabOP mechanism and gap

In the pinned `labop/execution/behavior_dynamics.py`:

- `SampleProvenanceObserver.handlers` registers TransferByMap, Transfer, Vortex, EmptyContainer, Provision, and SerialDilution. It does not register Spin or a magnetic-separation updater.
- `update()` skips unregistered behaviors instead of calculating material changes. The execution engine invokes this observer after activity execution.
- `compute_transfer()` calculates proportions from source reagent contents, subtracts transferred quantities, and adds them to destinations. The graph retains time-indexed sample states and ancestry. Basic transfer accounting is therefore present.
- `ProvisionUpdater` uses the resource identity as a reagent key. A static SBOL complex description is not thereby expanded into a component-state evolution model.
- `labop/lib/plate_handling.py` defines Spin's location, duration, and acceleration inputs. The missing material update, rather than the missing output signature alone, grounds the native-path No.

The full source search found no alternate registration supplying the missing separation updater in the inspected execution path. This is a frozen-version/default-path finding, not an impossibility claim about LabOP extensions or all backends.

## Released-only GFP execution

The [primary native program](gfp_labop.py) and [results](results/gfp-labop-native/results.json)
confirm the mechanism finding without added handlers. Both the `Spin` prefix
and the location-based continuation validate and complete normally. The latter
produces three 20-uL wells and observation coordinates. Its A2 **material
ledger** contains only buffer; its **provenance graph** nevertheless retains
a history path through the original sample. This generic ancestry does not
establish a distinct pellet or compute cellular content. Missing output-pin
lookups are authoring-time observations, not manufactured runtime failures.
The released-route evidence is primary for M3; the extension below is reported
separately under L4. Culsma uses its released separation/partition rules for
this task, without a newly supplied handler.

## Mechanism-level clarification (15 November 2026)

The M3 No is not inferred from the missing `Spin` registration alone. The
inspected default path consists of:

- `labop/sample_array.py::SampleArray.empty`: contents indexed by container,
  location and reagent, plus sample-location identifiers.
- `labop/execution/behavior_dynamics.py::ProvisionUpdater.update`: one supplied
  resource identity becomes a reagent key. It does not traverse an SBOL
  resource's internal component/relationship description to create evolving
  component records.
- `SampleProvenanceObserver.compute_transfer`: proportionally moves the
  quantities under these reagent keys and creates new sample states/ancestry.
- `SampleProvenanceObserver.handlers` / `update`: operation-specific dispatch,
  with unhandled behaviors logged and skipped. The registered updaters cover
  provisioning, container initialization, transfer, vortex and serial dilution;
  they do not interpret component transformations or declared partition rules.
- `labop/execution/execution_engine.py`: the sample-tracking path invokes this
  observer after a call. Protocol execution can therefore continue without a
  corresponding material-state update.

This establishes reagent-level transfer accounting and sample history, but
not the component/relationship/state evolution required by M3 on this route.
Handler dispatch itself is not a defect or a failure criterion. These are
handlers for operation types, not implementations rewritten for each experiment.
They already share reagent-quantity records and a sample-history graph. The
gap is in the material meanings represented and consumed by the released
handlers, not in the absence of shared storage: internal component relations,
transformations and product partitioning are not carried through this path.
`Spin` and the native GFP result illustrate this boundary; they are not the
premise from which absence of the general mechanism is inferred. Other
specializations and user-added handlers are outside this default-path claim.
No new execution was performed for this source audit.

## Code added for the comparison

[fractionation.py](fractionation.py) defines ClarifyLysate and FractionationUpdater. [gfp_labop_extended.py](gfp_labop_extended.py) explicitly registers the latter. This extension versions fraction sample states and adds ancestry edges while leaving all original liquid in the supernatant and the pellet's liquid ledger empty until buffer is added. It does not calculate a solid-component count or protein mass. The previous successful GFP volume/ancestry comparison must not be generalized to native component-resolved separation accounting.

## Interpretation correction

`transition(...)` supplies an author-assumed state change; it is not the material ledger itself. The earlier LabOP SBOL complex probe establishes static description only. Both findings remain valid within those narrower scopes, but neither is the revised M3 capability witness.

LabOP's [2023 paper, §6](https://jakebeal.github.io/Publications/JETC23-LabOP.pdf) lists reasoning about sample contents as future work. This historical statement is background, not a substitute for the pinned source audit, which also establishes that basic transfer accounting is present.

## Explicit state witness and limit (16 November 2026)

In the pinned source, `runtime/material/contents_state.py::record_partitioned_contents_state`
records product slots and partition validity; `suspension.py::refresh_cell_suspension_relationship`
maintains cellular-state relationships. In `results/culsma/run.json`,
`events[11].payload.material_state_snapshot` records the lysate's
`material_state: suspension`; `events[21].payload.material_state_snapshot`
records `material_state: pellet` (source: `scientific_model_provider`) and
`contents_states` of kind `partitioned`. Indices here are zero-based JSON
array indices. This is evidence of an implemented separation-state update,
not merely the presence of state-handling source files.

The final resuspended container and A2 still retain a `pellet` state/relation.
The manuscript therefore limits its state claim to the observed separation
update; it does not claim that this run establishes correct post-resuspension
state evolution. The retained component counts and transfer quantities are
reported separately. No new execution or source modification was performed.
