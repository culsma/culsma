"""Typed concentration arithmetic drives real transfers from current state."""
import pytest
from pathlib import Path

from culsma.common.quantity_arithmetic import QuantityArithmeticError, quantity_binary
from test_material_precision import run_source, material, BUFFER
from test_solution_concentration import stock, mass, concentration
from test_quantity_arithmetic_integration import checked


@pytest.mark.parametrize('op,left,right,expected', [
    ('*', (.005, 'mg_per_uL'), (10, 'uL'), (.05, 'mg')),
    ('*', (.01, 'mL'), (.005, 'mg_per_uL'), (.05, 'mg')),
    ('/', (25, 'ug'), (.005, 'mg_per_uL'), (5, 'uL')),
    ('/', (1, 'g'), (.005, 'mg_per_uL'), (200000, 'uL')),
    ('*', (0, 'mg_per_uL'), (10, 'uL'), (0, 'mg')),
])
def test_concentration_unit_conversion(op, left, right, expected):
    actual = quantity_binary(op, left, right)
    assert actual[1] == expected[1]
    assert actual[0] == pytest.approx(expected[0])


@pytest.mark.parametrize('op,left,right,reason', [
    ('/', (1, 'mg'), (0, 'mg_per_uL'), 'zero'),
    ('*', (1e308, 'mg_per_uL'), (10, 'uL'), 'nonfinite'),
    ('/', (1, 'mg'), (5e-324, 'mg_per_uL'), 'nonfinite'),
    ('+', (1, 'mg_per_uL'), (1, 'mg'), 'dimension'),
    ('*', (1, 'mg_per_uL'), (1, 'mg'), 'dimension'),
])
def test_invalid_concentration_arithmetic(op, left, right, reason):
    with pytest.raises(QuantityArithmeticError) as error:
        quantity_binary(op, left, right)
    assert error.value.reason == reason


@pytest.mark.parametrize('inline', [False, True])
def test_current_concentration_after_dilution_drives_dose_transfer(inline, capsys):
    source = stock().replace('capacity=10uL', 'capacity=100uL') + f'''
      let antibody=Stock.materials.get("A");
      let original=antibody.concentration;
      let PBS=tube(load=[{BUFFER}:10uL]); Stock << [PBS];
      let current=antibody.concentration;
      let dose=10ug / current;
      let calculated_mass=5uL * current;
      print(original); print(current); print(calculated_mass);
      let Target=tube(label="Target");
      Target << [Stock:{'10ug / antibody.concentration' if inline else 'dose'}];
    '''
    result = run_source('protocol T {' + source + '}')
    assert result.ok, result.diagnostics
    assert capsys.readouterr().out.splitlines() == [
        '0.005 mg_per_uL', '0.0025 mg_per_uL', '0.0125 mg']
    target = material(result, 'Target')
    assert target['volume_uL'] == pytest.approx(4)
    assert mass(target) == pytest.approx(.01)
    assert concentration(target) == pytest.approx(.0025)
    assert mass(material(result, 'Stock')) == pytest.approx(.04)


def test_literal_calculation_round_trip_initializes_and_transfers():
    result = run_source('protocol T {let c=5mg / 1mL; let m=c*10uL; let v=m/c;'
        + stock(concentration='c').replace(':10uL', ':v') +
        'let Target=tube(label="Target"); Target << [Stock:25ug / c];}')
    assert result.ok, result.diagnostics
    assert material(result, 'Target')['volume_uL'] == pytest.approx(5)
    assert mass(material(result, 'Target')) == pytest.approx(.025)


@pytest.mark.parametrize('expression', ['antibody.concentration + 1mg', '1mg / 0mg_per_uL'])
def test_known_wrong_dimensions_and_zero_are_rejected(expression):
    _, typed = checked('protocol T {'+stock()+
        'let antibody=Stock.materials.get("A");'
        f'let Target=tube(); Target << [Stock:{expression}];}}')
    assert not typed.ok
    assert any(d.severity == 'error' for d in typed.diagnostics)


@pytest.mark.parametrize('c,selector', [('0mg / 1mL','A'), (None,'A'), ('5mg / 1mL','MISSING')])
def test_unavailable_or_zero_current_concentration_cannot_move_material(c, selector):
    result = run_source('protocol T {'+stock(concentration=c)+
        f'let antibody=Stock.materials.get("{selector}");'
        'let dose=1ug / antibody.concentration;'
        'let Target=tube(label="Target"); Target << [Stock:dose];}')
    assert not result.ok
    assert material(result, 'Stock')['volume_uL'] == 10


def test_plain_record_concentration_does_not_acquire_quantity_identity(capsys):
    result = run_source('protocol T {let record={concentration:2}; print(record.concentration * 3);}')
    assert result.ok, result.diagnostics
    assert capsys.readouterr().out.strip() == '6'


def test_declared_zero_concentration_remains_readable_after_transfer(capsys):
    result = run_source('protocol T {' + stock(concentration='0mg / 1mL') + '''
        let Target=tube(label="Target");
        Target << [Stock:5uL];
        let original=Stock.materials.get("A");
        let transferred=Target.materials.get("A");
        print(original.concentration);
        print(transferred.concentration);
    }''')
    assert result.ok, result.diagnostics
    assert capsys.readouterr().out.splitlines() == ['0 mg_per_uL', '0 mg_per_uL']


def test_calculated_dose_benchmark(capsys):
    from culsma.runtime.replay import replay_events
    import json
    path = Path(__file__).resolve().parents[1] / 'benchmarks/concentration/calculated-dose.culs'
    result = run_source(path.read_text())
    assert result.ok, result.diagnostics
    assert capsys.readouterr().out.splitlines() == [
        '0.005 mg_per_uL', '0.0025 mg_per_uL', '4 uL', '0.01 mg']
    target = material(result, 'Target')
    assert target['volume_uL'] == pytest.approx(4)
    assert mass(target, 'ANTI_CD45') == pytest.approx(.01)
    replayed = replay_events(json.loads(json.dumps([e.to_dict() for e in result.events])))
    assert replayed.artifacts['material_state'] == result.state.artifacts['material_state']
