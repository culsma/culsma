"""Check simultaneous medium requirements against resolved target identities."""
from dataclasses import replace

from culsma.domains.environment import EnvironmentValueError
from culsma.domains.medium import CompositionCoverage, CompositionSpec, LiquidMedium
from culsma.pipeline.medium_boundary import resolve_medium, encode_descriptor, validate_medium_modifiers


def resolve_medium_targets(value, state):
    from culsma.runtime.values import resolve_medium_source, resolve_runtime_arg_value
    value = resolve_runtime_arg_value(value, state)
    if isinstance(value, list):
        return [target for child in value for target in resolve_medium_targets(child, state)]
    if isinstance(value, dict) and value.get('kind') in {'IRGroup', 'IRList'}:
        return resolve_medium_targets(value.get('elements', []), state)
    members = []
    while isinstance(value, dict) and value.get('kind') == 'IRMember':
        members.insert(0, value.get('member'))
        value = value.get('base')
    identity = resolve_medium_source(value, state)
    if identity is None:
        raise EnvironmentValueError('medium target must resolve to a container', reason='medium')
    # Bare hold targets and their contents accessor have the same meaning.
    return [(identity, tuple(members) if members != ['contents'] else ())]


def validate_medium_layers(gate, state):
    if not gate:
        return
    active = {}
    modifier_layers = []
    layers = gate.get('env_layers', [{'env': gate.get('env', {}), 'env_targets': gate.get('env_targets', [])}])
    for layer in layers:
        environment = layer.get('env', {})
        if any(key in environment for key in ('co2', 'o2', 'humidity')):
            modifier_layers.append(layer)
        payload = layer.get('env', {}).get('medium')
        if payload is None:
            continue
        declared = resolve_medium(environment)
        resolved_targets = resolve_medium_targets(layer.get('env_targets', []), state)
        if not resolved_targets:
            raise EnvironmentValueError('medium environment requires a target', reason='medium')
        for target in resolved_targets:
            current = declared
            previous = active.get(target)
            if previous is not None:
                if previous.phase is not current.phase or (
                        previous.source is not None and current.source is not None
                        and previous.source != current.source):
                    raise EnvironmentValueError('one target cannot occupy different nested media', reason='medium')
                if isinstance(current, LiquidMedium) and isinstance(previous, LiquidMedium) and (
                    current.contents is not None or previous.contents is not None
                ):
                    if current.contents != previous.contents or current.basis is not previous.basis or (
                        current.volume is not None and previous.volume is not None and current.volume != previous.volume
                    ):
                        raise EnvironmentValueError('conflicting nested liquid medium contents or volume', reason='medium')
                    active[target] = replace(current, volume=current.volume or previous.volume)
                    continue
                components = {c.material: c for c in previous.composition.components}
                for component in current.composition.components:
                    if component.material in components and components[component.material] != component:
                        raise EnvironmentValueError('conflicting nested medium composition', reason='medium')
                    components[component.material] = component
                for medium in (previous, current):
                    if medium.composition.coverage is CompositionCoverage.COMPLETE:
                        identities = {c.material for c in medium.composition.components}
                        if any(c.quantity[0] != 0 and c.material not in identities for c in components.values()):
                            raise EnvironmentValueError('nested medium conflicts with complete composition', reason='medium')
                try:
                    coverage = (CompositionCoverage.COMPLETE if any(
                        m.composition.coverage is CompositionCoverage.COMPLETE for m in (previous, current))
                        else CompositionCoverage.PARTIAL)
                    merged = CompositionSpec(tuple(components.values()), coverage)
                    current = type(current)(merged, current.source or previous.source)
                except ValueError as error:
                    raise EnvironmentValueError(str(error), reason='medium') from error
            active[target] = current
    for medium in active.values():
        if isinstance(medium, LiquidMedium) and medium.contents is not None and medium.volume is None:
            raise EnvironmentValueError('liquid medium requires a final volume for execution', reason='medium')
    if active:
        modifiers = {}
        for layer in modifier_layers:
            for target in resolve_medium_targets(layer.get('env_targets', []), state):
                if target not in active:
                    continue
                merged = modifiers.setdefault(target, {})
                for key in ('co2', 'o2', 'humidity'):
                    if key in layer['env']:
                        value = layer['env'][key]
                        if key in merged and merged[key]['value'] != value['value']:
                            raise EnvironmentValueError('conflicting nested medium gas modifiers', reason='medium')
                        merged[key] = value
        for target, conditions in modifiers.items():
            validate_medium_modifiers(encode_descriptor(active[target]), conditions)
