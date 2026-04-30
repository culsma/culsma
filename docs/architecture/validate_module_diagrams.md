# Validate Module Diagrams

Last updated: 2026-04-21

Related IR document:

1. [ir_structure_diagrams.md](https://github.com/culsma/culsma/blob/main/docs/architecture/ir_structure_diagrams.md)

## Scope

This document has four diagrams only:

1. Functional flowchart: what `validate` actually does.
2. Runtime sequence: the main runtime call chain.
3. Handler lifecycle template: the common statement-handler validation sequence.
4. Class/module diagram: which files/classes own each part.

Semantic validation consumes Canonical IR plus compile analysis and returns
`ValidationResult(ir, diagnostics)`. It does not do typecheck, plan lowering,
runtime execution, or material-state mutation.

## Functional Flowchart

```mermaid
flowchart TB
    Start([Start semantic validation])
    Init["Prepare diagnostics and validation options"]
    ProtocolLoop{"More protocols?"}
    ProtocolState["Create validation state for this protocol"]
    IncludeFacts["Load include/export facts for this protocol"]
    StatementLoop{"More statements?"}
    Dispatch["Select statement handler by statement type"]
    HandlerFound{"Handler exists?"}
    Handler["Execute the selected statement handler:<br/>semantic checks, diagnostics, state updates,<br/>and nested validation when needed"]
    NextStatement["Continue with next statement"]
    NextProtocol["Continue with next protocol"]
    Return["Return original IR with diagnostics"]

    Start --> Init
    Init --> ProtocolLoop
    ProtocolLoop -->|yes| ProtocolState
    ProtocolState --> IncludeFacts
    IncludeFacts --> StatementLoop

    StatementLoop -->|yes| Dispatch
    StatementLoop -->|no| NextProtocol
    NextProtocol --> ProtocolLoop
    ProtocolLoop -->|no| Return

    Dispatch --> HandlerFound
    HandlerFound -->|yes| Handler
    HandlerFound -->|no| NextStatement
    Handler --> NextStatement
    NextStatement --> StatementLoop
```

## Runtime Sequence

```mermaid
sequenceDiagram
    participant Caller as "cli / tests / API"
    participant V as "validator.py::validate"
    participant S as "statements.py::validate_statement_list_with_context"
    participant M as "handler type map"
    participant H as "selected statement handler"
    participant A as "analysis.py::CompileAnalysis / ProtocolAnalysis"

    Caller->>V: validate(ir, analysis, options)
    V->>V: create diagnostics / select operation_specs

    loop each protocol
        V->>A: analysis.protocols.get(protocol.id)
        V->>V: create StatementValidationContext
        V->>S: validate_statement_list_with_context(protocol.statements, ctx)

        loop each statement
            S->>M: look up handler by exact statement type
            M-->>S: selected handler or none
            alt handler exists
                S->>H: handle(stmt, ctx)
                H-->>S: diagnostics/state updated through ctx
            else no handler
                S->>S: ignore unsupported statement shape
            end
        end
    end

    V-->>Caller: ValidationResult(ir, diagnostics)
```

## Handler Lifecycle Template

The handler refactor makes `BaseStatementHandler.handle` own the validation
lifecycle. Concrete handlers only override the phases they need. Diagnostics
are appended when each validation phase runs, not collected as a separate
final phase. A phase can mark the handler state as stopped when later phases
would be invalid or redundant for the current statement.

```mermaid
flowchart TB
    Start([BaseStatementHandler.handle])
    Prepare["1. prepare"]
    Stop{"Stop this statement?"}
    PreContracts["2. validate pre-binding contracts"]
    StopAfterPre{"Stop this statement?"}
    Bindings["3. validate binding reads"]
    StopAfterBinding{"Stop this statement?"}
    PostContracts["4. validate post-binding contracts"]
    StopAfterPostBinding{"Stop this statement?"}
    StateBefore["5. apply state before children"]
    StopAfterStateBefore{"Stop this statement?"}
    Expressions["6. validate child expressions"]
    StopAfterExpressions{"Stop this statement?"}
    Blocks["7. validate child statement blocks"]
    StopAfterBlocks{"Stop this statement?"}
    PostChild["8. validate post-child contracts"]
    StopAfterPostChild{"Stop this statement?"}
    StateAfter["9. apply state after children"]
    Done([Return to statement dispatcher])

    Start --> Prepare
    Prepare --> Stop
    Stop -->|yes| Done
    Stop -->|no| PreContracts
    PreContracts --> StopAfterPre
    StopAfterPre -->|yes| Done
    StopAfterPre -->|no| Bindings
    Bindings --> StopAfterBinding
    StopAfterBinding -->|yes| Done
    StopAfterBinding -->|no| PostContracts
    PostContracts --> StopAfterPostBinding
    StopAfterPostBinding -->|yes| Done
    StopAfterPostBinding -->|no| StateBefore
    StateBefore --> StopAfterStateBefore
    StopAfterStateBefore -->|yes| Done
    StopAfterStateBefore -->|no| Expressions
    Expressions --> StopAfterExpressions
    StopAfterExpressions -->|yes| Done
    StopAfterExpressions -->|no| Blocks
    Blocks --> StopAfterBlocks
    StopAfterBlocks -->|yes| Done
    StopAfterBlocks -->|no| PostChild
    PostChild --> StopAfterPostChild
    StopAfterPostChild -->|yes| Done
    StopAfterPostChild -->|no| StateAfter
    StateAfter --> Done
```

| Phase | Semantic boundary | Typical owners |
| --- | --- | --- |
| `prepare` | Derive statement-local facts and decide whether validation can continue. | step operation lookup, builtin step classification |
| `validate_pre_binding_contracts` | Check rules that must use the incoming scope and statement declaration. | active constraint compatibility, unknown-step stop, assign target shape, let-call shape, step arg names, constructor/readout statement contracts |
| `validate_bindings` | Check all reads against names visible before the current statement mutates state. | unbound reads in let, assign, repeat, mutation, with-env, step |
| `validate_post_binding_contracts` | Check statement semantics that depend on binding or resolved values. | env contracts, mutation contracts |
| `apply_state_before_children` | Apply state that child expressions or blocks must see. | let expression/literal/group bindings, assign root binding, include exports |
| `validate_child_expressions` | Recurse into direct child expressions with shared expression contracts. | let value, assign target/value, step args, with-env args, repeat iterable, condition |
| `validate_child_blocks` | Recurse nested statement lists with derived block context. | with-env body, with-constraint body, repeat body, conditional branches |
| `validate_post_child_contracts` | Run checks intentionally placed after child expression validation. | agit-specific step checks, other order-sensitive checks |
| `apply_state_after_children` | Publish effects that should only affect later sibling statements. | let runtime name, step-defined names |

## Class And Module Diagram

```mermaid
classDiagram
    class ValidatorEntry {
        +validate(ir, analysis, options) ValidationResult
    }

    class StatementDispatcher {
        +validate_statement_list_with_context(statements, ctx) None
        -_STATEMENT_HANDLERS_BY_TYPE
    }

    class StatementValidationContext {
        +literal_bindings
        +expr_bindings
        +group_bindings
        +defined_names
        +active_requirements
        +diagnostics
        +operations
        +analysis
        +protocol_analysis
        +enforce_binding
        +content_whitelist_mode
        +content_type_policy
    }

    class HandlerState {
        +stop
    }

    class ChildExpression {
        +expr
        +node_id
    }

    class ChildBlock {
        +statements
        +defined_names
        +active_requirements
    }

    class BaseStatementHandler {
        +handle(stmt, ctx) None
        #prepare(stmt, ctx) HandlerState
        #validate_pre_binding_contracts(stmt, ctx, state) None
        #validate_bindings(stmt, ctx, state) None
        #validate_post_binding_contracts(stmt, ctx, state) None
        #apply_state_before_children(stmt, ctx, state) None
        #iter_child_expressions(stmt, ctx, state)
        #iter_child_blocks(stmt, ctx, state)
        #validate_post_child_contracts(stmt, ctx, state) None
        #apply_state_after_children(stmt, ctx, state) None
        #validate_expr(expr, ctx, node_id) None
        #recurse(statements, ctx) None
        #copy_block_context(ctx) StatementValidationContext
        #append_diagnostics(ctx, diagnostics) None
    }

    class LetHandler
    class AssignHandler
    class IncludeHandler
    class WithEnvHandler
    class WithConstraintHandler
    class RepeatHandler
    class ConditionalHandler
    class ControlHandler
    class MutationHandler
    class StepHandler

    class StatementContracts {
        +validate_assign_target_contract(...)
        +validate_with_constraint_contract(...)
        +validate_active_constraint_compatibility(...)
        +validate_active_env_constraint_compatibility(...)
        +validate_mutation_contract(...)
        +validate_let_call_contract(...)
        +validate_readout_schema_contract(...)
        +validate_agit_contract(...)
    }

    class ExpressionContracts {
        +validate_expr_contracts(...)
    }

    class BindingValidator
    class OperationContractValidator
    class EnvContractValidator
    class ConstructorValidator
    class GroupIndexValidator
    class ProgramContractValidator
    class ExprResolver
    class CompileAnalysis
    class ProtocolAnalysis
    class ValidationResult

    ValidatorEntry --> ValidationResult
    ValidatorEntry --> StatementValidationContext
    ValidatorEntry --> StatementDispatcher
    ValidatorEntry --> CompileAnalysis

    StatementDispatcher --> BaseStatementHandler : exact type mapping
    StatementDispatcher --> StatementValidationContext

    BaseStatementHandler --> HandlerState
    BaseStatementHandler --> ChildExpression
    BaseStatementHandler --> ChildBlock
    BaseStatementHandler <|-- LetHandler
    BaseStatementHandler <|-- AssignHandler
    BaseStatementHandler <|-- IncludeHandler
    BaseStatementHandler <|-- WithEnvHandler
    BaseStatementHandler <|-- WithConstraintHandler
    BaseStatementHandler <|-- RepeatHandler
    BaseStatementHandler <|-- ConditionalHandler
    BaseStatementHandler <|-- ControlHandler
    BaseStatementHandler <|-- MutationHandler
    BaseStatementHandler <|-- StepHandler

    BaseStatementHandler --> StatementValidationContext
    BaseStatementHandler --> ExpressionContracts

    LetHandler --> StatementContracts
    LetHandler --> BindingValidator
    LetHandler --> GroupIndexValidator
    AssignHandler --> StatementContracts
    AssignHandler --> BindingValidator
    IncludeHandler --> CompileAnalysis
    IncludeHandler --> ProtocolAnalysis
    WithEnvHandler --> StatementContracts
    WithEnvHandler --> BindingValidator
    WithEnvHandler --> EnvContractValidator
    WithConstraintHandler --> StatementContracts
    RepeatHandler --> BindingValidator
    MutationHandler --> StatementContracts
    MutationHandler --> BindingValidator
    StepHandler --> StatementContracts
    StepHandler --> BindingValidator
    StepHandler --> ConstructorValidator

    StatementContracts --> BindingValidator
    StatementContracts --> OperationContractValidator
    StatementContracts --> ConstructorValidator
    StatementContracts --> ExprResolver
    StatementContracts --> ExpressionContracts

    ExpressionContracts --> GroupIndexValidator
    ExpressionContracts --> ProgramContractValidator
    ExpressionContracts --> ConstructorValidator
    ExpressionContracts --> ExprResolver
```
