# Component Entry Identity

`runtime.material.component_entries` owns authoritative `component_entries` and
their container-local `entry_id` values. This is general Material Runtime
infrastructure used by separation, physical movement, ledger normalization, and
legacy hydration. The Scientific Model consumes entry IDs but does not create
or rename them.

`next_component_entry_id()` uses collision suffixes such as `content_ref_1`,
`content_ref_2`, and so on.

## 1. Functional Flow

```mermaid
flowchart LR
    Incoming["Receive an incoming material entry"]
    Compatible{"Can it safely combine with an existing same-content entry?"}
    Merge["Merge quantities and retain the existing entry identity"]
    Preferred{"Is its preferred entry ID available in this container?"}
    Preserve["Preserve the preferred entry ID"]
    Base{"Is the unsuffixed content code available?"}
    UseBase["Use the content code as the entry ID"]
    Suffix["Try the first free content-code suffix: _1, _2, ..."]
    Append["Append one distinct authoritative entry"]

    Incoming --> Compatible
    Compatible -->|yes| Merge
    Compatible -->|no| Preferred
    Preferred -->|yes| Preserve --> Append
    Preferred -->|no| Base
    Base -->|yes| UseBase --> Append
    Base -->|no| Suffix --> Append

```

The runtime never derives `content_ref` by removing a suffix from `entry_id`.
`content_ref` remains an independent authoritative field.

## 2. Implementation Sequence

Every message is an exact current module and method name.

```mermaid
sequenceDiagram
    participant Consumer as runtime.material.separation<br/>runtime.material.movement<br/>runtime.material.ledger
    participant Entries as runtime.material.component_entries
    participant Container as authoritative container record

    Consumer->>Entries: normalize_component_entries(container, state=state, container_id=container_id)
    Entries->>Entries: container_component_entries(container, state=state)
    Entries->>Entries: compress_component_entries(entries)

    loop incoming in entries
        Entries->>Entries: merge_component_entry(compressed, incoming)
        alt entries_can_compress(existing, incoming)
            Entries->>Entries: merge_entry_quantity(existing, incoming)
        else incompatible physical entry
            Entries->>Entries: available_component_entry_id(compressed, incoming)
            opt preferred entry_id is already used
                Entries->>Entries: next_component_entry_id(compressed, content_ref)
                Entries-->>Entries: content_ref_1, content_ref_2, ...
            end
        end
    end

    Entries-->>Consumer: list[dict[str, Any]]
    Consumer->>Entries: replace_component_entries(container, entries)
    Entries->>Entries: compress_component_entries(entries)
    Entries->>Entries: project_component_entries(container)
    Entries->>Container: component_entries, components, component_quantities, material_relationships
```

## 3. Complete Class Map

```mermaid
classDiagram
    direction LR

    class ComponentEntriesModule["runtime.material.component_entries"] {
        +container_component_entries(container, state) list~dict~
        +normalize_component_entries(container, state, container_id) list~dict~
        +entries_can_compress(left, right) bool
        +compress_component_entries(entries) list~dict~
        +merge_component_entry(entries, incoming) string
        +available_component_entry_id(entries, incoming) string
        +next_component_entry_id(entries, content_ref) string
        +plan_component_entry_transfer(source, target, transitions_by_entry_id, ...) ComponentEntryTransfer
        +replace_component_entries(container, entries)
        +project_component_entries(container)
    }
    class AuthoritativeComponentEntry {
        +entry_id : string
        +content_ref : string
        +amount : float
        +quantity : dict?
        +relation : string
        +associated_with : string?
        +association_target_kind : string?
    }
    class SeparationModule["runtime.material.separation"] {
        +apply_separation_material(...)
        +commit_separation_candidate(candidate, source, outputs_by_part) dict
    }
    class MovementModule["runtime.material.movement"] {
        +apply_material_movement(state, source, target, source_id, destination_id, ratio, material_effect_adapter, request_id) MaterialMovementApplicationResult
        +commit_material_movement(candidate, source, target) ComponentEntryTransfer
    }
    class LedgerModule["runtime.material.ledger"] {
        +normalize_material_state_detail_ledger(state)
    }
    class ScientificModelMaterialAdapter["runtime.material.scientific_model_adapter.ScientificModelMaterialAdapter"] {
        +resolve(...) ResolvedMaterialEffect
        +resolve_movement(...) ResolvedMaterialTransition | MaterialEffectFailure
    }

    ComponentEntriesModule *-- AuthoritativeComponentEntry : owns entry_id
    SeparationModule --> ComponentEntriesModule : normalize and commit
    MovementModule --> ComponentEntriesModule : transfer and commit
    LedgerModule --> ComponentEntriesModule : hydrate and normalize
    ScientificModelMaterialAdapter --> AuthoritativeComponentEntry : consumes identity only

```
