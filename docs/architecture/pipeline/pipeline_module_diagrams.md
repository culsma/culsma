# Pipeline Module Diagrams

Last updated: 2026-06-18

Related documents:

1. [global_architecture_diagrams.md](../../global_architecture_diagrams.md)
2. [ir_structure_diagrams.md](./ir_structure_diagrams.md)
3. [compile_module_diagrams.md](./compile_module_diagrams.md)
4. [validate_module_diagrams.md](./validate_module_diagrams.md)
5. [typecheck_module_diagrams.md](./typecheck_module_diagrams.md)
6. [plan_module_diagrams.md](./plan_module_diagrams.md)

## Scope

This document records cross-stage pipeline structure. It is the home for
pipeline-level design decisions that do not belong to one individual stage.

The pipeline layer covers Canonical IR, compile, validation, typecheck, plan
lowering, and shared pipeline semantic services. Parser source syntax, runtime
execution, material compute, and concrete drivers are documented separately.

## Pipeline Stage Overview

```mermaid
flowchart LR
    AST["Program"]
    Compile["IRCompiler<br/>CompileResult"]
    Validate["validate<br/>ValidationResult"]
    Typecheck["typecheck<br/>TypecheckResult"]
    Plan["lower_ir_to_plan<br/>PlanProgram"]

    AST --> Compile
    Compile --> Validate
    Validate --> Typecheck
    Typecheck --> Plan
```

## Shared Pipeline Semantics

Shared pipeline services are used by more than one stage and should not be
owned by a single stage handler.

```mermaid
flowchart TB
    Scope["pipeline.scope<br/>(planned)"]
    Compile["pipeline.compile"]
    Validate["pipeline.validate"]
    Typecheck["pipeline.typecheck"]
    Plan["pipeline.plan"]

    Compile -. uses .-> Scope
    Validate -. uses .-> Scope
    Typecheck -. uses .-> Scope
    Plan -. uses .-> Scope
```

## Scope Service Target

Local variable and frame semantics belong inside the pipeline layer as a shared
semantic service, not inside one compile, validate, typecheck, or plan handler.

Expected location:

```text
src/culsma/pipeline/scope.py
```

or, if it grows:

```text
src/culsma/pipeline/scope/
  analysis.py
  model.py
  queries.py
```

It should own protocol-local frames, formal parameter visibility, mutable local
slots, assignment target legality, repeat binding visibility, and the scope
facts needed by plan lowering. Runtime should still own runtime local values.
