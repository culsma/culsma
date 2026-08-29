# Runtime Module Diagrams

Last updated: 2026-08-25

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
10. Proposed pluggable scientific-model boundary.

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

## Proposed Pluggable Scientific-Model Boundary

This is a component structure, not an execution-flow or concurrency diagram.
Arrows describe dependency and contract direction; they do not introduce a
runtime fork. The scientific-model boundary is run-scoped; custom injection
is optional because the default resolver binds the built-in Reference provider.

```mermaid
flowchart LR
    subgraph Culsma["Culsma runtime boundary"]
        RunAPI["Runtime composition root<br/>run(..., scientific_model=...)"]
        Supplied{"resolver supplied?"}
        DefaultResolver["create default resolver<br/>bind built-in provider"]
        Runtime["Runtime kernel<br/>scheduling + operation execution"]
        Session["Runtime session<br/>owns configured MaterialCompute"]
        Compute["MaterialCompute<br/>existing material-state executor"]
        Effect["Operation-effect coordinator<br/>builds an immutable request"]
        Validate["Kernel effect validator<br/>units + bounds + conservation + allowed effects"]
        Commit["Authoritative commit<br/>material ledger + observations + provenance"]

        RunAPI --> Runtime
        RunAPI --> Supplied
        Supplied -->|"no"| DefaultResolver
        Runtime --> Session
        Session -->|"owns"| Compute
        Compute --> Effect
        Validate --> Commit
    end

    subgraph ExecutionBoundary["Existing execution backend boundary"]
        Driver["Driver<br/>capability check + execution receipt"]
    end

    subgraph ResolverBoundary["Stable resolution boundary"]
        Resolver["one ScientificModelResolver per run<br/>default: RegistryScientificModelResolver"]
        Registry["ScientificModelRegistry<br/>many capability@version bindings"]
        NoModel["No-model implementation<br/>returns not applicable"]

        NoModel -. implements .-> Resolver
        Resolver -->|"select binding"| Registry
    end

    subgraph PluginBoundary["zero-to-many replaceable providers"]
        Builtin["Built-in Reference Rulebook provider<br/>default separation_fate + state_transition"]
        ProviderA["Provider A<br/>explicit capability replacement"]
        ProviderB["Provider B<br/>another scientific capability"]
    end

    Effect -->|"immutable semantic facts"| Resolver
    Supplied -->|"yes: use supplied instance"| Resolver
    DefaultResolver --> Resolver
    Resolver -. "inject selected instance" .-> Compute
    Runtime -->|"execute declared operation"| Driver
    Driver -->|"execution receipt"| Runtime
    Registry -->|"material.separation_fate@1.0"| Builtin
    Registry -->|"material.state_transition@1.0"| Builtin
    Registry -. "replace one explicit binding" .-> ProviderA
    Registry -. "additional capability binding" .-> ProviderB
    Builtin -->|"typed proposed effect + provenance"| Resolver
    ProviderA -->|"same typed result boundary"| Resolver
    ProviderB -. "same typed result boundary" .-> Resolver
    Resolver -->|"resolved or not-applicable result"| Validate
```

The ownership boundary is fixed:

| Owner | Responsibility |
| --- | --- |
| Runtime kernel | Scheduling, operation success, structural invariants, and commit timing |
| Runtime composition root | Select one resolver and construct `MaterialCompute` for the run |
| Runtime session | Own the configured `MaterialCompute`; no duplicate resolver reference |
| `MaterialCompute` | Existing material-state execution, validation, movement derivation, and commit boundary |
| Scientific Model Resolver | Capability selection and typed transport; no state mutation |
| Model provider | Proposed scientific effect, assumptions, uncertainty, model identity, and version |
| Kernel effect validator | Reject or accept the proposal against the operation contract and runtime invariants |
| Authoritative commit | Apply only validated effects and record their provenance |

With no resolver supplied, the runtime constructs one resolver whose two default
material bindings use the built-in Reference Rulebook provider. The resolver may
hold many providers at the same time, while each `capability@contract_version`
selects exactly one provider for that run. The no-model
implementation remains available for an explicitly disabled or unsupported
capability. Aggregate volume and mass stay inside the kernel and are projected
from the authoritative component-detail ledger.

## Proposed Scientific Model API Contract

The API has three layers. The caller injects one resolver, the resolver dispatches
to explicitly configured providers, and the kernel privately validates every
proposal. Providers never receive `RuntimeState` and never receive a commit
handle.

```mermaid
classDiagram
    class RuntimeAPI {
        +run(plan, driver, scientific_model=None) RunResult
    }

    class ScientificModelResolver {
        <<interface>>
        +capabilities() CapabilityDescriptor[]
        +resolve(request) ModelResult
    }

    class NoScientificModelResolver {
        +capabilities() CapabilityDescriptor[]
        +resolve(request) ModelResult
    }

    class RegistryScientificModelResolver {
        -providers
        +capabilities() CapabilityDescriptor[]
        +resolve(request) ModelResult
    }

    class ScientificModelProvider {
        <<interface>>
        +descriptor() ProviderDescriptor
        +resolve(request) ModelResult
    }

    class BuiltinMaterialRulebookProvider {
        +descriptor() ProviderDescriptor
        +resolve(request) ModelResult
    }

    class ProviderDescriptor {
        +provider_id
        +provider_version
        +capabilities
        +deterministic
    }

    class CapabilityDescriptor {
        +capability
        +contract_version
        +lifecycle
    }

    class ModelRequest {
        +request_id
        +capability
        +contract_version
        +lifecycle
        +seed
        +payload
    }

    class ModelResult {
        +status
        +proposal
        +provenance
        +assumptions
        +uncertainty
        +diagnostics
    }

    class ScientificEffectValidator {
        <<kernel-private>>
        +validate(request, result) ValidatedEffect
    }

    RuntimeAPI --> ScientificModelResolver : injects
    NoScientificModelResolver ..|> ScientificModelResolver
    RegistryScientificModelResolver ..|> ScientificModelResolver
    RegistryScientificModelResolver o-- ScientificModelProvider : explicit capability binding
    BuiltinMaterialRulebookProvider ..|> ScientificModelProvider
    RegistryScientificModelResolver o-- BuiltinMaterialRulebookProvider : default material binding
    ScientificModelProvider --> ProviderDescriptor
    ProviderDescriptor o-- CapabilityDescriptor
    ScientificModelResolver --> ModelRequest
    ScientificModelResolver --> ModelResult
    ModelResult --> ScientificEffectValidator : proposed effect only
```

The public composition surface is intentionally small:

```python
result = run(
    plan=plan,
    driver=driver,
    scientific_model=resolver,  # optional
)
```

The stable provider-facing protocol is synchronous in Phase 1. A remote or
container adapter implements the same protocol and owns transport details.

```python
class ScientificModelResolver(Protocol):
    def capabilities(self) -> tuple[CapabilityDescriptor, ...]: ...
    def resolve(self, request: ModelRequest) -> ModelResult: ...


class ScientificModelProvider(Protocol):
    @property
    def descriptor(self) -> ProviderDescriptor: ...
    def resolve(self, request: ModelRequest) -> ModelResult: ...
```

Capability identifiers and contract versions are separate. The first binding
uses `capability="material.separation_fate"` and `contract_version="1.0"`;
the version is not embedded into the capability name.

### Common Request Envelope

| Field | Contract |
| --- | --- |
| `request_id` | Stable identifier for one resolution attempt within a run |
| `capability` | Names the requested scientific effect family |
| `contract_version` | Selects the typed payload/result schema |
| `lifecycle` | `runtime_precommit`, with future planning and post-run values reserved |
| `seed` | Optional deterministic seed selected by the runtime policy |
| `payload` | Immutable capability-specific semantic facts; never a mutable runtime object |

### Common Result Envelope

| Field | Contract |
| --- | --- |
| `status` | `resolved`, `not_applicable`, or `failed` |
| `proposal` | Capability-specific proposed effect; required only for `resolved` |
| `provenance` | Model ID, model version, provider ID, and optional calibration/dataset digest |
| `assumptions` | Explicit assumptions used by the provider |
| `uncertainty` | Optional typed interval, confidence, or provider-specific uncertainty record |
| `diagnostics` | Structured provider diagnostics; they do not directly become committed runtime diagnostics |

`rejected` is not a provider status. Rejection belongs to the kernel validator:
the provider may successfully produce a result that the kernel rejects as
out of bounds, non-conserving, incompatible with the operation contract, or
otherwise invalid.

### First Capability: `material.separation_fate`

The request contains every non-authored scientific fate candidate. Components
already owned by a validated author `component_fates` rule are resolved before
the resolver. The built-in Reference Rulebook is the default provider for the
remaining candidates; it is not a second fallback layer after the resolver.

| Request fact | Meaning |
| --- | --- |
| Operation descriptor | Separation program kind and complete declared arguments |
| Output contract | Stable part IDs plus semantic meanings such as `supernatant` and `pellet` |
| Environment | Declared thermal, duration, field, and other relevant execution facts |
| Component snapshot | Content ID, canonical kind/type, closed recognized attrs, native quantity axis, and quantity |
| Physical relationship | Association, accessibility, preservation state, and their provenance |
| Optional model context | Explicit calibration/device facts supplied by runtime configuration, not inferred from names |

The Phase 1 proposal is deliberately narrow:

```text
SeparationFateProposal
  component_fates[]
    component_id
    part_fractions[]
      part_id
      fraction
```

Every proposed component must exist in the request, every part ID must exist in
the output contract, each fraction must be finite and within `[0, 1]`, and the
fractions for one component must sum to `1` within the kernel tolerance. Loss,
new material identities, and state transformation are later capability versions
or separate capabilities; they are not implicit fields in the first contract.

Provider selection is explicit in Phase 1: one configured provider per
capability. The built-in Reference Rulebook is the default binding. An external
provider may replace it, and a chain, fallback, or ensemble is itself one
explicitly configured provider. This avoids hidden priority rules and makes run
reproduction depend only on recorded configuration and provenance.

The response path preserves current precedence:

```text
author rule
  -> provider selected by resolver
       default: built-in Reference Rulebook provider
       custom: external or composite provider
  -> explicit unresolved diagnostic
```

Provider exceptions are contained by the resolver and converted to `failed`.
A `not_applicable`/`failed` response does not trigger an implicit second
provider. A configured composite provider owns any desired fallback to the
built-in Rulebook. Otherwise runtime produces the documented unresolved
diagnostic without mutation.

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
    Family["Choose execution family:<br/>built-in, internal material,<br/>or driver-backed step"]
    BuiltIn["Run built-in runtime behavior:<br/>local assign, member assign, append,<br/>repeat body execution, break/continue"]
    InternalMaterial["Apply runtime-only material step<br/>without driver dispatch"]
    Preflight["Preflight material update on a working copy;<br/>resolve count aliquots to physical volume"]
    DriverPath["Check capability and execute driver<br/>with resolved physical transfer arguments"]
    Material["On driver success, commit preflight state;<br/>record material and observation artifacts"]
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
    Family -->|internal material step| InternalMaterial
    Family -->|driver-backed step| Preflight
    BuiltIn --> Finish
    InternalMaterial --> Finish
    Preflight -->|material error| Finish
    Preflight -->|valid resolved step| DriverPath
    Material --> Finish
    DriverPath -->|driver success| Material
    DriverPath -->|driver error| Finish
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
                H->>Mat: preflight apply_step(step, working material state)
                Mat-->>H: diagnostics, delta, resolved count aliquot, candidate state
                H->>Driver: check(resolved physical step)
                H->>Driver: execute(resolved physical step)
                H->>Session: commit candidate material state on driver success
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
| `dispatch into built-in, internal-material, or driver-backed execution path` | Keep runtime-only material finalization outside the physical driver boundary. | step dispatcher / concrete handlers |
| `execute step-family behavior` | Perform local/control/repeat logic, internal material logic, or material-preflight plus driver execution. | concrete runtime handlers |
| `apply material, observation, protocol-output, and cache effects` | Push cross-cutting execution side effects into dedicated services. | material compute, observation recorder, protocol-output recorder, ref cache updater |
| `record terminal status, diagnostics, history, and events` | Close the step with one consistent terminal outcome. | runtime session / final recorder logic |

## Material Compute `sep` Detail Flowchart

This flowchart expands the `runtime/material_compute.py::apply_step` boundary
for `sep` operations. It documents the Runtime/model handoff and the current
staged migration boundary.

```mermaid
flowchart TB
    Start(["apply_step(step, material_state)"])
    Op{"step.op == sep?"}
    Other["Dispatch to other material op handler:<br/>AllocContainer, DefineContent, LoadContent,<br/>Mutation, frac, or no-op"]
    Resolve["Resolve sep args:<br/>sample, bind name, program call"]
    Program["Read program kind:<br/>centrifuge, filtration, centrifugal filtration,<br/>phase partition, precipitation, magnetic, disrupt, field"]
    Slots["Determine output slot contract:<br/>group[0] / group[1] semantic names"]
    Identity["Apply identity policy:<br/>centrifuge keep_source may reuse source container"]
    Separation["material.separation<br/>single application boundary"]
    Gate{"scientific-model path migrated?"}
    ResolveEffect["Resolve typed material effect:<br/>built-in or replacement scientific provider"]
    Legacy["material.partition<br/>temporary compatibility strategy"]
    Project["Runtime projects candidate:<br/>quantities, state, conservation"]
    Bind["Bind indexed group:<br/>bind[0] and bind[1] to output container ids"]
    Delta["Return MaterialUpdateResult:<br/>updated material_state, diagnostics, delta"]

    Start --> Op
    Op -->|no| Other
    Op -->|yes| Resolve
    Resolve --> Program
    Program --> Slots
    Slots --> Identity
    Identity --> Separation
    Separation --> Gate
    Gate -->|centrifuge or filtration| ResolveEffect
    Gate -->|not yet| Legacy
    ResolveEffect --> Project
    Legacy --> Bind
    Project --> Bind
    Bind --> Delta
```

Current implementation note:

1. `Program` reads `program_kind`.
2. `centrifugal_filtration_program(..., drive=..., duration=...)` is a distinct
   program kind whose slot contract remains filtrate / retentate.
3. `Identity` handles `centrifuge_program(..., keep_source=...)` source-container
   reuse.
4. `material.separation.apply_separation_material(...)` is the only application
   entry used by ordinary `sep` and the compatibility `source.partition(...)`
   syntax.
5. Centrifuge and both filtration programs enter the injected scientific-model
   adapter and return one immutable `ResolvedMaterialEffect`; Runtime projects
   and commits it inside `material.separation`.
6. Other `sep` programs temporarily delegate from `material.separation` to the
   legacy strategy registry in `material.partition` until
   their authoritative typed operation facts and Rulebook rules are complete.
7. Legacy volume/mass-only state
   retains conservative bulk accounting. When dimensioned cell-count content is
   present, volume-bearing component quantities determine bulk volume while
   count-bearing quantities remain outside capacity accounting. Without an
   explicit mass-bearing component quantity, output bulk mass follows the
   partitioned carrier-volume ratio. When explicit volume and mass quantities
   coexist, each explicit axis is applied first and the remaining legacy
   cross-axis bulk proxy follows the opposite explicit axis. Total source bulk
   volume and mass remain conserved. The partition delta records the selected
   bulk-quantity policy.

## Current `sep` Migration Boundary

Centrifuge and both filtration programs no longer have Runtime strategies.
Their scientific decisions cross one typed boundary; Runtime retains only
projection, validation, and commit. The remaining strategy registry is
compatibility-only and is deleted after the corresponding programs have
authoritative provider rules.

```mermaid
flowchart TB
    Apply["apply_step"]
    Sep["_apply_sep orchestration"]
    Separation["material.separation<br/>apply_separation_material"]
    Gate{"program migrated?"}
    Adapter["ScientificModelPartitionAdapter"]
    Effect["ResolvedMaterialEffect"]
    Project["generic Runtime projection<br/>+ validation + commit"]
    Legacy["material.partition<br/>compatibility only"]
    Registry["SepPartitionStrategy registry"]
    Default["SepPartitionStrategy<br/>unknown fallback"]
    Phase["PhasePartitionStrategy<br/>target_phase / other_phase"]
    Precip["PrecipitationPartitionStrategy<br/>precipitate / supernatant"]
    Magnetic["MagneticPartitionStrategy<br/>bound / flowthrough"]
    Disrupt["DisruptPartitionStrategy<br/>lysate / debris_or_residue"]
    Field["FieldPartitionStrategy<br/>target_band / non_target"]
    Result["SepPartitionResult:<br/>slot containers, component deltas,<br/>cellular output state, diagnostics,<br/>binding metadata"]

    Apply --> Sep
    Sep --> Separation
    Separation --> Gate
    Gate -->|centrifuge or filtration| Adapter
    Adapter --> Effect --> Project --> Result
    Gate -->|not yet migrated| Legacy
    Legacy --> Registry
    Registry -->|unknown or unsupported| Default
    Registry -->|phase_partition_program| Phase
    Registry -->|precipitation_program| Precip
    Registry -->|magnetic_program| Magnetic
    Registry -->|disrupt_program| Disrupt
    Registry -->|field_program| Field
    Default --> Result
    Phase --> Result
    Precip --> Result
    Magnetic --> Result
    Disrupt --> Result
    Field --> Result
    Result --> Separation
    Separation --> Sep
```

Migration rule:

1. New scientific behavior enters only through the resolver/adapter port.
2. Program Registry is the sole owner of output-slot roles.
3. Legacy ratios are not copied into the built-in Rulebook without an accepted
   scientific rule.
4. The final state contains no Runtime scientific strategy registry and no
   program-kind feature gate.

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
