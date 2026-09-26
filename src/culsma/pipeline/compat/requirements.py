"""Static requirement source spellings; unknown names keep existing diagnostics."""
from culsma.domains.constraints import CONSTRAINT_REQUIREMENTS, ConstraintRequirement


class ConstraintSourceResolver:
    @staticmethod
    def resolve(name):
        if '.' not in name:
            for member in ConstraintRequirement:
                if member.value == name:
                    return member
            return name
        namespace, member = name.split('.', 1)
        family = CONSTRAINT_REQUIREMENTS.current.types.get(namespace)
        return family.__members__.get(member, name) if family is not None else name
