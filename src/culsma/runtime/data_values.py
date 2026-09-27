"""Persist runtime-local data references without leaking Python enum objects."""
from culsma.domains.data import DATA_KINDS, DataKind, DataKindBase


class DataReferenceBuilder:
    @staticmethod
    def build(constructor, arguments, result):
        value = arguments.get('kind')
        reference = {
            'kind': constructor,
            'data_kind': value.value if isinstance(value, DataKindBase) else value,
            'schema_ref': arguments.get('schema_ref'),
            'result': result,
        }
        if isinstance(value, DataKindBase):
            DATA_KINDS.validate(value)
            if type(value) is not DataKind:
                reference['data_kind_type'] = DATA_KINDS.current.encode(value)
        if constructor == 'data_ref':
            reference.update(subject_ref=arguments.get('subject_ref'), context_ref=arguments.get('context_ref'))
        elif constructor == 'data_group_ref':
            reference['items'] = []
        else:
            raise ValueError('Expected a data reference constructor')
        return reference
