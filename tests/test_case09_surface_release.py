"""Case 09 detaches counted cells before collection and chemical replacement."""
from pathlib import Path

import pytest

from culsma.driver.human import HumanDriver
from culsma.driver.robot import RobotDriver
from culsma.frontend.resolver import resolve_files, resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run

CASE = Path(__file__).resolve().parents[1] / 'archive/benchmarks-legacy/cases/09/protocol.culs'


def execute_case(stage, driver_type=HumanDriver):
    if stage == 'complete':
        bundle = resolve_files([CASE])
    else:
        markers = {
            'attached': '        let lifted_cells = sep(',
            'released': '        lysate << [lifted_cells[0]];',
            'collected': '    with env(thermal = 4C) {',
        }
        source = CASE.read_text().split(markers[stage], 1)[0]
        source = source.replace('include "antibody_preparation.culs";', '')
        source = source.replace('protocol CellCultureWesternBlot returns (blot_image)', 'protocol Probe')
        source += ('    }\n' if stage != 'collected' else '') + '}\nProbe();'
        bundle = resolve_program(parse(source))
    compiled = compile_ast(bundle.prepared_program)
    sem = validate(compiled.ir, analysis=compiled.analysis)
    assert sem.ok, sem.diagnostics
    typed = typecheck(sem.ir, analysis=compiled.analysis)
    assert typed.ok, typed.diagnostics
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
    assert not plan.diagnostics
    result = run(plan=plan, driver=driver_type(supported_requirements={'dropwise'}))
    assert result.ok, result.diagnostics
    return result


def live_cells(result):
    return [(container, entry)
            for container in result.state.artifacts['material_state']['containers'].values()
            for entry in container['component_entries']
            if entry['content_ref'] == 'HEK293T' and entry['amount'] > 0]


def test_case09_release_precedes_transfer_and_preserves_cells_and_buffer():
    attached, = live_cells(execute_case('attached'))
    assert attached[1]['relation'] == 'container_surface'
    assert attached[1]['amount'] == 200000
    released = execute_case('released')
    container, cells = live_cells(released)[0]
    assert len(live_cells(released)) == 1
    assert cells['relation'] == 'free'
    separation, = [e.payload['material_delta'] for e in released.events
                   if e.kind == 'STEP_COMPLETED'
                   and e.payload.get('material_delta', {}).get('partition', {}).get(
                       'operation_contract', {}).get('program_args', {}).get('drive') == 'cell_lifter']
    transition = separation['partition']['transitions_by_component'][attached[1]['entry_id']]['0']
    assert transition['source'] == 'author_transition'
    assert transition['next_relation'] == 'free'
    assert not transition['retire_quantity']
    assert cells['associated_with'] is None
    assert cells['amount'] == 200000
    assert container['volume_uL'] == 300
    assert container['components']['RIPA1'] == 300
    assert next(c for c in released.state.artifacts['material_state']['containers'].values()
                if c.get('metadata', {}).get('label') == 'CellLysate')['volume_uL'] == 0
    collected, = live_cells(execute_case('collected'))
    assert collected[0]['metadata']['label'] == 'CellLysate'
    assert collected[0]['volume_uL'] == 300
    assert collected[1]['relation'] == 'free'
    assert collected[1]['amount'] == 200000


@pytest.mark.parametrize('driver_type', [HumanDriver, RobotDriver])
def test_surface_release_driver_projection_and_complete_case(driver_type):
    result = execute_case('complete', driver_type)
    payloads = [e.payload.get('driver_payload', {}) for e in result.events if e.kind == 'STEP_COMPLETED']
    if driver_type is HumanDriver:
        lifting, = [p['instruction'] for p in payloads
                    if 'using a cell lifter' in p.get('instruction', {}).get('summary', '')]
        assert any(p.get('binding', {}).get('tool_label') == 'cell lifter' for p in payloads)
        assert any('0 C' in line or '0.0 C' in line or '0C' in line for line in lifting['details'])
    else:
        lifting, = [p for p in payloads
                    if p.get('binding', {}).get('action') == 'material.separate.surface_release']
        assert lifting['binding']['program_kind'] == 'filtration_program'
    assert not live_cells(result)
