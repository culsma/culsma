"""Numerical stock/capacity boundaries must preserve actual material, not invent it."""

from copy import deepcopy
from math import inf, nextafter, ulp

import pytest

from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_files, resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.plan_nodes import PlanStep
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.runtime.material.compute import MaterialCompute
from culsma.runtime.material.precision import (
    MATERIAL_BOUNDARY_ULPS, material_amounts_close, material_limit_exceeded, resolve_available_amount,
)

BUFFER = 'content(kind = ContentKind.FORMULATION, type = ContentType.BUFFER, code = "BUFFER")'


def run_source(source=None, bundle=None):
    compiled = compile_ast((bundle or resolve_program(parse(source))).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    assert semantic.ok, semantic.diagnostics
    typed = typecheck(semantic.ir, analysis=compiled.analysis)
    assert typed.ok, typed.diagnostics
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
    assert not plan.diagnostics
    return run(plan=plan, driver=StubDriver())


def material(result, label):
    return next(c for c in result.state.artifacts['material_state']['containers'].values()
                if c.get('metadata', {}).get('label') == label)


@pytest.mark.parametrize('available', [nextafter(10000, 0), nextafter(10000, inf)])
@pytest.mark.parametrize('quantity', ['10000uL', '10mL', '0.01L'])
@pytest.mark.parametrize('indexed', [False, True])
def test_near_total_volume_transfer_empties_source_without_creating_material(available, quantity, indexed):
    separation = '''sep(sample = source, program = centrifuge_program(drive = 12000g),
        component_fates = {BUFFER: {supernatant: 100%, pellet: 0%}});''' if indexed else ''
    selected = 'source.contents[0]' if indexed else 'source'
    result = run_source(f'''protocol T {{
        let source = tube(label = "Source", capacity = 20mL, load = [{BUFFER}:{available}uL]);
        {separation}
        let target = tube(label = "Target", capacity = 10mL);
        target << [{selected}:{quantity}];
    }}''')
    assert result.ok, result.diagnostics
    src, dst = material(result, 'Source'), material(result, 'Target')
    assert src['volume_uL'] == 0
    assert dst['volume_uL'] == available
    assert dst['components']['BUFFER'] == available
    assert all(entry['amount'] == 0 for entry in src['component_entries'])


@pytest.mark.parametrize('indexed', [False, True])
def test_real_shortage_still_fails_without_moving_material(indexed):
    separation = '''sep(sample = source, program = centrifuge_program(drive = 12000g),
        component_fates = {BUFFER: {supernatant: 100%, pellet: 0%}});''' if indexed else ''
    selected = 'source.contents[0]' if indexed else 'source'
    available = 10000 - 1e-6
    result = run_source(f'''protocol T {{
        let source = tube(label = "Source", capacity = 20mL, load = [{BUFFER}:{available}uL]);
        {separation}
        let target = tube(label = "Target", capacity = 10mL);
        target << [{selected}:10000uL];
    }}''')
    assert not result.ok
    assert any(d.code == 'MAT_INSUFFICIENT_VOLUME' for d in result.diagnostics)
    assert material(result, 'Source')['volume_uL'] == available
    assert material(result, 'Target')['volume_uL'] == 0


def test_included_dilution_with_two_aliquots_allows_explicit_total_transfer(tmp_path):
    (tmp_path / 'prep.culs').write_text(f'''protocol Prepare(total, dilution) returns (solution) {{
        let aliquot = total / dilution;
        let diluent = total - aliquot - aliquot;
        let a = tube(capacity = total, load = [{BUFFER}:aliquot]);
        let b = tube(capacity = total, load = [{BUFFER}:aliquot]);
        let d = tube(capacity = total, load = [{BUFFER}:diluent]);
        let solution = tube(label = "Solution", capacity = total);
        solution << [a:aliquot, b:aliquot, d:diluent];
        return solution;
    }}''')
    entry = tmp_path / 'main.culs'
    entry.write_text('''include "prep.culs";
        let solution = Prepare(total = 10mL, dilution = 5000);
        let target = tube(label = "Target", capacity = 10mL);
        target << [solution:10000uL];''')
    result = run_source(bundle=resolve_files([entry]))
    assert result.ok, result.diagnostics
    assert material(result, 'Solution')['volume_uL'] == 0
    assert material(result, 'Target')['volume_uL'] == 9999.999999999998


@pytest.mark.parametrize('indexed', [False, True])
def test_mass_transfers_share_boundary_policy(indexed):
    protein = 'content(kind = ContentKind.BIO_MOLECULE_OR_VIRUS, type = ContentType.PROTEIN, code = "PROTEIN")'
    separation = '''sep(sample = source, program = centrifuge_program(drive = 12000g),
        component_fates = {PROTEIN: {supernatant: 100%, pellet: 0%}});''' if indexed else ''
    selected = 'source.contents[0]' if indexed else 'source'
    amount = nextafter(10, 0)
    result = run_source(f'''protocol T {{
        let source = tube(label = "Source", load = [{protein}:{amount}mg]);
        {separation}
        let target = tube(label = "Target");
        target << [{selected}:10000ug];
    }}''')
    assert result.ok, result.diagnostics
    assert material(result, 'Source')['mass_mg'] == 0
    assert material(result, 'Target')['mass_mg'] == amount


@pytest.mark.parametrize('scale', [1e-9, 1, 10000, 1e9])
def test_boundary_uses_representation_precision_not_fixed_physical_tolerance(scale):
    available = nextafter(scale, 0)
    assert resolve_available_amount(scale, available) == available
    short = scale - (MATERIAL_BOUNDARY_ULPS + 4) * ulp(scale)
    assert resolve_available_amount(scale, short) is None
    assert material_limit_exceeded(scale, short)
    assert not material_limit_exceeded(scale, available)


@pytest.mark.parametrize('amount', [1e-300, 1e-12, 1.0])
def test_empty_source_never_satisfies_positive_amount(amount):
    assert not material_amounts_close(0, amount)
    assert resolve_available_amount(amount, 0) is None
    assert resolve_available_amount(0, amount) == 0


@pytest.mark.parametrize('value', [inf, -inf, float('nan'), -1.0])
def test_invalid_amount_is_not_an_accepted_transfer(value):
    assert resolve_available_amount(value, 10) is None
    assert resolve_available_amount(10, value) is None


def test_real_capacity_overflow_still_fails():
    result = run_source(f'''protocol T {{
        let source = tube(label = "Source", capacity = 20mL, load = [{BUFFER}:10000.000001uL]);
        let target = tube(label = "Target", capacity = 10mL);
        target << [source];
    }}''')
    assert not result.ok
    assert any(d.code == 'MAT_CONTAINER_OVERFLOW' for d in result.diagnostics)
    assert material(result, 'Source')['volume_uL'] == 10000.000001
    assert material(result, 'Target')['volume_uL'] == 0


@pytest.mark.parametrize('axis,unit,mode', [
    ('volume', 'mg', 'bridge_mass_to_volume'), ('mass', 'uL', 'bridge_volume_to_mass'),
])
def test_density_bridge_resolves_roundoff_before_computing_movement_ratio(axis, unit, mode):
    available = nextafter(10000, 0)
    state = {'containers': {
        'A': {'volume_uL': available if axis == 'volume' else 0,
              'mass_mg': available if axis == 'mass' else 0,
              'components': {'BUFFER': available}, 'metadata': {'density_g_per_mL': 1.0}},
        'B': {'volume_uL': 0, 'mass_mg': 0, 'components': {}, 'metadata': {}},
    }}
    before = deepcopy(state)
    step = PlanStep(step_id='transfer', op='Mutation', deps=[], args={
        'target': {'kind': 'IRIdentifier', 'name': 'B'},
        'sources': [{'kind': 'IRPair', 'left': {'kind': 'IRIdentifier', 'name': 'A'},
                     'right': {'kind': 'IRQuantity', 'value': 10000, 'unit': unit}}],
    })
    result = MaterialCompute().apply_step(step, state)
    assert result.ok, result.diagnostics
    assert state == before
    assert result.delta['sources'][0]['transfer_delta']['mode'] == mode
    assert result.delta['sources'][0]['transfer_delta']['component_ratio'] == 1
    assert result.material_state['containers']['A'][axis + ('_uL' if axis == 'volume' else '_mg')] == 0
    assert result.material_state['containers']['B'][axis + ('_uL' if axis == 'volume' else '_mg')] == available
