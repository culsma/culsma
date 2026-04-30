# Driver Module Diagrams

Last updated: 2026-04-25

Related runtime/driver documents:

1. [runtime_module_diagrams.md](https://github.com/culsma/culsma/blob/main/docs/architecture/runtime_module_diagrams.md)

## Scope

This document records the current `driver` structure.

The driver layer consumes runtime-ready `PlanStep` objects and returns:

- capability decisions through `DriverCapabilityResult`
- execution receipts through `DriverResult`

Its job is not to schedule execution, resolve runtime values, or update
material state. Those stay in `runtime/`.

The driver layer does three things:

1. decide whether a backend can execute one step under current constraints
2. project one canonical step into backend-facing command or instruction data
3. normalize backend-facing payloads into stable runtime receipts

The structure is intentionally conservative:

- `driver/base.py` defines the public contracts
- `driver/framework/driver.py` defines the reusable projection template
- `driver/framework/capability.py` owns formal capability checks
- `human_driver/` and `robot_driver/` mostly do component assembly
- `StubDriver` remains a concrete deterministic testing driver, not a base
  class for formal drivers

## Functional Flowchart

```mermaid
flowchart TB
    Start(["Receive runtime-ready PlanStep"])
    Check["Evaluate backend capability for this step:<br/>requirements, constraint options, driver-specific support"]
    Capability{"Capability OK?"}
    ReturnCapability["Return DriverCapabilityResult"]
    Execute["Execute driver step"]
    Normalize["Normalize PlanStep into MappingRecord"]
    Bind["Resolve backend-facing binding context"]
    Select["Select translator by semantic op / program kind"]
    Project["Project MappingRecord into DriverProjection"]
    Emit["Emit backend-facing payload:<br/>command or instruction"]
    Receipt["Normalize emitted payload into runtime receipt"]
    ReturnResult["Return DriverResult"]

    Start --> Check
    Check --> Capability
    Capability -->|no| ReturnCapability
    Capability -->|yes| Execute
    Execute --> Normalize
    Normalize --> Bind
    Bind --> Select
    Select --> Project
    Project --> Emit
    Emit --> Receipt
    Receipt --> ReturnResult
```

## Driver Sequence

```mermaid
sequenceDiagram
    participant Runtime as "runtime/steps.py::DriverBackedStepHandler"
    participant Base as "driver/base.py::Driver"
    participant Framework as "driver/framework/driver.py::ProjectionDriver"
    participant Policy as "driver/framework/capability.py::CapabilityPolicy"
    participant Norm as "driver/framework/mapping_core.py::normalize_step"
    participant Resolver as "driver/framework/contracts.py::BindingResolver"
    participant Registry as "driver/framework/registry.py::TranslatorRegistry"
    participant Translator as "driver/framework/contracts.py::Translator"
    participant Emit as "driver/framework/contracts.py::BackendEmitter"
    participant Receipt as "driver/framework/contracts.py::ReceiptNormalizer"

    Runtime->>Base: check(step)
    Base->>Framework: ProjectionDriver.check(step)
    Framework->>Policy: evaluate(step)
    Policy-->>Framework: DriverCapabilityResult
    Framework-->>Runtime: DriverCapabilityResult

    Runtime->>Base: execute(step)
    Base->>Framework: ProjectionDriver.execute(step)
    Framework->>Framework: _base_execute(step)
    Framework-->>Framework: base DriverResult
    alt projection stack configured
        Framework->>Norm: normalize_step(step)
        Norm-->>Framework: MappingRecord
        Framework->>Resolver: bind(record, context)
        Resolver-->>Framework: binding
        Framework->>Registry: select(record)
        Registry-->>Framework: Translator
        Framework->>Translator: translate(record, binding)
        Translator-->>Framework: DriverProjection
        Framework->>Emit: emit(projection)
        Emit-->>Framework: emitted payload
        Framework->>Receipt: normalize(base_payload=..., emitted_payload=...)
        Receipt-->>Framework: normalized payload
    end
    Framework-->>Runtime: DriverResult
```

## Driver Detail Sequence

```mermaid
sequenceDiagram
    participant Driver as "driver/framework/driver.py::ProjectionDriver"
    participant Norm as "driver/framework/mapping_core.py::normalize_step"
    participant Resolver as "driver/framework/contracts.py::BindingResolver"
    participant Registry as "driver/framework/registry.py::TranslatorRegistry"
    participant Translator as "driver/framework/contracts.py::Translator"
    participant Emit as "driver/framework/contracts.py::BackendEmitter"
    participant Receipt as "driver/framework/contracts.py::ReceiptNormalizer"

    Driver->>Norm: build_mapping_record(step)
    Norm-->>Driver: MappingRecord
    Driver->>Resolver: bind(record, context)
    Resolver-->>Driver: binding
    Driver->>Registry: select(record)
    Registry-->>Driver: Translator
    Driver->>Translator: translate(record, binding)
    Translator-->>Driver: DriverProjection
    Driver->>Emit: emit(projection)
    Emit-->>Driver: emitted payload
    Driver->>Receipt: normalize(base_payload=..., emitted_payload=...)
    Receipt-->>Driver: normalized payload
```

## Driver Detail Flowchart

```mermaid
flowchart TB
    Start(["ProjectionDriver.execute"])
    Normalize["1. normalize step into MappingRecord"]
    Bind["2. resolve backend binding context"]
    Select["3. select translator"]
    Project["4. translate into DriverProjection"]
    Emit["5. emit backend payload"]
    Receipt["6. normalize runtime receipt"]
    Return(["Return DriverResult"])

    Start --> Normalize
    Normalize --> Bind
    Bind --> Select
    Select --> Project
    Project --> Emit
    Emit --> Receipt
    Receipt --> Return
```

## Class And Module Diagram

```mermaid
classDiagram
    class Driver {
        <<protocol>>
        +check(step) DriverCapabilityResult
        +execute(step) DriverResult
    }

    class DriverCapabilityResult {
        +ok
        +code
        +unsupported_requirements
        +unsupported_constraint_options
        +payload
    }

    class DriverResult {
        +ok
        +code
        +payload
    }

    class CapabilityPolicy {
        +evaluate(step) DriverCapabilityResult
    }

    class StubDriver {
        +check(step) DriverCapabilityResult
        +execute(step) DriverResult
    }

    class ProjectionDriver {
        +driver_kind
        +ok_code
        +capability_policy
        +translator_registry
        +binding_resolver
        +backend_emitter
        +receipt_normalizer
        +check(step) DriverCapabilityResult
        +execute(step) DriverResult
        +project_step(step) DriverProjection
        +build_mapping_record(step) MappingRecord
        +build_context(step, record) DriverContext
        +select_translator(record) Translator
    }

    class DriverContext {
        +driver_kind
        +runtime_context
    }

    class MappingRecord {
        +step_id
        +semantic_op
        +semantic_args
        +program_kind
        +program_args
        +requirements
        +constraint_options
        +env
        +env_targets
        +trace_ref
    }

    class DriverProjection {
        +step_id
        +semantic_op
        +channel
        +label
        +summary
        +details
        +category
        +binding
        +payload
    }

    class TranslatorRegistry {
        +translators
        +default_translator
        +select(record) Translator
    }

    class BindingResolver {
        <<protocol>>
        +bind(record, context) dict
    }

    class Translator {
        <<protocol>>
        +translate(record, binding) DriverProjection
    }

    class BackendEmitter {
        <<protocol>>
        +emit(projection) dict
    }

    class ReceiptNormalizer {
        <<protocol>>
        +normalize(base_payload=..., emitted_payload=...) dict
    }

    class HumanDriver
    class RobotDriver

    Driver <|.. StubDriver
    Driver <|.. ProjectionDriver
    ProjectionDriver <|-- HumanDriver
    ProjectionDriver <|-- RobotDriver
    ProjectionDriver --> CapabilityPolicy : checks through
    ProjectionDriver --> DriverContext : builds
    ProjectionDriver --> MappingRecord : builds
    ProjectionDriver --> TranslatorRegistry : selects from
    ProjectionDriver --> BindingResolver : binds through
    ProjectionDriver --> Translator : projects through
    ProjectionDriver --> BackendEmitter : emits through
    ProjectionDriver --> ReceiptNormalizer : normalizes through
    Translator --> DriverProjection : returns
```
