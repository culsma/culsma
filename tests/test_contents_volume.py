"""Current container contents volume is a typed, read-only source quantity."""

import pytest

from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run


BUFFER = 'content(kind=ContentKind.FORMULATION,type=ContentType.BUFFER,code="B")'


def compile_source(source):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    typed = typecheck(semantic.ir, analysis=compiled.analysis)
    plan = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
    return semantic, typed, plan


class RecordingDriver(StubDriver):
    def __init__(self):
        super().__init__()
        self.mutations = []

    def execute(self, step):
        if step.op == "Mutation":
            self.mutations.append(step)
        return super().execute(step)


def test_contents_volume_reads_current_amount_after_transfer_and_in_repeat():
    source = f'''protocol T {{
        let sample = tube(label="Sample", capacity=500uL, load=[{BUFFER}:110uL]);
        let extra = tube(label="Extra", capacity=100uL, load=[{BUFFER}:20uL]);
        sample << [extra:20uL];
        repeat pipette_mix in schedule(start=1, end=10, step=1) {{
            sample << [sample:sample.contents.volume * 0.6];
        }}
    }}'''
    semantic, typed, plan = compile_source(source)
    assert semantic.ok and typed.ok and not plan.diagnostics

    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    assert len(driver.mutations) == 11
    assert [step.args["sources"][0]["right"]["value"] for step in driver.mutations[1:]] == [78.0] * 10
    assert all(step.args["sources"][0]["right"]["unit"] == "uL" for step in driver.mutations[1:])
    sample = next(container for container in result.state.artifacts["material_state"]["containers"].values()
                  if container["metadata"].get("label") == "Sample")
    assert sample["volume_uL"] == pytest.approx(130.0)


def test_contents_volume_re_evaluates_but_let_captures_its_read():
    source = f'''protocol T {{
        let sample = tube(capacity=500uL, load=[{BUFFER}:110uL]);
        let extra = tube(load=[{BUFFER}:20uL]);
        let initial_stroke = sample.contents.volume * 0.6;
        sample << [extra:20uL];
        sample << [sample:initial_stroke];
        sample << [sample:sample.contents.volume * 0.6];
    }}'''
    semantic, typed, plan = compile_source(source)
    assert semantic.ok and typed.ok and not plan.diagnostics
    driver = RecordingDriver()
    result = run(plan=plan, driver=driver)
    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    assert [step.args["sources"][0]["right"]["value"] for step in driver.mutations] == [20.0, 66.0, 78.0]


def test_contents_volume_is_read_only_and_other_nested_members_remain_invalid():
    source = f'''protocol T {{
        let sample = tube(capacity=500uL, load=[{BUFFER}:110uL]);
        let wrong = sample.contents.mass;
    }}'''
    semantic, _, _ = compile_source(source)
    assert "SEM_CONTAINER_TARGET_VIEW_INVALID" in {d.code for d in semantic.diagnostics}

    source = f'''protocol T {{
        let sample = tube(capacity=500uL, load=[{BUFFER}:110uL]);
        sample.contents.volume = 50uL;
    }}'''
    _, typed, _ = compile_source(source)
    assert "TYPE_MEMBER_ASSIGN_TARGET_FORBIDDEN" in {d.code for d in typed.diagnostics}


def test_record_contents_volume_keeps_ordinary_record_projection():
    source = '''protocol T {
        let record = {contents: {volume: 5uL}};
        let target = tube(label="Target", capacity=100uL);
        let source = tube(label="Source", load=[content(kind=ContentKind.FORMULATION,type=ContentType.BUFFER,code="B"):10uL]);
        target << [source:record.contents.volume];
    }'''
    semantic, typed, plan = compile_source(source)
    assert semantic.ok and typed.ok and not plan.diagnostics
    result = run(plan=plan, driver=StubDriver())
    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    target = next(container for container in result.state.artifacts["material_state"]["containers"].values()
                  if container["metadata"].get("label") == "Target")
    assert target["volume_uL"] == pytest.approx(5.0)
