"""Pipeline fixtures for the environment module's conformance tests."""
import pytest

from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate


@pytest.fixture
def compile_source():
    return lambda source: compile_ast(resolve_program(parse(source)).prepared_program)


@pytest.fixture
def env_source():
    return lambda args, body="hold(sample);": (
        'protocol T { let sample = tube(label="Sample"); '
        f'with env({args}) {{ {body} }} }}')


@pytest.fixture
def build_plan(compile_source):
    def build(source):
        compiled = compile_source(source)
        for check in (validate, typecheck):
            result = check(compiled.ir, analysis=compiled.analysis)
            assert result.ok, result.diagnostics
        plan = lower_ir_to_plan(compiled.ir, analysis=compiled.analysis)
        assert not plan.diagnostics, plan.diagnostics
        return plan
    return build
