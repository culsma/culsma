# Material Compute Module Diagrams

Last updated: 2026-05-09

Related runtime document:

1. [runtime_module_diagrams.md](./runtime_module_diagrams.md)

## Scope

This document isolates the runtime material-compute subsystem from the broader
runtime diagrams. The goal is to make the current 1600-line
`runtime/material_compute.py` structure visible before changing its class
structure.

Material compute owns deterministic updates to the runtime material ledger. It
does not parse language source, define protocol semantics, execute physical
drivers, or shape public protocol returns. It receives a resolved `PlanStep`
and a `material_state`, then returns a `MaterialUpdateResult`.

Current responsibilities include:

1. dispatching material operations;
2. allocating containers and defining/loading/annotating content;
3. resolving container, content, and indexed-group references;
4. moving volume, mass, components, and internal component metadata;
5. applying `sep` and `frac` material transforms;
6. classifying content for separation partitioning;
7. checking conservation invariants.

## Current Single-Module Structure

```mermaid
flowchart TB
    File["runtime/material_compute.py<br/>single 1600+ line module"]

    File --> Entry["apply_step(step, material_state)"]
    Entry --> Dispatch{"step.op"}

    Dispatch --> Alloc["_apply_alloc_container"]
    Dispatch --> Define["_apply_define_content"]
    Dispatch --> Load["_apply_load_content"]
    Dispatch --> Annotate["_apply_annotate_content"]
    Dispatch --> Mutation["_apply_mutation"]
    Dispatch --> Sep["_apply_sep"]
    Dispatch --> Frac["_apply_frac"]

    Mutation --> Transfer["_apply_transfer_by_qty<br/>_apply_transfer_volume<br/>_apply_transfer_mass"]
    Sep --> Partition["_partition_sep_material"]

    Partition --> Classes["ContentClassResolver<br/>ContentKind / ContentType / PartitionClass"]
    Partition --> Strategies["SepPartitionStrategy classes<br/>centrifuge / phase / precipitation / filtration<br/>magnetic / disrupt / field"]
    Partition --> Ledger["_set_container_material<br/>_move_explicit<br/>_container_component_classes"]

    Alloc --> Refs["reference and binding helpers"]
    Define --> Refs
    Load --> Refs
    Mutation --> Refs
    Sep --> Refs
    Frac --> Refs

    Transfer --> Ledger
    Frac --> Ledger

    Entry --> Conservation["_state_totals<br/>_totals_conserved"]
    File --> Args["IR arg helpers<br/>_arg_string / _arg_quantity / _call_arg_*"]
    File --> Units["unit, capacity, density helpers"]
```

Current issue:

- The single file is doing orchestration, operation handling, state-reference
  resolution, low-level ledger mutation, separation strategy, content
  classification, and invariant checks.
- Adding only a separate partition area would reduce the newest growth but
  would not fix the underlying class responsibility boundary.

## Current Class Structure

```mermaid
flowchart TB
    Apply["MaterialCompute<br/>apply_step orchestration"]
    Dispatcher["MaterialOpDispatcher"]
    BaseHandler["MaterialOpHandler"]

    Apply --> Dispatcher
    Dispatcher --> BaseHandler

    Apply --> Result["MaterialUpdateResult"]
    Apply --> Conservation["MaterialConservation"]

    BaseHandler --> ContainerHandler["ContainerContentHandler"]
    BaseHandler --> MutationHandler["MutationHandler"]
    BaseHandler --> SeparationHandler["SeparationHandler"]
    BaseHandler --> NoopHandler["NoopMaterialOpHandler"]

    ContainerHandler --> Args["MaterialArgReader"]
    MutationHandler --> Args
    SeparationHandler --> Args

    ContainerHandler --> Refs["MaterialRefResolver"]
    MutationHandler --> Refs
    SeparationHandler --> Refs

    ContainerHandler --> Ledger["MaterialLedger"]
    MutationHandler --> Ledger
    SeparationHandler --> Ledger

    SeparationHandler --> Partition["SepPartitionStrategyRegistry"]
    Partition --> Strategy["SepPartitionStrategy"]
    Strategy --> Classes["ContentClassResolver"]
```

Design goal:

- `MaterialCompute` owns apply-step orchestration and conservation gating.
- `MaterialOpDispatcher` maps `step.op` to a `MaterialOpHandler`.
- Each operation family owns its own handler behavior through a common base
  class.
- Low-level ledger mutation is represented as `MaterialLedger`, a shared
  service class used by handlers.
- File placement is intentionally coarse: one `runtime/material/` subpackage
  with four files, grouped by the class families below.

## Current File Grouping

```mermaid
flowchart TB
    Facade["runtime/material_compute.py<br/>compatibility facade"]
    Package["runtime/material/"]

    Facade --> ComputeFile["compute.py"]
    Package --> ComputeFile
    Package --> HandlerFile["handler.py"]
    Package --> PartitionFile["partition.py"]
    Package --> SupportFile["support.py"]

    ComputeFile --> MaterialCompute["MaterialCompute"]
    ComputeFile --> MaterialUpdateResult["MaterialUpdateResult"]
    ComputeFile --> MaterialOpDispatcher["MaterialOpDispatcher"]

    HandlerFile --> MaterialOpHandler["MaterialOpHandler"]
    HandlerFile --> ContainerContentHandler["ContainerContentHandler"]
    HandlerFile --> MutationHandler["MutationHandler"]
    HandlerFile --> SeparationHandler["SeparationHandler"]
    HandlerFile --> NoopMaterialOpHandler["NoopMaterialOpHandler"]

    PartitionFile --> SepPartitionStrategyRegistry["SepPartitionStrategyRegistry"]
    PartitionFile --> SepPartitionStrategy["SepPartitionStrategy"]
    PartitionFile --> ProgramStrategies["Centrifuge / Phase / Precipitation<br/>Filtration / Magnetic / Disrupt / Field"]
    PartitionFile --> ContentClassResolver["ContentClassResolver"]

    SupportFile --> MaterialLedger["MaterialLedger"]
    SupportFile --> MaterialRefResolver["MaterialRefResolver"]
    SupportFile --> MaterialArgReader["MaterialArgReader"]
    SupportFile --> MaterialConservation["MaterialConservation"]
```

This avoids one-file-per-class churn while still splitting the current
single-file material compute boundary into the three real behavior groups:
apply-step orchestration, step-op handling, and separation partition strategy.
Shared lower-level services stay together in `support.py` until they grow large
enough to justify further splitting.

## Current Apply-Step Flow

```mermaid
flowchart TB
    Start(["apply_step(step, material_state)"])
    Clone["Copy material_state<br/>initialize containers and bindings"]
    TotalsBefore["conservation.state_totals(before)"]
    Dispatch["MaterialOpDispatcher.handler_for(step.op)"]
    Handler["MaterialOpHandler.apply(step, state, ctx)"]

    Result{"result.ok?"}
    Conserved{"op needs conservation check<br/>and inventory check enabled?"}
    TotalsAfter["conservation.state_totals(after)"]
    Compare{"totals conserved?"}
    Error["Return MAT_CONSERVATION_VIOLATION"]
    Return["Return MaterialUpdateResult"]

    Start --> Clone
    Clone --> TotalsBefore
    TotalsBefore --> Dispatch
    Dispatch --> Handler
    Handler --> Result
    Result -->|no| Return
    Result -->|yes| Conserved
    Conserved -->|no| Return
    Conserved -->|yes| TotalsAfter
    TotalsAfter --> Compare
    Compare -->|no| Error
    Compare -->|yes| Return
```

## Separation Sequence

```mermaid
sequenceDiagram
    participant Compute as "MaterialCompute"
    participant Dispatch as "MaterialOpDispatcher"
    participant Sep as "SeparationHandler"
    participant Refs as "MaterialRefResolver"
    participant Partition as "SepPartitionStrategyRegistry"
    participant Strategy as "SepPartitionStrategy"
    participant Classes as "ContentClassResolver"
    participant Ledger as "MaterialLedger"

    Compute->>Dispatch: handler_for("sep")
    Dispatch-->>Compute: SeparationHandler
    Compute->>Sep: apply(step, state, ctx)
    Sep->>Refs: resolve sample container
    Sep->>Sep: read program kind and bind name
    Sep->>Sep: create group[0] and group[1] containers
    Sep->>Partition: strategy_for(program_kind)
    Partition-->>Sep: SepPartitionStrategy

    loop each component
        Strategy->>Classes: classify(content metadata, component id)
        Classes-->>Strategy: partition_class
        Strategy->>Strategy: ratios(partition_class)
        Strategy->>Strategy: output_class(partition_class, slot)
    end

    Strategy-->>Sep: component amounts and output classes
    Sep->>Ledger: set slot material and metadata
    Sep->>Ledger: clear source material if not reused
    Sep->>Refs: bind indexed group slots
    Sep-->>Compute: MaterialUpdateResult(delta includes partition summary)
```

This keeps the key semantic boundary: material classes are data traits;
separation programs own the behavior that interprets those traits.

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

    class MaterialOpDispatcher {
        +handler_for(op) MaterialOpHandler
    }

    class MaterialOpHandler {
        +set~str~ ops
        +apply(step, state, ctx) MaterialUpdateResult
    }

    class ContainerContentHandler {
        +set~str~ ops
        +apply(step, state, ctx) MaterialUpdateResult
        -apply_alloc_container(step, state)
        -apply_define_content(step, state)
        -apply_load_content(step, state)
        -apply_annotate_content(step, state)
    }

    class MutationHandler {
        +set~str~ ops
        +apply(step, state, ctx) MaterialUpdateResult
        -apply_transfer_by_qty(...)
        -apply_transfer_volume(...)
        -apply_transfer_mass(...)
    }

    class SeparationHandler {
        +set~str~ ops
        +apply(step, state, ctx) MaterialUpdateResult
        -apply_sep(step, state)
        -apply_frac(step, state)
    }

    class NoopMaterialOpHandler {
        +apply(step, state, ctx) MaterialUpdateResult
    }

    class MaterialLedger {
        +move_explicit(src, dst, volume, mass, component_ratio)
        +set_container_material(container, volume, mass, components, classes)
        +remove_ratio(source, ratio)
        +collect_unit_into_container(...)
    }

    class MaterialRefResolver {
        +resolve_container_ref(state, name)
        +resolve_content_ref(state, name)
        +resolve_structured_ref(state, value)
        +bind_indexed_group(state, group, slots)
    }

    class ContentClassResolver {
        +classify(state, container, component_id) PartitionClass
    }

    class MaterialArgReader {
        +arg_string(value) str
        +arg_quantity(value) dict
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
    class MagneticPartitionStrategy
    class DisruptPartitionStrategy
    class FieldPartitionStrategy

    MaterialCompute --> MaterialUpdateResult
    MaterialCompute --> MaterialOpDispatcher
    MaterialCompute --> MaterialConservation
    MaterialOpDispatcher --> MaterialOpHandler
    MaterialOpHandler <|-- ContainerContentHandler
    MaterialOpHandler <|-- MutationHandler
    MaterialOpHandler <|-- SeparationHandler
    MaterialOpHandler <|-- NoopMaterialOpHandler

    ContainerContentHandler --> MaterialArgReader
    ContainerContentHandler --> MaterialRefResolver
    ContainerContentHandler --> MaterialLedger
    MutationHandler --> MaterialArgReader
    MutationHandler --> MaterialRefResolver
    MutationHandler --> MaterialLedger
    SeparationHandler --> MaterialArgReader
    SeparationHandler --> MaterialRefResolver
    SeparationHandler --> MaterialLedger
    SeparationHandler --> SepPartitionStrategyRegistry
    SepPartitionStrategyRegistry --> SepPartitionStrategy

    SepPartitionStrategy --> ContentClassResolver
    SepPartitionStrategy <|-- CentrifugePartitionStrategy
    SepPartitionStrategy <|-- PhasePartitionStrategy
    SepPartitionStrategy <|-- PrecipitationPartitionStrategy
    SepPartitionStrategy <|-- FiltrationPartitionStrategy
    SepPartitionStrategy <|-- MagneticPartitionStrategy
    SepPartitionStrategy <|-- DisruptPartitionStrategy
    SepPartitionStrategy <|-- FieldPartitionStrategy
```

## Refactor Status

The material compute refactor is implemented with a behavior-preserving split:

1. `MaterialOpHandler` and `MaterialOpDispatcher` route material updates by
   `step.op`.
2. Container/content behavior lives in `ContainerContentHandler`.
3. Mutation and quantified transfer behavior live in `MutationHandler`.
4. `sep` and `frac` behavior live in `SeparationHandler`.
5. `SepPartitionStrategy` and its subclasses remain the second inheritance
   family, owned by separation behavior.
6. Argument reading, reference resolution, ledger mutation, and conservation
   live together in `support.py`.
7. The resulting class groups live in `runtime/material/compute.py`,
   `handler.py`, `partition.py`, and `support.py`.
8. `runtime/material_compute.py` remains as a compatibility facade.

Conformance rule: every stage should keep the existing material tests passing,
especially the separation program tests and DNA cleanup regression.
