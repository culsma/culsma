"""Plate allocation must use bound arguments, never frozen source defaults."""
import json

import pytest

from culsma.domains.labware import PlateFormat, selector_positions, validate_plate_position
from culsma.domains.readout import ReadoutQuantity
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.driver.stub import StubDriver


def compile_plate(body, params='format=PlateFormat.WELL_96'):
    compiled = compile_ast(resolve_program(parse(f'protocol T({params}) {{ {body} }}')).prepared_program)
    for result in (validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True),
                   typecheck(compiled.ir, analysis=compiled.analysis)):
        assert result.ok, [d.to_dict() for d in result.diagnostics]
    return compiled.ir


def plan_plate(ir, **args):
    return lower_ir_to_plan(ir, entry_args_by_protocol={'T': args})


def allocation_steps(plan):
    return [step for protocol in plan.plans for step in protocol.steps if step.op == 'AllocContainer']


@pytest.mark.parametrize('actual', [PlateFormat.WELL_24, '24well'])
def test_actual_format_controls_bounds_without_mutating_ir(actual):
    ir = compile_plate('let p=plate(format=format); let w=p[H12];')
    before = repr(ir)
    assert allocation_steps(plan_plate(ir))
    rejected = plan_plate(ir, format=actual)
    assert not rejected.plans
    assert 'PLAN_PLATE_SELECTOR_INVALID' in [d.code for d in rejected.diagnostics]
    assert repr(ir) == before
    assert allocation_steps(plan_plate(ir))


def test_override_can_make_default_out_of_bounds_selector_valid():
    ir = compile_plate('let p=plate(format=format); let w=p[H12];', 'format=PlateFormat.WELL_24')
    assert not plan_plate(ir).plans
    plan = plan_plate(ir, format=PlateFormat.WELL_96)
    assert not plan.diagnostics
    assert run(plan=plan, driver=StubDriver()).ok


@pytest.mark.parametrize('actual', [ReadoutQuantity.PH, 'typo', 42, True])
def test_invalid_actual_format_cannot_produce_partial_plan(actual):
    ir = compile_plate('let t=tube(); let p=plate(format=format); let w=p[A1];')
    plan = plan_plate(ir, format=actual)
    assert not plan.plans
    assert plan.diagnostics


@pytest.mark.parametrize('capacity,expected', [('', 3400.0), (',capacity=2mL', 2000.0)])
def test_actual_format_and_explicit_capacity_reach_runtime(capacity, expected):
    ir = compile_plate(f'let p=plate(format=format{capacity}); let w=p[A1];')
    plan = plan_plate(ir, format='24well')
    assert not plan.diagnostics
    json.dumps(plan.to_dict())
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    containers = result.state.artifacts['material_state']['containers']
    assert len(containers) == 1
    assert next(iter(containers.values()))['metadata']['capacity_uL'] == expected


def test_custom_dimensions_and_aliases_bind_before_bounds_check():
    ir = compile_plate('let p=plate(rows=rows,cols=cols); let alias=p; let w=alias[B2]; let same=p[B2];',
                       'rows=1,cols=1')
    assert not plan_plate(ir).plans
    plan = plan_plate(ir, rows=2, cols=2)
    assert not plan.diagnostics
    assert len(allocation_steps(plan)) == 1


@pytest.mark.parametrize('rows', [0, -1, 1.5, True, 'two'])
def test_invalid_bound_dimensions_fail(rows):
    ir = compile_plate('let p=plate(rows=rows,cols=2); let w=p[A1];', 'rows=2')
    assert not plan_plate(ir, rows=rows).plans


def test_selector_order_duplicate_guard_and_multiletter_rows():
    assert selector_positions([('B2', 'A1'), ('AA1', None)]) == ['A1', 'A2', 'B1', 'B2', 'AA1']
    with pytest.raises(ValueError, match='Duplicate'):
        selector_positions([('A1', 'B2'), ('A1', None)])
    with pytest.raises(ValueError):
        selector_positions([('A0', None)])
    validate_plate_position('AA1', rows=27, cols=1)
    with pytest.raises(ValueError, match='bounds'):
        validate_plate_position('AA1', rows=26, cols=1)


def test_bound_capacity_overrides_default_and_rejects_wrong_dimension():
    ir = compile_plate('let p=plate(format=format,capacity=cap); let w=p[A1];',
                       'format=PlateFormat.WELL_24,cap=1mL')
    quantity = {'kind': 'IRQuantity', 'value': 2, 'unit': 'mL'}
    plan = plan_plate(ir, cap=quantity)
    result = run(plan=plan, driver=StubDriver())
    assert result.ok
    well = next(iter(result.state.artifacts['material_state']['containers'].values()))
    assert well['metadata']['capacity_uL'] == 2000
    for invalid in ({'kind': 'IRQuantity', 'value': 2, 'unit': 's'},
                    {'kind': 'IRQuantity', 'value': -1, 'unit': 'mL'}, 2):
        assert not plan_plate(ir, cap=invalid).plans


def test_protocols_with_same_plate_name_have_independent_references():
    from culsma.pipeline.entrypoints import EntryResolution
    source = '''
protocol First { let p=plate(format=PlateFormat.WELL_96); let w=p[A1]; }
protocol Second { let p=plate(format=PlateFormat.WELL_24); let w=p[A1]; }
'''
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    for name in ('First', 'Second'):
        plan = lower_ir_to_plan(compiled.ir, entry_resolution=EntryResolution(
            kind='protocol', protocol_name=name, source='legacy_single_protocol'))
        assert not plan.diagnostics
        assert len(allocation_steps(plan)) == 1
        assert run(plan=plan, driver=StubDriver()).ok


def test_bound_plate_diagnostic_keeps_selector_source():
    ir = compile_plate('let p=plate(format=format); let w=p[H12];')
    from culsma.pipeline.ir_nodes import IRPlateWellRef
    reference = next(stmt for stmt in ir.protocols[0].statements
                     if isinstance(getattr(stmt, 'value', None), IRPlateWellRef))
    plan = plan_plate(ir, format='24well')
    diagnostic = next(d for d in plan.diagnostics if d.code == 'PLAN_PLATE_SELECTOR_INVALID')
    assert diagnostic.span == reference.value.span
    assert diagnostic.node_id == reference.id
