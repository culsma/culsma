# Parser Module Diagrams

Last updated: 2026-04-23

## Scope

This document has five diagrams only:

1. Functional flowchart: what parser actually does.
2. Runtime sequence: the main runtime call chain.
3. AST assembly detail flowchart: how parse-tree values become AST nodes.
4. Parse rule conversion sequence: how the handler-based transformer runs.
5. Class/module diagram: which files/classes own each part.

Parser consumes Culsma source text or local source files and returns a parser
AST `Program`. It owns grammar parsing, local source include assembly, span
capture, token decoding, parser-surface normalization, and AST construction.
It does not own bundled stdlib loading, installed library resolution, semantic
validation, IR lowering, compile analysis, or runtime execution.

Lark owns grammar parsing and callback-name dispatch. `CulsmaTransformer`
keeps the Lark-required callback method names, then routes each callback into
`ParseRuleDispatcher` and the `BaseParseRuleHandler` lifecycle.

## Functional Flowchart

This flowchart shows the core parser path: one source string becomes one
`Program` AST. File APIs such as `parse_file` and `parse_files` are wrappers
around this path; they read source text, call this parser flow, then tag or
merge returned `Program` objects.

```mermaid
flowchart TB
    Start(["parse(source: str)"])
    LarkParse["Check source text against grammar<br/>and produce a parse tree"]
    WalkTree["Walk the parse tree from children to parents"]
    PrimitiveValues["Convert raw tokens into parser values:<br/>source spans, names, literals, quantities,<br/>booleans, selectors"]
    Assemble["Assemble AST from transformed children"]
    Return["Return Program AST"]

    Start --> LarkParse
    LarkParse --> WalkTree
    WalkTree --> PrimitiveValues
    PrimitiveValues --> Assemble
    Assemble --> Return
```

## Runtime Sequence

```mermaid
sequenceDiagram
    participant Caller as "frontend / CLI / tests"
    participant API as "parser.py::parse"
    participant Lark as "lark.Lark + culsma.lark"
    participant T as "transformer.py::CulsmaTransformer"

    Caller->>API: parse(source)
    API->>Lark: parse source text
    Lark-->>API: parse tree
    API->>T: transform(parse tree)
    T-->>API: Program AST
    API-->>Caller: Program AST
```

## AST Assembly Detail Flowchart

This flowchart expands the single "Assemble AST" step from the main parser
flow. These are internal transformer details, not separate parser phases.

```mermaid
flowchart TB
    Start(["Assemble AST"])
    Dispatch["Dispatch grammar rule callback<br/>to parse rule handler"]
    Lifecycle["Run BaseParseRuleHandler lifecycle:<br/>prepare, read span, use children,<br/>normalize surface form, construct AST"]
    Leaf["Build primitive parser values:<br/>identifiers, literals, quantities,<br/>booleans, selectors"]
    Expr["Build expression AST:<br/>operators, calls, members,<br/>indexing, lists, groups"]
    Stmt["Build statement AST:<br/>let, assign, return, step,<br/>with blocks, mutation, repeat, if"]
    TopLevel["Build top-level AST:<br/>source includes, imports, protocols, Program"]
    Return["Return AST value to parent rule"]

    Start --> Dispatch
    Dispatch --> Lifecycle
    Lifecycle --> Leaf
    Lifecycle --> Expr
    Lifecycle --> Stmt
    Lifecycle --> TopLevel
    Leaf --> Return
    Expr --> Return
    Stmt --> Return
    TopLevel --> Return
```

## Parse Rule Conversion Sequence

```mermaid
sequenceDiagram
    participant Lark as "LarkParser"
    participant T as "CulsmaTransformer"
    participant Dispatcher as "ParseRuleDispatcher"
    participant Ctx as "ParseRuleContext"
    participant Base as "BaseParseRuleHandler"
    participant Top as "TopLevelRuleHandler"
    participant Stmt as "StatementRuleHandler"
    participant Expr as "ExpressionRuleHandler"
    participant Surface as "SurfaceRuleHandler"
    participant Common as "CommonHelpers"
    participant AST as "ast_nodes.py"

    loop child nodes before parent nodes
        Lark->>T: rule callback(meta, items)
        T->>Dispatcher: handler_for(rule_name)
        Dispatcher-->>T: BaseParseRuleHandler subclass
        T->>Ctx: provide span/token helper context
        T->>Base: handle(meta, items, ctx)
        Base->>Ctx: read span or decode token when needed
        Ctx->>Common: use shared parser helpers
        alt top-level rule
            Base->>Top: construct_ast(...)
            Top->>AST: construct Program or ProtocolDecl
            AST-->>Top: AST value
            Top-->>Base: AST value
        else statement rule
            Base->>Stmt: construct_ast(...)
            Stmt->>AST: construct Statement dataclass
            AST-->>Stmt: AST value
            Stmt-->>Base: AST value
        else expression rule
            Base->>Expr: construct_ast(...)
            Expr->>AST: construct Expression dataclass
            AST-->>Expr: AST value
            Expr-->>Base: AST value
        else surface-normalization rule
            Base->>Surface: construct_ast(...)
            Surface->>AST: construct normalized Statement or Expression
            AST-->>Surface: AST value
            Surface-->>Base: AST value
        end
        Base-->>T: AST value
        T-->>Lark: transformed child value for parent rule
    end
```

## Class And Module Diagram

```mermaid
classDiagram
    class ParserAPI {
        +parse(source) Program
        +parse_file(path) Program
        +parse_files(paths, entry_protocol) Program
        -_tag_protocol_modules(program, module_name) None
    }

    class LarkParser {
        +parse(source) Tree
    }

    class CulsmaTransformer {
        +start(meta, items)
        +protocol_decl(meta, items)
        +let_statement(meta, items)
        +call_statement(meta, items)
        +or_op(meta, items)
        +quantity(meta, items)
        +method_call_expr(meta, items)
        -_dispatch(rule_name, meta, items)
    }

    class ParseRuleDispatcher {
        +handler_for(rule_name) BaseParseRuleHandler
        +dispatch(rule_name, meta, items, ctx) object
        -handlers
    }

    class ParseRuleContext {
        +span_from_meta(meta) Span
        +decode_string_token(token) str
        +decode_quantity(token, meta) Quantity
        +decode_boolean(token, meta) BooleanLiteral
        +decode_selector_region(start_token, end_token, meta) SelectorRegion
    }

    class CommonHelpers {
        +span_from_meta(meta) Span
        +decode_string_token(token) str
        +decode_quantity(token, span) Quantity
        +decode_boolean(token, span) BooleanLiteral
        +decode_selector_region(start_token, end_token, span) SelectorRegion
    }

    class BaseParseRuleHandler {
        +handle(meta, items, ctx) object
        #prepare(meta, items, ctx) ParseRuleState
        #read_span(meta, ctx) Span
        #use_children(meta, items, ctx, state) None
        #normalize_surface(meta, items, ctx, state) None
        #construct_ast(meta, items, ctx, state) object
    }

    class TopLevelRuleHandler
    class StatementRuleHandler
    class ExpressionRuleHandler
    class SurfaceRuleHandler

    class StartHandler
    class ProtocolDeclHandler
    class LetStatementHandler
    class CallStatementHandler
    class RepeatStatementHandler
    class IfStatementHandler
    class QuantityHandler
    class CallExprHandler
    class MethodCallExprHandler

    class Program
    class ProtocolDecl
    class Statement
    class Expression

    ParserAPI --> LarkParser : uses
    ParserAPI --> CulsmaTransformer : owns singleton
    ParserAPI --> Program : returns
    CulsmaTransformer --> ParseRuleDispatcher : uses
    CulsmaTransformer --> ParseRuleContext : passes
    ParseRuleDispatcher --> BaseParseRuleHandler : selects
    ParseRuleContext --> CommonHelpers : uses
    BaseParseRuleHandler <|-- TopLevelRuleHandler
    BaseParseRuleHandler <|-- StatementRuleHandler
    BaseParseRuleHandler <|-- ExpressionRuleHandler
    BaseParseRuleHandler <|-- SurfaceRuleHandler
    TopLevelRuleHandler <|-- StartHandler
    TopLevelRuleHandler <|-- ProtocolDeclHandler
    StatementRuleHandler <|-- LetStatementHandler
    StatementRuleHandler <|-- RepeatStatementHandler
    StatementRuleHandler <|-- IfStatementHandler
    SurfaceRuleHandler <|-- CallStatementHandler
    ExpressionRuleHandler <|-- QuantityHandler
    ExpressionRuleHandler <|-- CallExprHandler
    ExpressionRuleHandler <|-- MethodCallExprHandler
    TopLevelRuleHandler --> Program : constructs
    TopLevelRuleHandler --> ProtocolDecl : constructs
    StatementRuleHandler --> Statement : constructs
    ExpressionRuleHandler --> Expression : constructs
```
