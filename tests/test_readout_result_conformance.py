"""Readout result contracts hold from source through driver payload recording."""

import pytest

from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run


CASES = [
    ('img', 'uv_absorbance', {'signal', 'channel'}),
    ('img', 'fluorescence', {'signal', 'channel'}),
    ('img', 'colorimetric', {'signal', 'channel'}),
    ('ecp', 'ph', {'ph'}),
    ('ecp', 'conductivity', {'conductivity'}),
    ('ecp', 'dissolved_oxygen', {'dissolved_oxygen'}),
    ('ecp', 'orp', {'orp'}),
    ('phy', 'temperature', {'temperature'}),
    ('phy', 'pressure', {'pressure'}),
    ('phy', 'flow_rate', {'flow_rate'}),
    ('phy', 'mass', {'mass'}),
    ('phy', 'volume', {'volume'}),
    ('phy', 'humidity', {'humidity'}),
    ('phy', 'current', {'current'}),
    ('phy', 'customized', set()),
]


def execute(family, quantity, *, save_raw, payload):
    source = f'''protocol Read {{
      let sample = tube(label="Sample");
      let schema = data_schema(label="Readout", fields=[quality]);
      let obs = {family}(sample=sample, quantity={quantity}, schema_ref=schema,
                        save_raw={'true' if save_raw else 'false'});
    }}'''
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis, enforce_binding=True)
    assert semantic.ok, [d.to_dict() for d in semantic.diagnostics]
    typed = typecheck(semantic.ir, analysis=compiled.analysis)
    assert typed.ok, [d.to_dict() for d in typed.diagnostics]
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
    assert not plan.diagnostics, [d.to_dict() for d in plan.diagnostics]
    result = run(plan, StubDriver(op_payloads={family: {'result': payload}}))
    assert result.ok, [d.to_dict() for d in result.diagnostics]
    return result


@pytest.mark.parametrize('family,quantity,fields', CASES, ids=[f'{f}-{q}' for f, q, _ in CASES])
@pytest.mark.parametrize('save_raw', [False, True])
def test_readout_fields_and_raw_exports_follow_the_declared_contract(family, quantity, fields, save_raw):
    payload = {field: 12.5 for field in fields}
    payload.update(quality='accepted', undeclared='ignored')
    result = execute(family, quantity, save_raw=save_raw, payload=payload)
    artifacts = result.state.artifacts
    data_id = artifacts['data_bindings']['obs']
    record = artifacts['data_objects'][data_id]
    assert record['family'] == family
    assert record['contract_kind'] == quantity
    assert record['result'] == {**{field: 12.5 for field in fields}, 'quality': 'accepted'}
    assert record['driver_payload']['result']['undeclared'] == 'ignored'
    assert record['resolved_sample']
    export = artifacts['data_exports'][data_id]['driver_profile']
    assert export['profile'] == 'driver:DRV_OK'
    assert export['kind'] == family
    if save_raw:
        raw = artifacts['raw_data'][data_id]
        assert record['raw_artifact'] == raw
        assert export['artifact_id'] == raw['artifact_id']
    else:
        assert 'raw_artifact' not in record
        assert 'artifact_id' not in export
        assert data_id not in artifacts.get('raw_data', {})


@pytest.mark.parametrize('payload', [None, [], 'malformed', 42])
def test_non_record_driver_result_leaves_declared_fields_unresolved(payload):
    result = execute('ecp', 'ph', save_raw=False, payload=payload)
    artifacts = result.state.artifacts
    record = artifacts['data_objects'][artifacts['data_bindings']['obs']]
    assert record['result'] == {'ph': None, 'quality': None}
