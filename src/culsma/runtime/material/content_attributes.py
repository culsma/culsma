"""Persist typed metadata without interpreting extension spellings as standard roles."""
from culsma.domains.content import CONTENT_ATTRIBUTE_CONTRACTS


class ContentAttributePersistence:
    @staticmethod
    def extension_identity(value):
        for contract in CONTENT_ATTRIBUTE_CONTRACTS:
            if isinstance(value, contract.enum_type) and type(value) is not contract.standard:
                return contract.current.encode(contract.validate(value))
        return None
