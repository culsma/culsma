"""Legacy external-parameter inputs; domain contracts themselves require enums."""
from enum import Enum
from culsma.domains.contracts import E, EnumParameter


def resolve_legacy_enum(value: str | E, contract: EnumParameter[E]) -> E:
    """Convert resolved old text, never coerce a foreign enum to its string value.

    Binding and source-token eligibility are checked by the caller. This adapter
    does not interpret identifiers or namespace expressions.
    """
    if isinstance(value, Enum):
        return contract.validate(value)
    if type(value) is not str:
        raise TypeError(f"Expected {contract.enum_type.__name__} or legacy text")
    return contract.decode(value)
