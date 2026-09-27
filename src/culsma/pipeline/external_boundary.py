"""Enum wire identity and bound parameter normalization, independent of execution plans."""
from enum import Enum
from types import MappingProxyType
from typing import Any

from culsma.domains.fractionation import (
    ACTIVE_CHROMATOGRAPHY_REGISTRY, ChromatographyAxisBase, ChromatographyOrderBase, ChromatographyParameter,
)
from culsma.common.enum_parameters import EnumParameter, RecordParameterContract
from culsma.enum_services import PARAMETER_ENUM_TYPES, PARAMETER_CONTRACTS, CALL_PARAMETER_CONTRACTS
from culsma.pipeline.external_inputs import (
    KNOWN_ENUM_TYPES, ExternalInputResolution, ExternalInputStatus, ExternalInputIssue,
)
from culsma.pipeline.compat.external_enums import resolve_legacy_enum


class ExternalEnumCodec:
    def __init__(self, enum_types=PARAMETER_ENUM_TYPES):
        # Only closed types use class-name payloads. Open families are always
        # encoded and restored through their current scoped identity registry.
        self.enum_types = MappingProxyType({
            name: family for name, family in enum_types.items()
            if PARAMETER_ENUM_TYPES.base_for_type(family) is None
        })

    def encode(self, value: Enum) -> dict[str, str]:
        registry = PARAMETER_ENUM_TYPES.registry_for_type(type(value))
        if registry is not None:
            return registry.encode(value)
        if type(value) not in self.enum_types.values():
            raise TypeError(f'Not an external parameter enum: {type(value).__name__}')
        return {'kind': 'ExternalEnum', 'enum': type(value).__name__, 'member': value.name}

    def decode(self, value: dict) -> Enum:
        if value.get('kind') == 'DomainEnum':
            return PARAMETER_ENUM_TYPES.decode_registered(value)
        if value.get('kind') == 'ChromatographyEnum':
            return ACTIVE_CHROMATOGRAPHY_REGISTRY.get().decode(value)
        if not isinstance(value.get('enum'), str) or not isinstance(value.get('member'), str):
            raise ValueError('Invalid external enum identity')
        family = self.enum_types.get(value.get('enum'))
        if value.get('kind') != 'ExternalEnum' or family is None:
            raise ValueError('Invalid external enum payload')
        try:
            return family[value['member']]
        except (KeyError, TypeError) as error:
            raise ValueError('Unknown external enum member') from error


class ExternalParameterNormalizer:
    def __init__(self, contracts=PARAMETER_CONTRACTS, codec=None, *, call_contracts=None):
        if call_contracts is None:
            call_contracts = CALL_PARAMETER_CONTRACTS if contracts is PARAMETER_CONTRACTS else {}
        else:
            fields = {(operation, name): field for operation, contract in call_contracts.items()
                      for name, field in contract.fields.items()}
            if contracts is not PARAMETER_CONTRACTS and dict(contracts) != fields:
                raise ValueError('Parameter fields must match the supplied call contracts')
            contracts = fields
        self.contracts = MappingProxyType(dict(contracts))
        self.call_contracts = MappingProxyType(dict(call_contracts))
        self.codec = codec if codec is not None else ExternalEnumCodec()

    def resolve_member(self, value, contract) -> ExternalInputResolution:
        try:
            member = self.resolve_value(value, contract, allow_deferred=True)
            status = ExternalInputStatus.DEFERRED if member is None else ExternalInputStatus.RESOLVED
            return ExternalInputResolution(status, value=member)
        except TypeError as error:
            return ExternalInputResolution(ExternalInputStatus.INVALID,
                issue=ExternalInputIssue.WRONG_TYPE, detail=str(error))
        except ValueError as error:
            return ExternalInputResolution(ExternalInputStatus.INVALID,
                issue=ExternalInputIssue.INVALID_VALUE, detail=str(error))

    def plan_member(self, value, contract):
        result = self.resolve_member(value, contract)
        if result.status == ExternalInputStatus.INVALID:
            if result.issue == ExternalInputIssue.WRONG_TYPE:
                raise TypeError(result.detail)
            raise ValueError(result.detail)
        return result.value

    def require_member(self, value, contract) -> Enum:
        return self.resolve_value(value, contract, allow_deferred=False)

    def normalize_plan_arguments(self, operation, arguments) -> dict:
        return self.normalize_arguments(operation, arguments, runtime=False)

    def normalize_runtime_arguments(self, operation, arguments) -> dict:
        return self.normalize_arguments(operation, arguments, runtime=True)

    def resolve_value(self, value: Any, contract: EnumParameter, *, allow_deferred: bool) -> Enum | None:
        if isinstance(value, dict):
            kind = value.get('kind')
            if kind in {'ExternalEnum', 'ChromatographyEnum', 'DomainEnum'}:
                return contract.validate(self.codec.decode(value))
            if kind == 'ContentEnum':
                raise TypeError(f"Expected {contract.enum_type.__name__}, got {value.get('enum')}")
            if kind == 'IRString':
                return resolve_legacy_enum(value.get('value'), contract)
            if kind == 'IRIdentifier':
                token = value.get('name')
                if not value.get('bound') and (token in contract.wire_values or getattr(contract, 'allow_legacy_text', False)):
                    return resolve_legacy_enum(token, contract)
                if allow_deferred:
                    return None
                raise ValueError(f'Unresolved enum parameter: {token}')
            if kind == 'IRMember':
                base = value.get('base', {})
                family = KNOWN_ENUM_TYPES.get(base.get('name')) if isinstance(base, dict) and base.get('kind') == 'IRIdentifier' and not base.get('bound') else None
                if family is not None:
                    try:
                        return contract.validate(family[value['member']])
                    except KeyError as error:
                        raise ValueError('Unknown enum member') from error
            if allow_deferred and kind in {'IRMember', 'IRIndex', 'IRCall', 'IRBinary'}:
                return None
            if kind in {'IRMember', 'IRIndex', 'IRCall', 'IRBinary'}:
                raise ValueError('Unresolved typed metadata expression')
            if getattr(contract, 'preserve_legacy_values', False):
                return value
            raise TypeError(f'Expected {contract.enum_type.__name__}')
        return resolve_legacy_enum(value, contract)

    def normalize_arguments(self, operation: str, arguments: dict, *, runtime: bool = False) -> dict:
        result = {}
        resolved_values = {}
        for name, value in arguments.items():
            contract = self.contracts.get((operation, name))
            if isinstance(contract, RecordParameterContract):
                result[name] = self.normalize_record(value, contract, runtime=runtime)
            elif contract is not None:
                member = self.require_member(value, contract) if runtime else self.plan_member(value, contract)
                if member is not None:
                    resolved_values[name] = member
                result[name] = value if member is None else member if runtime or not isinstance(member, Enum) else self.codec.encode(member)
            else:
                result[name] = self.normalize_tree(value, runtime=runtime)
        call_contract = self.call_contracts.get(operation)
        if call_contract is not None:
            call_contract.validate_resolved(resolved_values, frozenset(arguments))
        return result

    def normalize_record(self, value, contract, *, runtime):
        if not isinstance(value, dict) or value.get('kind') in {'IRIdentifier', 'IRMember', 'IRCall'}:
            return value
        result = dict(value)
        for name, field in contract.fields.items():
            if name in result:
                member = self.require_member(result[name], field) if runtime else self.plan_member(result[name], field)
                if member is not None:
                    result[name] = self.codec.encode(member) if not runtime and isinstance(member, Enum) else member
        return result

    def normalize_tree(self, value: Any, *, runtime: bool = False) -> Any:
        if isinstance(value, list):
            return [self.normalize_tree(item, runtime=runtime) for item in value]
        if isinstance(value, dict):
            if value.get('kind') == 'IRCall' and isinstance(value.get('args'), list):
                args = value['args']
                normalized = self.normalize_arguments(value.get('name'), {arg['name']: arg['value'] for arg in args}, runtime=runtime)
                return {**value, 'args': [{**arg, 'value': normalized[arg['name']]} for arg in args]}
            return {key: self.normalize_tree(item, runtime=runtime) for key, item in value.items()}
        return value


DEFAULT_EXTERNAL_ENUM_CODEC = ExternalEnumCodec()
DEFAULT_EXTERNAL_PARAMETER_NORMALIZER = ExternalParameterNormalizer(codec=DEFAULT_EXTERNAL_ENUM_CODEC)


class RuntimeParameterError(ValueError):
    """A local runtime constructor failed its registered parameter contract."""
