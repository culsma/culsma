"""
Culsma AST node definitions.

Each class corresponds to a grammar rule in the current parser grammar.
These are pure data structures with no behavior and no validation.
Semantic checks belong in a later stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from culsma.common.source import Span

# ============================================================
# Top-level
# ============================================================


@dataclass
class Program:
    """A Culsma source file (or merged workspace) with includes and protocols."""
    source_includes: list[SourceIncludeDecl] = field(default_factory=list)
    library_imports: list[LibraryImportDecl] = field(default_factory=list)
    protocols: list[ProtocolDecl] = field(default_factory=list)
    span: Span | None = None


@dataclass
class SourceIncludeDecl:
    """include "path/to/file.culs" (top-level only)"""
    path: str
    span: Span | None = None


@dataclass
class LibraryImportDecl:
    """import Foo; (top-level library import only)"""
    name: str
    span: Span | None = None


# ============================================================
# Statements
# ============================================================

@dataclass
class ProtocolDecl:
    """protocol <name>([params]) { <statements> }"""
    name: str
    module: str | None = None
    params: list[ParamDecl] = field(default_factory=list)
    returns: list[str] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    span: Span | None = None


@dataclass
class ParamDecl:
    """<name> [= <expression>]"""
    name: str
    default: Expression | None = None
    span: Span | None = None


@dataclass
class IncludeStatement:
    """include <name>"""
    name: str
    span: Span | None = None


@dataclass
class ProtocolRefStatement:
    """<module>.<protocol>([named_args])"""
    module: str
    protocol: str
    args: list[Arg] = field(default_factory=list)
    span: Span | None = None


@dataclass
class LetStatement:
    """let <name> = <expression>"""
    name: str
    value: Expression
    span: Span | None = None


@dataclass
class ReturnStatement:
    """return <expression> | return <name> = <expression>, ..."""
    value: Expression | None = None
    bindings: list[ReturnBinding] = field(default_factory=list)
    span: Span | None = None


@dataclass
class ReturnBinding:
    """<name> = <expression> inside named return"""
    name: str
    value: Expression
    span: Span | None = None


@dataclass
class AssignStatement:
    """<target> = <expression>"""
    target: Expression
    value: Expression
    span: Span | None = None


@dataclass
class ExprStatement:
    """<expression> as a standalone statement"""
    value: Expression
    span: Span | None = None


@dataclass
class StepCall:
    """<StepName>(<arg>, <arg>, ...)"""
    name: str
    args: list[Arg] = field(default_factory=list)
    span: Span | None = None


@dataclass
class WithEnvStmt:
    """with env(<env_args>) { <statements> }"""
    env_args: list[Arg] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    span: Span | None = None


@dataclass
class WithConstraintStmt:
    """with constraint(<requirements>, [<options>]) { <statements> }"""
    requirements: list[str] = field(default_factory=list)
    options: list[Arg] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    span: Span | None = None


@dataclass
class MutationStmt:
    """<target> << [<sources>]"""
    target: Expression
    sources: list[Expression] = field(default_factory=list)
    span: Span | None = None


@dataclass
class BreakStmt:
    """break"""
    span: Span | None = None


@dataclass
class ContinueStmt:
    """continue"""
    span: Span | None = None


@dataclass
class RepeatStatement:
    """repeat <times_expr> { ... } | repeat <name> in <iter_expr> { ... }"""
    times: Expression | None = None
    binding: str | None = None
    iterable: Expression | None = None
    statements: list[Statement] = field(default_factory=list)
    span: Span | None = None


@dataclass
class IfStatement:
    """if <condition_expr> { <then_statements> } [else { <else_statements> }]"""
    condition: Expression
    then_statements: list[Statement] = field(default_factory=list)
    else_statements: list[Statement] = field(default_factory=list)
    span: Span | None = None


@dataclass
class Arg:
    """<name> = <expression>  (inside a step call)"""
    name: str
    value: Expression
    span: Span | None = None


# ============================================================
# Expressions
# ============================================================

@dataclass
class BinaryOp:
    """<left> <op> <right>  where op is +, -, *, /, ==, !=, <, >, <=, >=, and, or"""
    op: str
    left: Expression
    right: Expression
    span: Span | None = None


@dataclass
class UnaryOp:
    """<op> <operand>  where op is -"""
    op: str
    operand: Expression
    span: Span | None = None


@dataclass
class Quantity:
    """A numeric literal with optional unit: 200uL, 37C, 12000rpm, 35"""
    value: float
    unit: str | None
    span: Span | None = None


@dataclass
class StringLiteral:
    """A double-quoted string: "BufferA" """
    value: str
    span: Span | None = None


@dataclass
class BooleanLiteral:
    """true or false"""
    value: bool
    span: Span | None = None


@dataclass
class Identifier:
    """A variable or name reference: buffer_vol, Supernatant, etc."""
    name: str
    span: Span | None = None


@dataclass
class ListLiteral:
    """[<expr>, <expr>, ...]"""
    elements: list[Expression] = field(default_factory=list)
    span: Span | None = None


@dataclass
class RecordLiteral:
    """{key: <expr>, ...}"""
    entries: dict[str, Expression] = field(default_factory=dict)
    span: Span | None = None


@dataclass
class GroupExpr:
    """group([<ref>, <ref>, ...])"""
    elements: list[Expression] = field(default_factory=list)
    span: Span | None = None


@dataclass
class SelectorRegion:
    """A1 or A1:D6"""
    start: str
    end: str | None = None
    span: Span | None = None


@dataclass
class CallExpr:
    """<Name>(<arg>, <arg>, ...)"""
    name: str
    args: list[Arg] = field(default_factory=list)
    span: Span | None = None


@dataclass
class PlateSelectorExpr:
    """<plate_ref>[A1:A12, C1:C12]"""
    base: Identifier
    regions: list[SelectorRegion] = field(default_factory=list)
    span: Span | None = None


@dataclass
class IndexExpr:
    """<base>[<index>]"""
    base: Expression
    index: Expression
    span: Span | None = None


@dataclass
class MemberExpr:
    """<base>.<name>"""
    base: Expression
    member: str
    span: Span | None = None


@dataclass
class MethodCallExpr:
    """<base>.<method>(<arg>, <arg>, ...)"""
    base: Expression
    method: str
    args: list[Expression] = field(default_factory=list)
    span: Span | None = None


@dataclass
class SourcePartitionExpr:
    """<source>.partition(<program>)[<index>]"""
    source: Expression
    program: Expression
    index: Expression
    span: Span | None = None


@dataclass
class PairExpr:
    """<left> : <right>"""
    left: Expression
    right: Expression
    span: Span | None = None


# ============================================================
# Type aliases
# ============================================================

Statement = (
    IncludeStatement
    | ProtocolRefStatement
    | LetStatement
    | ReturnStatement
    | AssignStatement
    | ExprStatement
    | StepCall
    | WithEnvStmt
    | WithConstraintStmt
    | MutationStmt
    | BreakStmt
    | ContinueStmt
    | RepeatStatement
    | IfStatement
)

Expression = (
    BinaryOp
    | UnaryOp
    | Quantity
    | StringLiteral
    | BooleanLiteral
    | Identifier
    | ListLiteral
    | RecordLiteral
    | GroupExpr
    | PlateSelectorExpr
    | CallExpr
    | IndexExpr
    | MemberExpr
    | MethodCallExpr
    | SourcePartitionExpr
    | PairExpr
)
