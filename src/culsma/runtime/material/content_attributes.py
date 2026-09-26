"""Persist typed metadata without interpreting extension spellings as standard roles."""
from culsma.domains.content_attributes import CONTENT_ATTRIBUTE_DOMAINS


class ContentAttributePersistence:
    @staticmethod
    def extension_identity(value):
        for domain in CONTENT_ATTRIBUTE_DOMAINS:
            if isinstance(value, domain.enum_type) and type(value) is not domain.standard:
                return domain.current.encode(domain.validate(value))
        return None
