"""Scope-aware external enum resolution shared by AST and IR consumers.

This module resolves identity, not diagnostics or execution. Unknown runtime
bindings remain deferred. Conversion of legacy spellings is owned by compat.
"""
from collections import ChainMap
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from typing import Any, Mapping, AbstractSet

from culsma.domains.chromatography import ChromatographyParameter
from culsma.domains.contracts import EnumParameter
from culsma.domains.registry import EXTERNAL_ENUM_TYPES
from culsma.common.content_contracts import CONTENT_ENUM_TYPES
from culsma.domains.separation import (
    SepProgramOutput, CentrifugeProgramOutput, MagneticProgramOutput,
    DisruptProgramOutput, FieldProgramOutput, FiltrationProgramOutput,
    CentrifugalFiltrationProgramOutput, PhasePartitionProgramOutput, PrecipitationProgramOutput,
)
from culsma.parser.ast_nodes import Identifier, MemberExpr, RecordLiteral, StringLiteral
from culsma.pipeline.ir_nodes import IRIdentifier, IRMember, IRRecord, IRString
from culsma.pipeline.compat.external_enums import resolve_legacy_enum

# Other known enum families must be recognized so that cross-family mistakes
# cannot degrade to arbitrary text or deferred values.
KNOWN_ENUM_TYPES = ChainMap({
    **CONTENT_ENUM_TYPES,
    **{cls.__name__: cls for cls in (
        SepProgramOutput, CentrifugeProgramOutput, MagneticProgramOutput,
        DisruptProgramOutput, FieldProgramOutput, FiltrationProgramOutput,
        CentrifugalFiltrationProgramOutput, PhasePartitionProgramOutput, PrecipitationProgramOutput,
    )},
}, EXTERNAL_ENUM_TYPES)


class ExternalInputStatus(StrEnum):
    RESOLVED = 'resolved'
    DEFERRED = 'deferred'
    INVALID = 'invalid'


class ExternalInputIssue(StrEnum):
    WRONG_TYPE = 'wrong_type'
    UNKNOWN_MEMBER = 'unknown_member'
    INVALID_VALUE = 'invalid_value'
    CYCLIC_BINDING = 'cyclic_binding'


@dataclass(frozen=True)
class DeferredExternalEnum:
    enum_type: type[Enum]


@dataclass(frozen=True)
class ExternalInputScope:
    bindings: Mapping[str, Any] = field(default_factory=dict)
    defined_names: AbstractSet[str] = frozenset()

    def has_binding(self, name: str) -> bool:
        return name in self.bindings or name in self.defined_names


@dataclass(frozen=True)
class ExternalInputResolution:
    status: ExternalInputStatus
    value: Enum | str | None = None
    issue: ExternalInputIssue | None = None
    detail: str = ''


class ExternalInputResolver:
    @staticmethod
    def validate_value(value: Any, contract: EnumParameter | None) -> ExternalInputResolution:
        try:
            if contract is not None:
                value = resolve_legacy_enum(value, contract)
            elif not isinstance(value, Enum):
                return ExternalInputResolution(ExternalInputStatus.DEFERRED)
            return ExternalInputResolution(ExternalInputStatus.RESOLVED, value=value)
        except TypeError as error:
            return ExternalInputResolution(ExternalInputStatus.INVALID, issue=ExternalInputIssue.WRONG_TYPE, detail=str(error))
        except ValueError as error:
            return ExternalInputResolution(ExternalInputStatus.INVALID, issue=ExternalInputIssue.INVALID_VALUE, detail=str(error))

    @staticmethod
    def resolve(
        expression: Any,
        contract: EnumParameter | None,
        scope: ExternalInputScope,
        seen: frozenset[str] = frozenset(),
    ) -> ExternalInputResolution:
        if isinstance(expression, DeferredExternalEnum):
            if contract is not None and not issubclass(expression.enum_type, contract.enum_type):
                return ExternalInputResolution(ExternalInputStatus.INVALID, issue=ExternalInputIssue.WRONG_TYPE, detail=expression.enum_type.__name__)
            return ExternalInputResolution(ExternalInputStatus.DEFERRED)
        if isinstance(expression, Enum):
            return ExternalInputResolver.validate_value(expression, contract)
        if isinstance(expression, (StringLiteral, IRString)):
            return ExternalInputResolver.validate_value(expression.value, contract)
        if isinstance(expression, str):
            return ExternalInputResolver.validate_value(expression, contract)
        if isinstance(expression, (Identifier, IRIdentifier)):
            name = expression.name
            if name in seen:
                return ExternalInputResolution(ExternalInputStatus.INVALID, issue=ExternalInputIssue.CYCLIC_BINDING, detail=name)
            if name in scope.bindings:
                return ExternalInputResolver.resolve(scope.bindings[name], contract, scope, seen | {name})
            if name in scope.defined_names:
                return ExternalInputResolution(ExternalInputStatus.DEFERRED)
            return ExternalInputResolver.validate_value(name, contract)
        if isinstance(expression, (MemberExpr, IRMember)):
            base = expression.base
            if isinstance(base, (Identifier, IRIdentifier)) and not scope.has_binding(base.name):
                family = KNOWN_ENUM_TYPES.get(base.name)
                if family is not None:
                    member = family.__members__.get(expression.member)
                    if member is None:
                        return ExternalInputResolution(ExternalInputStatus.INVALID, issue=ExternalInputIssue.UNKNOWN_MEMBER, detail=f'{base.name}.{expression.member}')
                    return ExternalInputResolver.validate_value(member, contract)
                if isinstance(contract, ChromatographyParameter):
                    return ExternalInputResolution(ExternalInputStatus.INVALID,
                        issue=ExternalInputIssue.UNKNOWN_MEMBER, detail=f'Unknown chromatography type: {base.name}')
            record = ExternalInputResolver.resolve_record(base, scope, seen)
            if isinstance(record, (RecordLiteral, IRRecord)) and expression.member in record.entries:
                return ExternalInputResolver.resolve(record.entries[expression.member], contract, scope, seen)
            # A shadowing, known non-record is a type error, never a namespace.
            if record is not None:
                return ExternalInputResolution(ExternalInputStatus.INVALID, issue=ExternalInputIssue.WRONG_TYPE, detail='Member base is not a record with this field')
            return ExternalInputResolution(ExternalInputStatus.DEFERRED)
        if expression is None:
            return ExternalInputResolution(ExternalInputStatus.DEFERRED)
        return ExternalInputResolution(ExternalInputStatus.INVALID, issue=ExternalInputIssue.WRONG_TYPE, detail=type(expression).__name__)

    @staticmethod
    def resolve_record(expression: Any, scope: ExternalInputScope, seen: frozenset[str]) -> Any:
        while isinstance(expression, (Identifier, IRIdentifier)):
            if expression.name in seen or expression.name not in scope.bindings:
                return None
            seen = seen | {expression.name}
            expression = scope.bindings[expression.name]
        return expression


def external_parameter_resolution(operation, parameter, expression, *, bindings=None, defined_names=frozenset()):
    from culsma.domains.registry import EXTERNAL_PARAMETERS
    contract = EXTERNAL_PARAMETERS[(operation, parameter)]
    return ExternalInputResolver.resolve(expression, contract, ExternalInputScope(bindings or {}, defined_names))


def external_parameter_type_diagnostics(value, *, scope, node_id=None):
    """Check this statement's expressions; nested statement blocks own their scopes."""
    from dataclasses import fields, is_dataclass
    from culsma.common.diagnostics import Diagnostic
    from culsma.domains.registry import EXTERNAL_PARAMETERS
    from culsma.pipeline.ir_nodes import IRCall, IRStep
    diagnostics = []
    if isinstance(value, (IRCall, IRStep)):
        for arg in value.args:
            contract = EXTERNAL_PARAMETERS.get((value.name, arg.name))
            if contract is not None:
                result = ExternalInputResolver.resolve(arg.value, contract, scope)
                if result.issue in {ExternalInputIssue.WRONG_TYPE, ExternalInputIssue.CYCLIC_BINDING}:
                    diagnostics.append(Diagnostic(
                        code='TYPE_EXTERNAL_ENUM_MISMATCH',
                        message=f"{value.name}.{arg.name} expects {contract.enum_type.__name__}: {result.detail}",
                        span=arg.span or value.span, node_id=node_id,
                    ))
    if isinstance(value, (list, tuple)):
        for item in value:
            diagnostics.extend(external_parameter_type_diagnostics(item, scope=scope, node_id=node_id))
    elif isinstance(value, dict):
        for item in value.values():
            diagnostics.extend(external_parameter_type_diagnostics(item, scope=scope, node_id=node_id))
    elif is_dataclass(value):
        for entry in fields(value):
            if entry.name not in {'span', 'statements', 'then_statements', 'else_statements'}:
                diagnostics.extend(external_parameter_type_diagnostics(getattr(value, entry.name), scope=scope, node_id=node_id))
    return diagnostics


def deferred_external_bindings(names, scope: ExternalInputScope) -> dict[str, DeferredExternalEnum]:
    updates = {}
    for name in names:
        previous = scope.bindings.get(name)
        if isinstance(previous, DeferredExternalEnum):
            updates[name] = previous
            continue
        result = ExternalInputResolver.resolve(IRIdentifier(name), None, scope)
        if result.status is ExternalInputStatus.RESOLVED and type(result.value) in EXTERNAL_ENUM_TYPES.values():
            updates[name] = DeferredExternalEnum(type(result.value))
    return updates
