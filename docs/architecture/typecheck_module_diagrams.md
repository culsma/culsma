# Typecheck Module Diagrams

Last updated: 2026-04-23

Related IR document:

1. [ir_structure_diagrams.md](https://github.com/culsma/culsma/blob/main/docs/architecture/ir_structure_diagrams.md)

## Scope

This document has five diagrams only:

1. Functional flowchart: what typecheck actually does.
2. Runtime sequence: the current runtime call chain.
3. Statement typecheck detail sequence: how one handler run uses shared services.
4. Statement typecheck lifecycle template.
5. Class/module diagram: the ownership split in the current implementation.

Typecheck consumes Canonical IR and returns `TypecheckResult(ir, diagnostics)`.
It owns type and unit diagnostics for quantities, local scalar assignments,
member assignments, program-call fields, constructor content, mutation
quantities, step arguments, and environment arguments. It does not mutate IR,
perform semantic validation, lower to plan, execute runtime behavior, or resolve
source libraries.

The implementation follows the same dispatcher plus handler lifecycle pattern
used by parser rule conversion, statement compile, and validation:
`typecheck/__init__.py` owns the public API, `typecheck/context.py` owns shared state,
`typecheck/statements.py` owns statement dispatch and handlers, and
`typecheck/expressions.py` owns expression, local-name, program-call, and
quantity/unit helper services.

## Functional Flowchart

```mermaid
flowchart TB
    Start(["Start typecheck"])
    Init["Prepare diagnostics and expected contracts:<br/>operation specs, program specs,<br/>built-in type/unit rules"]
    ProtocolLoop{"More protocols?"}
    ProtocolState["Create protocol-local name binding table"]
    StatementLoop{"More IR statements?"}
    Dispatch["Select statement typecheck behavior<br/>by IR statement type"]
    CheckStatement["Check statement value uses against contracts:<br/>resolve local names, classify value kinds,<br/>validate quantity dimensions,<br/>scan program calls, recurse nested blocks"]
    NextStatement["Continue with next statement"]
    NextProtocol["Continue with next protocol"]
    Return["Return original IR with type/unit diagnostics"]

    Start --> Init
    Init --> ProtocolLoop
    ProtocolLoop -->|yes| ProtocolState
    ProtocolState --> StatementLoop
    StatementLoop -->|yes| Dispatch
    Dispatch --> CheckStatement
    CheckStatement --> NextStatement
    NextStatement --> StatementLoop
    StatementLoop -->|no| NextProtocol
    NextProtocol --> ProtocolLoop
    ProtocolLoop -->|no| Return
```

## Runtime Sequence

```mermaid
sequenceDiagram
    participant Caller as "pipeline / tests"
    participant API as "typecheck/__init__.py::typecheck"
    participant Ctx as "typecheck/context.py::TypecheckContext"
    participant ST as "typecheck/statements.py::StatementTypechecker"
    participant H as "typecheck/statements.py::BaseTypecheckStatementHandler subclass"

    Caller->>API: typecheck(ir, operation_specs)
    API->>Ctx: create TypecheckContext(operation_specs, diagnostics)

    loop each protocol
        API->>Ctx: create protocol-local name binding table
        API->>ST: typecheck_list(protocol.statements, ctx)

        loop each IR statement
            ST->>ST: look up handlers_by_type by exact IR statement type
            alt handler exists
                ST->>H: handle(stmt, ctx)
                H-->>ST: statement typechecked
            else no handler
                ST->>ST: ignore unsupported statement shape
            end
        end
    end

    API-->>Caller: TypecheckResult(ir, diagnostics)
```

## Statement Typecheck Detail Sequence

```mermaid
sequenceDiagram
    participant ST as "typecheck/statements.py::StatementTypechecker"
    participant H as "typecheck/statements.py::BaseTypecheckStatementHandler subclass"
    participant Expr as "typecheck/expressions.py::TypecheckExpressionServices"
    participant Ctx as "typecheck/context.py::TypecheckContext"
    participant Registry as "program_registry.py"
    participant Diag as "common.diagnostics::Diagnostic"

    ST->>H: handle(stmt, ctx)
    H->>H: prepare(stmt, ctx)
    H->>H: validate_pre_binding_contracts(stmt, ctx, state)
    H->>H: update_or_derive_bindings(stmt, ctx, state)
    H->>H: check_child_expressions(stmt, ctx, state)
    H->>Expr: typecheck_program_calls_in_expr(...) / validate_quantity_dimensions(...)
    Expr->>Expr: resolve_bound_expr(...) / classify_local_expr_type(...)
    Expr->>Registry: get_program_spec(...) when program calls appear
    Expr-->>H: expression-level diagnostics
    H->>Ctx: extend(diagnostics)
    H->>H: check_statement_specific_rules(stmt, ctx, state)
    H->>Ctx: extend(statement-level diagnostics)
    Ctx->>Diag: append Diagnostic

    loop each child statement block
        H->>Ctx: derive_with_bindings(child_local_name_bindings)
        H->>ST: typecheck_list(child_statements, child_ctx)
    end

    H->>H: apply_post_child_effects(stmt, ctx, state)
    H-->>ST: return
```

## Statement Typecheck Lifecycle Template

`BaseTypecheckStatementHandler.handle` owns the statement lifecycle. Concrete
handlers override only the phases they need. Diagnostics are appended through
the shared context. Nested blocks recurse through the same statement dispatcher
with copied or derived local name binding tables.

```mermaid
flowchart TB
    Start([BaseTypecheckStatementHandler.handle])
    Prepare["1. Prepare statement state"]
    Pre["2. Check rules before new names are bound"]
    Bindings["3. Update or derive local name bindings"]
    Exprs["4. Check expressions and program calls"]
    StatementSpecific["5. Check statement type and unit contracts"]
    Blocks["6. Typecheck child statement blocks"]
    Post["7. Apply post child local name effects"]
    Done([Return to statement dispatcher])

    Start --> Prepare
    Prepare --> Pre
    Pre --> Bindings
    Bindings --> Exprs
    Exprs --> StatementSpecific
    StatementSpecific --> Blocks
    Blocks --> Post
    Post --> Done
```

| Phase | Semantic boundary | Typical owners |
| --- | --- | --- |
| `prepare` | Identify the IR statement shape and create handler-local state for later checks. | every statement handler |
| `validate_pre_binding_contracts` | Check rules that must run before this statement changes the local name table. The point is to avoid judging legality against names introduced by the statement itself. | assignment target shape, step operation lookup |
| `update_or_derive_bindings` | Update the local name table, meaning the map from a visible name to the expression it represents. `let volume = 10 mL` records `volume -> 10 mL`; repeat creates a child-only name for the loop variable. | let, repeat, nested block handlers |
| `check_child_expressions` | Resolve names inside expressions, scan nested program calls, and validate program-call argument kinds and dimensions. | let, assign, step, repeat, expression helpers |
| `check_statement_specific_rules` | Check this statement's own contracts: env dimensions, mutation amount dimensions, local assignment compatibility, step arg dimensions, content descriptor shapes, constructor load/capacity units. | with-env, mutation, assignment, step, constructor/program checks |
| `check_child_blocks` | Recurse into nested statement lists with copied or derived local name tables. | with-env, with-constraint, repeat |
| `apply_post_child_effects` | Apply after-child local name table changes if a future statement form needs them. | usually no-op in current behavior |

## Class And Module Diagram

```mermaid
classDiagram
    class TypecheckAPI {
        +typecheck(ir, operation_specs) TypecheckResult
    }

    class TypecheckResult {
        +ir
        +diagnostics
        +ok
    }

    class TypecheckContext {
        +operation_specs
        +diagnostics
        +expr_bindings
        +statement_typechecker
        +derive_with_bindings(bindings) TypecheckContext
        +emit(diagnostic) None
        +extend(diagnostics) None
    }

    class StatementTypechecker {
        +typecheck_list(statements, ctx) None
        +typecheck_statement(stmt, ctx) None
        -handlers_by_type
    }

    class TypecheckExpressionServices {
        +resolve_bound_expr(expr, bindings) object
        +classify_local_expr_type(expr, bindings) str
        +typecheck_program_calls_in_expr(expr, node_id, expr_bindings) list
        +typecheck_assignment(stmt, expr_bindings) list
        +typecheck_with_env(stmt, expr_bindings) list
        +typecheck_mutation(stmt, expr_bindings) list
        +validate_quantity_dimensions(value, expected, codes, label, span, node_id) list
    }

    class TypecheckStatementState {
        +stop
    }

    class ChildStatementBlock {
        +statements
        +expr_bindings
    }

    class BaseTypecheckStatementHandler {
        +handle(stmt, ctx) None
        #prepare(stmt, ctx) TypecheckStatementState
        #validate_pre_binding_contracts(stmt, ctx, state) None
        #update_or_derive_bindings(stmt, ctx, state) None
        #check_child_expressions(stmt, ctx, state) None
        #check_statement_specific_rules(stmt, ctx, state) None
        #iter_child_blocks(stmt, ctx, state) list
        #apply_post_child_effects(stmt, ctx, state) None
        #recurse(child, ctx) None
    }

    class LetTypecheckHandler
    class AssignTypecheckHandler
    class WithEnvTypecheckHandler
    class WithConstraintTypecheckHandler
    class RepeatTypecheckHandler
    class MutationTypecheckHandler
    class StepTypecheckHandler

    class OperationSpec
    class ProgramRegistry
    class Diagnostic
    class IRProgram
    class IRStatement

    TypecheckAPI --> TypecheckResult : returns
    TypecheckAPI --> StatementTypechecker : uses
    TypecheckAPI --> TypecheckContext : creates
    TypecheckContext --> OperationSpec : reads
    TypecheckContext --> Diagnostic : appends
    StatementTypechecker --> BaseTypecheckStatementHandler : dispatches to
    BaseTypecheckStatementHandler --> TypecheckContext : reads / emits through
    BaseTypecheckStatementHandler --> TypecheckExpressionServices : uses
    BaseTypecheckStatementHandler --> TypecheckStatementState : creates
    BaseTypecheckStatementHandler --> ChildStatementBlock : recurses through
    TypecheckExpressionServices --> ProgramRegistry : reads program field specs
    BaseTypecheckStatementHandler <|-- LetTypecheckHandler
    BaseTypecheckStatementHandler <|-- AssignTypecheckHandler
    BaseTypecheckStatementHandler <|-- WithEnvTypecheckHandler
    BaseTypecheckStatementHandler <|-- WithConstraintTypecheckHandler
    BaseTypecheckStatementHandler <|-- RepeatTypecheckHandler
    BaseTypecheckStatementHandler <|-- MutationTypecheckHandler
    BaseTypecheckStatementHandler <|-- StepTypecheckHandler
    IRProgram --> IRStatement : contains
```
