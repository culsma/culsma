"""PM #113: calculated quantities survive checking, expansion and material execution."""

import pytest

from culsma.common.quantity_arithmetic import QuantityArithmeticError, quantity_binary
from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_files, resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.runtime.state import RuntimeState
from culsma.runtime.values import RuntimeValueResolver, UNRESOLVED

BUFFER = 'content(kind = ContentKind.FORMULATION, type = ContentType.BUFFER, code = "BUFFER")'


def checked(source=None, bundle=None):
    compiled = compile_ast((bundle or resolve_program(parse(source))).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
    return compiled, typecheck(semantic.ir, analysis=compiled.analysis)


def execute(source=None, bundle=None):
    compiled, typed = checked(source, bundle)
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
    assert not plan.diagnostics
    result = run(plan=plan, driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    return result


def material(result, label):
    return next(c for c in result.state.artifacts['material_state']['containers'].values()
                if c.get('metadata', {}).get('label') == label)


@pytest.mark.parametrize('amount,expected', [
    ('10mL / 1000', 10), ('10000uL / 1000', 10),
    ('10mL / 2500', 4), ('10mL / 500', 20), ('10mL / 3000', 10/3),
    ('1mL - 100uL', 900), ('100uL + 1mL', 1100),
    ('2 * 10uL', 20), ('10uL * 2', 20), ('-(-10uL)', 10),
    ('10mL / (1mL / 1uL)', 10),
])
@pytest.mark.parametrize('bound', [False, True])
def test_calculated_load_and_transfer_update_actual_material(amount, expected, bound):
    binding = f'let total = {amount}; let aliquot = total / 2;' if bound else ''
    load = 'total' if bound else amount
    transfer = 'aliquot' if bound else f'({amount}) / 2'
    result = execute(f'''protocol T {{
        {binding}
        let stock = tube(label = "Stock", load = [{BUFFER}:{load}]);
        let target = tube(label = "Target");
        target << [stock:{transfer}];
    }}''')
    for label in ['Stock', 'Target']:
        container = material(result, label)
        assert container['volume_uL'] == pytest.approx(expected / 2)
        assert container['components']['BUFFER'] == pytest.approx(expected / 2)


@pytest.mark.parametrize('total,expected', [('10mL', 10000), ('25mL', 25000)])
def test_separate_prep_protocol_parameters_returns_and_multiple_dilutions(tmp_path, total, expected):
    prep = tmp_path / 'Prep.culs'
    prep.write_text(f'''protocol Prepare(total_volume, d1, d2, d3, d4) returns (solution) {{
        let a1 = total_volume / d1;
        let a2 = total_volume / d2;
        let a3 = total_volume / d3;
        let a4 = total_volume / d4;
        let diluent = total_volume - a1 - a2 - a3 - a4;
        let stock = tube(label = "Stock", capacity = total_volume * 2, load = [{BUFFER}:total_volume]);
        let solution = tube(label = "Solution", capacity = total_volume * 2, load = [{BUFFER}:diluent]);
        solution << [stock:a1, stock:a2, stock:a3, stock:a4];
        return solution;
    }}''')
    main = tmp_path / 'main.culs'
    main.write_text(f'''include "Prep.culs";
        let prepared = Prepare(total_volume = {total}, d1 = 1000, d2 = 2500, d3 = 500, d4 = 3000);
        let used = tube(label = "Used");
        used << [prepared:1mL];
    ''')
    result = execute(bundle=resolve_files([main], library_roots=[tmp_path]))
    assert material(result, 'Solution')['volume_uL'] == pytest.approx(expected - 1000)
    assert material(result, 'Used')['volume_uL'] == pytest.approx(1000)
    assert material(result, 'Stock')['volume_uL'] == pytest.approx(expected * (1 - 1/1000 - 1/2500 - 1/500 - 1/3000))


@pytest.mark.parametrize('expression,code', [
    ('1mL + 1mg', 'DIMENSION_MISMATCH'),
    ('1mL + 1', 'DIMENSION_MISMATCH'),
    ('1mL * 1uL', 'DIMENSION_MISMATCH'),
    ('1 / 1mL', 'DIMENSION_MISMATCH'),
    ('1mL / 1mg', 'DIMENSION_MISMATCH'),
    ('1mL / 0', 'TYPE_QUANTITY_DIVISION_BY_ZERO'),
    ('1mL / (2 - 2)', 'TYPE_QUANTITY_DIVISION_BY_ZERO'),
    ('1mL / 1uL', 'QUANTITY_UNIT_REQUIRED'),
])
@pytest.mark.parametrize('slot', ['load', 'transfer'])
def test_invalid_arithmetic_keeps_quantity_contract(expression, code, slot):
    if slot == 'load':
        body = f'let target = tube(load = [{BUFFER}:amount]);'
    else:
        body = f'let stock = tube(load = [{BUFFER}:10mL]); let target = tube(); target << [stock:amount];'
    _, typed = checked(f'protocol T {{ let amount = {expression}; {body} }}')
    assert not typed.ok
    assert any(d.code.endswith(code) for d in typed.diagnostics), typed.diagnostics


def test_parameter_zero_denominator_rejected_after_expansion():
    _, typed = checked(f'''protocol Prepare(total_volume, dilution) returns (solution) {{
        let amount = total_volume / dilution;
        let solution = tube(load = [{BUFFER}:amount]);
        return solution;
    }}
    let result = Prepare(total_volume = 10mL, dilution = 0);''')
    assert not typed.ok
    assert any(d.code == 'TYPE_QUANTITY_DIVISION_BY_ZERO' for d in typed.diagnostics)


def test_computed_fractional_cells_rejected():
    cellular = 'content(kind = ContentKind.BIO_CELLULAR, type = ContentType.CELL_LINE, code = "CELLS")'
    _, typed = checked(f'protocol T {{ let sample = tube(load = [{cellular}:3cells / 2]); }}')
    assert not typed.ok
    assert any(d.code == 'TYPE_CELL_COUNT_VALUE_INVALID' for d in typed.diagnostics)


def test_runtime_uses_live_bound_quantities_and_preserves_result_unit():
    state = RuntimeState()
    state.artifacts['local_bindings'] = {
        'total': {'kind': 'IRQuantity', 'value': 10, 'unit': 'mL'}, 'factor': 3000}
    expr = {'kind': 'IRBinary', 'op': '/',
            'left': {'kind': 'IRIdentifier', 'name': 'total'},
            'right': {'kind': 'IRIdentifier', 'name': 'factor'}}
    resolver = RuntimeValueResolver()
    value, unit = resolver.eval_expr(expr, state)
    assert value == pytest.approx(10/3000)
    assert unit == 'mL'
    state.artifacts['local_bindings']['factor'] = 0
    assert resolver.eval_expr(expr, state) is UNRESOLVED


def test_mass_conversion_and_mixed_temperature_boundary():
    assert quantity_binary('-', (1, 'mg'), (100, 'ug')) == pytest.approx((.9, 'mg'))
    with pytest.raises(QuantityArithmeticError, match='temperature conversion'):
        quantity_binary('+', (20, 'C'), (300, 'K'))


@pytest.mark.parametrize('updates,expected', [
    ('dilution = 1000;', 10),
    ('if true { dilution = 1000; }', 10),
    ('dilution = 1000; dilution = dilution * 2;', 5),
])
def test_mutable_dilution_uses_current_value(updates, expected):
    result = execute(f'''protocol T {{
        let dilution = 0;
        {updates}
        let sample = tube(label = "Sample", load = [{BUFFER}:10mL / dilution]);
    }}''')
    assert material(result, 'Sample')['volume_uL'] == pytest.approx(expected)


def test_let_quantity_captures_value_before_later_assignment():
    result = execute(f'''protocol T {{
        let dilution = 1000;
        let aliquot = 10mL / dilution;
        dilution = 0;
        let sample = tube(label = "Sample", load = [{BUFFER}:aliquot]);
    }}''')
    assert material(result, 'Sample')['volume_uL'] == pytest.approx(10)


def test_mass_arithmetic_reaches_material_accounting():
    result = execute('''protocol T {
        let sample = tube(label = "Sample", load = [
            content(kind = ContentKind.BIO_MOLECULE_OR_VIRUS, type = ContentType.PROTEIN, code = "PROTEIN"):1mg - 100ug]);
        let aliquot = tube(label = "Aliquot");
        aliquot << [sample:1mg / 2];
    }''')
    assert material(result, 'Sample')['mass_mg'] == pytest.approx(.4)
    assert material(result, 'Aliquot')['mass_mg'] == pytest.approx(.5)


def test_deferred_scalar_still_requires_a_unit():
    _, typed = checked(f'''protocol T {{
        let amount = 1;
        if true {{ amount = 2; }}
        let sample = tube(load = [{BUFFER}:amount]);
    }}''')
    assert not typed.ok
    assert any(d.code == 'TYPE_LOAD_QUANTITY_UNIT_REQUIRED' for d in typed.diagnostics)


def test_nonfinite_calculation_has_type_diagnostic():
    huge = '1' + '0' * 200
    _, typed = checked(f'protocol T {{ let sample = tube(load = [{BUFFER}:{huge}mL * {huge}]); }}')
    assert not typed.ok
    assert any(d.code == 'TYPE_QUANTITY_VALUE_NONFINITE' for d in typed.diagnostics)


@pytest.mark.parametrize('call,expected', [('dilution = 1000', 10), ('', None)])
def test_protocol_defaults_do_not_override_concrete_arguments(call, expected):
    source = f'''protocol Prepare(total = 10mL, dilution = 0) returns (solution) {{
        let amount = total / dilution;
        let solution = tube(label = "Solution", load = [{BUFFER}:amount]);
        return solution;
    }}
    let prepared = Prepare({call});'''
    if expected is None:
        _, typed = checked(source)
        assert not typed.ok
        assert any(d.code == 'TYPE_QUANTITY_DIVISION_BY_ZERO' for d in typed.diagnostics)
    else:
        result = execute(source)
        assert material(result, 'Solution')['volume_uL'] == pytest.approx(expected)


@pytest.mark.parametrize('expression,code', [
    ('1mL / 0', 'TYPE_QUANTITY_DIVISION_BY_ZERO'),
    ('1mL + 1mg', 'TYPE_LOAD_QUANTITY_DIMENSION_MISMATCH'),
])
def test_assignment_preserves_known_arithmetic_errors(expression, code):
    _, typed = checked(f'''protocol T {{
        let amount = 1mL;
        amount = {expression};
        let alias = amount;
        let sample = tube(load = [{BUFFER}:alias]);
    }}''')
    assert not typed.ok
    assert any(d.code == code for d in typed.diagnostics)


def test_generic_numeric_defaults_retain_dimension_checks():
    _, typed = checked(f'''protocol Prepare(total = 10min, dilution = 1000) returns (solution) {{
        let solution = tube(load = [{BUFFER}:total / dilution]);
        return solution;
    }}''')
    assert not typed.ok
    assert any(d.code == 'TYPE_LOAD_QUANTITY_DIMENSION_MISMATCH' for d in typed.diagnostics)


def test_environment_block_assignment_does_not_leave_stale_dilution():
    result = execute(f'''protocol T {{
        let dilution = 0;
        let base = tube();
        with env(thermal = 20C, duration = 1s) {{
            dilution = 1000;
            hold(sample = base);
        }}
        let sample = tube(label = "Sample", load = [{BUFFER}:10mL / dilution]);
    }}''')
    assert material(result, 'Sample')['volume_uL'] == pytest.approx(10)


@pytest.mark.parametrize('parameters,body', [
    ('drive = 12000g', 'let program = centrifuge_program(drive = drive);'),
    ('bins = 3', 'let program = density_gradient_program(axis = "density", order = "top_to_bottom", bins = bins);'),
])
def test_numeric_defaults_remain_usable_in_program_fields(parameters, body):
    _, typed = checked(f'protocol Prepare({parameters}) {{ {body} }} Prepare();')
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]
