# Compile Module Diagrams

Last updated: 2026-05-26

Related IR document:

1. [ir_structure_diagrams.md](./ir_structure_diagrams.md)

## Scope

This document has six diagrams only:

1. Functional flowchart: what compile actually does.
2. Runtime sequence: the main runtime call chain.
3. Formal-parameter static-control flowchart: how compile decides to defer.
4. Formal-parameter static-control sequence: module API calls for that decision.
5. Statement lowering lifecycle template: the common statement-handler lowering sequence.
6. Class/module diagram: which files/classes own each part.

Compile consumes the prepared AST from frontend resolution and returns
`CompileResult(ir, analysis)`. It owns AST-to-Canonical-IR lowering plus
compile-produced sidecar analysis. It does not do semantic validation,
typecheck, plan lowering, runtime execution, or material-state mutation.
Compile may classify formal-parameter-dependent static control as plan-static
when the control surface cannot be resolved before protocol argument binding;
the actual parameter-bound static evaluation remains owned by plan lowering.
`compile/static_control.py` owns that compile-stage classification boundary.

## Functional Flowchart

```mermaid
flowchart TB
    Start([Start compile])
    Session["Create compile session:<br/>protocol lookup, protocol ids,<br/>analysis builder, shared compiler state"]
    ProtocolLoop{"More protocols?"}
    ProtocolSetup["Prepare protocol context:<br/>protocol id, params as local/formal names,<br/>return contract checks"]
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
    participant Caller as "Frontend / CLI / Tests"
    participant API as "CompileAPI"
    participant C as "IRCompiler"
    participant Session as "CompileSession"
    participant SC as "StatementCompiler"
    participant H as "BaseStatementCompileHandler"
    participant Expr as "ExprCompiler"
    participant Analysis as "CompileAnalysisBuilder"

    Caller->>API: compile_ast(prepared_ast)
    API->>C: IRCompiler(ast).compile_program(ast)
    C->>Session: from_program(ast)

    loop ProtocolDecl
        C->>C: compile_protocol(proto, proto_index)
        C->>SC: compile_list(proto.statements, ctx)

        loop Statement
            SC->>SC: lookup handler by statement type
            alt BaseStatementCompileHandler
                SC->>H: handle(stmt, lowering_ctx)
                H->>H: prepare(stmt, lowering_ctx)
                H->>H: resolve_source_form(stmt, lowering_ctx, state)
                H->>H: validate_source_shape(stmt, lowering_ctx, state)
                H->>H: apply_state_before_lowering(stmt, lowering_ctx, state)
                H->>H: lower_prefix_ir(stmt, lowering_ctx, state)
                H->>H: lower_current_or_children(stmt, lowering_ctx, state)
                H->>H: apply_state_after_lowering(stmt, lowering_ctx, state, output)
                H->>Expr: compile(...) / compile_arg(...)
                Expr-->>H: IRExpr / IRArg
                H-->>SC: list[IRStatement]
                SC->>Analysis: record_statement_effects(...)
            else None
                SC->>SC: raise TypeError
            end
        end

        SC-->>C: list[IRStatement]
        C->>Expr: compile(return_value / return_bindings)
        C-->>C: IRProtocol
    end

    C->>Analysis: build(protocol_ids)
    Analysis-->>C: CompileAnalysis
    C-->>API: CompileResult(ir, analysis)
    API-->>Caller: CompileResult(ir, analysis)
```

## Formal Parameter Static-Control Detail

This section is an internal compile detail. It explains how the selected
statement handler, running inside the common `BaseStatementCompileHandler`
lifecycle above, decides whether a control surface is resolved during compile
or preserved for parameter-bound static evaluation during plan lowering.
`SelectedStatementHandler` means the concrete handler currently executing that
base lifecycle; it is not a separate module in the compile architecture.
`RepeatControlLowerer` is the repeat-specific compile service called from
`RepeatHandler.lower_current_or_children` to keep the handler lifecycle adapter
separate from repeat control lowering algorithms.

```mermaid
flowchart TB
    Start([Selected statement handler reaches control surface])
    Surface{"Control surface kind?"}
    Env["Env time boundary:<br/>duration or thermal_program duration"]
    RepeatCount["Repeat count expression"]
    RepeatSchedule["Repeat schedule expression"]
    IfCondition["If condition expression"]
    TryCompile["Try compile-time evaluation with current let/const context"]
    Resolved{"Resolved at compile time?"}
    LowerNow["Lower or expand during compile"]
    IfSupported{"Supported runtime/formal predicate surface?"}
    CheckFormal["Check whether unresolved env/repeat expression contains formal parameters"]
    Deferable{"Can defer to plan static evaluation?"}
    PreserveRepeat["Preserve IRRepeat with schedule/count payload"]
    PreserveEnv["Compile child block with env_time_boundary_deferred"]
    PreserveIf["Emit IRConditional for plan/runtime selection"]
    Error["Raise compile-time shape/value error"]
    Plan["Plan lowering binds protocol args<br/>and completes static evaluation"]

    Start --> Surface
    Surface --> Env
    Surface --> RepeatCount
    Surface --> RepeatSchedule
    Surface --> IfCondition
    Env --> TryCompile
    RepeatCount --> TryCompile
    RepeatSchedule --> TryCompile
    IfCondition --> TryCompile
    TryCompile --> Resolved
    Resolved -->|yes| LowerNow
    Resolved -->|no if condition| IfSupported
    IfSupported -->|yes| PreserveIf
    IfSupported -->|no| Error
    Resolved -->|no env/repeat| CheckFormal
    CheckFormal --> Deferable
    Deferable -->|env boundary| PreserveEnv
    Deferable -->|repeat count/schedule| PreserveRepeat
    Deferable -->|no| Error
    PreserveEnv --> Plan
    PreserveRepeat --> Plan
    PreserveIf --> Plan
```

```mermaid
sequenceDiagram
    participant H as "SelectedStatementHandler"
    participant RCL as "RepeatControlLowerer"
    participant Sched as "ScheduleEvaluator"
    participant Static as "StaticControlClassifier"
    participant Ctx as "BlockContext"
    participant SC as "StatementCompiler"
    participant Expr as "ExprCompiler"

    H->>H: lower_current_or_children(stmt, lowering_ctx, state)
    alt WithEnvStmt boundary
        H->>Sched: extract_env_time_boundary(stmt, ctx)
        Sched->>Sched: resolve_bound_expr(expr, ctx)
        Sched->>Sched: is_time_point(quantity)
        alt compile-time boundary
            Sched-->>H: Quantity boundary
            H->>Ctx: derive(env_time_boundary=boundary)
        else formal-param boundary
            Sched-->>H: None
            H->>Static: can_defer_env_time_boundary(stmt, ctx)
            Static->>Static: resolve_bound_expr(expr, ctx)
            Static->>Static: contains_unresolved_param_reference(expr, ctx)
            Static-->>H: true
            H->>Ctx: derive(env_time_boundary_deferred=True)
        end
        H->>Expr: compile_arg(env_arg) / compile(target)
        H->>SC: compile_list(child_statements, child_ctx)
    else RepeatStatement count
        H->>RCL: lower_repeat(stmt, lowering_ctx)
        RCL->>RCL: lower_count_repeat(stmt, lowering_ctx)
        RCL->>Sched: eval_repeat_count(times, ctx)
        alt compile-time count
            Sched-->>RCL: int iterations
            RCL->>SC: compile(nested_stmt, nested_ctx, stmt_index)
        else formal-param count
            RCL->>Static: can_defer_repeat_count(times, ctx)
            Static->>Static: contains_unresolved_param_reference(times, ctx)
            Static-->>RCL: true
            RCL->>RCL: count_repeat_schedule_expr(stmt)
            RCL->>RCL: lower_deferred_static_repeat(stmt, lowering_ctx, iterable)
            RCL->>SC: compile_list(body, child_ctx)
        end
    else RepeatStatement schedule
        H->>RCL: lower_repeat(stmt, lowering_ctx)
        RCL->>Sched: resolve_repeat_iterable_values(iterable, ctx)
        RCL->>Sched: resolve_bound_expr(iterable, ctx)
        RCL->>Sched: resolve_schedule_mode(iterable, ctx)
        alt discrete schedule resolved
            RCL->>Sched: eval_schedule_points(iterable, ctx)
            Sched-->>RCL: list[Quantity]
            RCL->>RCL: lower_iterable_values(stmt, lowering_ctx, points)
        else continuous schedule resolved
            RCL->>Sched: eval_continuous_schedule_boundary(iterable, ctx)
            Sched-->>RCL: Quantity boundary
            RCL->>Ctx: derive(env_time_boundary=boundary)
            RCL->>SC: compile(nested_stmt, nested_ctx, stmt_index)
        else schedule depends on formal params
            RCL->>Static: can_defer_discrete_schedule(iterable, ctx)
            RCL->>Static: can_defer_continuous_schedule(iterable, ctx)
            Static->>Static: schedule_args(iterable, ctx)
            Static->>Static: schedule_mode(args)
            Static->>Static: contains_unresolved_param_reference(arg_value, ctx)
            Static-->>RCL: true
            RCL->>RCL: lower_deferred_static_repeat(stmt, lowering_ctx, iterable)
            RCL->>SC: compile_list(body, child_ctx)
        end
    else IfStatement condition
        H->>Sched: try_eval_bool_expr(condition, ctx)
        alt compile-time bool
            Sched-->>H: true or false
            H->>SC: compile(selected_stmt, ctx, stmt_index)
        else runtime or formal-param predicate
            H->>Sched: supports_runtime_boolean_surface(condition)
            H->>SC: compile_list(then_statements, child_ctx)
            H->>SC: compile_list(else_statements, child_ctx)
        end
    end
    alt RepeatStatement or IfStatement post effect
        H->>Sched: invalidate_runtime_mutated_names(statements, ctx)
    end
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
        +param_names
        +env_time_boundary
        +env_time_boundary_deferred
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
        +static_control_classifier
        +repeat_control_lowerer
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
        +eval_continuous_schedule_boundary(expr, ctx)
        +eval_schedule_points(expr, ctx)
        +eval_repeat_count(expr, ctx)
        +statement_requires_runtime_control(stmt, ctx)
        +static_control_action(statements)
        +invalidate_runtime_mutated_names(statements, ctx)
        +resolve_bound_expr(expr, ctx)
        +extract_env_time_boundary(stmt, ctx)
        +supports_runtime_boolean_surface(expr)
        +is_time_point(point)
    }

    class StaticControlClassifier {
        +can_defer_repeat_count(expr, ctx)
        +can_defer_discrete_schedule(expr, ctx)
        +can_defer_continuous_schedule(expr, ctx)
        +can_defer_env_time_boundary(stmt, ctx)
        +schedule_args(expr, ctx)
        +schedule_mode(args)
        +resolve_bound_expr(expr, ctx)
        +contains_unresolved_param_reference(expr, ctx)
    }

    class RepeatControlLowerer {
        +lower_repeat(stmt, lowering_ctx)
        +lower_binding_repeat(stmt, lowering_ctx)
        +lower_count_repeat(stmt, lowering_ctx)
        +lower_iterable_values(stmt, lowering_ctx, iterable_values)
        +lower_continuous_schedule(stmt, lowering_ctx)
        +lower_deferred_static_repeat(stmt, lowering_ctx, iterable)
        +count_repeat_schedule_expr(stmt)
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
    IRCompiler --> CallableLowering
    IRCompiler --> TargetResolver
    IRCompiler --> ScheduleEvaluator
    IRCompiler --> StaticControlClassifier
    IRCompiler --> RepeatControlLowerer
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
    StatementLoweringContext --> StaticControlClassifier
    StatementLoweringContext --> RepeatControlLowerer

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
    WithEnvHandler --> StaticControlClassifier
    WithEnvHandler --> ExprCompiler
    MutationHandler --> TargetResolver
    MutationHandler --> ExprCompiler
    StepCallHandler --> CallableLowering
    StepCallHandler --> ExprCompiler
    RepeatHandler --> RepeatControlLowerer
    RepeatControlLowerer --> ScheduleEvaluator
    RepeatControlLowerer --> StaticControlClassifier
    RepeatControlLowerer --> StatementCompiler
    RepeatControlLowerer --> ExprCompiler
    IfHandler --> ScheduleEvaluator
```
