# Compile Module Diagrams

Last updated: 2026-04-21

Related IR document:

1. [ir_structure_diagrams.md](https://github.com/culsma/culsma/blob/main/docs/architecture/ir_structure_diagrams.md)

## Scope

This document has four diagrams only:

1. Functional flowchart: what compile actually does.
2. Runtime sequence: the main runtime call chain.
3. Statement lowering lifecycle template: the common statement-handler lowering sequence.
4. Class/module diagram: which files/classes own each part.

Compile consumes the prepared AST from frontend resolution and returns
`CompileResult(ir, analysis)`. It owns AST-to-Canonical-IR lowering plus
compile-produced sidecar analysis. It does not do semantic validation,
typecheck, plan lowering, runtime execution, or material-state mutation.

## Functional Flowchart

```mermaid
flowchart TB
    Start([Start compile])
    Session["Create compile session:<br/>protocol lookup, protocol ids,<br/>analysis builder, shared compiler state"]
    ProtocolLoop{"More protocols?"}
    ProtocolSetup["Prepare protocol context:<br/>protocol id, params as local names,<br/>return contract checks"]
    StatementLoop{"More source statements?"}
    Dispatch["Select statement lowering handler<br/>by AST statement type"]
    HandlerFound{"Handler exists?"}
    LowerStatement["Lower statement through handler lifecycle:<br/>normalize source form, update compile context,<br/>emit zero or more IR statements,<br/>compile nested blocks when needed"]
    RecordAnalysis["Record sidecar analysis facts<br/>from emitted IR statements"]
    NextStatement["Continue with next source statement"]
    ReturnLowering["Compile protocol return value and bindings"]
    EmitProtocol["Emit IRProtocol"]
    NextProtocol["Continue with next protocol"]
    BuildAnalysis["Build CompileAnalysis for all protocols"]
    Return["Return CompileResult(ir, analysis)"]
    Unsupported["Raise unsupported statement error"]

    Start --> Session
    Session --> ProtocolLoop
    ProtocolLoop -->|yes| ProtocolSetup
    ProtocolSetup --> StatementLoop

    StatementLoop -->|yes| Dispatch
    Dispatch --> HandlerFound
    HandlerFound -->|yes| LowerStatement
    HandlerFound -->|no| Unsupported
    LowerStatement --> RecordAnalysis
    RecordAnalysis --> NextStatement
    NextStatement --> StatementLoop

    StatementLoop -->|no| ReturnLowering
    ReturnLowering --> EmitProtocol
    EmitProtocol --> NextProtocol
    NextProtocol --> ProtocolLoop

    ProtocolLoop -->|no| BuildAnalysis
    BuildAnalysis --> Return
```

## Runtime Sequence

```mermaid
sequenceDiagram
    participant Caller as "frontend / CLI / tests"
    participant API as "compiler.py::compile_ast"
    participant C as "compiler.py::IRCompiler"
    participant Session as "context.py::CompileSession"
    participant SC as "statements.py::StatementCompiler"
    participant M as "statement handler type map"
    participant H as "selected statement lowering handler"
    participant Expr as "expressions.py::ExprCompiler"
    participant Analysis as "analysis.py::CompileAnalysisBuilder"

    Caller->>API: compile_ast(prepared_ast)
    API->>C: IRCompiler(ast).compile_program(ast)
    C->>Session: CompileSession.from_program(ast)

    loop each protocol
        C->>C: validate return contract / create BlockContext
        C->>SC: compile_list(proto.statements, ctx)

        loop each source statement
            SC->>M: look up handler by exact AST statement type
            M-->>SC: selected handler or none
            alt handler exists
                SC->>H: handle(stmt, lowering_ctx)
                H->>Expr: compile expressions / args when needed
                Expr-->>H: IRExpr / IRArg
                H-->>SC: list[IRStatement]
                SC->>Analysis: record_statement_effects(...)
            else no handler
                SC->>SC: raise unsupported statement error
            end
        end

        SC-->>C: protocol IR statements
        C->>Expr: compile return value and return bindings
        C-->>C: emit IRProtocol
    end

    C->>Analysis: build(protocol_ids)
    Analysis-->>C: CompileAnalysis
    C-->>API: CompileResult(ir, analysis)
    API-->>Caller: CompileResult(ir, analysis)
```

## Statement Lowering Lifecycle Template

The statement lowering refactor makes `BaseStatementCompileHandler.handle`
own the lowering lifecycle. Concrete handlers override only the phases they
need. A phase can return final IR output early when the source form is expanded
or lowered completely by that phase.

```mermaid
flowchart TB
    Start([BaseStatementCompileHandler.handle])
    Prepare["1. prepare"]
    StopAfterPrepare{"Final output ready?"}
    Resolve["2. resolve or normalize source form"]
    StopAfterResolve{"Final output ready?"}
    Validate["3. validate source shape"]
    StopAfterValidate{"Final output ready?"}
    StateBefore["4. apply compile-time state before lowering"]
    Prefix["5. lower prefix IR"]
    Current["6. lower current statement or nested blocks"]
    PostEffects["7. apply state after lowering"]
    Return["8. return IR statements"]

    Start --> Prepare
    Prepare --> StopAfterPrepare
    StopAfterPrepare -->|yes| Return
    StopAfterPrepare -->|no| Resolve
    Resolve --> StopAfterResolve
    StopAfterResolve -->|yes| Return
    StopAfterResolve -->|no| Validate
    Validate --> StopAfterValidate
    StopAfterValidate -->|yes| Return
    StopAfterValidate -->|no| StateBefore
    StateBefore --> Prefix
    Prefix --> Current
    Current --> PostEffects
    PostEffects --> Return
```

| Phase | Semantic boundary | Typical owners |
| --- | --- | --- |
| `prepare` | Require source span, use statement id, create handler state. | every statement handler |
| `resolve_source_form` | Resolve or classify frontend syntax before lowering. | protocol-ref name resolution, readout normalization, with-env hold detection, repeat/if mode selection |
| `validate_source_shape` | Reject source forms that are illegal before IR exists. | forbidden legacy/internal calls, assignment target rules, hold placement, runtime-if predicate support |
| `apply_state_before_lowering` | Update compile-time context visible to current/nested lowering. | let/assign `local_names`, `const_env`, `let_bindings` |
| `lower_prefix_ir` | Emit synthesized IR that must appear before the main lowered statement. | grouped readout prefix lets, env target prefix lets, mutation target prefix lets |
| `lower_current_or_children` | Emit direct IR or compile nested statement blocks. | include, let, assign, step, mutation, with-env, with-constraint, repeat, if, control |
| `apply_state_after_lowering` | Update compile-time context after nested lowering decisions. | invalidate runtime-mutated names after repeat/if |
| `return_ir` | Return `list[IRStatement]` to the statement-list dispatcher. | all handlers |

## Class And Module Diagram

```mermaid
classDiagram
    class CompileAPI {
        +compile_ast(ast) CompileResult
    }

    class IRCompiler {
        +compile_program(ast) CompileResult
        +compile_protocol(proto, proto_index) IRProtocol
    }

    class CompileResult {
        +ir
        +analysis
    }

    class CompileSession {
        +qualified_protocol_lookup
        +protocol_lookup
        +protocol_id_by_name
        +analysis_builder
        +state
    }

    class BlockContext {
        +scope_id
        +const_env
        +let_bindings
        +ir_const_env
        +ir_expr_bindings
        +local_names
        +env_time_boundary
        +derive(...)
    }

    class StatementCompiler {
        +compile_list(statements, ctx) list[IRStatement]
        +compile(stmt, ctx, stmt_index) list[IRStatement]
        -_STATEMENT_HANDLERS_BY_TYPE
    }

    class StatementLoweringContext {
        +stmt_id
        +stmt_index
        +block_context
        +statement_compiler
        +session
        +expr_compiler
        +callable_lowering
        +target_resolver
        +schedule_evaluator
    }

    class StatementLoweringState {
        +output
    }

    class BaseStatementCompileHandler {
        +handle(stmt, lowering_ctx) list[IRStatement]
        #prepare(stmt, lowering_ctx) StatementLoweringState
        #resolve_source_form(stmt, lowering_ctx, state) None
        #validate_source_shape(stmt, lowering_ctx, state) None
        #apply_state_before_lowering(stmt, lowering_ctx, state) None
        #lower_prefix_ir(stmt, lowering_ctx, state) list[IRStatement]
        #lower_current_or_children(stmt, lowering_ctx, state) list[IRStatement]
        #apply_state_after_lowering(stmt, lowering_ctx, state, output) None
    }

    class IncludeHandler
    class ProtocolRefHandler
    class LetHandler
    class AssignHandler
    class ExprStatementHandler
    class ReturnHandler
    class WithEnvHandler
    class WithConstraintHandler
    class MutationHandler
    class StepCallHandler
    class ControlHandler
    class RepeatHandler
    class IfHandler

    class ExprCompiler {
        +compile(expr) IRExpr
        +compile_arg(arg) IRArg
        +compile_param(param) IRParam
    }

    class CallableLowering {
        +lower_callable(name, args, span)
        +normalize_grouped_readout_call(call, stmt_id, ctx)
        +normalize_grouped_readout_stepcall(stmt, stmt_id, ctx)
    }

    class TargetResolver {
        +expand_env_targets(targets, stmt_id, ctx)
        +infer_env_targets_from_source_statements(statements, stmt_id, ctx)
        +expand_mutation_targets(target, stmt_id, ctx)
        +expand_mutation_sources(sources, target, flattened_targets, ctx)
    }

    class ScheduleEvaluator {
        +try_eval_numeric_expr(expr, ctx)
        +try_eval_bool_expr(expr, ctx)
        +resolve_repeat_iterable_values(expr, ctx)
        +resolve_schedule_mode(expr, ctx)
        +eval_schedule_points(expr, ctx)
        +eval_repeat_count(expr, ctx)
        +statement_requires_runtime_control(stmt, ctx)
        +invalidate_runtime_mutated_names(statements, ctx)
    }

    class CompileAnalysisBuilder {
        +record_statement_effects(...)
        +build(protocol_ids) CompileAnalysis
    }

    class CompileAnalysis
    class ProtocolAnalysis
    class IRProgram
    class IRProtocol
    class IRStatement

    CompileAPI --> IRCompiler
    IRCompiler --> CompileResult
    IRCompiler --> CompileSession
    IRCompiler --> StatementCompiler
    IRCompiler --> ExprCompiler
    IRCompiler --> IRProtocol
    CompileResult --> IRProgram
    CompileResult --> CompileAnalysis

    CompileSession --> CompileAnalysisBuilder
    CompileAnalysisBuilder --> CompileAnalysis
    CompileAnalysis --> ProtocolAnalysis

    StatementCompiler --> BlockContext
    StatementCompiler --> StatementLoweringContext
    StatementCompiler --> BaseStatementCompileHandler : exact type mapping
    StatementCompiler --> CompileAnalysisBuilder

    StatementLoweringContext --> CompileSession
    StatementLoweringContext --> BlockContext
    StatementLoweringContext --> ExprCompiler
    StatementLoweringContext --> CallableLowering
    StatementLoweringContext --> TargetResolver
    StatementLoweringContext --> ScheduleEvaluator

    BaseStatementCompileHandler --> StatementLoweringState
    BaseStatementCompileHandler --> IRStatement

    BaseStatementCompileHandler <|-- IncludeHandler
    BaseStatementCompileHandler <|-- ProtocolRefHandler
    BaseStatementCompileHandler <|-- LetHandler
    BaseStatementCompileHandler <|-- AssignHandler
    BaseStatementCompileHandler <|-- ExprStatementHandler
    BaseStatementCompileHandler <|-- ReturnHandler
    BaseStatementCompileHandler <|-- WithEnvHandler
    BaseStatementCompileHandler <|-- WithConstraintHandler
    BaseStatementCompileHandler <|-- MutationHandler
    BaseStatementCompileHandler <|-- StepCallHandler
    BaseStatementCompileHandler <|-- ControlHandler
    BaseStatementCompileHandler <|-- RepeatHandler
    BaseStatementCompileHandler <|-- IfHandler

    LetHandler --> CallableLowering
    LetHandler --> ScheduleEvaluator
    LetHandler --> ExprCompiler
    AssignHandler --> ScheduleEvaluator
    AssignHandler --> ExprCompiler
    WithEnvHandler --> TargetResolver
    WithEnvHandler --> ScheduleEvaluator
    WithEnvHandler --> ExprCompiler
    MutationHandler --> TargetResolver
    MutationHandler --> ExprCompiler
    StepCallHandler --> CallableLowering
    StepCallHandler --> ExprCompiler
    RepeatHandler --> ScheduleEvaluator
    IfHandler --> ScheduleEvaluator
```
