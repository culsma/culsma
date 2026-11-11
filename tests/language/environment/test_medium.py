"""Typed media through source, serialized plans and executor boundaries."""
from copy import deepcopy
import json

import pytest

from culsma.domains.medium import (
    Medium, MediumPhase, GasMedium, LiquidMedium, CompositionSpec, ComponentRequirement,
    CompositionCoverage as Coverage, CompositionBasis as Basis,
)
from culsma.pipeline.medium_boundary import decode_descriptor, encode_descriptor, normalize_medium
from culsma.pipeline.environment_boundary import DEFAULT_ENVIRONMENT_PARAMETER_NORMALIZER as NORMALIZER
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.driver.stub import StubDriver
from culsma.driver.base import DriverCapabilityResult


class RecordingDriver(StubDriver):
    def __init__(self):
        super().__init__()
        self.steps = []

    def execute(self, step):
        self.steps.append(deepcopy(step))
        return super().execute(step)


def test_typed_medium_roundtrip():
    composition = CompositionSpec((
        ComponentRequirement('ETHANOL', (80, '%'), Basis.VOLUME_FRACTION),
        ComponentRequirement('WATER', (20, '%'), Basis.VOLUME_FRACTION),
    ), Coverage.COMPLETE)
    medium = LiquidMedium(composition, 'bath-a')
    assert isinstance(medium, Medium)
    assert decode_descriptor(json.loads(json.dumps(encode_descriptor(medium)))) == medium
    assert normalize_medium(encode_descriptor(medium)) == encode_descriptor(medium)
    with pytest.raises(TypeError):
        Medium(composition)


@pytest.mark.parametrize('components,coverage', [
    ([('A', 70, Basis.MOLE_FRACTION), ('B', 40, Basis.MOLE_FRACTION)], Coverage.PARTIAL),
    ([('A', 70, Basis.MOLE_FRACTION)], Coverage.COMPLETE),
    ([('A', 50, Basis.MOLE_FRACTION), ('A', 50, Basis.MOLE_FRACTION)], Coverage.COMPLETE),
    ([('A', 50, Basis.MOLE_FRACTION), ('B', 50, Basis.MASS_FRACTION)], Coverage.COMPLETE),
    ([], Coverage.COMPLETE),
])
def test_invalid_composition(components, coverage):
    with pytest.raises(ValueError):
        CompositionSpec(tuple(ComponentRequirement(code, (value, '%'), basis)
                              for code, value, basis in components), coverage)


@pytest.mark.parametrize('quantity', [(-1, '%'), (101, '%'), (float('nan'), '%'),
                                      (float('inf'), '%'), (True, '%'), (5, 'mL')])
def test_invalid_component_quantity(quantity):
    with pytest.raises(ValueError):
        ComponentRequirement('A', quantity, Basis.MOLE_FRACTION)


def test_liquid_concentration_is_not_gas_fraction():
    spec = CompositionSpec((ComponentRequirement('SALT', (1, 'mg_per_uL'), Basis.MASS_CONCENTRATION),))
    assert LiquidMedium(spec).composition == spec
    with pytest.raises(ValueError):
        GasMedium(spec)


def test_successive_baths_preserve_identity_and_materials(build_plan):
    source = '''protocol T {
      let sample=chamber(label="cassette", open=true);
      let a=chamber(label="same label"); let b=chamber(label="same label");
      with env(medium=liquid_medium(source=a), duration=45min) { hold(sample); }
      with env(medium=liquid_medium(source=b), duration=45min) { hold(sample); }
    }'''
    driver = RecordingDriver()
    result = run(build_plan(source), driver)
    assert result.ok, result.diagnostics
    holds = [s for s in driver.steps if s.op == 'env_hold']
    media = [s.gate['env']['medium'] for s in holds]
    assert len(holds) == 2
    assert media[0]['source']['id'] != media[1]['source']['id']
    assert all(s.gate['env']['duration']['value'] == 45 for s in holds)
    assert all(s.gate['env'] == s.gate['env_layers'][-1]['env'] for s in holds)
    assert all(c['volume_uL'] == 0 for c in result.state.artifacts['material_state']['containers'].values())


def test_source_composition_and_enum_parameters(build_plan):
    source = '''protocol T {
      let sample=tube();
      let air=gas_medium(composition=composition(
        coverage=CompositionCoverage.PARTIAL,
        components=[medium_component(material="CO2", quantity=5%, basis=CompositionBasis.VOLUME_FRACTION)]));
      with env(medium=air, thermal=37C, co2=5%, duration=1min) { hold(sample); }
    }'''
    driver = RecordingDriver()
    result = run(build_plan(source), driver)
    assert result.ok, result.diagnostics
    env = next(s.gate['env'] for s in driver.steps if s.op == 'env_hold')
    assert env['medium']['composition']['components'][0]['material'] == 'CO2'
    assert len(env['medium']['composition']['components']) == 1
    assert 'source' not in env['medium']


@pytest.mark.parametrize('medium', [
    '"air"', 'composition(components=[])', 'liquid_medium()',
    'liquid_medium(source="bath")', 'gas_medium(unknown=1)',
    'gas_medium(composition=composition(components=[medium_component(material="CO2", quantity=110%, basis=CompositionBasis.MOLE_FRACTION)]))',
])
def test_invalid_source_medium(compile_source, medium):
    compiled = compile_source(f'protocol T {{ let s=tube(); with env(medium={medium}, duration=1min) {{ hold(s); }} }}')
    result = typecheck(compiled.ir, analysis=compiled.analysis)
    assert not result.ok
    assert any(d.code == 'TYPE_ENV_MEDIUM_INVALID' for d in result.diagnostics)


def test_pure_medium_requires_duration(compile_source):
    compiled = compile_source('protocol T { let s=tube(); let b=chamber(); with env(medium=liquid_medium(source=b)) { hold(s); } }')
    result = validate(compiled.ir, analysis=compiled.analysis)
    assert any(d.code == 'SEM_ENV_DURATION_REQUIRED' for d in result.diagnostics)


@pytest.mark.parametrize('value', [
    {'kind': 'liquid_medium', 'composition': {'kind': 'composition', 'components': [], 'typo': 1}},
    {'kind': 'liquid_medium', 'source': 'bath'},
    {'kind': 'unknown_medium'},
    {'kind': 'IRCall', 'name': 'liquid_medium', 'args': [
        {'name': 'source', 'value': 1}, {'name': 'source', 'value': 2}]},
])
def test_malformed_wire_medium(value):
    with pytest.raises(ValueError):
        normalize_medium(value)


def test_legacy_gas_conflict():
    medium = GasMedium(CompositionSpec((ComponentRequirement('CO2', (5, '%'), Basis.VOLUME_FRACTION),)))
    env = {'medium': encode_descriptor(medium),
           'thermal': {'kind': 'IRQuantity', 'value': 37, 'unit': 'C'},
           'co2': {'kind': 'IRQuantity', 'value': 6, 'unit': '%'}}
    with pytest.raises(ValueError, match='conflict'):
        NORMALIZER.normalize_runtime_environment(env)


def test_unsupported_medium_rejected_before_hold(build_plan):
    class RejectMedium(RecordingDriver):
        def check(self, step):
            if step.gate and 'medium' in step.gate.get('env', {}):
                return DriverCapabilityResult(ok=False, code='DRV_REQ_UNSUPPORTED', unsupported_requirements=('medium',))
            return super().check(step)
    driver = RejectMedium()
    result = run(build_plan('protocol T { let s=tube(); let b=chamber(); with env(medium=liquid_medium(source=b), duration=1min) { hold(s); } }'), driver)
    assert not result.ok
    assert not any(s.op == 'env_hold' for s in driver.steps)


@pytest.mark.parametrize('same_target', [True, False])
def test_nested_bath_conflicts_use_target_identity(build_plan, same_target):
    target = 'alias' if same_target else 'other'
    source = f'''protocol T {{
      let s=tube(); let alias=s; let other=tube(); let a=chamber(); let b=chamber();
      with env(medium=liquid_medium(source=a)) {{
        hold(s);
        with env(medium=liquid_medium(source=b), duration=1min) {{ hold({target}); }}
      }}
    }}'''
    driver = RecordingDriver()
    result = run(build_plan(source), driver)
    assert result.ok is not same_target, result.diagnostics
    if same_target:
        assert any(d.code == 'RT_ENV_ARGUMENT_INVALID' for d in result.diagnostics)
        assert not any(s.op == 'env_hold' for s in driver.steps)


def test_protocol_medium_arguments_and_return(build_plan):
    source = '''protocol Expose(sample, environment, time) {
      with env(medium=environment, duration=time) { hold(sample); }
      return environment;
    }
    let s=tube(); let bath=chamber();
    let medium=liquid_medium(source=bath);
    let result=Expose(sample=s, environment=medium, time=1min);
    print(result);
    return result;
    '''
    driver = RecordingDriver()
    result = run(build_plan(source), driver)
    assert result.ok, result.diagnostics
    returned = result.state.artifacts['protocol_outputs']['entry']['value']
    held_medium = next(s.gate['env']['medium'] for s in driver.steps if s.op == 'env_hold')
    assert returned == held_medium
    assert returned['source']['id'] in result.state.artifacts['material_state']['containers']


def test_medium_json_plan_roundtrip(build_plan):
    from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan
    plan = build_plan('protocol T { let s=tube(); let b=chamber(); with env(medium=liquid_medium(source=b), duration=1min) { hold(s); } }')
    payload = json.loads(json.dumps(plan.to_dict()))
    steps = [PlanStep(step_id=s['step_id'], op=s['op'], args=s['args'], deps=s['deps'], gate=s['gate'])
             for s in payload['plans'][0]['steps']]
    restored = PlanProgram(plans=[ProtocolPlan('restored', 'T', steps=steps)])
    result = run(restored, RecordingDriver())
    assert result.ok, result.diagnostics


def test_no_implicit_driver_medium_support():
    from culsma.driver.framework.capability import CapabilityPolicy
    from culsma.pipeline.plan_nodes import PlanStep
    medium = encode_descriptor(LiquidMedium(source='bath'))
    step = PlanStep(step_id='test', op='env_hold', args={}, deps=[], gate={'env': {'medium': medium}})
    assert not CapabilityPolicy().evaluate(step).ok
    assert CapabilityPolicy(supported_medium_phases=frozenset({MediumPhase.LIQUID})).evaluate(step).ok


def test_partial_composition_and_legacy_modifiers_cannot_overfill():
    medium = GasMedium(CompositionSpec((ComponentRequirement('N2', (80, '%'), Basis.VOLUME_FRACTION),)))
    env = {'medium': encode_descriptor(medium),
           'thermal': {'kind': 'IRQuantity', 'value': 37, 'unit': 'C'},
           'co2': {'kind': 'IRQuantity', 'value': 30, 'unit': '%'}}
    with pytest.raises(ValueError, match='exceed'):
        NORMALIZER.normalize_runtime_environment(env)


def test_returned_medium_can_be_used_again(build_plan):
    driver = RecordingDriver()
    result = run(build_plan('''
      protocol Make(b) { return liquid_medium(source=b); }
      let b=chamber(); let s=tube(); let m=Make(b=b);
      with env(medium=m, duration=1min) { hold(s); }
      return {medium: m, sources: [m]};
    '''), driver)
    assert result.ok, result.diagnostics
    returned = result.state.artifacts['protocol_outputs']['entry']['value']
    held = next(s.gate['env']['medium'] for s in driver.steps if s.op == 'env_hold')
    assert returned == {'medium': held, 'sources': [held]}


def test_medium_exposure_preserves_loaded_inventory(build_plan):
    prefix = '''protocol T {
      let sample=chamber(load=[content(kind=ContentKind.FORMULATION,
          type=ContentType.BUFFER, code="SAMPLE"):50uL]);
      let bath=chamber(capacity=25mL,load=[content(kind=ContentKind.FORMULATION,
          type=ContentType.OTHER_FORMULATION, code="BATH"):20mL]);
    '''
    plain = run(build_plan(prefix + '}'), StubDriver())
    exposed = run(build_plan(prefix + '''
      with env(medium=liquid_medium(source=bath), duration=1min) { hold(sample); }
    }'''), StubDriver())
    assert plain.ok and exposed.ok
    assert plain.state.artifacts['material_state'] == exposed.state.artifacts['material_state']


def test_nested_legacy_modifier_conflicts_with_medium(build_plan):
    source = '''protocol T {
      let s=tube();
      let air=gas_medium(composition=composition(components=[
        medium_component(material="CO2",quantity=5%,basis=CompositionBasis.VOLUME_FRACTION)]));
      with env(thermal=37C,co2=6%) { hold(s);
        with env(medium=air,duration=1min) { hold(s); }
      }
    }'''
    driver = RecordingDriver()
    result = run(build_plan(source), driver)
    assert not result.ok
    assert any(d.code == 'RT_ENV_ARGUMENT_INVALID' for d in result.diagnostics)
    assert not any(s.op == 'env_hold' for s in driver.steps)


def test_medium_condition_does_not_leak_after_scope(build_plan):
    driver = RecordingDriver()
    result = run(build_plan('''protocol T {
      let s=tube(); let b=chamber();
      with env(medium=liquid_medium(source=b),duration=1min) { hold(s); }
      with env(thermal=22C,duration=1min) { hold(s); }
    }'''), driver)
    assert result.ok, result.diagnostics
    holds = [s for s in driver.steps if s.op == 'env_hold']
    assert 'medium' in holds[0].gate['env']
    assert 'medium' not in holds[1].gate['env']
    assert all('medium' not in layer['env'] for layer in holds[1].gate['env_layers'])


@pytest.mark.parametrize('basis,coverage,prefix', [
    ('"mole_fraction"', 'CompositionCoverage.PARTIAL', ''),
    ('CompositionBasis.MOLE_FRACTION', '"partial"', ''),
    ('CompositionCoverage.PARTIAL', 'CompositionCoverage.PARTIAL', ''),
    ('CompositionBasis.MOLE_FRACTION', 'CompositionBasis.MOLE_FRACTION', ''),
    ('choice', 'CompositionCoverage.PARTIAL', 'let choice="mole_fraction";'),
    ('CompositionBasis.MOLE_FRACTION', 'choice', 'let choice="partial";'),
])
def test_medium_source_options_require_enum_members(compile_source, basis, coverage, prefix):
    compiled = compile_source(f'''protocol T {{
      {prefix}
      let s=tube();
      with env(medium=gas_medium(composition=composition(coverage={coverage},
        components=[medium_component(material="CO2",quantity=5%,basis={basis})])),duration=1min) {{ hold(s); }}
    }}''')
    result = typecheck(compiled.ir, analysis=compiled.analysis)
    assert not result.ok
    assert any(d.code in {'TYPE_ENV_MEDIUM_INVALID', 'TYPE_EXTERNAL_ENUM_MISMATCH'} for d in result.diagnostics)


def test_medium_phase_and_driver_options_are_typed():
    from enum import StrEnum
    from culsma.driver.framework.capability import CapabilityPolicy

    class OtherPhase(StrEnum):
        GAS = 'gas'

    assert GasMedium(source='gas-source').phase is MediumPhase.GAS
    assert LiquidMedium(source='bath').phase is MediumPhase.LIQUID
    for invalid in ('gas', OtherPhase.GAS):
        class InvalidMedium(GasMedium):
            phase = invalid
        with pytest.raises(ValueError, match='MediumPhase'):
            InvalidMedium(source='source')
        with pytest.raises(TypeError, match='MediumPhase'):
            CapabilityPolicy(supported_medium_phases={invalid})
        with pytest.raises(TypeError, match='MediumPhase'):
            StubDriver(supported_medium_phases={invalid})


def test_source_strings_rejected_but_wire_enums_decode():
    descriptor = {'kind': 'IRCall', 'name': 'medium_component', 'args': [
        {'name': 'material', 'value': {'kind': 'IRString', 'value': 'CO2'}},
        {'name': 'quantity', 'value': {'kind': 'IRQuantity', 'value': 5, 'unit': '%'}},
        {'name': 'basis', 'value': {'kind': 'IRString', 'value': 'mole_fraction'}},
    ]}
    with pytest.raises(ValueError, match='CompositionBasis'):
        decode_descriptor(descriptor)
    component = ComponentRequirement('CO2', (5, '%'), Basis.MOLE_FRACTION)
    assert decode_descriptor(json.loads(json.dumps(encode_descriptor(component)))) == component


def test_ordinary_atmosphere_is_the_implicit_default():
    from culsma.domains.medium import DEFAULT_MEDIUM
    from culsma.pipeline.external_boundary import resolve_medium
    original = {'thermal': {'kind': 'IRQuantity', 'value': 22, 'unit': 'C'},
                'duration': {'kind': 'IRQuantity', 'value': 1, 'unit': 'min'}}
    normalized = NORMALIZER.normalize_runtime_environment(original, require_duration=True)
    assert normalized == original
    assert resolve_medium(normalized) is DEFAULT_MEDIUM
    assert DEFAULT_MEDIUM == GasMedium()
    assert DEFAULT_MEDIUM.phase is MediumPhase.GAS
    assert DEFAULT_MEDIUM.composition.components == ()
    assert DEFAULT_MEDIUM.source is None
    bath = LiquidMedium(source='bath')
    assert resolve_medium(normalized, inherited=bath) is bath
    assert resolve_medium({'medium': encode_descriptor(DEFAULT_MEDIUM)}, inherited=bath) == DEFAULT_MEDIUM


def test_atmosphere_only_timed_hold_needs_no_explicit_medium(build_plan):
    driver = RecordingDriver()
    driver.supported_medium_phases = frozenset()  # Existing atmosphere path.
    result = run(build_plan('protocol T { let s=tube(); with env(duration=1min) { hold(s); } }'), driver)
    assert result.ok, result.diagnostics
    hold = next(s for s in driver.steps if s.op == 'env_hold')
    assert set(hold.gate['env']) == {'duration'}


def test_ordinary_atmosphere_descriptor_can_be_explicit(build_plan):
    driver = RecordingDriver()
    result = run(build_plan('protocol T { let s=tube(); with env(medium=gas_medium(),duration=1min) { hold(s); } }'), driver)
    assert result.ok, result.diagnostics
    medium = next(s.gate['env']['medium'] for s in driver.steps if s.op == 'env_hold')
    assert decode_descriptor(medium) == GasMedium()


def test_implicit_atmosphere_does_not_override_enclosing_bath(build_plan):
    from culsma.pipeline.external_boundary import resolve_medium
    driver = RecordingDriver()
    result = run(build_plan('''protocol T {
      let s=tube(); let b=chamber();
      with env(medium=liquid_medium(source=b)) { hold(s);
        with env(duration=1min) { hold(s); }
      }
      with env(duration=1min) { hold(s); }
    }'''), driver)
    assert result.ok, result.diagnostics
    first, second = [s for s in driver.steps if s.op == 'env_hold']
    outer, inner = first.gate['env_layers']
    bath = resolve_medium(outer['env'])
    assert resolve_medium(inner['env'], inherited=bath) == bath
    assert bath.phase is MediumPhase.LIQUID
    assert resolve_medium(second.gate['env']) == GasMedium()


def test_gas_modifiers_refine_default_atmosphere_without_fabricated_balance(build_plan):
    driver = RecordingDriver()
    result = run(build_plan('''protocol T { let s=tube();
      with env(thermal=37C,co2=5%,rh=80%,duration=1min) { hold(s); }
    }'''), driver)
    assert result.ok, result.diagnostics
    env = next(s.gate['env'] for s in driver.steps if s.op == 'env_hold')
    assert set(env) == {'thermal', 'co2', 'humidity', 'duration'}
    assert env['co2']['value'] == 5


ETHANOL_CONTENTS = """
    let ethanol = content(kind=ContentKind.CHEMICAL, type=ContentType.SOLVENT, code="ETHANOL");
    let water = content(kind=ContentKind.CHEMICAL, type=ContentType.SOLVENT, code="WATER");
"""


def test_liquid_contents_reach_driver_without_allocating_bath(build_plan):
    source = ETHANOL_CONTENTS + """
    protocol Expose(sample, alcohol, solvent, ratio, final_volume) {
      let medium = liquid_medium(
        contents={alcohol: ratio, solvent: 100% - ratio},
        basis=CompositionBasis.VOLUME_FRACTION, volume=final_volume);
      with env(medium=medium, duration=45min, thermal=22C) { hold(sample); }
      return medium;
    }
    let sample = tube();
    let medium = Expose(sample=sample, alcohol=ethanol, solvent=water, ratio=80%, final_volume=500mL);
    return medium;
    """
    from culsma.pipeline.plan_nodes import PlanProgram, PlanStep, ProtocolPlan

    payload = json.loads(json.dumps(build_plan(source).to_dict()))
    plans = [
        ProtocolPlan(**{key: value for key, value in plan.items() if key not in {'kind', 'span', 'steps'}}, steps=[
            PlanStep(step_id=s['step_id'], op=s['op'], args=s['args'], deps=s['deps'], gate=s['gate'])
            for s in plan['steps']
        ])
        for plan in payload['plans']
    ]
    driver = RecordingDriver()
    result = run(PlanProgram(plans=plans), driver)
    assert result.ok, result.diagnostics
    held = next(s.gate['env']['medium'] for s in driver.steps if s.op == 'env_hold')
    assert result.state.artifacts['protocol_outputs']['entry']['value'] == held
    assert decode_descriptor(held).contents == {'ETHANOL': (80, '%'), 'WATER': (20, '%')}
    assert decode_descriptor(held).volume == (500000, 'uL')
    assert set(held) == {'kind', 'contents', 'basis', 'volume'}
    assert len(result.state.artifacts['material_state']['containers']) == 1
    assert not result.state.artifacts['material_state'].get('content_registry')


def test_liquid_contents_can_use_absolute_volume(build_plan):
    driver = RecordingDriver()
    result = run(build_plan(ETHANOL_CONTENTS + """
      let sample = tube();
      with env(medium=liquid_medium(contents={ethanol: 400mL, water: 100mL}), duration=1min) {
        hold(sample);
      }
    """), driver)
    assert result.ok, result.diagnostics
    medium = decode_descriptor(next(s.gate['env']['medium'] for s in driver.steps if s.op == 'env_hold'))
    assert medium.contents == {'ETHANOL': (400000, 'uL'), 'WATER': (100000, 'uL')}
    assert medium.volume == (500000, 'uL')


@pytest.mark.parametrize('args, message', [
    ('contents={ethanol: 80%, water: 10%}, basis=CompositionBasis.VOLUME_FRACTION', 'total 100%'),
    ('contents={ethanol: 80%, ethanol: 20%}, basis=CompositionBasis.VOLUME_FRACTION', 'duplicate'),
    ('contents={ethanol: 80%, alias: 20%}, basis=CompositionBasis.VOLUME_FRACTION', 'duplicate'),
    ('contents={"ethanol": 80%, water: 20%}, basis=CompositionBasis.VOLUME_FRACTION', 'declared content'),
    ('contents={ethanol: 80%, water: 20%}', 'volume quantities'),
    ('contents={ethanol: 400mL, water: 100mL}, volume=400mL', 'sum of its contents'),
    ('contents={ethanol: 80%, water: 20%}, basis=CompositionBasis.VOLUME_FRACTION, volume=500mg', 'positive volume'),
    ('contents={ethanol: 80%, water: 20%}, basis="volume_fraction"', 'CompositionBasis'),
    ('contents=[content(kind=ContentKind.CHEMICAL, type=ContentType.SOLVENT, code="ETHANOL"):10mL]', 'map keyed'),
])
def test_invalid_liquid_contents(compile_source, args, message):
    compiled = compile_source(ETHANOL_CONTENTS + f"""
        let alias=ethanol;
        let medium=liquid_medium({args});
    """)
    checked = typecheck(compiled.ir, analysis=compiled.analysis)
    assert any(d.code == 'TYPE_ENV_MEDIUM_INVALID' and message in d.message for d in checked.diagnostics)


def test_liquid_fraction_recipe_requires_volume_only_when_used(build_plan):
    recipe = ETHANOL_CONTENTS + """
      let recipe = liquid_medium(contents={ethanol: 80%, water: 20%},
                                basis=CompositionBasis.VOLUME_FRACTION);
    """
    described = run(build_plan(recipe + 'return recipe;'), RecordingDriver())
    assert described.ok, described.diagnostics
    driver = RecordingDriver()
    used = run(build_plan(recipe + """
      let sample=tube();
      with env(medium=recipe, duration=1min) { hold(sample); }
    """), driver)
    assert not used.ok
    assert any(d.code == 'RT_ENV_ARGUMENT_INVALID' and 'final volume' in d.message for d in used.diagnostics)
    assert not any(step.op == 'env_hold' for step in driver.steps)
