"""Read media through the same checked boundary used by ENV."""
from culsma.common.value_contracts import UNRESOLVED_VALUE
from culsma.pipeline.medium_boundary import decode_descriptor, encode_descriptor
from culsma.runtime.value_adapters.contracts import AdaptedValue


class MediumValueAdapter:
    def read(self, type_id, value, state, resolver):
        from culsma.runtime.values import resolve_runtime_arg_value, resolve_medium_source
        try:
            medium = decode_descriptor(resolve_runtime_arg_value(value, state),
                resolve_source=lambda source: resolve_medium_source(source, state))
            return AdaptedValue(type_id, encode_descriptor(medium))
        except (TypeError, ValueError, KeyError):
            return UNRESOLVED_VALUE

    def describe(self, value):
        return dict(value)
