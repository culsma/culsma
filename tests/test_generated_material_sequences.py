"""Seeded operation sequences checked against an independent rational ledger.

All separation fates are explicitly authored; these tests make no assumptions
about experimental recovery or scientific-model predictions.
"""

from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
import json
import random

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


CODES = ('X', 'Y', 'Z')


def quantity(amount, unit):
    scaled = amount / (1000 if unit == 'mL' else 1)
    return f'{Decimal(scaled.numerator) / Decimal(scaled.denominator)}{unit}'


def generate(seed, unit):
    rng = random.Random(seed)
    lines = [f'let v{i}=tube(label="V{i}",capacity=300uL,load=['
             f'content(kind=formulation,type=buffer,code="{code}"):100uL]);'
             for i, code in enumerate(CODES)]
    ledger = [{code: Fraction(100 if i == j else 0) for j, code in enumerate(CODES)} for i in range(3)]
    checkpoints = {}
    # Every seed includes transfer, explicit separation/recombination and mixing;
    # seed controls vessel choices, proportions, quantities and source form.
    for index in range(12):
        candidates = [i for i in range(3) if sum(ledger[i].values()) > 0]
        source = rng.choice(candidates)
        target = rng.choice([i for i in range(3) if i != source])
        if index % 4 == 1:
            fates = ','.join(f'{code}:{{pellet:{p}%,supernatant:{100-p}%}}'
                             for code in CODES if ledger[source][code] > 0
                             for p in [rng.choice([0, 25, 50, 75, 100])])
            lines.append(f'let parts{index}=sep(sample=v{source},program=centrifuge_program(drive=300g),'
                         f'component_fates={{{fates}}});')
            lines.append(f'v{source} << [parts{index}[0],parts{index}[1]];')
        elif index % 4 == 2:
            lines.append(f'agit(sample=v{source},mode=vortex,duration=1s);')
        else:
            fraction = rng.choice([Fraction(0), Fraction(1, 4), Fraction(1, 2), Fraction(1)])
            amount = sum(ledger[source].values()) * fraction
            source_expr = f'v{source}' if fraction == 1 and rng.choice([True, False]) else (
                f'v{source}:{quantity(amount, unit)}')
            lines.append(f'v{target} << [{source_expr}];')
            for code in CODES:
                moved = ledger[source][code] * fraction
                ledger[source][code] -= moved
                ledger[target][code] += moved
        checkpoints[len(lines)] = deepcopy(ledger)
    return '\n'.join(lines), checkpoints


@pytest.mark.parametrize('seed', [0, 1, 2, 7, 19, 42, 103, 2026])
@pytest.mark.parametrize('unit', ['uL', 'mL'])
def test_generated_sequences_conserve_each_component_after_every_operation(seed, unit):
    source, checkpoints = generate(seed, unit)
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    for result in (validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True),
                   typecheck(compiled.ir, analysis=compiled.analysis)):
        assert result.ok, (seed, unit, result.diagnostics, source)
    plan = lower_ir_to_plan(compiled.ir, analysis=compiled.analysis)
    assert not plan.diagnostics, plan.diagnostics
    result = run(plan, StubDriver())
    assert result.ok, (seed, unit, result.diagnostics, source)
    snapshots_by_line = {}
    for event in result.events:
        material = event.payload.get('material_state_snapshot')
        if event.kind != 'STEP_COMPLETED' or material is None or event.span.line <= 3:
            continue
        containers = material['containers']
        assert sum(c['volume_uL'] for c in containers.values()) == pytest.approx(300), (seed, event.step_id)
        for code in CODES:
            assert sum(c.get('components', {}).get(code, 0) for c in containers.values()) == pytest.approx(100)
        for container in containers.values():
            assert container['volume_uL'] >= -1e-9
            assert all(v >= -1e-9 for v in container.get('components', {}).values())
            capacity = container.get('metadata', {}).get('capacity_uL')
            if capacity is not None:
                assert container['volume_uL'] <= capacity + 1e-9
        snapshots_by_line[event.span.line] = material

    assert set(checkpoints) <= set(snapshots_by_line)
    for line, expected in checkpoints.items():
        material = snapshots_by_line[line]
        for i in range(3):
            vessel = material['containers'][material['bindings'][f'v{i}']]
            assert vessel['volume_uL'] == pytest.approx(float(sum(expected[i].values()))), (seed, unit, line, i)
            for code in CODES:
                assert vessel.get('components', {}).get(code, 0) == pytest.approx(float(expected[i][code])), (
                    seed, unit, line, i, code,
                )
    replayed = replay_events(json.loads(json.dumps([e.to_dict() for e in result.events])))
    assert replayed.step_status == result.state.step_status
    assert replayed.artifacts['material_state'] == result.state.artifacts['material_state']
