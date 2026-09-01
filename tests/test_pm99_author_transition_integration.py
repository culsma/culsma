from __future__ import annotations

from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run


def _source(
    *,
    state: str = "adherent",
    material_index: str = "0",
    output: str = "retentate",
    to: str = "free",
    program: str = (
        "filtration_program(membrane = adherent_cell_surface, drive = aspiration)"
    ),
) -> str:
    return f'''protocol T {{
  let source = tube(
    label = "Source",
    load = [
      content(
        kind = bio_cellular,
        type = cell_line,
        code = "RPE1",
        attrs = {{ state: {state} }}
      ):100000cells
    ]
  );
  let result = sep(
    sample = source,
    program = {program},
    transitions = [
      transition(
        subject = source.materials[{material_index}],
        output = {output},
        to = {to}
      )
    ]
  );
}}'''


def _compile(source: str):
    compiled = compile_ast(resolve_program(parse(source)).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    return compiled, semantic


def _plan(source: str):
    compiled, semantic = _compile(source)
    assert semantic.ok, [diagnostic.to_dict() for diagnostic in semantic.diagnostics]
    typed = typecheck(semantic.ir, analysis=compiled.analysis)
    assert typed.ok, [diagnostic.to_dict() for diagnostic in typed.diagnostics]
    planned = lower_ir_to_plan(typed.ir, analysis=compiled.analysis)
    assert not planned.diagnostics
    return planned


def test_frontend_lowers_inline_content_load_and_materials_index_selector() -> None:
    plan = _plan(_source())
    steps = plan.plans[0].steps

    assert [step.op for step in steps] == [
        "AllocContainer",
        "DefineContent",
        "LoadContent",
        "FinalizeContainerContents",
        "sep",
    ]
    assert steps[2].args["content"]["value"] == "RPE1"
    transition = steps[-1].args["transitions"]["elements"][0]
    assert transition["name"] == "transition"
    subject = next(
        arg["value"]
        for arg in transition["args"]
        if arg["name"] == "subject"
    )
    assert subject["kind"] == "IRIndex"
    assert subject["base"]["member"] == "materials"
    assert subject["index"]["value"] == 0.0


def test_runtime_applies_container_surface_to_free_author_transition() -> None:
    result = run(plan=_plan(_source()), driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material_state = result.state.artifacts["material_state"]
    retained_id = material_state["indexed_bindings"]["result"]["1"]
    retained = material_state["containers"][retained_id]["component_entries"]
    assert len(retained) == 1
    assert retained[0]["content_ref"] == "RPE1"
    assert retained[0]["amount"] == 100000.0
    assert retained[0]["relation"] == "free"
    assert retained[0]["associated_with"] is None
    assert retained[0]["association_target_kind"] is None
    assert retained[0]["preservation"] is None
    assert retained[0]["relationship_source"] == "author_transition"


def test_runtime_rejects_transition_when_current_relation_is_not_container_surface() -> None:
    result = run(plan=_plan(_source(state="suspension")), driver=StubDriver())

    assert not result.ok
    assert "MAT_AUTHOR_TRANSITION_NOT_ALLOWED" in {
        diagnostic.code for diagnostic in result.diagnostics
    }
    material_state = result.state.artifacts["material_state"]
    source_id = material_state["bindings"]["source"]
    entries = material_state["containers"][source_id]["component_entries"]
    assert entries[0]["relation"] == "free"
    assert entries[0]["amount"] == 100000.0


def test_author_transition_runs_after_provider_resolves_separation_fate() -> None:
    result = run(plan=_plan(_source()), driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material_state = result.state.artifacts["material_state"]
    retained_id = material_state["indexed_bindings"]["result"]["1"]
    retained = material_state["containers"][retained_id]["component_entries"]
    assert retained[0]["amount"] == 100000.0
    assert retained[0]["relation"] == "free"
    assert retained[0]["relationship_source"] == "author_transition"


def test_author_transition_selects_cells_from_mixed_tube_materials() -> None:
    source = '''protocol T {
  let source = tube(
    label = "Source",
    load = [
      content(
        kind = formulation,
        type = medium,
        code = "DMEM"
      ):300uL,
      content(
        kind = bio_cellular,
        type = cell_line,
        code = "RPE1",
        attrs = { state: adherent }
      ):100000cells
    ]
  );
  let result = sep(
    sample = source,
    program = filtration_program(
      membrane = adherent_cell_surface,
      drive = aspiration
    ),
    transitions = [
      transition(
        subject = source.materials[1],
        output = retentate,
        to = free
      )
    ]
  );
}'''

    result = run(plan=_plan(source), driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material_state = result.state.artifacts["material_state"]
    slots = material_state["indexed_bindings"]["result"]
    filtrate = material_state["containers"][slots["0"]]["component_entries"]
    retentate = material_state["containers"][slots["1"]]["component_entries"]
    live_filtrate = [entry for entry in filtrate if entry["amount"] > 0]
    live_retentate = [entry for entry in retentate if entry["amount"] > 0]
    assert [(entry["content_ref"], entry["amount"]) for entry in live_filtrate] == [
        ("DMEM", 300.0)
    ]
    assert len(live_retentate) == 1
    assert live_retentate[0]["content_ref"] == "RPE1"
    assert live_retentate[0]["relation"] == "free"
    assert live_retentate[0]["relationship_source"] == "author_transition"


def test_runtime_rejects_author_transition_for_zero_quantity_output() -> None:
    result = run(
        plan=_plan(_source(output="filtrate")),
        driver=StubDriver(),
    )

    assert not result.ok
    assert "MAT_MATERIAL_TRANSITION_OUTPUT_EMPTY" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_frontend_rejects_free_text_relation_and_unknown_output() -> None:
    _, text_relation = _compile(_source(to='"free"'))
    _, unknown_output = _compile(_source(output="unknown_fraction"))

    assert "SEM_MATERIAL_TRANSITION_TARGET_INVALID" in {
        diagnostic.code for diagnostic in text_relation.diagnostics
    }
    assert "SEM_MATERIAL_TRANSITION_OUTPUT_INVALID" in {
        diagnostic.code for diagnostic in unknown_output.diagnostics
    }


def test_frontend_rejects_dynamic_and_negative_material_indices() -> None:
    _, dynamic_semantic = _compile(_source(material_index="source"))
    _, negative_semantic = _compile(_source(material_index="-1"))

    assert "SEM_MATERIAL_INDEX_NOT_STATIC_INTEGER" in {
        diagnostic.code for diagnostic in dynamic_semantic.diagnostics
    }
    assert "SEM_MATERIAL_INDEX_NOT_NONNEGATIVE_INTEGER" in {
        diagnostic.code for diagnostic in negative_semantic.diagnostics
    }


def test_runtime_rejects_material_index_out_of_range() -> None:
    result = run(plan=_plan(_source(material_index="1")), driver=StubDriver())

    assert not result.ok
    assert "MAT_MATERIAL_INDEX_OUT_OF_RANGE" in {
        diagnostic.code for diagnostic in result.diagnostics
    }
