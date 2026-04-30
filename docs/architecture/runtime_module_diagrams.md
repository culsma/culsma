# Runtime Module Diagrams

Last updated: 2026-04-25

Related plan/runtime documents:

1. [plan_module_diagrams.md](https://github.com/culsma/culsma/blob/main/docs/architecture/plan_module_diagrams.md)

## Scope

This document records the current runtime structure with one functional
flowchart plus four structural diagrams:

1. Functional flowchart: what runtime execution actually does.
2. Runtime sequence.
3. Runtime step detail sequence.
4. Runtime step detail flowchart.
5. Class/module diagram.

Runtime consumes `PlanProgram` and returns `RunResult(state, events,
diagnostics, user_result)`. It owns deterministic scheduling, dependency and
runtime-gate checks, repeat/control handling, protocol-reference reuse
decisions, driver capability checks, driver execution, material-state compute,
observation recording, protocol-output capture, and user-facing run summary
generation. It does not parse source, validate IR, lower IR to plan, or define
driver backends.

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
    Init["Prepare runtime state:<br/>init or reuse RuntimeState,<br/>create EventLog, diagnostics, step lookup tables"]
    Order["Flatten protocol plans into one ordered step list:<br/>compute dependency layers, protocol output capture points,<br/>reference-call groups and cache"]
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

    Start --> Init
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
    participant Final as "runtime/finalize.py::RuntimeFinalizer"
    participant User as "runtime/user_result.py::build_user_result"

    Caller->>API: run(plan, driver, state, ...)
    API->>Exec: RuntimeExecutor(...)
    API->>Session: create RuntimeSession(plan, driver, runtime_state, services)
    API->>Exec: execute(session)

    loop scheduler rounds
        Exec->>Exec: scan pending steps and pick ready step
        Exec->>Disp: dispatch(step, session)
        Disp->>H: handle(step, session)
        H-->>Exec: step result recorded through session
    end

    Exec->>Final: finalize(session)
    Exec->>User: build_user_result(...)
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

    class UserResultBuilder {
        +build_user_result(ok, diagnostics, state, events, plan, initial_material_state) dict
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
    RuntimeAPI --> UserResultBuilder : builds report through
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
    MaterialCompute --> MaterialUpdateResult : returns
    BaseRuntimeStepHandler <|-- ControlStepHandler
    BaseRuntimeStepHandler <|-- LocalStateStepHandler
    BaseRuntimeStepHandler <|-- RepeatStepHandler
    BaseRuntimeStepHandler <|-- DriverBackedStepHandler
    RuntimeSession --> PlanStep : indexes
```
