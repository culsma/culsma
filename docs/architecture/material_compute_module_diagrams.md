# Material Compute Module Diagrams

Last updated: 2026-08-24

Related runtime document:

1. [runtime_module_diagrams.md](./runtime_module_diagrams.md)

## Scope

This document isolates the runtime material-compute subsystem from the broader
runtime diagrams. The goal is to make the current material-compute structure
visible before changing its class structure further.

Material compute owns deterministic updates to the runtime material ledger. It
does not parse language source, define protocol semantics, execute physical
drivers, or shape public protocol returns. It receives a resolved `PlanStep`
and a `material_state`, then returns a `MaterialUpdateResult`.

Current responsibilities include:

1. dispatching material operations;
2. allocating containers, defining/loading content, and finalizing container
   material relationships;
3. resolving container, content, and indexed-group references;
4. resolving count-addressed cell-suspension aliquots from eligible carrier
   volume and moving volume, mass, components, and internal metadata;
5. applying `sep` and `frac` material transforms;
6. classifying content for separation partitioning;
7. checking conservation invariants;
8. distinguishing physical volume used for capacity and driver execution from
   cross-axis bulk compatibility proxies.

## Material Operation Responsibility Flowchart

This top-level flowchart shows the target lifecycle for one material runtime
step. It shows how the runtime decides what material state, if any, changes for
that step.

Read the three diagrams as nested views:

1. Material operation responsibility is the top-level apply-step lifecycle.
2. Material state change expands how a step changes material records,
   quantities, components, or indexed parts.
3. The separation outcome activity diagram expands how `sep` derives and
   records indexed container contents.

```mermaid
flowchart TB
    Start(["Start material update for one runtime step"])
    Frame["Prepare a working copy<br/>of the current material state"]
    ReadStep["Read what the step is trying to do<br/>to containers or material"]
    ChangesMaterial{"Does this step change<br/>material state?"}
    PickChange["Decide what kind of<br/>material state change is needed"]
    ApplyChange["Apply the material state change<br/><br/>container records, volume, mass,<br/>components, or indexed parts<br/>(expanded in Flowchart 2)"]
    Finalize["Build diagnostics and delta"]
    Conservation["Check material totals<br/>when conservation should hold"]
    Return["Return material state,<br/>diagnostics, and material delta"]

    Start --> Frame
    Frame --> ReadStep
    ReadStep --> ChangesMaterial
    ChangesMaterial -->|yes| PickChange
    PickChange --> ApplyChange
    ChangesMaterial -->|no| Finalize
    ApplyChange --> Finalize
    Finalize --> Conservation
    Conservation --> Return
```

Design goal:

- `MaterialCompute` owns apply-step orchestration and conservation gating.
- `MaterialStateManager` is the single target owner for material-state changes
  after the step has been interpreted.
- `MaterialStateManager` decides whether the step changes container records,
  volume, mass, components, indexed parts, or no material state.
- Reusable behavior is represented by public material services, not
  cross-module imports of underscore-prefixed helper functions.
- `MaterialIndexedPartsStateManager` is an internal collaborator for partitioned or
  indexed container contents. It is not a top-level material-operation branch.
- Separation strategy remains a separate inheritance family because each
  separation program owns a different slot contract and component-fate policy.
  It is a strategy collaborator used while applying separation or
  fractionation, not a top-level material-operation branch.

## Material State Change Flowchart

This flowchart expands the material-state change box from the top-level
material operation flowchart. It shows the target manager deciding and applying
the material change needed by the current step.

```mermaid
flowchart TB
    Step(["Apply the material state change"])
    Action{"What kind of material<br/>state changes?"}

    ContainerRecord["Container or content record:<br/>create a container, define content,<br/>load material, finalize relationships,<br/>or add annotations"]
    ContainerApply["Write container/content records;<br/>FinalizeContainerContents may derive<br/>a cell-suspension carrier + relation"]

    QuantityComposition["Quantity or composition:<br/>resolve volume, mass, or cells;<br/>move components and metadata"]
    QuantityApply["Count request: validate suspension,<br/>resolve carrier volume + component ratio;<br/>move bulk through ledger primitives"]

    SepFrac["Separation or fractionation:<br/>create tracked output parts"]
    Partition["Decide output parts,<br/>component fate, part quantities,<br/>and any preservation condition<br/>(expanded in the activity diagram below)"]
    Materialize["Use ledger primitives<br/>to materialize the output parts"]
    RecordPartition["Record active indexed parts"]

    Select["Indexed part access:<br/>choose one recorded part"]
    Validate["Validate the selected part<br/>and any preservation condition"]
    SelectionImpact["Move, preserve, clear,<br/>or report a diagnostic"]

    Reset["Mixing, resuspension, or reset:<br/>discard tracked parts"]
    ResetImpact["Mark parts mixed<br/>or clear indexed state"]

    Return["Return updated material state,<br/>diagnostics, and delta"]

    Step --> Action

    Action -->|container/content record| ContainerRecord
    ContainerRecord --> ContainerApply
    ContainerApply --> Return

    Action -->|volume, mass, or components| QuantityComposition
    QuantityComposition --> QuantityApply
    QuantityApply --> Return

    Action -->|separate or fractionate| SepFrac
    SepFrac --> Partition
    Partition --> Materialize
    Materialize --> RecordPartition
    RecordPartition --> Return

    Action -->|indexed part access| Select
    Select --> Validate
    Validate --> SelectionImpact
    SelectionImpact --> Return

    Action -->|mix, resuspend, or reset parts| Reset
    Reset --> ResetImpact
    ResetImpact --> Return

```

Design judgment:

1. This flowchart is entered only after the top-level flow has decided that the
   step changes material state.
2. Container records, quantities, components, and indexed parts are all material
   state, so the target flow routes them through the same state-change manager.
3. `sep` and `frac` create tracked output parts and attach any preservation
   condition required by later indexed part access.
4. `container.contents[i]` consumes an indexed part. It must validate any
   preservation condition declared by that state before moving or preserving
   material.
5. Mixing, resuspension, and equivalent reset operations intentionally discard
   tracked parts instead of validating them.
6. Preservation checks are scoped to the source, target, group members, wells,
   or shared environment affected by the current operation. They should not scan
   unrelated material state.
7. `suspension.py` owns the runtime policy, implicit-carrier provenance,
   dispersion relationships, and relationship refresh after movement or
   partitioning. It does not add a new content kind.

## Separation Outcome UML Activity Overview

The overview shows the sequential calculation boundary. The following four
activity diagrams expand every major action without depending on implementation
module names.

```mermaid
stateDiagram-v2
    direction TB

    [*] --> ResolveContract
    state "Resolve the operation contract<br/>(Detail A)" as ResolveContract
    state ContractChoice <<choice>>
    ResolveContract --> ContractChoice

    state "Initialize content iteration" as InitializeIteration
    ContractChoice --> InitializeIteration : [contract is usable]
    ContractChoice --> FailureMerge : [contract is invalid]
    InitializeIteration --> ContentChoice

    state ContentChoice <<choice>>
    ContentChoice --> ResolveFate : [an unprocessed content remains]
    ContentChoice --> FinalizeResult : [all contents are evaluated]

    state "Resolve one content's physical fate<br/>(Detail B)" as ResolveFate
    state FateChoice <<choice>>
    ResolveFate --> FateChoice
    FateChoice --> AllocateQuantity : [fate is resolved or safely conservative]
    FateChoice --> FailureMerge : [state or constraints contradict]

    state "Allocate the content's quantities<br/>(Detail C)" as AllocateQuantity
    state AllocationChoice <<choice>>
    AllocateQuantity --> AllocationChoice
    AllocationChoice --> ContentChoice : [allocation is valid]
    AllocationChoice --> FailureMerge : [allocation is invalid]

    state "Finalize and validate all resulting parts<br/>(Detail D)" as FinalizeResult
    state FinalChoice <<choice>>
    FinalizeResult --> FinalChoice
    FinalChoice --> Record : [all invariants hold]
    FinalChoice --> FailureMerge : [an invariant fails]

    state FailureMerge <<choice>>
    state "Record the resulting indexed parts" as Record
    state "Reject the result and<br/>report a diagnostic" as Reject
    FailureMerge --> Reject
    Record --> [*]
    Reject --> [*]
```

### Detail A: Operation Contract Resolution

This activity determines what the operation means physically before any
content quantity is routed.

```mermaid
stateDiagram-v2
    direction TB

    [*] --> ReadDescription
    state "Read the complete operation description" as ReadDescription
    state "Validate required operation conditions<br/>and normalize declared values" as ValidateDescription
    ReadDescription --> ValidateDescription

    state DescriptionChoice <<choice>>
    ValidateDescription --> DescriptionChoice
    DescriptionChoice --> DefineParts : [description is supported]
    DescriptionChoice --> FailureMerge : [required information is invalid]

    state "Define each resulting part's<br/>physical and semantic meaning" as DefineParts
    state "Identify transport mechanisms:<br/>phase movement, size, affinity,<br/>field, density, or disruption" as IdentifyTransport
    state "Identify retention mechanisms:<br/>surface, support, boundary,<br/>pellet, membrane, or field" as IdentifyRetention
    state "Identify conditions that must remain true<br/>for a retained state to stay valid" as IdentifyPreservation
    DefineParts --> IdentifyTransport
    IdentifyTransport --> IdentifyRetention
    IdentifyRetention --> IdentifyPreservation

    state SufficiencyChoice <<choice>>
    IdentifyPreservation --> SufficiencyChoice
    SufficiencyChoice --> CompleteContract : [conditions determine safe routing]
    SufficiencyChoice --> ConservativeContract : [safe conservative behavior exists]
    SufficiencyChoice --> FailureMerge : [no safe interpretation exists]

    state "Record part meanings, movement rules,<br/>retention rules, and preservation conditions" as CompleteContract
    state "Record conservative movement rules<br/>and an uncertainty diagnostic" as ConservativeContract
    state FailureMerge <<choice>>
    state "Reject the operation contract<br/>and report a diagnostic" as Reject
    FailureMerge --> Reject
    CompleteContract --> [*]
    ConservativeContract --> [*]
    Reject --> [*]
```

### Detail B: Per-Content Physical Fate

This activity resolves one content independently of its quantity dimension.
Count, volume, and mass describe amount; they do not by themselves establish
whether the content is mobile or retained.

```mermaid
stateDiagram-v2
    direction TB

    [*] --> ReadFacts
    state "Read physical form, association,<br/>accessibility, preservation state,<br/>classification, and declared fate rules" as ReadFacts

    state ExplicitRuleChoice <<choice>>
    ReadFacts --> ExplicitRuleChoice
    ExplicitRuleChoice --> ValidateExplicitRule : [an explicit fate rule exists]
    ExplicitRuleChoice --> CheckAssociation : [no explicit fate rule exists]

    state "Validate the explicit rule against<br/>part meanings, ratio bounds,<br/>and quantity conservation" as ValidateExplicitRule
    state ExplicitRuleValidity <<choice>>
    ValidateExplicitRule --> ExplicitRuleValidity
    ExplicitRuleValidity --> ApplyExplicitRule : [rule is valid]
    ExplicitRuleValidity --> FailureMerge : [rule contradicts constraints]
    state "Use the explicit content-fate rule" as ApplyExplicitRule

    state "Determine whether the content is free<br/>or associated with a surface, support,<br/>particle, boundary, or other material" as CheckAssociation
    state AssociationChoice <<choice>>
    CheckAssociation --> AssociationChoice
    AssociationChoice --> EvaluateAssociation : [content has a known association]
    AssociationChoice --> EvaluateTransport : [content is known to be free]
    AssociationChoice --> EvaluateTransport : [no retained association is declared]

    state "Compare the association with the operation's<br/>release, retention, and preservation rules" as EvaluateAssociation
    state AssociationEffect <<choice>>
    EvaluateAssociation --> AssociationEffect
    AssociationEffect --> EvaluateTransport : [operation explicitly releases the association]
    AssociationEffect --> KeepAssociated : [operation preserves the association and required conditions hold]
    AssociationEffect --> FailureMerge : [a required preservation condition is violated]
    AssociationEffect --> ConservativeRoute : [operation effect on association is unspecified]

    state "Keep content with the part<br/>that preserves its association" as KeepAssociated

    state "Compare the free content's physical form<br/>with the operation's transport mechanisms" as EvaluateTransport
    state TransportChoice <<choice>>
    EvaluateTransport --> TransportChoice
    TransportChoice --> ApplySelection : [a declared selection mechanism applies]
    TransportChoice --> FollowPhase : [otherwise, content follows a moving phase]
    TransportChoice --> KeepImmobile : [otherwise, physical form is immobile]
    TransportChoice --> ConservativeRoute : [mobility cannot be determined]

    state "Route content according to the<br/>declared selection mechanism" as ApplySelection
    state "Route content with<br/>the moving phase" as FollowPhase
    state "Keep content with the<br/>stationary or residual part" as KeepImmobile
    state "Use a conservative fate<br/>and emit an uncertainty diagnostic" as ConservativeRoute

    state FateMerge <<choice>>
    ApplyExplicitRule --> FateMerge
    KeepAssociated --> FateMerge
    ApplySelection --> FateMerge
    FollowPhase --> FateMerge
    KeepImmobile --> FateMerge
    ConservativeRoute --> FateMerge

    state "Produce an ideal per-part fate<br/>and the resulting association,<br/>accessibility, and preservation states" as ProduceFate
    FateMerge --> ProduceFate
    ProduceFate --> [*]

    state FailureMerge <<choice>>
    state "Reject this content fate<br/>and report a diagnostic" as Reject
    FailureMerge --> Reject
    Reject --> [*]
```

The association path is the implemented decision boundary. It compares
the complete operation contract from Detail A with the content's association
and preservation state. The quantity axis is carried forward for accounting,
but it does not select the retained or mobile branch.

An author may override the reference fate for a named content at the `sep`
boundary. Output names come from the selected program's part contract; both
outputs are required and their ratios must sum to 100%.

```culsma
let parts = sep(
  sample = source,
  program = filtration_program(membrane = "0.2um", drive = "pressure"),
  component_fates = {
    RPE1: { filtrate: 25%, retentate: 75% }
  }
);
```

| Fate source precedence | Meaning |
| --- | --- |
| author-declared content fate | Exact conservative split supplied by the protocol author |
| preserved or released association | Deterministic consequence of the operation contract |
| reference transport prediction | Default split for freely mobile classified content |
| conservative unresolved fate | Equal split plus an uncertainty diagnostic |

### Detail C: Per-Content Quantity Allocation

This activity converts the physical fate into quantities while preserving the
content's authoritative quantity axis.

```mermaid
stateDiagram-v2
    direction TB

    [*] --> ReadQuantity
    state "Read the authoritative quantity axis<br/>and source amount" as ReadQuantity
    state "Apply the ideal per-part fate<br/>on that same quantity axis" as ApplyIdealFate
    ReadQuantity --> ApplyIdealFate

    state PredictionChoice <<choice>>
    ApplyIdealFate --> PredictionChoice
    PredictionChoice --> ApplyPrediction : [an applicable prediction is configured]
    PredictionChoice --> PredictionMerge : [no prediction is configured]

    state "Apply explicit recovery, loss,<br/>and carryover estimates with provenance" as ApplyPrediction
    state PredictionValidity <<choice>>
    ApplyPrediction --> PredictionValidity
    PredictionValidity --> PredictionMerge : [prediction is valid]
    PredictionValidity --> FailureMerge : [prediction is invalid or out of range]

    state PredictionMerge <<choice>>
    state "Calculate each part's amount<br/>on the native count, volume, or mass axis" as CalculateNativeAmounts
    PredictionMerge --> CalculateNativeAmounts

    state "Derive only permitted bulk compatibility values<br/>from explicit volume or mass and valid carrier relations" as DeriveBulk
    CalculateNativeAmounts --> DeriveBulk

    state "Check non-negative amounts, ratio bounds,<br/>axis consistency, and explicit loss accounting" as ValidateAllocation
    DeriveBulk --> ValidateAllocation

    state AllocationValidity <<choice>>
    ValidateAllocation --> AllocationValidity
    AllocationValidity --> [*] : [allocation is valid]
    AllocationValidity --> FailureMerge : [allocation is invalid]

    state FailureMerge <<choice>>
    state "Reject this allocation<br/>and report a diagnostic" as Reject
    FailureMerge --> Reject
    Reject --> [*]
```

### Detail D: Aggregate Result Finalization

This activity validates the complete separation result before it becomes
container-owned indexed contents.

```mermaid
stateDiagram-v2
    direction TB

    [*] --> AssembleParts
    state "Assemble all routed contents<br/>into the defined resulting parts" as AssembleParts
    state "Apply resulting association,<br/>accessibility, and preservation states" as ApplyStates
    AssembleParts --> ApplyStates

    state "Compare source and result totals<br/>independently on count, volume, and mass axes" as CheckConservation
    ApplyStates --> CheckConservation

    state ConservationChoice <<choice>>
    CheckConservation --> ConservationChoice
    ConservationChoice --> CheckOrganization : [outputs plus explicit loss equal the source]
    ConservationChoice --> FailureMerge : [material is created or disappears without an explicit loss]

    state "Check part meanings, component placement,<br/>state consistency, and preservation requirements" as CheckOrganization
    state ResultChoice <<choice>>
    CheckOrganization --> ResultChoice
    ResultChoice --> Record : [result is internally consistent]
    ResultChoice --> FailureMerge : [result is inconsistent]

    state "Record the active indexed contents<br/>as the result of this separation" as Record
    state FailureMerge <<choice>>
    state "Reject the complete result without<br/>committing partial material changes" as Reject
    FailureMerge --> Reject
    Record --> [*]
    Reject --> [*]
```

Design judgment:

1. Separation planning receives the complete operation conditions, not only a
   broad separation category.
2. Quantity dimension does not decide mobility. A count-bearing cell component
   may be suspended, pelleted, surface-associated, or otherwise immobilized.
3. Association and accessibility decide whether the operation may move a
   component. A preserved association follows the retaining part by default; a
   prediction model may later add explicit loss.
4. The same separation outcome determines each part's physical state. Solid or
   retained parts must not become transferable suspensions merely because
   residual liquid exists.
5. Concentration uses eligible carrier component quantities. Aggregate
   `container.volume_uL` remains the compatibility bulk ledger and may include
   cross-axis proxy volume.
6. Bulk quantity accounting remains separate from component fate ratios, but
   both belong to the same separation outcome. Dimensioned component
   quantities are authoritative. Any remaining legacy bulk contribution is
   preserved as a cross-axis proxy: mass residual follows partitioned carrier
   volume, while volume residual follows partitioned explicit mass. This covers
   mixed count/volume/mass state without losing bulk totals; insufficient
   information retains the conservative fallback.
7. Indexed contents are projections of the recorded separation outcome;
   indexed access must not rerun or reinterpret the separation model.

## Material Operation Sequence

Read the three sequence diagrams as nested views:

1. Material operation sequence is the top-level target runtime dispatch path.
2. Material state change sequence expands
   `MaterialStateManager.apply_change(...)`.
3. Separation implementation detail shows how the complete program description,
   content state, and optional author fate reach native-axis allocation.

```mermaid
sequenceDiagram
    participant Executor as "runtime.executor.RuntimeExecutor"
    participant StepDispatcher as "runtime.steps.RuntimeStepDispatcher"
    participant DriverHandler as "runtime.steps.DriverBackedStepHandler"
    participant Driver as "driver.base.Driver"
    participant MaterialFacade as "runtime.material_compute.apply_step"
    participant Compute as "material.compute.MaterialCompute"
    participant StateManager as "material.state.MaterialStateManager"

    Executor->>StepDispatcher: dispatch(step, session)
    StepDispatcher->>DriverHandler: handle(step, session)
    DriverHandler->>DriverHandler: execute_current_step(step, session, state)
    DriverHandler->>Driver: check(runtime_step)
    DriverHandler->>Driver: execute(runtime_step)

    alt result.ok and isinstance(material_state, dict)
        DriverHandler->>MaterialFacade: apply_step(step=runtime_step, material_state=material_state)
        MaterialFacade->>Compute: apply_step(step, material_state)
    end

    Compute->>Compute: create_step_frame(step, material_state)
    Compute->>StateManager: plan_material_state_change(step, state)
    StateManager-->>Compute: MaterialStateChangePlan?

    opt change_plan is not None
        Compute->>StateManager: apply_change(change_plan, state)
        StateManager-->>Compute: MaterialUpdateResult
    end

    Compute->>Compute: finalize_result(result, step, before_totals)
    Compute-->>MaterialFacade: MaterialUpdateResult
    MaterialFacade-->>DriverHandler: MaterialUpdateResult
```

This sequence shows the target control boundary: material runtime steps enter a
single material-state manager, which decides and applies the material state
change before `MaterialCompute` builds diagnostics, conservation checks, and the
result delta.

## Material State Change Sequence

```mermaid
sequenceDiagram
    participant StateManager as "material.state.MaterialStateManager"
    participant ContainerContent as "material.container_content"
    participant Ledger as "material.ledger"
    participant Mutation as "material.mutation"
    participant PartsManager as "material.contents_state.MaterialIndexedPartsStateManager"

    StateManager->>StateManager: apply_change(change_plan, state)

    alt change_plan.kind == "container_record"
        alt step.op == "AllocContainer"
            StateManager->>ContainerContent: apply_alloc_container(step, state)
        else step.op == "DefineContent"
            StateManager->>ContainerContent: apply_define_content(step, state)
        else step.op == "LoadContent"
            StateManager->>ContainerContent: apply_load_content(step, state)
        else step.op == "AnnotateContent"
            StateManager->>ContainerContent: apply_annotate_content(step, state)
        end
    else change_plan.kind == "quantity_or_composition"
        StateManager->>Mutation: apply_mutation(step, state)
        Mutation->>Mutation: apply_transfer_by_qty(step, state, qty)
        Mutation->>Ledger: move_explicit(src, dst, volume_uL, mass_mg, component_ratio)
    else change_plan.kind == "partition_or_index"
        StateManager->>StateManager: contents_plan = change_plan.payload["contents_plan"]
        StateManager->>PartsManager: apply_partition_or_index_change(contents_plan, state)
    end

    StateManager-->>StateManager: MaterialUpdateResult
```

This sequence expands the material-state change from the top sequence. The
manager can update container records, quantities, components, partitioned or
indexed contents.

## Partition And Indexed Contents Sequence

```mermaid
sequenceDiagram
    participant PartsManager as "material.contents_state.MaterialIndexedPartsStateManager"
    participant PartsState as "material.contents_state"
    participant Partition as "material.partition"
    participant Ledger as "material.ledger"

    PartsManager->>PartsManager: apply_partition_or_index_change(transition_plan, state)

    alt step.op == "sep"
        PartsManager->>PartsManager: apply_sep(step, state)
        PartsManager->>PartsManager: record_sep_transition(step=step, state=working, source_id=source_id, program_kind=program_kind, keep_source=keep_source)
        PartsManager->>Partition: partition_sep_material(state=state, source=source, slot0=slot0, slot1=slot1, program_kind=program_kind)
        PartsManager->>PartsState: record_partitioned_contents_state(state=state, source_id=source_id, source=source, parts={"0": slot0, "1": slot1}, kind="partitioned", producer_op="sep", program_kind=program_kind, slot_contract=partition.get("slot_contract"), preservation_contract=partition.get("preservation_contract"), step_id=step.step_id)
        PartsManager->>PartsState: remove_transient_containers(state, [slot0_id, slot1_id], preserve=source_id)
    else step.op == "frac"
        PartsManager->>PartsManager: apply_frac(step, state)
        PartsManager->>PartsManager: record_frac_transition(step=step, state=working, source_id=source_id, bins=bins, program_kind=program_kind)
        PartsManager->>Ledger: move_explicit(source, slot, moved_volume, moved_mass, component_ratio=component_ratio)
        PartsManager->>PartsState: record_partitioned_contents_state(state=state, source_id=source_id, source=source, parts=concrete_parts, kind="fractionated", producer_op="frac", program_kind=program_kind, slot_contract={slot: f"fraction_{slot}" for slot in slot_bindings}, preservation_contract=None, step_id=step.step_id)
        PartsManager->>PartsState: remove_transient_containers(state, list(slot_bindings.values()), preserve=source_id)
    else step.op == "Mutation" and is_contents_index_ref(source_ref)
        PartsManager->>PartsManager: apply_mutation_transition(step, state)
        PartsManager->>PartsManager: resolve_indexed_part(step=step, state=state, contents_ref=contents_ref)
        alt isinstance(selection, MaterialUpdateResult)
            PartsManager-->>PartsManager: MaterialUpdateResult
        else isinstance(selection, ContentsPartSelection)
            PartsManager->>Ledger: container(state, selection.source_id)
            PartsManager->>Ledger: container(state, target_id)
            PartsManager->>Ledger: check_capacity_guard(step=step, state=state, container_id=target_id, added_uL=moved_uL)
            PartsManager->>PartsManager: move_contents_part_material(part, source, target, moved_uL, moved_mg, ratio)
            PartsManager->>PartsState: moved_snapshot_from_explicit(part_before, moved_uL=moved_uL, moved_mg=moved_mg, ratio=ratio)
            PartsManager->>PartsManager: record_target_addition_impact(step=step, state=state, target_id=target_id, moved_snapshot=moved_snapshot)
        end
    else step.op == "Mutation" and has_active_contents_state(source_id, target_id)
        PartsManager->>PartsManager: apply_mutation_transition(step, state)
        PartsManager->>PartsManager: record_target_addition_impact(step=step, state=state, target_id=target_id, moved_snapshot=moved_snapshot)
        PartsManager->>PartsState: invalidate_contents_state(state, source_id, reason=reason)
    else step.op == "agit"
        PartsManager->>PartsState: mark_contents_state_mixed(state, container_id, step_id=step.step_id)
    end
```

This sequence is the target partition and indexed-part path. `sep`, `frac`,
indexed-part access, and tracked-part reset enter
`MaterialIndexedPartsStateManager` only after `MaterialStateManager` has selected
that kind of material-state change.

## Current Separation Implementation Gap

```mermaid
sequenceDiagram
    participant PartsManager as "material.contents_state.MaterialIndexedPartsStateManager"
    participant Partition as "material.partition"
    participant Registry as "material.partition.SepPartitionStrategyRegistry"
    participant Strategy as "material.partition.SepPartitionStrategy"
    participant Classes as "material.partition.ContentClassResolver"
    participant Fate as "material.separation_fate"
    participant Ledger as "material.ledger"

    PartsManager->>Partition: partition_sep_material(state, source, slot0, slot1, program, explicit_fates)
    Partition->>Registry: strategy_for(program_kind)
    Registry-->>Partition: SepPartitionStrategy
    Partition->>Fate: resolve operation contract from complete program and slot meanings
    Fate-->>Partition: movement, retention, release, and preservation rules

    loop for name, amount in list(source_components.items())
        Partition->>Classes: classify(state, source, str(name))
        Classes-->>Partition: PartitionClass
        Partition->>Fate: resolve physical state and author override
        Partition->>Strategy: ratios(partition_class)
        Partition->>Fate: resolve content fate using precedence contract
        Fate-->>Partition: slot ratios and provenance
        Partition->>Partition: allocate authoritative count, volume, or mass quantity
        Partition->>Strategy: output_class(partition_class, slot="0")
        Partition->>Strategy: output_class(partition_class, slot="1")
    end

    Partition->>Ledger: set each slot's component quantities on their native axes
    Partition->>Partition: normalize permitted bulk compatibility quantities and validate conservation
    Partition->>Ledger: set_container_material(source, volume_uL=0.0, mass_mg=0.0, components={})
    Partition->>Strategy: preservation_contract()
    Partition-->>PartsManager: parts, fate provenance, operation contract, and diagnostics
```

The implementation now retains the complete operation description through fate
resolution. Indexed contents record the resulting parts and serve projections;
they do not rerun the separation decision.

## Target Module Boundaries

The target structure should keep material state management as a real module, not
as helper functions embedded in operation modules:

| Module | Owns | Must not own |
| --- | --- | --- |
| `compute.py` | `MaterialCompute`, apply-step frame setup, conservation gating, result return | operation-specific material behavior |
| `state.py` | `MaterialStateManager`, `MaterialStateChangePlan`, material-state change planning, state-change dispatch | ledger primitives, partition strategy internals, runtime driver dispatch |
| `container_content.py` | container/content record updates | material-state change planning |
| `mutation.py` | mutation transform and mutation source dispatch | top-level material-state change planning |
| `partition.py` | `SepPartitionStrategyRegistry`, `SepPartitionStrategy`, content partition classification | runtime operation lifecycle |
| `contents_state.py` | `MaterialIndexedPartsStateManager`, indexed part records, selection, sep/frac partition/index application, narrow preservation impact, invalidation, and mixed-state impact | top-level material-state change planning, full runtime step dispatch, broad protocol semantics |
| `ledger.py` | volume, mass, component, and metadata mutation primitives | source-expression interpretation |
| `diagnostics.py` | material diagnostic result construction | material state mutation |
| `refs.py` | material reference resolution and binding | transfer policy |
| `args.py` | operation argument extraction and normalization | semantic operation behavior |
| `conservation.py` | material total snapshots and conservation checks | operation dispatch |

## Class Diagram

```mermaid
classDiagram
    class MaterialUpdateResult {
        +dict material_state
        +list diagnostics
        +dict delta
        +bool ok
    }

    class MaterialCompute {
        +apply_step(step, material_state) MaterialUpdateResult
    }

    class MaterialStateManager {
        +plan_material_state_change(step, state) MaterialStateChangePlan?
        +apply_change(change_plan, state) MaterialUpdateResult
    }

    class MaterialStateChangePlan {
        +str kind
        +PlanStep step
        +dict payload
    }

    class ContainerContent {
        +apply_alloc_container(step, state) MaterialUpdateResult
        +apply_define_content(step, state) MaterialUpdateResult
        +apply_load_content(step, state) MaterialUpdateResult
        +apply_annotate_content(step, state) MaterialUpdateResult
    }

    class MutationTransform {
        +apply_mutation(step, state) MaterialUpdateResult
    }

    class MutationSourceDispatcher {
        +apply(ctx) MaterialUpdateResult
    }

    class MaterialIndexedPartsStateManager {
        +apply_partition_or_index_change(plan, state) MaterialUpdateResult
        +apply_sep(step, state) MaterialUpdateResult
        +apply_frac(step, state) MaterialUpdateResult
        +apply_agit(step, state) MaterialUpdateResult
        +apply_mutation_transition(step, state) MaterialUpdateResult
        +apply_contents_index_mutation(step, state) MaterialUpdateResult
        +record_sep_transition(...) ContentsPartitionTransition | MaterialUpdateResult
        +record_frac_transition(...) ContentsPartitionTransition | MaterialUpdateResult
        +record_partitioned(...) ContentsStateSummary
        +resolve_indexed_part(...) ContentsPartSelection | MaterialUpdateResult
        +record_source_selection_impact(...) ContentsStateImpact
        +record_target_addition_impact(...) ContentsStateImpact
        +invalidate(container, reason) None
        +mark_mixed(container) ContentsStateImpact
    }

    class ContentsStateSummary {
        +str source_id
        +str kind
        +str program_kind
        +list slots
    }

    class ContentsPartitionTransition {
        +dict contents_state
        +dict partition
        +dict slot_ids
        +float split_ratio
    }

    class ContentsStateTransitionPlan {
        +str transition
        +PlanStep step
        +dict payload
    }

    class ContentsPartSelection {
        +str source_id
        +str slot
        +dict snapshot
        +dict state_record
    }

    class ContentsStateImpact {
        +str action
        +str reason
        +dict details
    }

    class MaterialDiagnostics {
        +result(step, state, code, message) MaterialUpdateResult
    }

    class MaterialLedger {
        +container(state, container_id)
        +ensure_container(state, container_id)
        +move_explicit(src, dst, volume, mass, component_ratio)
        +set_container_material(container, volume, mass, components, classes)
        +remove_ratio(source, ratio)
        +collect_unit_into_container(...)
    }

    class MaterialRefResolver {
        +resolve_container_ref(state, name)
        +resolve_target_ref(state, value)
        +resolve_source_ref(state, value, qty)
        +resolve_content_ref(state, name)
        +resolve_structured_ref(state, value)
        +bind_name(state, name, container_id, step_id)
        +bind_indexed_group(state, group, slots)
    }

    class ContentClassResolver {
        +classify(state, container, component_id) PartitionClass
    }

    class MaterialArgReader {
        +arg_string(value) str
        +arg_quantity(value) dict
        +arg_call(value) dict
        +call_arg_value(call, name) object
    }

    class MaterialConservation {
        +state_totals(state) dict
        +totals_conserved(before, after) bool
    }

    class SepPartitionStrategyRegistry {
        +strategy_for(program_kind) SepPartitionStrategy
    }

    class SepPartitionStrategy {
        +str program_kind
        +dict slot_contract
        +ratios(partition_class) tuple
        +output_class(partition_class, slot) str
    }

    class CentrifugePartitionStrategy
    class PhasePartitionStrategy
    class PrecipitationPartitionStrategy
    class FiltrationPartitionStrategy
    class CentrifugalFiltrationPartitionStrategy
    class MagneticPartitionStrategy
    class DisruptPartitionStrategy
    class FieldPartitionStrategy

    MaterialCompute --> MaterialUpdateResult
    MaterialCompute --> MaterialStateManager
    MaterialCompute --> MaterialConservation
    MaterialStateManager --> MaterialStateChangePlan
    MaterialStateManager --> ContainerContent
    MaterialStateManager --> MutationTransform
    MaterialStateManager --> MaterialIndexedPartsStateManager
    ContainerContent --> MaterialLedger
    MutationTransform --> MutationSourceDispatcher
    MutationTransform --> MaterialLedger
    MaterialIndexedPartsStateManager --> MaterialLedger
    MaterialIndexedPartsStateManager --> SepPartitionStrategyRegistry
    MaterialIndexedPartsStateManager --> ContentsStateTransitionPlan
    MaterialIndexedPartsStateManager --> ContentsPartitionTransition
    MaterialIndexedPartsStateManager --> ContentsStateSummary
    MaterialIndexedPartsStateManager --> ContentsPartSelection
    MaterialIndexedPartsStateManager --> ContentsStateImpact

    SepPartitionStrategyRegistry --> SepPartitionStrategy
    SepPartitionStrategy --> ContentClassResolver
    SepPartitionStrategy <|-- CentrifugePartitionStrategy
    SepPartitionStrategy <|-- PhasePartitionStrategy
    SepPartitionStrategy <|-- PrecipitationPartitionStrategy
    SepPartitionStrategy <|-- FiltrationPartitionStrategy
    FiltrationPartitionStrategy <|-- CentrifugalFiltrationPartitionStrategy
    SepPartitionStrategy <|-- MagneticPartitionStrategy
    SepPartitionStrategy <|-- DisruptPartitionStrategy
    SepPartitionStrategy <|-- FieldPartitionStrategy
```

## Refactor Status

The material compute refactor is in a transitional state:

1. `MaterialCompute` asks `MaterialStateManager` to plan material-state changes.
2. `MaterialCompute` calls `MaterialStateManager.apply_change(...)` only when
   the plan says the step changes material state.
3. `MaterialStateManager` dispatches concrete state changes to
   `container_content.py`, `mutation.py`, or `MaterialIndexedPartsStateManager`.
4. `MaterialIndexedPartsStateManager` is an internal collaborator for separation,
   fractionation, indexed part access, and tracked-part reset.
5. `MaterialOpDispatcher`, `MaterialOpHandler`, and the ordinary material
   update branch have been removed from this target path.
6. `SepPartitionStrategy` and its subclasses remain the second inheritance
   family, owned by partition strategy behavior.
7. Argument reading, reference resolution, ledger mutation, diagnostics, and
   conservation now live behind public service modules instead of cross-module
   imports from `support.py`.
8. `runtime/material_compute.py` remains as a compatibility facade.

Conformance rule: every stage should keep the existing material tests passing,
especially the separation program tests and DNA cleanup regression.
