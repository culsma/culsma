"""PM #136: configuration fields share value resolution across the pipeline."""
from pathlib import Path

import pytest

from culsma.driver.stub import StubDriver
from culsma.common.quantity_arithmetic import UNIT_TO_DIMENSION, UNIT_SCALES
from culsma.pipeline.typecheck.expressions import TypecheckExpressionServices
from culsma.pipeline.plan.serialization import PlanExpressionSerializer
from culsma.frontend.resolver import resolve_files, resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.expression_resolution import resolve_expression, ResolutionStatus
from culsma.pipeline.ir_nodes import IRIdentifier, IRMember, IRQuantity, IRRecord
from culsma.runtime.executor import run
from culsma.runtime.state import RuntimeState
from culsma.runtime.values import evaluate_runtime_expression

PROTOCOLS = '''
protocol Capture(sample, antibody, antibody_volume) {
  let reagent = tube(load = [
    content(kind = antibody.identity.kind, type = antibody.identity.type,
            code = antibody.code, attrs = antibody.attrs):antibody_volume
  ]);
  sample << [reagent:antibody_volume];
  let captured = sep(sample = sample, program = magnetic_program(duration = antibody.duration),
      component_fates = antibody.component_fates,
      transitions = [transition(
        subject = sample.materials.get("ANTIBODY"),
        output = MagneticProgramOutput.BOUND,
        to = MaterialRelation.BEAD_BOUND,
        associated_with = sample.materials.get("BEADS")
      )]);
}
protocol Workflow(selected_antibody) {
  let sample = tube(label = "Sample", load = [
    content(kind = bio_fluid, type = whole_blood, code = "BLOOD"):500uL,
    content(kind = particulate, type = beads, code = "BEADS",
            attrs = { bead_property: magnetic }):100uL
  ]);
  Capture(sample = sample, antibody = selected_antibody,
          antibody_volume = selected_antibody.addition_volume);
}
'''
CONFIG = '''
let antibody_code = "ANTIBODY";
let fate = { bound: 100%, flowthrough: 0% };
let antibody_config = {
  identity: { kind: ContentKind.BIO_MOLECULE_OR_VIRUS, type: ContentType.PROTEIN },
  code: antibody_code,
  attrs: { role: "capture" },
  addition_volume: AMOUNT,
  duration: 5min,
  component_fates: {
    ANTIBODY: fate,
    BEADS: fate,
    BLOOD: { bound: 0%, flowthrough: 100% }
  }
};
let alias = antibody_config;
let condition = { pair: { antibody: alias } };
CALL(selected_antibody = condition.pair.antibody);
'''


def check(source=None, bundle=None):
    compiled = compile_ast((bundle or resolve_program(parse(source))).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    typed = typecheck(compiled.ir, analysis=compiled.analysis)
    return compiled, semantic, typed


def execute(source=None, bundle=None):
    compiled, semantic, typed = check(source, bundle)
    assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]
    plan = lower_ir_to_plan(compiled.ir, analysis=compiled.analysis)
    assert not plan.diagnostics
    result = run(plan=plan, driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    return result


@pytest.mark.parametrize('amount,expected', [('5uL', 5), ('0.005mL', 5), ('10mL / 1000', 10)])
@pytest.mark.parametrize('imported', [False, True])
def test_configuration_fields_execute_through_nested_protocols(tmp_path: Path, amount, expected, imported):
    config = CONFIG.replace('AMOUNT', amount).replace('CALL', 'Library.Workflow' if imported else 'Workflow')
    if imported:
        (tmp_path / 'Library.culs').write_text(PROTOCOLS)
        main = tmp_path / 'main.culs'
        main.write_text('import Library;\n' + config)
        result = execute(bundle=resolve_files([main], library_roots=[tmp_path]))
    else:
        result = execute(PROTOCOLS + config)
    material = result.state.artifacts['material_state']
    # Separation empties source; conservation is measured over concrete outputs.
    outputs = [c for c in material['containers'].values() if c.get('component_quantities', {}).get('ANTIBODY', {}).get('value', 0) > 0]
    assert sum(c['component_quantities']['ANTIBODY']['value'] for c in outputs) == pytest.approx(expected)
    antibody = next(e for c in outputs for e in c['component_entries'] if e['content_ref'] == 'ANTIBODY')
    assert antibody['relation'] == 'bead_bound'
    assert antibody['associated_with']
    assert antibody['association_target_kind'] == 'component_entry'


@pytest.mark.parametrize('amount,code', [('"5uL"', 'TYPE_LOAD_QUANTITY_UNIT_REQUIRED'), ('5', 'TYPE_LOAD_QUANTITY_UNIT_REQUIRED'), ('5min', 'TYPE_LOAD_QUANTITY_DIMENSION_MISMATCH')])
def test_record_quantities_still_enforce_units_and_dimensions(amount, code):
    _, _, typed = check(PROTOCOLS + CONFIG.replace('AMOUNT', amount).replace('CALL', 'Workflow'))
    assert not typed.ok
    assert code in {d.code for d in typed.diagnostics}


@pytest.mark.parametrize('source,code', [
    ('let cfg = { amount: 5uL }; let x = cfg.missing;', 'SEM_RECORD_FIELD_MISSING'),
    ('let cfg = 5uL; let x = cfg.amount;', 'SEM_RECORD_MEMBER_BASE_INVALID'),
    ('let cfg = { inner: { amount: 5uL } }; let x = cfg.inner.missing;', 'SEM_RECORD_FIELD_MISSING'),
])
def test_field_errors_report_the_projection_failure(source, code):
    _, semantic, _ = check(source)
    assert not semantic.ok
    assert code in {d.code for d in semantic.diagnostics}


def test_alias_and_projection_cycles_are_bounded():
    for bindings, expression in [
        ({'a': IRIdentifier('b'), 'b': IRIdentifier('a')}, IRIdentifier('a')),
        ({'r': IRRecord({'x': IRMember(IRIdentifier('r'), 'x')})}, IRMember(IRIdentifier('r'), 'x')),
    ]:
        result = resolve_expression(expression, bindings)
        assert result.status is ResolutionStatus.INVALID
        assert result.issue == 'binding_cycle'
    qty = IRQuantity(5, 'uL')
    record = IRRecord({'amount': qty, 'copy': IRMember(IRIdentifier('r'), 'amount')})
    assert resolve_expression(IRMember(IRIdentifier('r'), 'copy'), {'r': record}).value is qty


def test_serialized_runtime_record_fields_preserve_units_and_text():
    state = RuntimeState()
    state.artifacts['local_bindings'] = {'cfg': {
        'kind': {'kind': 'IRString', 'value': 'configuration'},
        'nested': {'amount': {'kind': 'IRQuantity', 'value': 5, 'unit': 'uL'}},
        'text': {'kind': 'IRString', 'value': '5uL'},
    }}
    root = {'kind': 'IRIdentifier', 'name': 'cfg'}
    nested = {'kind': 'IRMember', 'base': root, 'member': 'nested'}
    cases = [
        ({'kind': 'IRMember', 'base': nested, 'member': 'amount'}, (5, 'uL')),
        ({'kind': 'IRMember', 'base': root, 'member': 'text'}, '5uL'),
        ({'kind': 'IRMember', 'base': root, 'member': 'kind'}, 'configuration'),
    ]
    for expression, expected in cases:
        assert evaluate_runtime_expression(expression, state) == expected



@pytest.mark.parametrize('before,after,code', [
    ('code: antibody_code', 'code: 5uL', 'TYPE_CONTENT_CODE_NOT_TEXT'),
    ('attrs: { role: "capture" }', 'attrs: "capture"', 'TYPE_CONTENT_ATTRS_NOT_RECORD'),
    ('let fate = { bound: 100%, flowthrough: 0% }', 'let fate = { bound: 80%, flowthrough: 0% }', 'SEM_SEPARATION_FATE_RULE_TOTAL_INVALID'),
    ('code = antibody.code', 'code = antibody.missing', 'SEM_RECORD_FIELD_MISSING'),
])
def test_record_projection_does_not_bypass_receiving_contracts(before, after, code):
    source = (PROTOCOLS + CONFIG.replace('AMOUNT', '5uL').replace('CALL', 'Workflow')).replace(before, after)
    _, semantic, typed = check(source)
    assert code in {d.code for d in [*semantic.diagnostics, *typed.diagnostics]}


def test_arithmetic_through_cyclic_bindings_terminates():
    from culsma.pipeline.ir_nodes import IRBinary
    from culsma.pipeline.typecheck.expressions import TypecheckExpressionServices
    services = TypecheckExpressionServices()
    arithmetic = IRBinary('+', IRIdentifier('amount'), IRQuantity(5, 'uL'))
    assert services.evaluate_quantity(IRIdentifier('amount'), {'amount': arithmetic}) is None
    field = IRMember(IRIdentifier('config'), 'amount')
    record = IRRecord({'amount': IRBinary('+', field, IRQuantity(5, 'uL'))})
    assert services.evaluate_quantity(field, {'config': record}) is None




@pytest.mark.parametrize('unit,dimension', list(UNIT_TO_DIMENSION.items()))
def test_every_supported_unit_survives_field_resolution_and_execution(unit, dimension):
    compiled, semantic, typed = check(f'''
      let inner = {{ amount: 10{unit} }};
      let alias = inner;
      let config = {{ selected: alias }};
      let amount = config.selected.amount;
    ''')
    assert semantic.ok and typed.ok
    statements = compiled.ir.script_entry.statements
    bindings = {s.name: s.value for s in statements}
    value = statements[-1].value
    services = TypecheckExpressionServices()
    quantity = services.evaluate_quantity(value, bindings)
    assert quantity.value == 10
    assert quantity.unit == unit
    diagnostics = services.validate_quantity_dimensions(
        value, expr_bindings=bindings, expected=[dimension],
        non_quantity_code='NON_QUANTITY', mismatch_code='WRONG_DIMENSION',
        unknown_code='UNKNOWN_UNIT', label='audit', span=None, node_id=None,
    )
    assert not any(d.severity == 'error' for d in diagnostics)
    serializer = PlanExpressionSerializer()
    env = {}
    for stmt in statements:
        env[stmt.name] = serializer.serialize_expr(stmt.value, env)
    assert evaluate_runtime_expression(env['amount'], RuntimeState()) == (10, unit)
    # The same suffix in text must never be promoted to a quantity.
    _, _, invalid = check(f'let cfg={{amount:"10{unit}"}}; let x=tube(load=[content(kind=formulation,type=buffer):cfg.amount]);')
    assert 'TYPE_LOAD_QUANTITY_UNIT_REQUIRED' in {d.code for d in invalid.diagnostics}


@pytest.mark.parametrize('unit', list(UNIT_SCALES['time']))
def test_schedule_time_fields_use_shared_ast_resolution(unit):
    source = f'''let cfg={{start:0{unit}, end:2{unit}, step:1{unit}}};
      let alias=cfg;
      repeat tick in schedule(start=alias.start,end=alias.end,step=alias.step) {{ let x=tube(); }}'''
    result = execute(source)
    assert len(result.state.artifacts['material_state']['containers']) == 3


def test_environment_time_boundary_from_record_matches_literal():
    source = '''let cfg={duration:2min}; let target=tube();
      let feed=tube(load=[content(kind=formulation,type=buffer):10uL]);
      with env(thermal=37C,duration=cfg.duration) {
        repeat tick in schedule(start=0s,step=1min) {
          target << [feed:1uL];
        }
      }'''
    compiled, semantic, typed = check(source)
    literal, literal_sem, literal_type = check(source.replace('duration=cfg.duration','duration=2min'))
    assert semantic.ok and typed.ok and literal_sem.ok and literal_type.ok
    plan = lower_ir_to_plan(compiled.ir, analysis=compiled.analysis)
    literal_plan = lower_ir_to_plan(literal.ir, analysis=literal.analysis)
    assert [s.op for s in plan.plans[0].steps] == [s.op for s in literal_plan.plans[0].steps]


@pytest.mark.parametrize('unit', ['g', 'rpm'])
def test_centrifuge_drive_accepts_calculated_configuration_quantity(unit):
    _, semantic, typed = check(f'''protocol T {{
      let cfg={{drive:1000{unit}}};
      let sample=tube();
      let result=sep(sample=sample,program=centrifuge_program(drive=cfg.drive * 2));
    }}''')
    assert semantic.ok
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]


@pytest.mark.parametrize("amount", ["cfg.count", "cfg.count * 2", "cfg.count / 2"])
def test_count_field_load_retains_container_finalization(amount):
    source = '''let cfg={count:100cells};
      let sample=tube(label="Cells",load=[content(kind=bio_cellular,type=cell_line,code="CELLS"):AMOUNT]);'''.replace("AMOUNT", amount)
    compiled, semantic, typed = check(source)
    assert semantic.ok and typed.ok
    plan = lower_ir_to_plan(compiled.ir, analysis=compiled.analysis)
    assert 'FinalizeContainerContents' in [s.op for s in plan.plans[0].steps]
    result = run(plan=plan, driver=StubDriver())
    assert result.ok, [d.to_dict() for d in result.diagnostics]


def test_replacement_quantity_record_field_is_validated_and_executed():
    result = execute('''protocol T {
      let cfg={mass:10ug};
      let sample=tube(label="Source",load=[
        content(kind=bio_cellular,type=cell_line,code="CELLS"):200000cells,
        content(kind=formulation,type=buffer,code="BUFFER"):310uL
      ]);
      sample.materials.replace({sample.materials[0]:
        content(kind=bio_molecule_or_virus,type=protein,code="PROTEIN"):cfg.mass});
    }''')
    container = next(c for c in result.state.artifacts['material_state']['containers'].values()
                     if c.get('metadata', {}).get('label') == 'Source')
    entry = next(e for e in container['component_entries'] if e['content_ref'] == 'PROTEIN')
    assert entry['quantity']['dimension'] == 'mass'
    assert entry['quantity']['value'] == pytest.approx(.01)


@pytest.mark.parametrize('unit', ['ng_per_uL', 'ug_per_mL', 'rcf', 'xg', 'mM', 'uM', 'nM', 'M', 'nm', 'um', 'mW', 'W', 'X'])
def test_parser_only_units_remain_rejected_through_records(unit):
    _, _, typed = check(f'let cfg={{amount:10{unit}}}; let x=tube(load=[content(kind=formulation,type=buffer):cfg.amount]);')
    assert 'TYPE_UNKNOWN_UNIT' in {d.code for d in typed.diagnostics}


def test_resolution_calls_do_not_share_bindings_or_traversal_state():
    field = IRMember(IRIdentifier("cfg"), "amount")
    first, second = IRQuantity(5, "uL"), IRQuantity(10, "mg")
    assert resolve_expression(field, {"cfg": IRRecord({"amount": first})}).value is first
    assert resolve_expression(field, {"cfg": IRRecord({"amount": second})}).value is second
    assert resolve_expression(field, {"cfg": IRRecord({"amount": first})}).value is first


@pytest.mark.parametrize("base", [
    {"kind": "IRString", "value": "text"},
    {"kind": "IRQuantity", "value": 5, "unit": "uL"},
    {"kind": "IRBoolean", "value": True},
    {"kind": "IRList", "elements": []},
])
def test_serialized_scalar_projection_is_invalid_not_deferred(base):
    from culsma.pipeline.expression_resolution import project_record_member
    result = project_record_member(base, "missing")
    assert result.status is ResolutionStatus.INVALID
    assert result.issue == "non_record"


@pytest.mark.parametrize("member", ["dilution", "content_kind", "motion"])
def test_runtime_record_members_decode_enum_and_unitless_values(member):
    from culsma.pipeline.content_vocab import ContentKind
    from culsma.domains.agitation import AgitationMode
    state = RuntimeState()
    state.artifacts["local_bindings"] = {"cfg": {
        "dilution": {"kind": "IRQuantity", "value": 1000, "unit": None},
        "content_kind": {"kind": "ContentEnum", "enum": "ContentKind", "member": "FORMULATION"},
        "motion": {"kind": "ExternalEnum", "enum": "AgitationMode", "member": "VORTEX"},
    }}
    expected = {"dilution": 1000, "content_kind": ContentKind.FORMULATION, "motion": AgitationMode.VORTEX}[member]
    value = evaluate_runtime_expression({
        "kind": "IRMember", "base": {"kind": "IRIdentifier", "name": "cfg"}, "member": member,
    }, state)
    assert value == expected
    assert type(value) is type(expected)


def test_quantity_unit_inference_defers_unknowns_and_cycles():
    from culsma.pipeline.expression_resolution import quantity_expression_unit
    from culsma.pipeline.ir_nodes import IRBinary
    expr = IRBinary("+", IRIdentifier("parameter"), IRQuantity(10, "cells"))
    assert quantity_expression_unit(expr, {}) is None
    expr = IRBinary("+", IRIdentifier("amount"), IRQuantity(10, "cells"))
    assert quantity_expression_unit(IRIdentifier("amount"), {"amount": expr}) is None


@pytest.mark.parametrize("representation", ["ast", "ir", "serialized"])
def test_quantity_unit_inference_preserves_nested_arithmetic_across_representations(representation):
    from culsma.pipeline.expression_resolution import quantity_expression_unit
    from culsma.pipeline.ir_nodes import IRBinary, IRUnary
    from culsma.parser.ast_nodes import BinaryOp, UnaryOp, Identifier, MemberExpr, Quantity, RecordLiteral
    if representation == "ast":
        amount = MemberExpr(Identifier("cfg"), "count")
        expr = BinaryOp("/", UnaryOp("-", amount), Quantity(2, None))
        bindings = {"cfg": RecordLiteral({"count": Quantity(100, "cells")})}
    else:
        amount = IRMember(IRIdentifier("cfg"), "count")
        expr = IRBinary("/", IRUnary("-", amount), IRQuantity(2, None))
        bindings = {"cfg": IRRecord({"count": IRQuantity(100, "cells")})}
        if representation == "serialized":
            serializer = PlanExpressionSerializer()
            expr = serializer.serialize_expr(expr)
            bindings = {key: serializer.serialize_expr(value) for key, value in bindings.items()}
    assert quantity_expression_unit(expr, bindings) == "cells"



def test_unit_inference_helper_distinguishes_unitless_and_unknown_operands():
    from culsma.pipeline.expression_resolution import infer_quantity_unit, UNKNOWN_UNIT
    from culsma.pipeline.ir_nodes import IRBinary
    assert infer_quantity_unit(IRQuantity(2, None), {}) is None
    assert infer_quantity_unit(IRQuantity(10, "cells"), {}) == "cells"
    expr = IRBinary("*", IRIdentifier("runtime_count"), IRQuantity(2, None))
    assert infer_quantity_unit(expr, {}) is UNKNOWN_UNIT
    assert infer_quantity_unit(expr, {"runtime_count": IRQuantity(10, "cells")}) == "cells"
