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
    Source["1. Source protocol<br/>.culs / includes / source surface syntax"]
    ParseCompile["2. Parse + compile<br/>parser, component expansion,<br/>Canonical IR generation"]
    Validate["3. Semantic validation<br/>reference shape, contracts,<br/>lowering gates"]
    Typecheck["4. Type + unit checking<br/>dimensional and ordered-step consistency"]
    Plan["5. Plan lowering<br/>workflow plan, dependencies,<br/>environment and execution gates"]
    Runtime["6. Runtime execution<br/>scheduler, lifecycle, material compute,<br/>events, artifacts, user result"]
    Driver["Driver module<br/>backend realization"]

    Source --> ParseCompile
    ParseCompile --> Validate
    Validate --> Typecheck
    Typecheck --> Plan
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
    participant PlanStatementLowerer
    participant PlanProgram
    participant RuntimeExecutor
    participant Driver
    participant RunResult

    Program->>IRCompiler: compile_program(Program)
    IRCompiler-->>CompileResult: CompileResult
    CompileResult-->>ValidationResult: validate(IRProgram)
    ValidationResult-->>TypecheckResult: typecheck(IRProgram)
    TypecheckResult->>PlanStatementLowerer: lower IR statements
    PlanStatementLowerer-->>PlanProgram: PlanProgram
    PlanProgram->>RuntimeExecutor: execute(PlanProgram, Driver)
    loop for each PlanStep
        RuntimeExecutor->>Driver: check(PlanStep)
        Driver-->>RuntimeExecutor: DriverCapabilityResult
        RuntimeExecutor->>Driver: execute(PlanStep)
        Driver-->>RuntimeExecutor: DriverResult
    end
    RuntimeExecutor-->>RunResult: RunResult
```
