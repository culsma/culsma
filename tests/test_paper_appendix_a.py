from __future__ import annotations

from pathlib import Path

import pytest

from culsma.frontend.resolver import resolve_program
from culsma.pipeline.analysis import build_compile_analysis
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.parser.parser import parse_file


ROOT = Path(__file__).resolve().parents[1]
APPENDIX_A_FIXTURES = ROOT / "tests" / "fixtures_paper" / "appendix_a"


APPENDIX_A_CASES = (
    "marker_panel.culs",
    "density_fraction.culs",
)


@pytest.mark.parametrize("fixture_name", APPENDIX_A_CASES)
def test_appendix_a_fixture_lowers_to_plan(fixture_name: str) -> None:
    ast = parse_file(APPENDIX_A_FIXTURES / fixture_name)
    compiled = compile_ast(resolve_program(ast).prepared_program)

    validation = validate(compiled.ir, analysis=build_compile_analysis(compiled.ir))
    assert validation.ok, [diagnostic.to_dict() for diagnostic in validation.diagnostics]

    checked = typecheck(validation.ir)
    assert checked.ok, [diagnostic.to_dict() for diagnostic in checked.diagnostics]

    plan = lower_ir_to_plan(checked.ir)
    assert not plan.diagnostics, [diagnostic.to_dict() for diagnostic in plan.diagnostics]
    assert plan.plans
