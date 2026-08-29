# Scientific Model Module Diagrams

Status: `implementation in progress`
Phase: `1 — material separation and state-transition decisions`
Current boundary: `ResolvedMaterialEffect` is the Runtime handoff; centrifuge
Tables 1–3 are authoritative through one injected adapter; remaining `sep`
programs await typed-context migration.
Normative extension contract: `culsma-reference/extensions/scientific_model/README.md`
Built-in provider semantics: `culsma-reference/extensions/scientific_model/builtin_material_rulebook.md`

## 1. Architecture Decision

| Item | Decision |
| --- | --- |
| Architecture | Ports and adapters + pure decision core |
| Package | `src/culsma/scientific_model/` |
| Runtime integration | Explicit dependency injection |
| Plug-in discovery | Explicit provider registration in Phase 1 |
| Stable public unit | `capability + contract_version + ModelRequest/ModelResult` |
| Provider replacement | Change binding only; Runtime adapter remains unchanged |
| Default scientific implementation | Built-in Reference Rulebook Provider |
| Resolver scope | Resolve every non-authored scientific decision through the selected provider |
| Provider authority | Propose typed scientific effects |
| Commit authority | Runtime kernel only |
| Mutable runtime state across boundary | Forbidden |
| Default provider | `BuiltinMaterialRulebookProvider` |

## 2. Vocabulary Boundary

| Term | Meaning | Authority |
| --- | --- | --- |
| Built-in Reference Rulebook | Official default provider behavior; Tables 1–3 | Culsma Reference |
| Rulebook implementation | Built-in scientific-model provider | `scientific_model.material` |
| Scientific Model Resolver | Typed capability resolution | `scientific_model.resolver` |
| Scientific Provider | Replaceable source of typed scientific decisions | External or built-in adapter |
| Proposal validator | Validates untrusted provider output | Culsma kernel |
| Candidate validator | Validates quantities, state, conservation, and capacity | `runtime.material` |
| Commit | Atomic material-ledger mutation | `runtime.material` |

## 3. Dependency Boundary

```mermaid
flowchart LR
    subgraph Runtime["culsma.runtime"]
        Run["run()"]
        Session["RuntimeSession"]
        Material["MaterialCompute"]
        Adapter["ScientificModelPartitionAdapter<br/>snapshot + decision merge"]
        ResolvedEffect["ResolvedMaterialEffect<br/>one immutable Runtime handoff"]
        Candidate["candidate build + commit validation"]
        Ledger["material ledger commit"]
    end

    subgraph PublicPort["stable public scientific-model port"]
        Request["ModelRequest<br/>capability + contract_version + immutable payload"]
        Resolver["ScientificModelResolver.resolve(request)"]
        ProviderAPI["ScientificModelProvider.resolve(request)"]
        Result["ModelResult<br/>typed proposal + provenance"]
    end

    subgraph ScientificModel["culsma.scientific_model internals"]
        Coordinator["SepEffectCoordinator"]
        ProposalValidation["provider proposal validation"]
        NoModel["NoScientificModelResolver"]
    end

    subgraph Providers["replaceable providers behind the same port"]
        Builtin["BuiltinMaterialRulebookProvider"]
        Classification["Table 1 classification"]
        Fate["Table 2 separation fate"]
        Transition["Table 3 relationship transition"]
        External["External ScientificModelProvider"]
    end

    Run -->|"construct with resolver"| Material
    Session -->|"owns configured instance"| Material
    Material --> Adapter
    Adapter -->|"immutable operation + component snapshots"| Coordinator
    Coordinator --> Request
    Request --> Resolver
    Resolver -->|"dispatch selected binding"| ProviderAPI
    Builtin -. "implements; default binding" .-> ProviderAPI
    External -. "implements; explicit replacement" .-> ProviderAPI
    Builtin --> Classification
    Classification --> Fate
    Classification --> Transition
    NoModel -. implements .-> Resolver
    ProviderAPI -->|"same versioned result contract"| Result
    Result --> ProposalValidation
    ProposalValidation -->|"validated decision"| Coordinator
    Coordinator -->|"validated capability decisions;<br/>no mutation"| Adapter
    Adapter -->|"merge Table 2 + Table 3"| ResolvedEffect
    ResolvedEffect --> Candidate
    Candidate --> Ledger
```

Only the public port crosses the replaceable-model boundary. `MaterialCompute`,
runtime dictionaries, candidate construction, and ledger commit are not provider
APIs.

### Import Rules

| From | May import | Must not import |
| --- | --- | --- |
| `scientific_model` | standard library; its own public contracts | `runtime`, mutable material state, driver implementations |
| External provider | `scientific_model` public contracts | `runtime`, ledger, container dictionaries |
| `runtime.material` | `scientific_model` contracts/coordinator | external provider implementation |
| `pipeline.program_registry` | pipeline types | scientific calculation rules |
| `scientific_model.material` | normalized operation contract | parser AST, plan nodes, runtime dictionaries |

## 4. Package Layout

```text
src/culsma/
├── scientific_model/
│   ├── __init__.py
│   ├── contracts.py
│   ├── resolver.py
│   ├── registry.py
│   └── material/
│       ├── __init__.py
│       ├── contracts.py
│       ├── classification.py
│       ├── rulebook.py
│       ├── builtin.py
│       ├── coordinator.py
│       └── validation.py
│
└── runtime/
    ├── executor.py
    ├── session.py
    └── material/
        ├── compute.py
        ├── scientific_model_adapter.py
        ├── partition.py
        ├── separation_fate.py
        ├── contents_state.py
        ├── conservation.py
        └── ledger.py
```

## 5. Target Module Ownership

| Module | Owns | Does not own |
| --- | --- | --- |
| `scientific_model/contracts.py` | capability envelope, status, provenance, provider protocol | material-specific facts |
| `scientific_model/resolver.py` | provider selection, dispatch, exception containment, `NoModel` | provider rules, state mutation |
| `scientific_model/registry.py` | explicit `capability → provider` binding | automatic environment discovery |
| `material/contracts.py` | immutable operation/component/relationship snapshots and decisions | runtime dictionaries |
| `material/classification.py` | built-in provider Table 1: canonical `kind/type → G` | external provider behavior |
| `material/rulebook.py` | built-in provider Tables 2–3 | provider dispatch, quantity mutation |
| `material/builtin.py` | official provider implementing the Reference Rulebook | resolver selection, ledger commit |
| `material/coordinator.py` | author precedence, resolver request, final typed decision | ledger commit |
| `material/validation.py` | provider proposal shape, bounds, IDs, fraction sums | capacity and ledger conservation |
| `runtime/material/scientific_model_adapter.py` | public snapshot adapter; combines capability decisions into one `ResolvedMaterialEffect`; no mutation | quantity projection, scientific rules, ledger commit |
| `runtime/material/partition.py` | one quantity projection and candidate construction from resolved decisions | provider calls, scientific classification and ratio tables |
| `runtime/material/conservation.py` | candidate conservation | scientific resolution |
| `runtime/material/ledger.py` | authoritative state mutation | scientific decisions |

## 6. Typed Contracts

```mermaid
classDiagram
    class CapabilityDescriptor {
        +capability
        +contract_version
        +lifecycle
    }

    class ProviderDescriptor {
        +provider_id
        +provider_version
        +capabilities
        +deterministic
    }

    class ModelRequest {
        +request_id
        +capability
        +contract_version
        +lifecycle
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

    class OperationSnapshot {
        +program_kind
        +program_args
        +output_contract
        +effect_kind
    }

    class ComponentSnapshot {
        +entry_id
        +content_ref
        +canonical_kind
        +canonical_type
        +quantity
        +relationship
    }

    class SeparationDecision {
        +component_fates
        +decision_source
        +provenance
    }

    class StateTransitionDecision {
        +transitions
        +decision_source
        +provenance
    }

    ModelRequest --> OperationSnapshot
    ModelRequest --> ComponentSnapshot
    ModelResult --> SeparationDecision : material.separation_fate
    ModelResult --> StateTransitionDecision : material.state_transition
    CapabilityDescriptor --> ModelRequest
    ProviderDescriptor o-- CapabilityDescriptor
```

One separation candidate may use the port twice before any mutation: Table 2
returns `SeparationDecision`, then Table 3 returns `StateTransitionDecision` for
the positive output entries. A state-transition-only program such as `disrupt`
uses only the second capability. Both decisions belong to one candidate and one
atomic commit.

### Runtime Handoff Contract

```mermaid
classDiagram
    class ResolvedMaterialEffect {
        +operation_id
        +program_kind
        +outputs
        +component_effects
    }

    class ResolvedOutput {
        +part_id
        +semantic_role
    }

    class ResolvedComponentEffect {
        +source_component_id
        +source_amount
        +source_relation
        +source_accessibility
        +source_preservation
        +outputs
    }

    class ResolvedComponentOutput {
        +part_id
        +semantic_role
        +fraction
        +next_relation
        +next_label
        +retire_quantity
        +replacement_quantity
        +decision_source
        +fate_provenance
        +transition_provenance
    }

    ResolvedMaterialEffect *-- ResolvedOutput
    ResolvedMaterialEffect *-- ResolvedComponentEffect
    ResolvedComponentEffect *-- ResolvedComponentOutput
```

| Boundary side | Contract |
| --- | --- |
| Provider port | `ModelResult` containing one capability-specific proposal |
| Coordinator → adapter | validated `SeparationDecision` and/or `StateTransitionDecision` |
| Adapter → Runtime candidate builder | exactly one immutable `ResolvedMaterialEffect` |
| Runtime consumers | must not read parallel `ratios`, `fates`, or `transitions` dictionaries |

## 7. Resolution Order

```mermaid
flowchart TD
    Start["component entry + operation"] --> Author{"validated author decision?"}
    Author -->|"yes"| AuthorDecision["RESOLVED: author"]
    Author -->|"no"| Resolver["Resolver selects configured provider"]
    Resolver --> Default{"custom binding configured?"}
    Default -->|"no"| Builtin["Built-in Reference Rulebook Provider"]
    Default -->|"yes"| External["External or composite provider"]
    Builtin --> Response{"provider outcome"}
    External --> Response
    Response -->|"resolved"| Predict["typed provider result"]
    Predict --> Validate{"proposal valid?"}
    Validate -->|"no"| Reject
    Validate -->|"yes"| ProviderDecision["RESOLVED: provider"]
    Response -->|"not_applicable / failed / UNRESOLVED"| Unresolved["unresolved; no mutation"]

    AuthorDecision --> Candidate["runtime candidate"]
    ProviderDecision --> Candidate
    Candidate --> CommitValidate{"candidate valid?"}
    CommitValidate -->|"yes"| Commit["atomic commit"]
    CommitValidate -->|"no"| Reject
    Reject["REJECT; no mutation"]
```

### Precedence Table

| Priority | Source | Can override earlier result? | Next step |
| ---: | --- | --- | --- |
| 1 | Validated author `component_fates` | No | candidate |
| 2 | Explicit resolver capability binding | Selects one provider or composite provider | result validation |
| 3 | Built-in Reference Rulebook Provider | Default when no custom binding exists | proposal validation or unresolved |
| 4 | No provider / not applicable / failed / `UNRESOLVED` | No | unresolved diagnostic |

## 8. Resolver Contract

```python
class ScientificModelResolver(Protocol):
    def capabilities(self) -> tuple[CapabilityDescriptor, ...]: ...
    def resolve(self, request: ModelRequest) -> ModelResult: ...


class ScientificModelProvider(Protocol):
    @property
    def descriptor(self) -> ProviderDescriptor: ...
    def resolve(self, request: ModelRequest) -> ModelResult: ...
```

| Rule | Phase 1 value |
| --- | --- |
| Capabilities | `material.separation_fate`, `material.state_transition` |
| Contract version | `1.0` |
| Lifecycle | `runtime_precommit` |
| Provider count | One configured provider per capability |
| Resolver count | One configured resolver per run |
| Providers per resolver | Zero to many; selected through capability bindings |
| Multiple models | A chain/ensemble implements one provider |
| Default capability bindings | Both material capabilities → `BuiltinMaterialRulebookProvider` |
| External component | Explicitly replaces or wraps the built-in provider |
| Implicit fallback chain | Forbidden |
| Transport | Synchronous interface; adapter owns remote/container transport |
| Provider statuses | `resolved`, `not_applicable`, `failed` |
| Kernel-only status | `rejected` |
| Discovery | Explicit injection; no package auto-discovery |

### Stable Public Replacement Contract

| Surface | Compatibility rule |
| --- | --- |
| `ScientificModelResolver.resolve(ModelRequest) -> ModelResult` | Stable public call boundary |
| `ScientificModelProvider.resolve(ModelRequest) -> ModelResult` | Every built-in, external, remote, or future provider implements the same boundary |
| `capability` | Selects the decision family without exposing provider internals |
| `contract_version` | Versions payload/result schemas independently of provider versions |
| Provider replacement | Change explicit capability binding; no Runtime adapter or ledger change |
| Contract upgrade | Add/version the capability contract; do not reinterpret an existing version |
| Runtime objects | Never cross the boundary |
| Commit authority | Never crosses the boundary |

## 9. Target Runtime Composition

```mermaid
sequenceDiagram
    participant API as run()
    participant Session as RuntimeSession
    participant Compute as MaterialCompute
    participant Partition as runtime.material.partition
    participant Adapter as ScientificModelPartitionAdapter
    participant Model as SepEffectCoordinator
    participant Resolver as ScientificModelResolver
    participant Provider as selected ScientificModelProvider
    participant Ledger as MaterialLedger

    API->>Compute: construct with custom or built-in resolver
    API->>Session: configured MaterialCompute
    Compute->>Partition: apply sep/state-transition step
    Partition->>Adapter: operation + Runtime component records
    Adapter->>Adapter: build immutable operation + component snapshots
    opt fraction-producing separation
        Adapter->>Model: material.separation_fate request
        Model->>Model: resolve validated author fate decision
        opt no author fate decision
            Model->>Resolver: capability + contract version + immutable payload
            Resolver->>Resolver: select explicit provider or built-in default
            Resolver->>Provider: resolve(request)
            Provider-->>Resolver: ModelResult
            Resolver-->>Model: SeparationDecision / unresolved / failed
            Model->>Model: validate fraction proposal
        end
    end
    loop every affected or positive-output component
        Adapter->>Model: material.state_transition request
        Model->>Resolver: capability + contract version + immutable payload
        Resolver->>Resolver: select explicit provider or built-in default
        Resolver->>Provider: resolve(request)
        Provider-->>Resolver: ModelResult
        Resolver-->>Model: StateTransitionDecision / unresolved / failed
        Model->>Model: validate transition proposal
    end
    Model-->>Adapter: validated fate + transition decisions
    Adapter->>Adapter: merge as ResolvedMaterialEffect
    Adapter-->>Partition: ResolvedMaterialEffect
    Partition->>Partition: generic quantity projection + candidate
    Partition->>Partition: validate state, capacity, conservation
    Partition->>Ledger: atomic commit
```

### Runtime API

```python
result = run(
    plan=plan,
    driver=driver,
    scientific_model=resolver,  # optional
)
```

| Compatibility rule | Decision |
| --- | --- |
| Existing callers | Unchanged |
| Default parameter | `None` → resolver with built-in Reference provider |
| Default resolver implementation | `RegistryScientificModelResolver` from `create_default_scientific_model_resolver()` |
| Global resolver singleton | Forbidden |
| Session lifetime | One selected resolver per run |
| Resolver contents | Many providers permitted; one selected binding per `capability@contract_version` |
| Existing `apply_step(...)` facade | Retained temporarily |
| Internal execution path | `session.material_compute.apply_step(...)` |

## 10. Current-to-Target Move Map

### Current conflict: two program dispatch systems

```mermaid
flowchart TB
    Step["sep or source-partition operation"] --> Partition["partition_sep_material"]
    Partition --> ProgramRegistry["Program Registry<br/>single slot-contract source"]
    Partition --> Gate{"program_kind == centrifuge_program?"}

    Gate -->|yes| Adapter["ScientificModelPartitionAdapter"]
    Adapter --> Resolver["ScientificModelResolver"]
    Resolver --> Provider["built-in or external provider"]
    Provider --> Tables["Table 1 classification<br/>Table 2 fate<br/>Table 3 transition"]

    Gate -->|no| Legacy["Runtime legacy scientific path"]
    Legacy --> RuntimeStrategy["SepPartitionStrategyRegistry"]
    Legacy --> OldClass["ContentClassResolver"]
    Legacy --> OldFate["per-program strategy ratios"]
    Legacy --> OldState["output_class + cell state<br/>+ preservation rules"]

    Tables --> Projection["quantity projection"]
    OldClass --> Projection
    OldFate --> Projection
    OldState --> Projection
    ProgramRegistry --> Projection

    OldClass -. "overlaps Table 1" .-> Tables
    OldFate -. "overlaps Table 2" .-> Tables
    OldState -. "overlaps Table 3" .-> Tables
```

| Current symptom | Architectural cause |
| --- | --- |
| Only centrifuge enters the adapter | Runtime owns a `program_kind` feature gate |
| Other programs select Runtime subclasses | `SepPartitionStrategyRegistry` remains a second scientific dispatcher |
| Filtration, precipitation, and magnetic rules exist in two systems | Runtime strategy and Rulebook both own scientific fate |
| Missing transition may fall back to strategy state | Runtime still retains a second state authority |
| Centrifuge has no Runtime strategy, but other programs do | Migration state remains encoded by `program_kind` |

### Target convergence: one scientific decision boundary

```mermaid
flowchart TB
    Step["any registered sep program"] --> ProgramRegistry["Program Registry"]
    ProgramRegistry --> Contract["one normalized OperationContract<br/>program kind + output roles + operation facts"]
    Step --> Partition["generic partition candidate builder"]
    Contract --> Adapter["ScientificModelPartitionAdapter"]
    Partition --> Adapter

    Adapter --> Coordinator["SepEffectCoordinator"]
    Coordinator --> Resolver["one configured ScientificModelResolver"]
    Resolver --> Provider["selected built-in or external provider"]

    Provider --> T1["Table 1<br/>component → calculation group"]
    T1 --> Effect{"operation effect"}
    Effect -->|fraction-producing| T2["Table 2<br/>ordered output fractions"]
    Effect -->|all affected outputs| T3["Table 3<br/>relationship transition"]
    T2 --> Decision["typed material-effect decision"]
    T3 --> Decision

    Decision --> Adapter
    Adapter --> Projector["generic quantity projector<br/>no program-specific branch"]
    Projector --> Validate["candidate validation"]
    Validate --> Ledger["atomic ledger commit"]
```

| Boundary | Target owner | Rule |
| --- | --- | --- |
| Program names, fields, output roles | `pipeline.program_registry` | One contract source; consumers reference it |
| Runtime dictionary ↔ immutable model contract | `ScientificModelPartitionAdapter` | No scientific rules and no mutation |
| Program-specific scientific behavior | selected provider / Rulebook | Tables 1–3 are the only built-in authority |
| Quantity projection | generic Runtime projector | Apply typed fractions once; no `program_kind` branch |
| Candidate validation and commit | Runtime kernel | Provider never mutates Runtime state |
| Legacy compatibility, if temporarily required | provider behind the same resolver port | Never branch around the adapter |

Target deletion condition:

```text
partition.py contains no per-program scientific strategy subclasses
partition.py contains no scientific-model feature gate
partition.py does not construct a resolver
all sep programs enter the same adapter
```

### Responsibility migration

```mermaid
flowchart LR
    subgraph Legacy["remove from runtime.material.partition"]
        OldClass["PartitionClass + content mapping"]
        OldFate["strategy ratios + resolve_content_fate"]
        OldState["relationship/output-state rules"]
    end

    subgraph NewProvider["built-in provider behind public port"]
        T1["Table 1<br/>classification"]
        T2["Table 2<br/>separation fate"]
        T3["Table 3<br/>state transition"]
    end

    subgraph RetainedRuntime["retained Runtime kernel"]
        Adapter["snapshot/candidate adapter"]
        Projection["quantity projection + merge execution"]
        Validate["state + capacity + conservation"]
        Commit["ledger + movements + atomic commit"]
    end

    OldClass -. "replaced by" .-> T1
    OldFate -. "replaced by" .-> T2
    OldState -. "replaced by" .-> T3
    T1 --> T2
    T1 --> T3
    T2 --> Adapter
    T3 --> Adapter
    Adapter --> Projection --> Validate --> Commit
```

| Current location | Current responsibility | Target |
| --- | --- | --- |
| `runtime/material/partition.py::PartitionClass` | calculation groups | `scientific_model/material/classification.py` |
| `runtime/material/partition.py::_CONTENT_CLASS_BY_KIND_TYPE` | Table 1 | `scientific_model/material/classification.py` |
| `runtime/material/partition.py::SepPartitionStrategy*` | ratios + output classes | `scientific_model/material/rulebook.py` |
| `runtime/material/separation_fate.py` | operation/relationship decisions | contracts + Rulebook + coordinator |
| `runtime/material/contents_state.py` relationship refresh | post-separation state decisions | apply validated Table 3 transitions only |
| `runtime/material/scientific_model_adapter.py::ScientificModelPartitionAdapter` | immutable snapshots + provider decision resolution | stable Runtime/model boundary |
| `runtime/material/partition.py::partition_sep_material` | decision application + one quantity projection | candidate construction only |
| `runtime/steps.py::apply_material_step` | global material-compute facade | session-owned `MaterialCompute` |
| `pipeline/program_registry.py` | program syntax/fields/result slots | unchanged |
| `runtime/material/ledger.py` | authoritative quantities | unchanged |

## 11. Implementation Slices

| Slice | Status | Change | Exit condition |
| ---: | --- | --- | --- |
| 1 | Done | Add contracts, resolver, registry, provider shell, and `run → session → MaterialCompute` wiring | injection tests pass |
| 2 | Done | Implement built-in provider Table 1 classification | classification conformance passes |
| 3 | Done | Implement centrifuge Table 2 fate and Table 3 transitions | exact `100/0` fates and relationships pass |
| 4 | Done | Introduce `ResolvedMaterialEffect`, pure projection, candidate validation, and commit | one typed effect crosses into Runtime |
| 5 | Done | Inject one adapter through ordinary `sep` and `source.partition` paths | no nested resolver construction or custom-provider bypass |
| 6 | Done | Remove legacy centrifuge strategy and duplicate slot ownership | centrifuge uses Tables 1–3; Program Registry owns output roles |
| 7 | Rules ready; adapter pending | Migrate filtration, centrifugal filtration, precipitation, magnetic | typed guards replace legacy guesses |
| 8 | Pending | Route phase partition, field, generic `sep`, disrupt through coordinator | every registered `sep` has controlled outcome |
| 9 | Pending | Remove compatibility-only classifier and strategy registry | no Runtime scientific dispatcher or `program_kind` feature gate |

## 12. Phase 1 Invariants

| Invariant | Required |
| --- | ---: |
| Provider receives immutable semantic snapshots only | Yes |
| Provider receives already-resolved components | No |
| Provider mutates runtime state | No |
| Provider introduces a new `content_ref` | No |
| Fractions are finite and in `[0, 1]` | Yes |
| Per-component output fractions sum to `1` | Yes |
| Built-in Rulebook is reached through the resolver | Yes |
| External provider selection is explicit and recorded | Yes |
| External provider may replace or wrap built-in provider | Yes |
| Runtime silently appends built-in fallback after an external provider | No |
| `UNRESOLVED` silently becomes `0.5/0.5` | No |
| Candidate commits before validation | No |
| Provenance is recorded with provider decisions | Yes |
| Next operation reclassifies committed components | Yes |
