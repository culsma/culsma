# Global Architecture Diagrams

Last updated: 2026-06-18

This document records the repository-level execution architecture. It gives the
global source-to-runtime flow first, then records cross-stage semantic
dependencies that are not themselves pipeline stages. Module-specific details
remain in the existing parser, compile, validate, typecheck, plan, runtime,
material, and driver documents.

## Global Execution Flow

This activity-style flowchart is the global pipeline. It intentionally uses
conceptual stage names rather than internal helper objects. Implementation
module names are included only to connect the architecture to the repository.

```mermaid
flowchart LR
    CLI["0. CLI run inputs<br/>one file or batch"]
    Batch{"Multiple input files?"}
    PerFile["Per-file run boundary<br/>independent state + output"]
    Source["1. Source files<br/>entry source + definition dependencies"]
    ParseCompile["2. Parse + compile<br/>parser, module roles,<br/>Canonical IR generation"]
    Validate["3. Semantic validation<br/>reference shape, contracts,<br/>lowering gates"]
    Typecheck["4. Type + unit checking<br/>dimensional and ordered-step consistency"]
    Entry["5. Entry resolution<br/>entry-source script,<br/>compatibility fallback,<br/>or no run"]
    Compat["6. 1.0.5 compatibility adapter<br/>entry-source legacy single-protocol entry"]
    Plan["7. Plan lowering<br/>selected root, workflow plan,<br/>dependencies, execution gates"]
    Runtime["8. Runtime execution session<br/>scheduler, lifecycle, material compute,<br/>events, artifacts, user result"]
    Driver["Driver module<br/>backend realization"]

    CLI --> Batch
    Batch -->|one| Source
    Batch -->|many| PerFile
    PerFile --> Source
    Source --> ParseCompile
    ParseCompile --> Validate
    Validate --> Typecheck
    Typecheck --> Entry
    Entry --> Compat
    Compat --> Plan
    Plan --> Runtime
    Runtime --> Driver
```

## Main Execution Sequence

This sequence diagram shows the main cross-module path. It uses representative
classes that exist in the implementation and omits internal helpers.

```mermaid
sequenceDiagram
    participant Program
    participant IRCompiler
    participant CompileResult
    participant ValidationResult
    participant TypecheckResult
    participant EntrySelection
    participant EntryCompatibilityAdapter
    participant PlanStatementLowerer
    participant PlanProgram
    participant RuntimeExecutor
    participant Driver
    participant RunResult

    Program->>IRCompiler: compile_program(Program)
    IRCompiler-->>CompileResult: CompileResult
    CompileResult-->>ValidationResult: validate(IRProgram)
    ValidationResult-->>TypecheckResult: typecheck(IRProgram)
    TypecheckResult->>EntrySelection: resolve entry-source script, compatibility fallback, or no-run
    EntrySelection->>EntryCompatibilityAdapter: apply isolated 1.0.5 entry-source fallback if enabled
    alt selected entry
        EntryCompatibilityAdapter->>PlanStatementLowerer: lower selected execution boundary
        PlanStatementLowerer-->>PlanProgram: PlanProgram
        PlanProgram->>RuntimeExecutor: execute selected session
        loop for each PlanStep
            RuntimeExecutor->>Driver: check(PlanStep)
            Driver-->>RuntimeExecutor: DriverCapabilityResult
            RuntimeExecutor->>Driver: execute(PlanStep)
            Driver-->>RuntimeExecutor: DriverResult
        end
        RuntimeExecutor-->>RunResult: RunResult
    else no selected entry
        EntryCompatibilityAdapter-->>PlanProgram: no executable plan
    end
```
