# Pipeline Module Diagrams

Last updated: 2026-06-18

Related documents:

1. [global_architecture_diagrams.md](../../global_architecture_diagrams.md)
2. [ir_structure_diagrams.md](./ir_structure_diagrams.md)
3. [compile_module_diagrams.md](./compile_module_diagrams.md)
4. [validate_module_diagrams.md](./validate_module_diagrams.md)
5. [typecheck_module_diagrams.md](./typecheck_module_diagrams.md)
6. [plan_module_diagrams.md](./plan_module_diagrams.md)
7. [scope_module_diagrams.md](./scope_module_diagrams.md)

## Scope

This document records cross-stage pipeline structure. It is the home for
pipeline-level design decisions that do not belong to one individual stage.

The pipeline layer covers Canonical IR, compile, validation, typecheck, plan
lowering, and shared pipeline semantic services. Parser source syntax, runtime
execution, material compute, and concrete drivers are documented separately.

## Entrypoint And Module Boundary

```mermaid
flowchart TB
    Sources["Resolved source set"]
    EntrySource["Entry source<br/>CLI input file"]
    DependencySource["Dependency sources<br/>import / include / stdlib"]
    DefinitionsOnly["Definitions only<br/>protocols visible to entry"]
    Explicit{"Explicit entry<br/>requested?"}
    ExplicitEntry["Explicit protocol entry"]
    HasScript{"Default run:<br/>entry source has top-level statements?"}
    ScriptEntry["Script entry<br/>lower entry-source statements"]
    Compat{"1.0.5 legacy adapter<br/>single entry-source root?"}
    LegacyEntry["Legacy protocol entry<br/>warning"]
    NoRun["No executable entry"]

    Sources --> EntrySource
    Sources --> DependencySource
    DependencySource --> DefinitionsOnly
    EntrySource --> Explicit
    Explicit -->|yes| ExplicitEntry
    Explicit -->|no| HasScript
    HasScript -->|yes| ScriptEntry
    HasScript -->|no| Compat
    Compat -->|yes| LegacyEntry
    Compat -->|no| NoRun
```

## Pipeline Stage Overview

```mermaid
flowchart LR
    AST["Resolved modules<br/>entry + dependencies"]
    Compile["IRCompiler<br/>CompileResult"]
    Validate["validate<br/>ValidationResult"]
    Typecheck["typecheck<br/>TypecheckResult"]
    Entry["Entry resolution<br/>explicit protocol / entry-source script<br/>or no run"]
    Compat["Entry compatibility adapter<br/>1.0.5 entry-source legacy fallback"]
    Plan["lower_ir_to_plan<br/>selected execution PlanProgram"]

    AST --> Compile
    Compile --> Validate
    Validate --> Typecheck
    Typecheck --> Entry
    Entry --> Compat
    Compat --> Plan
```

## Shared Pipeline Semantics

Shared pipeline services are used by more than one stage and should not be
owned by a single stage handler.

```mermaid
flowchart TB
    Scope["pipeline.scope"]
    EntryCompat["pipeline.entrypoints<br/>compatibility adapter"]
    Compile["pipeline.compile"]
    Validate["pipeline.validate"]
    Typecheck["pipeline.typecheck"]
    Plan["pipeline.plan"]

    Compile -. uses .-> Scope
    Validate -. uses .-> Scope
    Typecheck -. uses .-> Scope
    Plan -. uses .-> Scope
    EntryCompat -. selects entry for .-> Plan
```

## Scope Service Target

Detailed design:

1. [scope_module_diagrams.md](./scope_module_diagrams.md)
