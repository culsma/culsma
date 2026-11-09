"""One checked boundary between source descriptors, typed media and wire values."""
from culsma.domains.medium import (
    ComponentRequirement, CompositionBasis, CompositionCoverage, CompositionSpec,
    GasMedium, LiquidMedium, Medium, MediumPhase, DEFAULT_MEDIUM,
)
from culsma.domains.environment import EnvironmentValueError

MEDIUM_CALLS = frozenset({'gas_medium', 'liquid_medium', 'composition', 'medium_component'})
CALL_FIELDS = {
    'gas_medium': ({'composition', 'source'}, set()),
    'liquid_medium': ({'composition', 'source'}, set()),
    'composition': ({'components', 'coverage'}, {'components'}),
    'medium_component': ({'material', 'quantity', 'basis'}, {'material', 'quantity', 'basis'}),
}


def _fields(value, allowed, required):
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValueError(f"medium fields must be {sorted(allowed)}; required: {sorted(required)}")
    return value


def _enum(value, family, *, allow_wire_text=False):
    if isinstance(value, dict) and value.get('kind') == 'ExternalEnum':
        if value.get('enum') != family.__name__:
            raise ValueError(f"expected {family.__name__}")
        try:
            return family[value['member']]
        except (KeyError, TypeError) as error:
            raise ValueError(f"invalid {family.__name__} member") from error
    if type(value) is family:
        return value
    if allow_wire_text and type(value) is str:
        return family(value)
    raise ValueError(f"expected {family.__name__}")


def _literal(value):
    if isinstance(value, dict):
        if value.get('kind') == 'IRString':
            return value.get('value')
        if value.get('kind') == 'IRQuantity':
            return (value.get('value'), value.get('unit'))
    return value


def decode_descriptor(value, *, resolve_source=None):
    """Decode constructors or the canonical JSON form, never arbitrary records."""
    if not isinstance(value, dict):
        raise ValueError("medium requires a typed gas_medium or liquid_medium descriptor")
    source_call = value.get('kind') == 'IRCall'
    if source_call:
        name = value.get('name')
        if name not in MEDIUM_CALLS:
            raise ValueError("expected a medium constructor")
        args = value.get('args')
        if not isinstance(args, list) or any(not isinstance(a, dict) or 'name' not in a or 'value' not in a for a in args):
            raise ValueError("invalid medium constructor arguments")
        names = [a['name'] for a in args]
        if any(not isinstance(n, str) for n in names) or len(names) != len(set(names)):
            raise ValueError("duplicate or invalid medium constructor argument")
        fields = _fields({a['name']: a['value'] for a in args}, *CALL_FIELDS[name])
    else:
        name = value.get('kind')
        if name not in MEDIUM_CALLS:
            raise ValueError("unknown medium descriptor kind")
        fields = _fields({k: v for k, v in value.items() if k != 'kind'}, *CALL_FIELDS[name])
    if name == 'medium_component':
        return ComponentRequirement(_literal(fields['material']), _literal(fields['quantity']),
                                    _enum(_literal(fields['basis']), CompositionBasis, allow_wire_text=not source_call))
    if name == 'composition':
        items = fields['components']
        if isinstance(items, dict) and items.get('kind') == 'IRList':
            items = items.get('elements')
        if not isinstance(items, list):
            raise ValueError("composition components must be a list")
        return CompositionSpec(tuple(decode_descriptor(item) for item in items),
                               _enum(_literal(fields.get('coverage', CompositionCoverage.PARTIAL)),
                                     CompositionCoverage, allow_wire_text=not source_call))
    composition = decode_descriptor(fields['composition']) if 'composition' in fields else CompositionSpec()
    source = None
    if 'source' in fields:
        raw = fields['source']
        if resolve_source is not None:
            source = resolve_source(raw)
        elif isinstance(raw, dict) and raw.get('kind') == 'container_ref':
            source = raw.get('id')
        if not isinstance(source, str) or not source:
            raise ValueError("medium source must resolve to an existing container reference")
    cls = GasMedium if name == 'gas_medium' else LiquidMedium
    return cls(composition=composition, source=source)


def encode_descriptor(value):
    if isinstance(value, ComponentRequirement):
        return {'kind': 'medium_component', 'material': value.material,
                'quantity': {'kind': 'IRQuantity', 'value': value.quantity[0], 'unit': value.quantity[1]},
                'basis': value.basis.value}
    if isinstance(value, CompositionSpec):
        return {'kind': 'composition', 'coverage': value.coverage.value,
                'components': [encode_descriptor(c) for c in value.components]}
    if isinstance(value, Medium):
        result = {'kind': f'{value.phase.value}_medium', 'composition': encode_descriptor(value.composition)}
        if value.source is not None:
            result['source'] = {'kind': 'container_ref', 'id': value.source}
        return result
    raise ValueError("unsupported medium descriptor value")


def normalize_medium(value, *, resolve_source=None):
    try:
        medium = decode_descriptor(value, resolve_source=resolve_source)
        if not isinstance(medium, Medium):
            raise ValueError("env.medium requires GasMedium or LiquidMedium")
        return encode_descriptor(medium)
    except (ValueError, TypeError, KeyError) as error:
        raise EnvironmentValueError(str(error), reason='medium') from error


def resolve_medium(environment, *, inherited=None, resolve_source=None) -> Medium:
    """Read the effective medium without inserting defaults into stored gates.

    The caller supplies the inherited medium for the same target. Gas modifiers
    remain separate authored conditions; ordinary atmosphere has no invented
    numeric composition, humidity, temperature or pressure.
    """
    if inherited is not None and not isinstance(inherited, Medium):
        raise EnvironmentValueError('inherited medium must be Medium', reason='medium')
    if not isinstance(environment, dict):
        raise EnvironmentValueError('environment must be a mapping', reason='medium')
    if 'medium' not in environment:
        return inherited if inherited is not None else DEFAULT_MEDIUM
    return decode_descriptor(normalize_medium(environment['medium'], resolve_source=resolve_source))


def validate_medium_modifiers(medium, environment):
    """Legacy gas modifiers remain additional requirements, never overrides."""
    if not any(key in environment for key in ('co2', 'o2', 'humidity')):
        return
    decoded = decode_descriptor(medium)
    if decoded.phase is not MediumPhase.GAS:
        raise EnvironmentValueError('co2/o2/rh cannot describe a liquid medium', reason='medium')
    spec = decoded.composition
    combined = {c.material: c.quantity[0] for c in spec.components}
    if any(key in environment for key in ('co2', 'o2')) and any(
            c.basis is not CompositionBasis.VOLUME_FRACTION for c in spec.components):
        raise EnvironmentValueError('co2/o2 require volume-fraction medium composition for comparison', reason='medium')
    for key, code in (('co2', 'CO2'), ('o2', 'O2')):
        if key not in environment:
            continue
        component = next((c for c in spec.components if c.material == code), None)
        if component is None:
            if spec.coverage is CompositionCoverage.COMPLETE and environment[key]['value'] != 0:
                raise EnvironmentValueError(f'{key} conflicts with complete medium composition', reason='medium')
            combined[code] = environment[key]['value']
            continue
        if component.basis is not CompositionBasis.VOLUME_FRACTION:
            raise EnvironmentValueError(f'{key} requires a volume-fraction medium component for comparison', reason='medium')
        if component.quantity[0] != environment[key]['value']:
            raise EnvironmentValueError(f'{key} conflicts with medium composition', reason='medium')
    if sum(combined.values()) > 100 + 1e-9:
        raise EnvironmentValueError('medium composition and co2/o2 together exceed 100%', reason='medium')
