# Runtime Module Diagrams

Last updated: 2026-07-11

Related plan/runtime documents:

1. [plan_module_diagrams.md](./pipeline/plan_module_diagrams.md)
2. [material_compute_module_diagrams.md](./material_compute_module_diagrams.md)

## Scope

This document records the current runtime structure with one functional
flowchart plus material-compute detail diagrams and structural diagrams:

1. Functional flowchart: what runtime execution actually does.
2. Runtime sequence.
3. Runtime step detail sequence.
4. Runtime step detail flowchart.
5. Material compute `sep` detail flowchart.
6. Proposed `sep` partition strategy diagram.
7. Report data-structure diagram.
8. Report-accounting integration.
9. Class/module diagram.

Runtime consumes `PlanProgram` and returns `RunResult(state, events,
diagnostics, user_result)`. It owns deterministic scheduling, dependency and
runtime-gate checks, repeat/control handling, protocol-reference reuse
decisions, driver capability checks, driver execution, material-state compute,
observation recording, protocol-output capture, and user-facing run summary
generation. It does not parse source, validate IR, lower IR to plan, or define
driver backends.

For executable programs, `run()` is the only report-producing execution path.
If frontend errors prevent execution, the CLI preserves the output contract
with an explicitly unexecuted report; it does not treat that report as an
experiment result.

The implementation now follows a scheduler plus dispatcher plus handler split:

- `RuntimeExecutor` owns scheduler rounds and finalization
- `RuntimeSession` owns shared run state and services
- `RuntimeStepDispatcher` chooses a handler by step execution family
- `BaseRuntimeStepHandler` defines the ready-step lifecycle
- concrete handlers own built-in/runtime/driver-backed execution families
- helper services own gate evaluation, value resolution, ref reuse,
  observation capture, protocol-output capture, and finalization helpers

## Functional Flowchart

```mermaid
flowchart TB
    Start(["Start runtime run"])
    Boundary["Confirm execution boundary:<br/>selected entry session"]
    Init["Prepare session-scoped runtime state:<br/>init or reuse RuntimeState,<br/>create EventLog, diagnostics, step lookup tables"]
    Order["Order steps inside the session:<br/>compute dependency layers, protocol output capture points,<br/>reference-call groups and cache"]
    RoundLoop{"More scheduler rounds<br/>with progress?"}
    StepLoop{"More pending steps<br/>to scan this round?"}
    Select["Select one pending step"]
    Deps{"Are dependencies satisfied?"}
    Gate["Evaluate runtime gate:<br/>run, skip, or fail if unresolved"]
    Ref["Decide whether a referenced-protocol subtree<br/>should reuse cached results or rerun"]
    StartStep["Mark step running and emit STEP_STARTED"]
    Family["Choose execution family:<br/>built-in runtime step or driver-backed step"]
    BuiltIn["Run built-in runtime behavior:<br/>local assign, member assign, append,<br/>repeat body execution, break/continue"]
    DriverPath["Run driver-backed behavior:<br/>resolve runtime args, check driver capability,<br/>execute driver step"]
    Material["Apply deterministic material-state update<br/>and record observation artifacts when needed"]
    Finish["Record terminal result:<br/>completed / skipped / failed,<br/>history, diagnostics, events,<br/>protocol outputs, ref cache"]
    Finalize["Finalize unresolved steps:<br/>mark unsatisfied dependency skips,<br/>mark stuck pending failures,<br/>capture protocol outputs"]
    Build["Build user-facing run summary"]
    Return["Return RunResult(state, events, diagnostics, user_result)"]

    Start --> Boundary
    Boundary --> Init
    Init --> Order
    Order --> RoundLoop
    RoundLoop -->|yes| StepLoop
    StepLoop -->|yes| Select
    Select --> Deps
    Deps -->|no| StepLoop
    Deps -->|yes| Gate
    Gate -->|skip| Finish
    Gate -->|error| Finish
    Gate -->|run| Ref
    Ref -->|reuse cached subtree| Finish
    Ref -->|rerun| StartStep
    StartStep --> Family
    Family -->|built-in runtime step| BuiltIn
    Family -->|driver-backed step| DriverPath
    BuiltIn --> Finish
    DriverPath --> Material
    Material --> Finish
    Finish --> StepLoop
    StepLoop -->|no| RoundLoop
    RoundLoop -->|no| Finalize
    Finalize --> Build
    Build --> Return
```

## Runtime Sequence

```mermaid
sequenceDiagram
    participant Caller as "pipeline / tests"
    participant API as "runtime/executor.py::run"
    participant Exec as "runtime/executor.py::RuntimeExecutor"
    participant Session as "runtime/session.py::RuntimeSession"
    participant Disp as "runtime/steps.py::RuntimeStepDispatcher"
    participant H as "runtime/steps.py::BaseRuntimeStepHandler"
    participant Accounting as "runtime/material/accounting.py::MaterialAccountingRecorder"
    participant Final as "runtime/finalize.py::RuntimeFinalizer"
    participant Report as "runtime/user_result.py::ReportBuilder"

    Caller->>API: run(selected-entry plan, driver, state, ...)
    API->>Exec: RuntimeExecutor(...)
    Exec->>Accounting: initialize(initial_material_state)
    API->>Session: create RuntimeSession(plan, driver, runtime_state, services)
    API->>Exec: execute(session)

    loop scheduler rounds
        Exec->>Exec: scan pending steps and pick ready step
        Exec->>Disp: dispatch(step, session)
        Disp->>H: handle(step, session)
        H->>Accounting: record successful material update
        H-->>Exec: step result recorded through session
    end

    Exec->>Final: finalize(session)
    Exec->>Final: build_report(session, ok)
    Final->>Report: build(...)
    Exec-->>Caller: RunResult(state, events, diagnostics, user_result)
```

## Runtime Step Detail Sequence

```mermaid
sequenceDiagram
    participant H as "runtime/steps.py::BaseRuntimeStepHandler"
    participant Gate as "runtime/gates.py::GateEvaluator"
    participant Ref as "runtime/references.py::RefReuseDecider"
    participant Values as "runtime/values.py::RuntimeValueResolver"
    participant Driver as "driver.base::Driver"
    participant Mat as "runtime/material_compute.py::apply_step"
    participant Obs as "runtime/observation.py::ObservationRecorder"
    participant Out as "runtime/protocol_outputs.py::ProtocolOutputRecorder"
    participant Session as "runtime/session.py::RuntimeSession"

    H->>H: prepare(step, session)
    H->>Gate: evaluate(step, state, session=session)
    alt skip or unresolved gate
        H->>Session: mark skipped/failed and emit terminal event
    else run
        H->>Ref: group_for_step(step_id, session)
        H->>Ref: decide(group, session) when step is ref-subtree root
        alt reuse cached subtree
            H->>Session: mark reused subtree and emit reuse events
        else execute current step
            H->>Session: mark running and emit STEP_STARTED
            alt built-in runtime handler
                H->>Values: resolve local/member/runtime values
                H->>Session: apply local/control/repeat effects
            else driver-backed handler
                H->>Values: resolve_step_args(step, state)
                H->>Driver: check(step)
                H->>Driver: execute(step)
                H->>Mat: apply_step(step, material_state)
                H->>Obs: record(step, session, driver_code, driver_payload)
            end
            H->>Out: capture_if_ready(step, session)
            H->>Session: record terminal status, diagnostics, and events
        end
    end
```

## Runtime Step Detail Flowchart

```mermaid
flowchart TB
    Start([BaseRuntimeStepHandler.handle])
    Prepare["1. Prepare step-local state"]
    Gate["2. Evaluate gate and ready-step policy"]
    Ref["3. Decide ref-subtree reuse or rerun"]
    Begin["4. Mark running and emit STEP_STARTED"]
    Dispatch["5. Dispatch into built-in or driver-backed execution path"]
    Execute["6. Execute step-family behavior"]
    Effects["7. Apply material, observation, protocol-output, and cache effects"]
    Record["8. Record terminal status, diagnostics, history, and events"]
    Done([Return to scheduler])

    Start --> Prepare
    Prepare --> Gate
    Gate --> Ref
    Ref --> Begin
    Begin --> Dispatch
    Dispatch --> Execute
    Execute --> Effects
    Effects --> Record
    Record --> Done
```

| Phase | Semantic boundary | Typical owners |
| --- | --- | --- |
| `prepare` | Identify step family, preload step-local scratch state, and expose shared services. | every runtime step handler |
| `evaluate gate and ready-step policy` | Decide whether the already-ready step should run, skip, or fail before side effects begin. | gate evaluator, scheduler/handler boundary |
| `decide ref-subtree reuse or rerun` | Apply protocol-reference caching policy before executing a reference-root subtree. | ref reuse decider |
| `mark running and emit STEP_STARTED` | Publish the transition into active execution. | base handler / runtime session |
| `dispatch into built-in or driver-backed execution path` | Separate pure-runtime steps from driver-mediated steps. | step dispatcher / concrete handlers |
| `execute step-family behavior` | Perform local/control/repeat logic or driver check/execute logic. | concrete runtime handlers |
| `apply material, observation, protocol-output, and cache effects` | Push cross-cutting execution side effects into dedicated services. | material compute, observation recorder, protocol-output recorder, ref cache updater |
| `record terminal status, diagnostics, history, and events` | Close the step with one consistent terminal outcome. | runtime session / final recorder logic |

## Material Compute `sep` Detail Flowchart

This flowchart expands the `runtime/material_compute.py::apply_step` boundary
for `sep` operations. It documents the current responsibility split and the
program-specific material partition behavior.

```mermaid
flowchart TB
    Start(["apply_step(step, material_state)"])
    Op{"step.op == sep?"}
    Other["Dispatch to other material op handler:<br/>AllocContainer, DefineContent, LoadContent,<br/>Mutation, frac, or no-op"]
    Resolve["Resolve sep args:<br/>sample, bind name, program call"]
    Program["Read program kind:<br/>centrifuge, filtration, centrifugal filtration,<br/>phase partition, precipitation, magnetic, disrupt, field"]
    Slots["Determine output slot contract:<br/>group[0] / group[1] semantic names"]
    Identity["Apply identity policy:<br/>centrifuge keep_source may reuse source container"]
    Partition["Compute material partition:<br/>bulk volume/mass, component fate"]
    Bind["Bind indexed group:<br/>bind[0] and bind[1] to output container ids"]
    Delta["Return MaterialUpdateResult:<br/>updated material_state, diagnostics, delta"]

    Start --> Op
    Op -->|no| Other
    Op -->|yes| Resolve
    Resolve --> Program
    Program --> Slots
    Slots --> Identity
    Identity --> Partition
    Partition --> Bind
    Bind --> Delta
```

Current implementation note:

1. `Program` reads `program_kind`.
2. `centrifugal_filtration_program(..., drive=..., duration=...)` is a distinct
   program kind whose slot contract remains filtrate / retentate.
3. `Identity` handles `centrifuge_program(..., keep_source=...)` source-container
   reuse.
4. `Partition` uses a strategy selected by `program_kind`.
5. Component fate uses program-specific ratios. Legacy volume/mass-only state
   retains conservative bulk accounting. When dimensioned cell-count content is
   present, volume-bearing component quantities determine bulk volume while
   count-bearing quantities remain outside capacity accounting. Without an
   explicit mass-bearing component quantity, output bulk mass follows the
   partitioned carrier-volume ratio and preserves total source mass. The
   partition delta records the selected bulk-quantity policy.

## Implemented `sep` Partition Strategy

The current runtime architecture already prefers dispatcher/handler ownership
over large conditional blocks. `sep` material partitioning follows the same
pattern. A compact strategy registry keeps `material_compute.apply_step`
responsible for orchestration while
letting each separation program own its own partition contract.

```mermaid
flowchart TB
    Apply["apply_step"]
    Sep["_apply_sep orchestration"]
    Registry["SepPartitionStrategy registry"]
    Default["SepPartitionStrategy<br/>unknown fallback"]
    Centrifuge["CentrifugePartitionStrategy<br/>supernatant / pellet"]
    Phase["PhasePartitionStrategy<br/>target_phase / other_phase"]
    Precip["PrecipitationPartitionStrategy<br/>precipitate / supernatant"]
    Filter["FiltrationPartitionStrategy<br/>filtrate / retentate"]
    CentrifugalFilter["CentrifugalFiltrationPartitionStrategy<br/>filtrate / retentate"]
    Magnetic["MagneticPartitionStrategy<br/>bound / flowthrough"]
    Disrupt["DisruptPartitionStrategy<br/>lysate / debris_or_residue"]
    Field["FieldPartitionStrategy<br/>target_band / non_target"]
    Result["SepPartitionResult:<br/>slot containers, component deltas,<br/>diagnostics, binding metadata"]

    Apply --> Sep
    Sep --> Registry
    Registry -->|unknown or unsupported| Default
    Registry -->|centrifuge_program| Centrifuge
    Registry -->|phase_partition_program| Phase
    Registry -->|precipitation_program| Precip
    Registry -->|filtration_program| Filter
    Registry -->|centrifugal_filtration_program| CentrifugalFilter
    Registry -->|magnetic_program| Magnetic
    Registry -->|disrupt_program| Disrupt
    Registry -->|field_program| Field
    Default --> Result
    Centrifuge --> Result
    Phase --> Result
    Precip --> Result
    Filter --> Result
    CentrifugalFilter --> Result
    Magnetic --> Result
    Disrupt --> Result
    Field --> Result
    Result --> Sep
```

Design judgment:

1. Program-specific component fate is not implemented as a growing conditional
   ladder because each program has a different slot contract,
   residual/carryover rules, and diagnostics.
2. A strategy registry preserves the runtime boundary: the runtime executes
   explicit program semantics; it does not infer biological intent from labels
   or hard-coded component names.

## Report Data Structure

`ReportBuilder` builds these dataclasses from runtime state and online material
accounting. `LabReport.to_dict()` projects them to the compatible
`lab_report_v1` JSON format held in `RunResult.user_result`; it is not the
formal protocol return value.

```mermaid
classDiagram
    class LabReport {
        +execution
        +headline
        +materials
        +qc_results
        +resource_summary
        +process_summary
        +alerts
        +to_dict() dict
    }

    class ExecutionSummary {
        +ok
        +diagnostic_count
        +total_steps
        +completed_steps
        +failed_steps
        +skipped_steps
    }

    class MaterialsReport {
        +has_material_state
        +input_inventory
        +final_products
        +intermediate_materials
        +reagent_consumption
    }

    class InputInventoryRow {
        +name
        +initial_uL
        +initial_mL
        +initial_mg
        +initial_cells
    }

    class FinalProductRow {
        +name
        +volume_uL
        +volume_mL
        +mass_mg
        +primary_component
        +count_cells
    }

    class IntermediateMaterialRow {
        +name
        +final_uL
        +final_mL
        +mass_mg
        +primary_component
        +count_cells
    }

    class ReagentConsumptionRow {
        +name
        +roles
        +consumed_uL
        +consumed_mL
        +consumed_mg
        +consumed_cells
    }

    class QcResult {
        +item
        +values
    }

    class ResourceSummary {
        +containers
        +instruments
    }

    class ContainerResourceSummary {
        +allocated_count
        +touched_count
        +container_kinds
        +touched_names
    }

    class ContainerKindCount {
        +kind
        +count
    }

    class InstrumentSummary {
        +tools
        +devices
    }

    class NamedCount {
        +name
        +count
    }

    class ProcessSummary {
        +mutation_steps
        +separation_steps
        +environment_steps
        +readout_steps
    }

    LabReport *-- ExecutionSummary : execution
    LabReport *-- MaterialsReport : materials
    LabReport *-- QcResult : qc_results
    LabReport *-- ResourceSummary : resource_summary
    LabReport *-- ProcessSummary : process_summary
    MaterialsReport *-- InputInventoryRow : input_inventory
    MaterialsReport *-- FinalProductRow : final_products
    MaterialsReport *-- IntermediateMaterialRow : intermediate_materials
    MaterialsReport *-- ReagentConsumptionRow : reagent_consumption
    ResourceSummary *-- ContainerResourceSummary : containers
    ResourceSummary *-- InstrumentSummary : instruments
    ContainerResourceSummary *-- ContainerKindCount : container_kinds
    InstrumentSummary *-- NamedCount : tools / devices
```

## Report-Accounting Integration

`MaterialAccounting` is a runtime artifact. It is distinct from the existing
`MaterialLedger`, which mutates container quantities but does not keep input
provenance. Report calculation reads accounting directly; `EventLog` remains a
trace and diagnostic record, not the source of report accounting.

### Class Design

Names in this class diagram are exact Python symbols.

```mermaid
classDiagram
    class MaterialAccountingRecorder {
        +initialize(initial_material_state) MaterialAccounting
        +record(step, result, accounting) None
    }

    class MaterialUpdateResult {
        +material_state
        +diagnostics
        +delta
        +movements
    }

    class MaterialMovementSpec {
        +source
        +destination
        +volume_uL
        +mass_mg
        +count_cells
    }

    class MaterialAccounting {
        +input_lots
        +container_allocations
        +movements
        +consumed_allocations
        +register_input_lot(lot) None
        +record_movement(step_id, source, destination, quantity) None
        +list_input_lots() list
        +consumption_by_input() dict
        +container_allocation(container_id) dict
    }

    class ReportBuilder {
        +build(ok, diagnostics, state, plan, initial_material_state, material_accounting) LabReport
    }

    class RuntimeExecutor
    class RuntimeSession {
        +material_accounting_recorder
        +material_accounting
    }
    class BaseRuntimeStepHandler
    class MaterialCompute
    class derive_material_movements
    class RuntimeFinalizer
    class LabReport

    RuntimeExecutor --> MaterialAccountingRecorder : initializes through
    RuntimeSession o-- MaterialAccountingRecorder : owns service
    RuntimeSession o-- MaterialAccounting : owns run artifact
    BaseRuntimeStepHandler --> MaterialAccountingRecorder : records through
    MaterialCompute --> derive_material_movements : derives operation movements
    derive_material_movements --> MaterialMovementSpec : creates
    MaterialUpdateResult *-- MaterialMovementSpec : movements
    MaterialAccountingRecorder --> MaterialUpdateResult : consumes movements
    MaterialAccountingRecorder --> MaterialAccounting : creates and updates
    RuntimeFinalizer --> ReportBuilder : build_report
    ReportBuilder --> MaterialAccounting : reads
    ReportBuilder --> LabReport : builds
```

`MaterialAccountingRecorder` has two public lifecycle methods: `initialize()`
creates the run accounting from initial state, and `record()` applies one
successful material update. `MaterialAccounting` owns mutation and query
methods so `ReportBuilder` does not inspect its internal dictionaries. The
recorder is a `RuntimeSession` service: `RuntimeExecutor` uses it once for
initialization, and `BaseRuntimeStepHandler` uses it after each successful
material update.

### Accounting Activity

```mermaid
flowchart TD
    Start(["Experiment begins"]) --> Initial["Register every starting material as a separately identifiable input batch"]
    Initial --> Execute["Perform the next experimental operation"]
    Execute --> Success{"Did the operation succeed?"}

    Success -- "No" --> Unchanged["Leave material accounting unchanged"]
    Success -- "Yes" --> NewInput{"Did new material enter the experiment?"}
    NewInput -- "Yes" --> Register["Register the new material as a distinct input batch"]
    NewInput -- "No" --> QuantityChange{"Did any material quantity move or leave the system?"}

    QuantityChange -- "No" --> NoMovement["Keep existing material origins and quantities unchanged"]
    QuantityChange -- "Yes" --> Relation{"Are the source, destination, and moved quantity explicit?"}
    Relation -- "No" --> Incomplete["The operation cannot be accounted reliably and must define the missing movement relationship"]
    Relation -- "Yes" --> Movement["Create one movement record for each source-to-destination relationship"]

    Movement --> MoreMovements{"Are there unprocessed movement records?"}
    MoreMovements -- "Yes" --> Composition["Determine the moved material's input-batch composition from its source"]
    Composition --> Withdraw["Remove that composition from the source"]
    Withdraw --> Destination{"Does the movement have a destination?"}
    Destination -- "Yes" --> Propagate["Add the same input-batch composition to the destination"]
    Destination -- "No" --> Remove["Record the material as removed from the experiment"]
    Propagate --> Original{"Did the material leave its original input container?"}
    Remove --> Original
    Original -- "Yes" --> Consume["Add the moved quantity to that input batch's consumption total"]
    Original -- "No" --> MoreMovements
    Consume --> MoreMovements
    MoreMovements -- "No" --> Continue

    Register --> Continue
    NoMovement --> Continue
    Unchanged --> Continue
    Continue{"Are there more experimental operations?"}
    Continue -- "Yes" --> Execute
    Continue -- "No" --> Report["Summarize inputs, consumption, remaining materials, resources, and execution status"]
    Report --> Output(["Produce the structured experiment report"])
```

### Runtime Sequence

```mermaid
sequenceDiagram
    participant RuntimeExecutor
    participant RuntimeSession
    participant BaseRuntimeStepHandler
    participant MaterialCompute
    participant MaterialAccountingRecorder
    participant MaterialAccounting
    participant EventLog
    participant RuntimeFinalizer
    participant ReportBuilder

    RuntimeExecutor->>MaterialAccountingRecorder: initialize(initial_material_state)
    MaterialAccountingRecorder->>MaterialAccounting: register_input_lot(lot)
    RuntimeExecutor->>RuntimeSession: material_accounting_recorder = recorder
    RuntimeExecutor->>RuntimeSession: material_accounting = accounting

    loop each successful material step
        RuntimeExecutor->>BaseRuntimeStepHandler: handle(step, session)
        BaseRuntimeStepHandler->>MaterialCompute: apply_step(step, material_state)
        MaterialCompute->>MaterialCompute: normalize operation semantics into movements
        MaterialCompute-->>BaseRuntimeStepHandler: MaterialUpdateResult(movements)
        RuntimeSession-->>BaseRuntimeStepHandler: material_accounting_recorder, material_accounting
        BaseRuntimeStepHandler->>MaterialAccountingRecorder: record(step, result, accounting)
        alt LoadContent
            MaterialAccountingRecorder->>MaterialAccounting: register_input_lot(lot)
        else transfer or sep
            MaterialAccountingRecorder->>MaterialAccounting: record_movement() for each result.movements item
        end
        BaseRuntimeStepHandler->>EventLog: emit(STEP_COMPLETED, payload)
    end

    RuntimeExecutor->>RuntimeFinalizer: finalize(session)
    RuntimeSession-->>RuntimeFinalizer: material_accounting, runtime_state
    RuntimeFinalizer->>ReportBuilder: build(ok, diagnostics, state, plan, initial_material_state, material_accounting)
    ReportBuilder->>MaterialAccounting: list_input_lots()
    ReportBuilder->>MaterialAccounting: consumption_by_input()
    ReportBuilder-->>RuntimeFinalizer: LabReport
```

Accounting invariants:

1. Initial inventory and every `LoadContent` create distinct input lots, even
   when they share a container.
2. Every quantity-changing operation exposes normalized
   `MaterialUpdateResult.movements`; `MaterialAccountingRecorder` consumes only
   that contract and does not reconstruct movements from state differences.
3. `ReportBuilder` emits complete lists. Terminal and UI renderers own any
   top-N or compact display policy.
4. Multiple sources and targets are represented as separate movement records.
   Missing source-to-destination relations are an operation implementation gap,
   never an invitation to invent allocations from aggregate totals. A
   quantity-changing operation without movements fails with
   `MAT_MOVEMENT_CONTRACT_MISSING`.

## Class And Module Diagram

```mermaid
classDiagram
    class RuntimeAPI {
        +run(plan, driver, state, ...) RunResult
    }

    class RuntimeExecutor {
        +execute(session) RunResult
    }

    class RuntimeSession {
        +plan
        +driver
        +state
        +diagnostics
        +event_log
        +step_by_id
        +ordered_steps
        +ref_cache
        +mark_running(step) None
        +record_completed(step, payload) None
        +record_failed(step, reason, payload) None
        +record_skipped(step, reason) None
    }

    class RuntimeStepDispatcher {
        +dispatch(step, session) bool
    }

    class RuntimeStepState {
        +resolved_step
        +driver_code
        +driver_payload
        +material_delta
        +observation_delta
        +recorded
    }

    class BaseRuntimeStepHandler {
        +handle(step, session) bool
        #prepare(step, session) RuntimeStepState
        #execute_current_step(step, session, state) None
        #record_terminal_result(step, session, state) None
    }

    class ControlStepHandler
    class LocalStateStepHandler
    class RepeatStepHandler
    class DriverBackedStepHandler

    class RuntimeState {
        +step_status
        +artifacts
        +locks
        +history
        +to_dict() dict
    }

    class EventLog {
        +events
        +emit(kind, step_id, payload, span) RuntimeEvent
    }

    class RuntimeEvent {
        +seq
        +kind
        +step_id
        +payload
        +span
        +to_dict() dict
    }

    class Driver {
        +check(step) capability
        +execute(step) result
    }

    class GateEvaluator {
        +evaluate(step, state, session) str
    }

    class RefReuseDecider {
        +group_for_step(step_id, session) RefGroup
        +decide(group, session) RefDecision
    }

    class RuntimeValueResolver {
        +eval_expr(expr, state) object
        +resolve_step_args(step, state) PlanStep
    }

    class ObservationRecorder {
        +record(step, session, driver_code, driver_payload) dict
    }

    class ProtocolOutputRecorder {
        +capture_if_ready(step, session) None
        +capture_all(session) None
    }

    class RuntimeFinalizer {
        +finalize(session, *, aborted_due_to_error) None
        +build_report(session, *, ok) LabReport
    }

    class MaterialCompute {
        +apply_step(step, material_state) MaterialUpdateResult
    }

    class MaterialUpdateResult {
        +material_state
        +diagnostics
        +delta
        +ok
    }

    class MaterialAccountingRecorder {
        +initialize(initial_material_state) MaterialAccounting
        +record(step, result, accounting) None
    }

    class MaterialAccounting

    class ReportBuilder {
        +build(...) LabReport
    }

    class RunResult {
        +state
        +events
        +diagnostics
        +user_result
        +ok
    }

    class PlanStep

    RuntimeAPI --> RuntimeExecutor : creates
    RuntimeAPI --> RuntimeSession : builds
    RuntimeExecutor --> RuntimeSession : mutates
    RuntimeExecutor --> RuntimeStepDispatcher : dispatches through
    RuntimeExecutor --> RuntimeFinalizer : finalizes through
    RuntimeExecutor --> RunResult : returns
    RuntimeSession --> RuntimeState : wraps
    RuntimeSession --> EventLog : writes through
    EventLog --> RuntimeEvent : contains
    RuntimeStepDispatcher --> BaseRuntimeStepHandler : selects
    BaseRuntimeStepHandler --> RuntimeStepState : creates
    BaseRuntimeStepHandler --> RuntimeSession : records through
    BaseRuntimeStepHandler --> GateEvaluator : uses
    BaseRuntimeStepHandler --> RefReuseDecider : uses
    BaseRuntimeStepHandler --> RuntimeValueResolver : uses
    BaseRuntimeStepHandler --> ObservationRecorder : uses
    BaseRuntimeStepHandler --> ProtocolOutputRecorder : uses
    BaseRuntimeStepHandler --> Driver : uses
    BaseRuntimeStepHandler --> MaterialCompute : uses
    RuntimeExecutor --> MaterialAccountingRecorder : initializes through
    RuntimeSession --> MaterialAccountingRecorder : owns service
    RuntimeSession --> MaterialAccounting : owns run artifact
    BaseRuntimeStepHandler --> MaterialAccountingRecorder : records through
    MaterialAccountingRecorder --> MaterialAccounting : updates
    RuntimeFinalizer --> ReportBuilder : builds through
    MaterialCompute --> MaterialUpdateResult : returns
    BaseRuntimeStepHandler <|-- ControlStepHandler
    BaseRuntimeStepHandler <|-- LocalStateStepHandler
    BaseRuntimeStepHandler <|-- RepeatStepHandler
    BaseRuntimeStepHandler <|-- DriverBackedStepHandler
    RuntimeSession --> PlanStep : indexes
```
