"""Source-to-execution invariants for literal and late-bound loop counts."""

import json

import pytest

from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.runtime.replay import replay_events


def execute(body, *, parameters='', entry_args=None):
    source = f'''protocol Aliquot{parameters} {{
      let stock = tube(label="Stock", capacity=200uL, load=[
        content(kind=formulation, type=buffer, code="BUFFER"):100uL]);
      let target = tube(label="Target", capacity=200uL);
      {body}
      return target;
    }}'''
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
    typed = typecheck(semantic.ir, analysis=compiled.analysis)
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis,
                            entry_args_by_protocol={'Aliquot': entry_args} if entry_args else None)
    assert not plan.diagnostics, [d.to_dict() for d in plan.diagnostics]
    result = run(plan, StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    return result


def material_by_label(result):
    return {c['metadata']['label']: c for c in
            result.state.artifacts['material_state']['containers'].values()}


@pytest.mark.parametrize('cycles', [0, 1, 3, 10])
@pytest.mark.parametrize('loop', ['count', 'schedule'])
@pytest.mark.parametrize('binding', ['literal', 'parameter', 'overridden-default'])
def test_loop_aliquots_conserve_material_and_survive_json_replay(cycles, loop, binding):
    count = str(cycles) if binding == 'literal' else 'cycles'
    header = f'repeat {count}' if loop == 'count' else (
        f'repeat tick in schedule(start=1, end={count}, step=1)')
    parameters = {'literal': '', 'parameter': '(cycles)', 'overridden-default': '(cycles=2)'}[binding]
    result = execute(f'{header} {{ target << [stock:10uL]; }}', parameters=parameters,
                     entry_args=None if binding == 'literal' else {'cycles': cycles})

    containers = material_by_label(result)
    assert containers['Stock']['volume_uL'] == pytest.approx(100 - cycles * 10)
    assert containers['Target']['volume_uL'] == pytest.approx(cycles * 10)
    assert sum(c['volume_uL'] for c in containers.values()) == pytest.approx(100)
    assert sum(c.get('components', {}).get('BUFFER', 0) for c in containers.values()) == pytest.approx(100)

    # Splitting an addition across iterations must agree with one bulk addition.
    bulk = execute(f'target << [stock:{cycles * 10}uL];' if cycles else '')
    for label, container in material_by_label(bulk).items():
        assert containers[label]['volume_uL'] == pytest.approx(container['volume_uL'])
        assert containers[label].get('components', {}) == pytest.approx(container.get('components', {}))

    events = json.loads(json.dumps([event.to_dict() for event in result.events]))
    replayed = replay_events(events)
    assert replayed.step_status == result.state.step_status
    assert replayed.artifacts['material_state'] == result.state.artifacts['material_state']


@pytest.mark.parametrize('control,expected', [('continue', 30), ('break', 10)])
def test_nested_loop_control_only_affects_its_own_loop(control, expected):
    result = execute(f'''
      repeat 2 {{
        repeat 3 {{
          target << [stock:5uL];
          {control};
          target << [stock:1uL];
        }}
      }}
    ''')
    containers = material_by_label(result)
    assert containers['Target']['volume_uL'] == pytest.approx(expected)
    assert containers['Stock']['volume_uL'] == pytest.approx(100 - expected)
    assert any(status == 'skipped' for status in result.state.step_status.values())
