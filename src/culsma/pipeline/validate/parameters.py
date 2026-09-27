"""Registered expression parameter contracts; domain rules do not emit diagnostics."""
from culsma.common.diagnostics import Diagnostic
from culsma.enum_services import CALL_PARAMETER_CONTRACTS
from culsma.pipeline.external_inputs import ExternalInputResolver, ExternalInputScope, ExternalInputStatus, ExternalInputIssue
from types import MappingProxyType

# Stage ownership: program/readout/agitation handlers retain their existing diagnostics.
EXPRESSION_PARAMETER_CONTRACTS = MappingProxyType({
    **{name: CALL_PARAMETER_CONTRACTS[name] for name in ('stream', 'content', 'DefineContent', 'data_ref', 'data_group_ref')},
})


class ExpressionParameterValidator:
    @staticmethod
    def validate(call, *, bindings, defined_names, node_id):
        contract = EXPRESSION_PARAMETER_CONTRACTS.get(call.name)
        if contract is None:
            return []
        diagnostics, values = [], {}
        scope = ExternalInputScope(bindings, defined_names)
        for arg in call.args:
            parameter = contract.fields.get(arg.name)
            if parameter is None:
                continue
            for path, field, result in ExternalInputResolver.resolve_fields(arg.value, parameter, scope, arg.name):
                if result.status is ExternalInputStatus.RESOLVED:
                    values[path] = result.value
                elif result.issue in {ExternalInputIssue.UNKNOWN_MEMBER, ExternalInputIssue.INVALID_VALUE}:
                    diagnostics.append(Diagnostic(code='SEM_INVALID_EXTERNAL_PARAMETER',
                        message=f'{call.name}.{path}: {result.detail}',
                        span=arg.span or call.span, node_id=node_id))
        try:
            contract.validate_resolved(values, frozenset(arg.name for arg in call.args))
        except (TypeError, ValueError) as error:
            diagnostics.append(Diagnostic(code='SEM_INVALID_EXTERNAL_PARAMETER',
                message=str(error), span=call.span, node_id=node_id))
        return diagnostics
