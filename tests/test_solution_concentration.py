"""Concentration load and ordinary volume transfer integration evidence."""
import pytest
import json
from pathlib import Path
from test_material_precision import run_source, material, BUFFER

def protein(code='A', concentration='5mg / 1mL'):
    extra = '' if concentration is None else ', concentration = '+concentration
    return ('content(kind=ContentKind.BIO_MOLECULE_OR_VIRUS, '
            'type=ContentType.PROTEIN, code="'+code+'"'+extra+')')

def stock(label='Stock',code='A',concentration='5mg / 1mL'):
    return f'let {label} = tube(label="{label}",capacity=10uL,load=[{protein(code,concentration)}:10uL]);'

def mass(c,code='A'):
    return c['component_quantities'][code]['value']

def concentration(c,code='A'):
    return c['component_concentrations'][code]['value']

def test_variable_and_continued_transfer_preserve_volume_and_mass():
    r=run_source('protocol T { let c=5mg / 1mL; '+stock(concentration='c')+'''
      let Target=tube(label="Target"); let Third=tube(label="Third");
      Target << [Stock:5uL]; Third << [Target:2uL]; }''')
    assert r.ok, r.diagnostics
    for label,v,m in [('Stock',5,.025),('Target',3,.015),('Third',2,.010)]:
        c=material(r,label)
        assert c['volume_uL']==pytest.approx(v)
        assert mass(c)==pytest.approx(m)
        assert concentration(c)==pytest.approx(.005)

@pytest.mark.parametrize('code',['A','B'])
def test_same_and_different_solutes_mix_and_dilute(code):
    r=run_source('protocol T {'+stock()+stock('Other',code,'1mg / 1mL')+f'''
      let Mix=tube(label="Mix"); let Aliquot=tube(label="Aliquot");
      let PBS=tube(load=[{BUFFER}:20uL]);
      Mix << [Stock,Other]; Aliquot << [Mix:5uL]; Mix << [PBS]; }}''')
    assert r.ok,r.diagnostics
    mix,aliquot=material(r,'Mix'),material(r,'Aliquot')
    assert mix['volume_uL']==35
    assert aliquot['volume_uL']==5
    if code=='A':
        assert mass(aliquot)==pytest.approx(.015)
        assert concentration(mix)==pytest.approx(.045/35)
    else:
        assert mass(aliquot)==pytest.approx(.0125)
        assert mass(aliquot,'B')==pytest.approx(.0025)
        assert concentration(mix)==pytest.approx(.0375/35)
        assert concentration(mix,'B')==pytest.approx(.0075/35)

@pytest.mark.parametrize('c',['5mg / 1mL','50ug / 10uL','0.005mg / 1uL'])
def test_equivalent_units(c):
    r=run_source('protocol T {'+stock(concentration=c)+'}')
    assert r.ok
    assert mass(material(r,'Stock'))==pytest.approx(.05)
    assert material(r,'Stock')['volume_uL']==10

def test_zero_and_omitted_are_distinct():
    r=run_source('protocol T {'+stock(concentration='0mg / 1mL')+stock('Old','B',None)+'}')
    assert r.ok
    assert mass(material(r,'Stock'))==0
    assert material(r,'Stock')['volume_uL']==10
    assert 'component_concentrations' not in material(r,'Old')

@pytest.mark.parametrize('tail,expected',[
    ('let Target=tube(label="Target"); Target << [Stock:11uL];','MAT_INSUFFICIENT_VOLUME'),
    ('let Target=tube(label="Target",capacity=1uL); Target << [Stock:2uL];','MAT_CONTAINER_OVERFLOW'),
    ('let Target=tube(label="Target",load=['+protein(concentration=None)+':1uL]); Target << [Stock:2uL];','MAT_CONTENT_QUANTITY_AXIS_CONFLICT'),
])
def test_failed_transfer_preserves_source(tail,expected):
    r=run_source('protocol T {'+stock()+tail+'}')
    assert not r.ok
    assert expected in [d.code for d in r.diagnostics]
    assert mass(material(r,'Stock'))==pytest.approx(.05)
    assert material(r,'Stock')['volume_uL']==10

def test_negative_concentration_fails_without_loading_material():
    r=run_source('protocol T {'+stock(concentration='-5mg / 1mL')+'}')
    assert not r.ok
    assert 'MAT_INVALID_SOLUTION_CONCENTRATION' in [d.code for d in r.diagnostics]
    assert material(r,'Stock')['volume_uL']==0

@pytest.mark.parametrize('value',['5','5mg','5mL','5mg / 0mL'])
def test_invalid_concentration_rejected_before_execution(value):
    from culsma.frontend.resolver import resolve_program
    from culsma.parser.parser import parse
    from culsma.pipeline.compile import compile_ast
    from culsma.pipeline.validate import validate
    from culsma.pipeline.typecheck import typecheck
    compiled=compile_ast(resolve_program(parse('protocol T {'+stock(concentration=value)+'}')).prepared_program)
    sem=validate(compiled.ir,analysis=compiled.analysis)
    assert sem.ok
    typed=typecheck(sem.ir,analysis=compiled.analysis)
    assert not typed.ok
    assert any(d.code.startswith('TYPE_') for d in typed.diagnostics)

def test_protocol_parameter_and_whole_transfer():
    r=run_source('''protocol Prepare(c) returns (result) {
      let result=tube(label="Stock",load=['''+protein(concentration='c')+''':10uL]);
      return result;
    }
    let source=Prepare(c=5mg / 1mL);
      let target=tube(label="Target"); target << [source];
    ''')
    assert r.ok,r.diagnostics
    assert material(r,'Target')['volume_uL']==10
    assert mass(material(r,'Target'))==pytest.approx(.05)

def test_public_return_keeps_solute_quantity_and_current_concentration():
    from culsma.runtime.values import RuntimeValueResolver
    r=run_source('protocol T {'+stock()+'}')
    c=material(r,'Stock')
    state=r.state.artifacts['material_state']
    cid=next(k for k,v in state['containers'].items() if v is c)
    resolver=RuntimeValueResolver()
    payload=resolver.protocol_output_serialize(resolver.container_ref_payload(state,cid))
    assert payload['component_quantities']['A']['value']==pytest.approx(.05)
    assert payload['component_concentrations']['A']['value']==pytest.approx(.005)

@pytest.mark.parametrize('action',[
    'let t=tube(label="Target"); t << [Stock:1ug];',
    'sep(sample=Stock,program=centrifuge_program(drive=12000g));',
])
def test_unmodeled_solution_operations_fail_without_changing_source(action):
    r=run_source('protocol T {'+stock()+action+'}')
    assert not r.ok
    assert 'MAT_SOLUTION_OPERATION_UNSUPPORTED' in [d.code for d in r.diagnostics]
    assert mass(material(r,'Stock'))==pytest.approx(.05)
    assert material(r,'Stock')['volume_uL']==10

def test_replacement_cannot_silently_ignore_concentration():
    from culsma.frontend.resolver import resolve_program
    from culsma.parser.parser import parse
    from culsma.pipeline.compile import compile_ast
    from culsma.pipeline.validate import validate
    source='protocol T {'+stock()+f'Stock.materials.replace({{Stock.materials[0]: {protein("B")}:1ug}}); }}'
    compiled=compile_ast(resolve_program(parse(source)).prepared_program)
    result=validate(compiled.ir,analysis=compiled.analysis)
    assert not result.ok
    assert any('concentration' in d.message for d in result.diagnostics)


@pytest.mark.parametrize('amount,attrs', [
    ('1mg', ', attrs={state:solid}'),
    ('1mg', ''),
    ('2uL', ', attrs={state:solid}'),
    ('2uL', ', attrs={state:unknown}'),
    ('2uL', ', attrs={state:suspension}'),
])
@pytest.mark.parametrize('direction', ['Stock << [Other];', 'Other << [Stock:5uL];'])
def test_unsupported_mixture_preserves_both_containers(amount, attrs, direction):
    prefix = stock().replace('capacity=10uL', 'capacity=100uL') + f'''
      let Other=tube(label="Other",capacity=100uL,load=[
        content(kind=ContentKind.BIO_MOLECULE_OR_VIRUS,type=ContentType.PROTEIN,
                code="OTHER"{attrs}):{amount}]);'''
    before = run_source('protocol T {' + prefix + '}')
    assert before.ok, before.diagnostics
    after = run_source('protocol T {' + prefix + direction + '}')
    assert not after.ok
    assert 'MAT_SOLUTION_MIXTURE_UNSUPPORTED' in [d.code for d in after.diagnostics]
    for label in ('Stock', 'Other'):
        assert material(after, label) == material(before, label)


@pytest.mark.parametrize('reverse', [False, True])
def test_mixed_initial_loads_reject_undeclared_mass_in_either_order(reverse):
    items = [protein() + ':10uL', protein('B', None) + ':1mg']
    if reverse:
        items.reverse()
    result = run_source('protocol T {let Stock=tube(label="Stock",load=[' + ','.join(items) + ']);}')
    assert not result.ok
    assert 'MAT_SOLUTION_MIXTURE_UNSUPPORTED' in [d.code for d in result.diagnostics]
    # Individual loads are separate steps: only the rejected load is rolled back.
    quantities = material(result, 'Stock')['component_quantities']
    assert ('A' in quantities) != reverse
    assert ('B' in quantities) == reverse


def test_unknown_material_cannot_enter_declared_solution():
    prefix = stock().replace('capacity=10uL', 'capacity=100uL') + f'''
      let Other=tube(label="Other",load=[{protein('INPUT', None)}:1mg]);
      Other.materials.replace({{Other.materials[0]:{protein('PRODUCT', None)}:unknown(dimension=mass)}});'''
    before = run_source('protocol T {' + prefix + '}')
    assert before.ok, before.diagnostics
    result = run_source('protocol T {' + prefix + 'Stock << [Other];}')
    assert not result.ok
    assert 'MAT_SOLUTION_MIXTURE_UNSUPPORTED' in [d.code for d in result.diagnostics]
    for label in ('Stock', 'Other'):
        assert material(result, label) == material(before, label)


def test_solution_replacement_is_rejected_without_retiring_material():
    prefix = stock()
    before = run_source('protocol T {' + prefix + '}')
    result = run_source('protocol T {' + prefix +
        f'Stock.materials.replace({{Stock.materials[1]:{protein("B", None)}:1mg}});}}')
    assert not result.ok
    assert 'MAT_SOLUTION_OPERATION_UNSUPPORTED' in [d.code for d in result.diagnostics]
    assert material(result, 'Stock') == material(before, 'Stock')


@pytest.mark.parametrize('c', ['0mg / 1mL', '0.00000000001mg / 1mL'])
def test_zero_and_trace_concentrations_survive_partial_transfer(c):
    prefix = stock(concentration=c)
    before = run_source('protocol T {' + prefix + '}')
    result = run_source('protocol T {' + prefix +
        'let Target=tube(label="Target"); Target << [Stock:5uL];}')
    assert result.ok, result.diagnostics
    original = material(before, 'Stock')
    for label in ('Stock', 'Target'):
        current = material(result, label)
        assert current['volume_uL'] == 5
        assert mass(current) == pytest.approx(mass(original) / 2, abs=0)
        assert concentration(current) == pytest.approx(concentration(original), abs=0)


def test_solution_benchmark_and_replay():
    from culsma.runtime.replay import replay_events
    directory = Path(__file__).resolve().parents[1] / 'benchmarks/concentration'
    result = run_source((directory / 'protocol.culs').read_text())
    assert result.ok, result.diagnostics
    expected = json.loads((directory / 'expected.json').read_text())
    for label, values in expected.items():
        current = material(result, label)
        assert current['volume_uL'] == pytest.approx(values['volume_uL'])
        for code, expected_mass in values.get('mass_mg', {}).items():
            assert mass(current, code) == pytest.approx(expected_mass)
            assert concentration(current, code) == pytest.approx(expected_mass / values['volume_uL'])
    # Check each solute globally; the same registry identity has several loads.
    containers = result.state.artifacts['material_state']['containers'].values()
    for code, total in [('ANTI_CD45', .05), ('RNA', .01), ('COMPOUND', .02)]:
        assert sum(c.get('component_quantities', {}).get(code, {}).get('value', 0)
                   for c in containers) == pytest.approx(total)
    events = json.loads(json.dumps([event.to_dict() for event in result.events]))
    replayed = replay_events(events)
    assert replayed.artifacts['material_state'] == result.state.artifacts['material_state']
