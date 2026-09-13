from copy import deepcopy
from pathlib import Path

import pytest

from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.runtime.material.compute import MaterialCompute
from culsma.runtime.material.component_entries import split_component_entry, component_entry_has_quantity
from culsma.runtime.material.unknown_quantity import is_unknown

PRODUCT = 'content(kind = ContentKind.BIO_MOLECULE_OR_VIRUS, type = ContentType.PROTEIN, code = "PROTEIN"):unknown(dimension = mass)'
REPLACE = f'sample.materials.replace(subject = sample.materials[0], products = [{PRODUCT}]);'
SOURCE = '''protocol T {
    let sample = tube(label = "Source", load = [
        content(kind = ContentKind.BIO_CELLULAR, type = ContentType.CELL_LINE, code = "CELLS"):200000cells,
        content(kind = ContentKind.FORMULATION, type = ContentType.BUFFER, code = "BUFFER"):310uL
    ]);
    REPLACEMENT
    TAIL
}'''


def compile_source(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    sem = validate(compiled.ir, analysis=compiled.analysis)
    return compiled, sem


def plan_source(source):
    compiled, sem = compile_source(source)
    assert sem.ok, [d.to_dict() for d in sem.diagnostics]
    typed = typecheck(sem.ir, analysis=compiled.analysis)
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
    assert not plan.diagnostics
    return plan


def source(replacement=REPLACE, tail=''):
    return SOURCE.replace('REPLACEMENT', replacement).replace('TAIL', tail)


def material(result, label):
    return next(c for c in result.state.artifacts['material_state']['containers'].values()
                if c.get('metadata', {}).get('label') == label)


def protein(container):
    return next(e for e in container['component_entries'] if e['content_ref'] == 'PROTEIN')


def test_replace_retires_cells_and_preserves_unknown_mass_and_volume():
    result = run(plan=plan_source(source()), driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    state = result.state.artifacts['material_state']
    sample = material(result, 'Source')
    assert sample['volume_uL'] == 310
    assert 'CELLS' not in sample['components']
    entry = protein(sample)
    assert entry['amount'] is None
    assert entry['quantity']['value'] is None
    assert entry['quantity']['status'] == 'unknown'
    assert sample['components']['PROTEIN'] is None
    assert sample['unknown_quantity_dimensions'] == ['mass']
    assert state['material_replacements'][0]['retired_entry']['quantity']['value'] == 200000
    assert entry['provenance']['source_entry_id'] == 'CELLS'


def test_separation_aliquots_and_recombination_preserve_symbolic_share():
    tail = '''
    let split = sep(sample = sample, program = centrifuge_program(drive = 12000g),
        component_fates = {PROTEIN: {supernatant: 100%, pellet: 0%}, BUFFER: {supernatant: 100%, pellet: 0%}});
    let aliquot = tube(label = "Aliquot");
    aliquot << [split[0]:65uL];
    let remainder = tube(label = "Remainder");
    remainder << [split[0]];
    let recombined = tube(label = "Recombined");
    recombined << [aliquot, remainder];
    '''
    result = run(plan=plan_source(source(tail=tail)), driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    recovered = material(result, 'Recombined')
    assert recovered['volume_uL'] == pytest.approx(310)
    assert list(protein(recovered)['quantity']['shares'].values()) == pytest.approx([1])
    assert protein(recovered)['provenance']['source_entry_id'] == 'CELLS'
    assert not any(is_unknown(e.get('quantity')) for e in material(result, 'Aliquot')['component_entries'])


def test_volume_aliquot_keeps_unknown_quantity():
    result = run(plan=plan_source(source(tail='let aliquot = tube(label = "Aliquot"); aliquot << [sample:65uL];')), driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    moved = protein(material(result, 'Aliquot'))
    assert moved['quantity']['value'] is None
    assert list(moved['quantity']['shares'].values()) == pytest.approx([65/310])
    assert list(protein(material(result, 'Source'))['quantity']['shares'].values()) == pytest.approx([245/310])


def test_mass_transfer_reports_unknown_and_is_atomic():
    result = run(plan=plan_source(source(tail='let aliquot = tube(label = "Aliquot"); aliquot << [sample:10ug];')), driver=StubDriver())
    assert not result.ok
    assert 'MAT_QUANTITY_UNKNOWN' in [d.code for d in result.diagnostics]
    assert material(result, 'Source')['volume_uL'] == 310
    assert material(result, 'Aliquot')['volume_uL'] == 0


def test_unknown_is_not_zero_on_empty_split():
    result = run(plan=plan_source(source()), driver=StubDriver())
    entry = protein(material(result, 'Source'))
    remaining, moved = split_component_entry(entry, 0)
    assert component_entry_has_quantity(remaining)
    assert not component_entry_has_quantity(moved)
    assert moved['quantity']['value'] == 0
    assert not is_unknown(moved['quantity'])


@pytest.mark.parametrize('replacement', [
    REPLACE.replace('sample.materials[0]', 'missing.materials[0]'),
    REPLACE.replace('products =', 'wrong ='),
    REPLACE.replace('unknown(dimension = mass)', 'unknown(dimension = volume)'),
    REPLACE.replace('unknown(dimension = mass)', '40ug'),
    'sample.materials.replace(subject = sample.materials[0], products = []);',
])
def test_invalid_replacement_contract(replacement):
    _, sem = compile_source(source(replacement=replacement))
    assert not sem.ok
    assert 'SEM_MATERIAL_REPLACE_INVALID' in [d.code for d in sem.diagnostics]


def test_missing_source_does_not_mutate_registry_or_material():
    plan = plan_source(source(replacement=REPLACE.replace('materials[0]', 'materials[99]')))
    compute = MaterialCompute()
    state = {'containers': {}}
    for step in plan.plans[0].steps:
        before = deepcopy(state)
        result = compute.apply_step(step, state)
        if step.op == 'replace':
            assert not result.ok
            assert result.material_state == before
            assert state == before
        else:
            assert result.ok
            state = result.material_state


def test_unknown_requires_explicit_separation_fate():
    result = run(plan=plan_source(source(tail='sep(sample = sample, program = centrifuge_program(drive = 12000g));')), driver=StubDriver())
    assert not result.ok
    assert 'MAT_QUANTITY_UNKNOWN' in [d.code for d in result.diagnostics]
    assert material(result, 'Source')['volume_uL'] == 310


def test_in_place_separation_retains_dry_unknown_material_and_return_payload():
    text = source(tail='''
        sep(sample = sample, program = filtration_program(membrane = "pvdf", drive = "aspiration"),
            component_fates = {PROTEIN: {filtrate: 0%, retentate: 100%}, BUFFER: {filtrate: 100%, retentate: 0%}});
        let waste = tube(label = "Waste");
        waste << [sample.contents[0]];
    ''')
    result = run(plan=plan_source(text), driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    retained = material(result, 'Source')
    assert retained['volume_uL'] == 0
    assert list(protein(retained)['quantity']['shares'].values()) == [1]
    from culsma.runtime.values import _container_ref_payload, _runtime_protocol_output_serialize
    state = result.state.artifacts['material_state']
    cid = next(k for k, v in state['containers'].items() if v == retained)
    payload = _runtime_protocol_output_serialize(_container_ref_payload(state, cid))
    assert payload['mass_mg'] is None
    assert payload['component_quantities']['PROTEIN']['status'] == 'unknown'
    assert next(e for e in payload['component_entries'] if e['content_ref'] == 'PROTEIN')['provenance']['source_entry_id'] == 'CELLS'


def test_second_invalid_product_rolls_back_entire_replacement():
    duplicate = REPLACE.replace(f'[{PRODUCT}]', f'[{PRODUCT}, {PRODUCT}]')
    plan = plan_source(source(replacement=duplicate))
    state = {'containers': {}}
    compute = MaterialCompute()
    for step in plan.plans[0].steps:
        before = deepcopy(state)
        result = compute.apply_step(step, state)
        if step.op == 'replace':
            assert not result.ok
            assert result.diagnostics[0].code == 'MAT_MATERIAL_REPLACE_DUPLICATE_PRODUCT'
            assert result.material_state == before
            assert 'PROTEIN' not in result.material_state['content_registry']
        else:
            assert result.ok
            state = result.material_state


def test_case09_full_pipeline_keeps_protein_without_fabricated_yield():
    case = Path(__file__).parents[1] / 'benchmarks/cases/09/protocol.culs'
    result = run(plan=plan_source(case.read_text()), driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    state = result.state.artifacts['material_state']
    proteins = [e for c in state['containers'].values() for e in c['component_entries']
                if e['content_ref'] == 'HEK293T_TOTAL_PROTEIN']
    assert proteins
    assert all(e['amount'] is None and e['quantity']['value'] is None for e in proteins)
    assert sum(sum(e['quantity']['shares'].values()) for e in proteins) == pytest.approx(1)
    assert len(state['material_replacements']) == 1
    membrane = material(result, 'PIO80356TransferredMembraneTank')
    assert any(e['content_ref'] == 'HEK293T_TOTAL_PROTEIN' for e in membrane['component_entries'])


def test_zero_entry_accepts_returned_unknown_material():
    tail = '''
        sep(sample = sample, program = filtration_program(membrane = "pvdf", drive = "aspiration"),
            component_fates = {PROTEIN: {filtrate: 0%, retentate: 100%}, BUFFER: {filtrate: 100%, retentate: 0%}});
        let recovered = tube(label = "Recovered");
        recovered << [sample.contents[1]];
        sample << [recovered];
    '''
    result = run(plan=plan_source(source(tail=tail)), driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    assert list(protein(material(result, 'Source'))['quantity']['shares'].values()) == [1]


def test_mass_aliquot_from_indexed_contents_is_unknown():
    tail = '''
        sep(sample = sample, program = centrifuge_program(drive = 12000g),
            component_fates = {PROTEIN: {supernatant: 100%, pellet: 0%}, BUFFER: {supernatant: 100%, pellet: 0%}});
        let aliquot = tube(label = "Aliquot");
        aliquot << [sample.contents[0]:10ug];
    '''
    result = run(plan=plan_source(source(tail=tail)), driver=StubDriver())
    assert not result.ok
    assert 'MAT_QUANTITY_UNKNOWN' in [d.code for d in result.diagnostics]
    assert material(result, 'Aliquot')['volume_uL'] == 0
