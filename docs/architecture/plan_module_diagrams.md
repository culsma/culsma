# Plan Module Diagrams

Last updated: 2026-04-23

Related IR / Plan documents:

1. [ir_structure_diagrams.md](https://github.com/culsma/culsma/blob/main/docs/architecture/ir_structure_diagrams.md)

## Scope

This document has five diagrams only:

1. Functional flowchart: what plan lowering actually does.
2. Runtime sequence: the current runtime call chain.
3. Plan statement detail sequence: the current statement-lowering internals.
4. Statement lowering lifecycle template.
5. Class/module diagram: the ownership split in the current implementation.

Plan lowering consumes Canonical IR and returns `PlanProgram(plans, diagnostics)`.
It owns protocol-root selection, protocol-call/include expansion, protocol
parameter binding, IR-to-PlanStep lowering, gate propagation for env /
constraint / runtime conditions, local environment serialization, and linear
dependency assignment between emitted steps. It does not perform semantic
validation, type checking, runtime execution, or driver realization.

The implementation now follows the same dispatcher plus handler pattern used by
parser rule conversion, statement compile, validation, and typecheck:
`plan/__init__.py` owns the public API, `plan/context.py` owns shared lowering
state, `plan/references.py` owns protocol reference expansion and parameter
binding, `plan/serialization.py` owns expression/env serialization, and
`plan/statements.py` owns statement dispatch and handlers.

## Functional Flowchart

```mermaid
flowchart TB
    Start(["Start plan lowering"])
    Init["Prepare lowering state:<br/>protocol lookup, referenced protocol names,<br/>diagnostics collection"]
    Roots["Select executable root protocols:<br/>protocols not referenced by other protocols;<br/>fall back to all protocols when cycles hide every root"]
    ProtocolLoop{"More root protocols?"}
    Bind["Bind entry protocol parameters<br/>into a protocol-local runtime env"]
    StatementLoop{"More IR statements<br/>in this protocol or nested block?"}
    Dispatch["Select lowering behavior<br/>by IR statement type"]
    LowerStmt["Rewrite current IR statement into runtime plan form:<br/>update local env, expand protocol references,<br/>serialize payloads, attach env/constraint/branch gates,<br/>or emit direct PlanStep values"]
    NextStmt["Continue lowering the next statement"]
    Linearize["Turn emitted steps into an ordered execution chain<br/>by filling linear dependencies"]
    Build["Assemble one protocol execution plan:<br/>returns, return bindings, ordered steps"]
    Return["Return PlanProgram(plans, diagnostics)"]

    Start --> Init
    Init --> Roots
    Roots --> ProtocolLoop
    ProtocolLoop -->|yes| Bind
    Bind --> StatementLoop
    StatementLoop -->|yes| Dispatch
    Dispatch --> LowerStmt
    LowerStmt --> NextStmt
    NextStmt --> StatementLoop
    StatementLoop -->|no| Linearize
    Linearize --> Build
    Build --> ProtocolLoop
    ProtocolLoop -->|no| Return
```

## Runtime Sequence

```mermaid
sequenceDiagram
    participant Caller as "pipeline / tests"
    participant API as "plan/__init__.py::lower_ir_to_plan"
    participant Ref as "plan/references.py::PlanReferenceResolver"
    participant Ctx as "plan/context.py::PlanLoweringContext"
    participant Lower as "plan/statements.py::PlanStatementLowerer"
    participant Ser as "plan/serialization.py::PlanExpressionSerializer"
    participant Diag as "common.diagnostics::Diagnostic"

    Caller->>API: lower_ir_to_plan(ir, entry_args_by_protocol)
    API->>Ref: collect_referenced_protocol_names(...)
    API->>API: select root protocols

    loop each root protocol
        API->>Ref: bind_protocol_params(..., entry_mode=True)
        Ref->>Diag: emit arg/default diagnostics when needed
        API->>Ctx: create PlanLoweringContext(local_env, gate_base, protected_names)
        API->>Lower: lower_list(protocol.statements, ctx)
        Lower->>Diag: emit plan-lowering diagnostics when needed
        API->>Ser: linearize_steps(ordered_steps)
        API->>API: build ProtocolPlan
    end

    API-->>Caller: PlanProgram(plans, diagnostics)
```

## Plan Statement Detail Sequence

```mermaid
sequenceDiagram
    participant Lower as "plan/statements.py::PlanStatementLowerer"
    participant H as "plan/statements.py::BasePlanStatementHandler subclass"
    participant Ref as "plan/references.py::PlanReferenceResolver"
    participant Ser as "plan/serialization.py::PlanExpressionSerializer"
    participant Gate as "plan/gates.py"
    participant Ctx as "plan/context.py::PlanLoweringContext"
    participant Diag as "common.diagnostics::Diagnostic"

    Lower->>H: handle(stmt, ctx)
    H->>H: prepare(stmt, ctx)
    H->>H: validate_pre_lowering_rules(stmt, ctx, state)
    H->>H: update_or_derive_local_env(stmt, ctx, state)
    H->>H: serialize_child_expressions(stmt, ctx, state)
    alt include statement
        H->>Ref: expand_reference_steps(...)
        Ref->>Ref: bind_protocol_params(...)
        Ref->>Ctx: extend_diagnostics(...)
        Ref->>Lower: lower_list(referenced_protocol.statements, child_ctx)
    else let / assign / mutation / control / step
        H->>Ser: serialize_expr(...) / serialize_arg_list(...)
        H->>Gate: merge_gate(...)
        H-->>Lower: emitted direct PlanStep list
    else with-env / with-constraint / repeat / conditional
        H->>Gate: merge env / constraint / runtime condition payload
        H->>Lower: lower_list(child_statements, child_ctx)
        H->>Ser: linearize_steps(...) / invalidate_local_env_names(...)
    end
    H->>Ctx: extend_diagnostics(...) when emitted
    Lower->>Diag: append diagnostics when emitted
```

## Statement Lowering Lifecycle Template

```mermaid
flowchart TB
    Start([BasePlanStatementHandler.handle])
    Prepare["1. Prepare statement state"]
    Pre["2. Check pre-lowering rules"]
    Env["3. Update or derive local env"]
    Exprs["4. Serialize child expressions and payloads"]
    Lower["5. Lower current statement or child blocks"]
    Post["6. Apply post-lowering env effects"]
    Done([Return emitted PlanStep list])

    Start --> Prepare
    Prepare --> Pre
    Pre --> Env
    Env --> Exprs
    Exprs --> Lower
    Lower --> Post
    Post --> Done
```

| Phase | Semantic boundary | Typical owners |
| --- | --- | --- |
| `prepare` | Identify the IR statement shape and compute handler-local lowering state. | every statement handler |
| `validate_pre_lowering_rules` | Check rules that must run before env updates or recursion. | protected parameter redeclare, reference lookup preconditions |
| `update_or_derive_local_env` | Update the local serialized env or derive nested child env scopes. | let, repeat, reference-call param binding |
| `serialize_child_expressions` | Precompute plan payload pieces from IR expressions using the current local env. | let-call lowering, assign, mutation, step, env/constraint gates |
| `lower_current_or_children` | Emit direct `PlanStep` values or recurse into child statements and referenced protocols. | assign, mutation, control, step, with-env, with-constraint, repeat, conditional, include/reference |
| `apply_post_lowering_effects` | Invalidate or rewrite local env names after runtime-mutating nested statements. | let local-runtime refs, assign, with-env, with-constraint, repeat, conditional |

## Class And Module Diagram

```mermaid
classDiagram
    class PlanAPI {
        +lower_ir_to_plan(ir, entry_args_by_protocol) PlanProgram
    }

    class PlanLoweringContext {
        +protocols_by_name
        +diagnostics
        +local_env
        +gate_base
        +protected_names
        +statement_lowerer
        +derive(...) PlanLoweringContext
        +emit_diagnostic(diagnostic) None
        +extend_diagnostics(diagnostics) None
    }

    class PlanStatementLowerer {
        +lower_list(statements, ctx) list
        +lower_statement(stmt, ctx) list
        -handlers_by_type
    }

    class PlanExpressionSerializer {
        +serialize_expr(value, env) object
        +serialize_arg_list(args, env) dict
        +linearize_steps(steps) list
        +invalidate_local_env_names(env, statements) None
        +find_arg_by_name(args, name) IRArg
        +load_content_ref_expr(call, fallback_ref) object
    }

    class PlanReferenceResolver {
        +collect_referenced_protocol_names(statements) list
        +bind_protocol_params(target_protocol, call_args, caller_env, ...) tuple
        +expand_reference_steps(ref_name, ref_args, ctx, ...) list
    }

    class PlanStatementLoweringState {
        +output
    }

    class LetPlanState {
        +call
    }

    class BasePlanStatementHandler {
        +handle(stmt, ctx) list
        #prepare(stmt, ctx) PlanStatementLoweringState
        #validate_pre_lowering_rules(stmt, ctx, state) None
        #update_or_derive_local_env(stmt, ctx, state) None
        #serialize_child_expressions(stmt, ctx, state) None
        #lower_current_or_children(stmt, ctx, state) list
        #apply_post_lowering_effects(stmt, ctx, state, output) None
    }

    class LetPlanHandler
    class AssignPlanHandler
    class IncludePlanHandler
    class WithEnvPlanHandler
    class WithConstraintPlanHandler
    class RepeatPlanHandler
    class ConditionalPlanHandler
    class MutationPlanHandler
    class ControlPlanHandler
    class StepPlanHandler

    class PlanProgram
    class ProtocolPlan
    class PlanStep
    class Diagnostic
    class IRProgram
    class IRStatement

    PlanAPI --> PlanLoweringContext : creates
    PlanAPI --> PlanStatementLowerer : uses
    PlanAPI --> PlanProgram : returns
    PlanLoweringContext --> Diagnostic : appends
    PlanStatementLowerer --> BasePlanStatementHandler : dispatches to
    BasePlanStatementHandler --> PlanLoweringContext : reads / emits through
    BasePlanStatementHandler --> PlanStatementLoweringState : creates
    LetPlanState --|> PlanStatementLoweringState
    BasePlanStatementHandler --> PlanExpressionSerializer : uses
    BasePlanStatementHandler --> PlanReferenceResolver : uses
    BasePlanStatementHandler <|-- LetPlanHandler
    BasePlanStatementHandler <|-- AssignPlanHandler
    BasePlanStatementHandler <|-- IncludePlanHandler
    BasePlanStatementHandler <|-- WithEnvPlanHandler
    BasePlanStatementHandler <|-- WithConstraintPlanHandler
    BasePlanStatementHandler <|-- RepeatPlanHandler
    BasePlanStatementHandler <|-- ConditionalPlanHandler
    BasePlanStatementHandler <|-- MutationPlanHandler
    BasePlanStatementHandler <|-- ControlPlanHandler
    BasePlanStatementHandler <|-- StepPlanHandler
    IRProgram --> IRStatement : contains
    PlanProgram --> ProtocolPlan : contains
    ProtocolPlan --> PlanStep : contains
```
