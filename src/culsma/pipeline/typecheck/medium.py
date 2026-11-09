"""Resolve static medium data through existing expression/quantity services."""
from dataclasses import fields, is_dataclass

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRIdentifier, IRCall, IRMember, IRBinary, IRUnary
from culsma.pipeline.medium_boundary import decode_descriptor, MEDIUM_CALLS
from culsma.domains.medium import Medium


class DeferredMedium(Exception):
    pass


def check_medium(expr, bindings, services, *, node_id, require_medium=False):
    def serialize(value):
        value = services.resolve_bound_expr(value, bindings)
        if isinstance(value, IRIdentifier):
            raise DeferredMedium()
        if isinstance(value, IRMember) and isinstance(value.base, IRIdentifier):
            from culsma.enum_services import PARAMETER_ENUM_TYPES
            if value.base.name in PARAMETER_ENUM_TYPES and value.base.name not in bindings:
                return {'kind': 'ExternalEnum', 'enum': value.base.name, 'member': value.member}
        if isinstance(value, (IRBinary, IRUnary)):
            quantity = services.coerce_quantity_like(value, bindings)
            if quantity is None:
                raise DeferredMedium()
            value = quantity
        if is_dataclass(value):
            return {'kind': type(value).__name__, **{
                f.name: serialize(getattr(value, f.name)) for f in fields(value) if f.name != 'span'}}
        if isinstance(value, list):
            return [serialize(item) for item in value]
        if isinstance(value, dict):
            return {k: serialize(v) for k, v in value.items()}
        return value

    def source(value):
        # Typecheck the reference shape; allocation identity is runtime-owned.
        if isinstance(value, dict) and value.get('kind') == 'IRCall' and value.get('name') == 'AllocContainer':
            return '<deferred-container-identity>'
        if isinstance(value, dict) and value.get('kind') == 'IRPlateWellRef':
            return '<deferred-well-identity>'
        raise ValueError('medium source requires a container reference')

    try:
        descriptor = decode_descriptor(serialize(expr), resolve_source=source)
        if require_medium and not isinstance(descriptor, Medium):
            raise ValueError('env.medium requires GasMedium or LiquidMedium')
    except DeferredMedium:
        return []
    except (ValueError, TypeError, KeyError) as error:
        return [Diagnostic(code='TYPE_ENV_MEDIUM_INVALID', message=str(error),
                           span=getattr(expr, 'span', None), node_id=node_id)]
    return []
