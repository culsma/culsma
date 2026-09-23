"""Scope-aware enum identity before binding to pipeline consumers."""
import pytest
from culsma.domains.agitation import AGITATION_MODE, AgitationMode
from culsma.domains.readout import READOUT_QUANTITIES, ReadoutQuantity
from culsma.domains.separation import CENTRIFUGE_KEEP_SOURCE, CentrifugeProgramOutput
from culsma.pipeline.external_inputs import ExternalInputResolver, ExternalInputScope, ExternalInputStatus, ExternalInputIssue
from culsma.parser.ast_nodes import Identifier, MemberExpr, StringLiteral, RecordLiteral
from culsma.pipeline.ir_nodes import IRIdentifier, IRMember, IRString, IRQuantity, IRRecord


@pytest.mark.parametrize('ident,member,string,record', [
    (Identifier, MemberExpr, StringLiteral, RecordLiteral),
    (IRIdentifier, IRMember, IRString, IRRecord),
])
def test_direct_alias_record_and_shadowing(ident, member, string, record):
    value = member(ident('AgitationMode'), 'VORTEX')
    scope = ExternalInputScope({'a': value, 'b': ident('a'), 'r': record({'mode': ident('b')})})
    for expr in (value, ident('b'), member(ident('r'), 'mode'), string('vortex'), ident('vortex')):
        result = ExternalInputResolver.resolve(expr, AGITATION_MODE, scope)
        assert result.value is AgitationMode.VORTEX
    shadowed = ExternalInputScope({'AgitationMode': string('vortex')})
    assert ExternalInputResolver.resolve(value, AGITATION_MODE, shadowed).issue is ExternalInputIssue.WRONG_TYPE
    shadowed = ExternalInputScope({'AgitationMode': record({'VORTEX': string('shake')})})
    assert ExternalInputResolver.resolve(value, AGITATION_MODE, shadowed).value is AgitationMode.SHAKE


def test_binding_precedes_bare_token_compatibility():
    scope = ExternalInputScope({'vortex': IRQuantity(2, None)})
    assert ExternalInputResolver.resolve(IRIdentifier('vortex'), AGITATION_MODE, scope).issue is ExternalInputIssue.WRONG_TYPE
    scope = ExternalInputScope(defined_names={'vortex'})
    assert ExternalInputResolver.resolve(IRIdentifier('vortex'), AGITATION_MODE, scope).status is ExternalInputStatus.DEFERRED
    scope = ExternalInputScope({'a': IRIdentifier('b'), 'b': IRIdentifier('a')})
    assert ExternalInputResolver.resolve(IRIdentifier('a'), AGITATION_MODE, scope).issue is ExternalInputIssue.CYCLIC_BINDING


def test_errors_preserve_type_and_member_distinction():
    scope = ExternalInputScope()
    assert ExternalInputResolver.resolve(IRMember(IRIdentifier('AgitationMode'), 'TYPO'), AGITATION_MODE, scope).issue is ExternalInputIssue.UNKNOWN_MEMBER
    assert ExternalInputResolver.resolve(IRMember(IRIdentifier('ContentType'), 'MEDIUM'), AGITATION_MODE, scope).issue is ExternalInputIssue.WRONG_TYPE
    assert ExternalInputResolver.resolve(IRString('TYPO'), AGITATION_MODE, scope).issue is ExternalInputIssue.INVALID_VALUE
    assert ExternalInputResolver.resolve(ReadoutQuantity.FLUORESCENCE, READOUT_QUANTITIES['ecp'], scope).issue is ExternalInputIssue.INVALID_VALUE
    assert ExternalInputResolver.resolve(IRMember(IRIdentifier('CentrifugeProgramOutput'), 'PELLET'), CENTRIFUGE_KEEP_SOURCE, scope).value is CentrifugeProgramOutput.PELLET
