from __future__ import annotations

import pytest

from culsma.driver.stub import StubDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run
from culsma.scientific_model.material import (
    AUTHOR_SETTABLE_MATERIAL_RELATIONS,
    COMPONENT_BOUND_MATERIAL_RELATIONS,
    MaterialRelation,
)


def _source(
    *,
    state: str = "adherent",
    material_index: str = "0",
    output: str = "retentate",
    to: str = "free",
    associated_with: str | None = None,
    program: str = (
        "filtration_program(membrane = adherent_cell_surface, drive = aspiration)"
    ),
) -> str:
    association_arg = (
        f",\n        associated_with = source.materials[{associated_with}]"
        if associated_with is not None
        else ""
    )
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
        to = {to}{association_arg}
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


@pytest.mark.parametrize(
    "target_relation",
    [
        MaterialRelation.CONTAINER_SURFACE,
        MaterialRelation.PELLET,
        MaterialRelation.PRECIPITATE,
        MaterialRelation.DISRUPTED,
        MaterialRelation.FIELD_RETAINED,
    ],
)
def test_runtime_applies_each_container_associated_target_relation(
    target_relation: MaterialRelation,
) -> None:
    result = run(
        plan=_plan(_source(to=target_relation.value)),
        driver=StubDriver(),
    )

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material_state = result.state.artifacts["material_state"]
    retained_id = material_state["indexed_bindings"]["result"]["1"]
    retained = material_state["containers"][retained_id]["component_entries"]
    assert retained[0]["relation"] == target_relation.value
    assert retained[0]["associated_with"] == retained_id
    assert retained[0]["association_target_kind"] == "container"
    assert retained[0]["relationship_source"] == "author_transition"


def test_pm99_runtime_releases_bead_bound_target_into_flowthrough() -> None:
    source = '''protocol T {
  let source = tube(
    label = "IP beads",
    load = [
      content(
        kind = particulate,
        type = beads,
        code = "PROTEIN_G_MAGNETIC_BEADS",
        attrs = { bead_property: magnetic }
      ):10mg,
      content(
        kind = bio_molecule_or_virus,
        type = protein,
        code = "GFP_TARGET_PROTEIN"
      ):1ug,
      content(
        kind = formulation,
        type = buffer,
        code = "LYSATE_BUFFER"
      ):100uL
    ]
  );
  let captured = sep(
    sample = source,
    program = magnetic_program(duration = 2min),
    component_fates = {
      PROTEIN_G_MAGNETIC_BEADS: { bound: 100%, flowthrough: 0% },
      GFP_TARGET_PROTEIN: { bound: 100%, flowthrough: 0% },
      LYSATE_BUFFER: { bound: 0%, flowthrough: 100% }
    }
  );
  let bead_fraction = captured[0];
  let released = sep(
    sample = bead_fraction,
    program = magnetic_program(duration = 2min),
    component_fates = {
      PROTEIN_G_MAGNETIC_BEADS: { bound: 100%, flowthrough: 0% },
      GFP_TARGET_PROTEIN: { bound: 0%, flowthrough: 100% }
    },
    transitions = [
      transition(
        subject = bead_fraction.materials[1],
        output = flowthrough,
        to = free
      )
    ]
  );
}'''

    result = run(plan=_plan(source), driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material_state = result.state.artifacts["material_state"]
    released_id = material_state["indexed_bindings"]["released"]["1"]
    released_entries = material_state["containers"][released_id]["component_entries"]
    target = next(
        entry
        for entry in released_entries
        if entry["content_ref"] == "GFP_TARGET_PROTEIN"
    )
    assert target["amount"] == 0.001
    assert target["quantity"] == {
        "dimension": "mass",
        "unit": "mg",
        "value": 0.001,
    }
    assert target["relation"] == "free"
    assert target["associated_with"] is None
    assert target["association_target_kind"] is None
    assert target["relationship_source"] == "author_transition"


@pytest.mark.parametrize(
    "target_relation",
    [
        MaterialRelation.BEAD_BOUND,
        MaterialRelation.MEMBRANE_BOUND,
        MaterialRelation.CELL_BOUND,
    ],
)
def test_runtime_applies_each_component_bound_target_with_typed_material_selector(
    target_relation: MaterialRelation,
) -> None:
    source = '''protocol T {
  let source = tube(
    label = "Binding",
    load = [
      content(
        kind = particulate,
        type = beads,
        code = "MAGNETIC_BEADS",
        attrs = { bead_property: magnetic }
      ):10mg,
      content(
        kind = bio_molecule_or_virus,
        type = protein,
        code = "TARGET_PROTEIN"
      ):1ug
    ]
  );
  let captured = sep(
    sample = source,
    program = magnetic_program(duration = 2min),
    component_fates = {
      MAGNETIC_BEADS: { bound: 100%, flowthrough: 0% },
      TARGET_PROTEIN: { bound: 100%, flowthrough: 0% }
    },
    transitions = [
      transition(
        subject = source.materials[1],
        output = bound,
        to = TARGET_RELATION,
        associated_with = source.materials[0]
      )
    ]
  );
}'''.replace("TARGET_RELATION", target_relation.value)

    result = run(plan=_plan(source), driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material_state = result.state.artifacts["material_state"]
    bound_id = material_state["indexed_bindings"]["captured"]["0"]
    entries = material_state["containers"][bound_id]["component_entries"]
    beads = next(entry for entry in entries if entry["content_ref"] == "MAGNETIC_BEADS")
    target = next(entry for entry in entries if entry["content_ref"] == "TARGET_PROTEIN")
    assert target["relation"] == target_relation.value
    assert target["associated_with"] == beads["entry_id"]
    assert target["association_target_kind"] == "component_entry"
    assert target["relationship_source"] == "author_transition"


def test_runtime_applies_multiple_different_transitions_in_one_separation() -> None:
    source = '''protocol T {
  let source = tube(
    label = "Mixed material",
    load = [
      content(
        kind = bio_cellular,
        type = cell_line,
        code = "RPE1",
        attrs = { state: adherent }
      ):100000cells,
      content(
        kind = bio_molecule_or_virus,
        type = protein,
        code = "BSA"
      ):1mg
    ]
  );
  let result = sep(
    sample = source,
    program = filtration_program(
      membrane = adherent_cell_surface,
      drive = aspiration
    ),
    component_fates = {
      RPE1: { filtrate: 0%, retentate: 100% },
      BSA: { filtrate: 0%, retentate: 100% }
    },
    transitions = [
      transition(
        subject = source.materials[0],
        output = retentate,
        to = free
      ),
      transition(
        subject = source.materials[1],
        output = retentate,
        to = precipitate
      )
    ]
  );
}'''

    result = run(plan=_plan(source), driver=StubDriver())

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material_state = result.state.artifacts["material_state"]
    retentate_id = material_state["indexed_bindings"]["result"]["1"]
    entries = material_state["containers"][retentate_id]["component_entries"]
    by_content = {entry["content_ref"]: entry for entry in entries}
    assert by_content["RPE1"]["relation"] == "free"
    assert by_content["RPE1"]["associated_with"] is None
    assert by_content["BSA"]["relation"] == "precipitate"
    assert by_content["BSA"]["associated_with"] == retentate_id
    assert all(
        entry["relationship_source"] == "author_transition"
        for entry in by_content.values()
    )


def test_runtime_rejects_component_association_target_absent_from_selected_output() -> None:
    source = '''protocol T {
  let source = tube(
    label = "Binding",
    load = [
      content(
        kind = particulate,
        type = beads,
        code = "MAGNETIC_BEADS",
        attrs = { bead_property: magnetic }
      ):10mg,
      content(
        kind = bio_molecule_or_virus,
        type = protein,
        code = "TARGET_PROTEIN"
      ):1ug
    ]
  );
  let captured = sep(
    sample = source,
    program = magnetic_program(duration = 2min),
    component_fates = {
      MAGNETIC_BEADS: { bound: 0%, flowthrough: 100% },
      TARGET_PROTEIN: { bound: 100%, flowthrough: 0% }
    },
    transitions = [
      transition(
        subject = source.materials[1],
        output = bound,
        to = bead_bound,
        associated_with = source.materials[0]
      )
    ]
  );
}'''

    result = run(plan=_plan(source), driver=StubDriver())

    assert not result.ok
    assert "MAT_MATERIAL_TRANSITION_ASSOCIATION_OUTPUT_EMPTY" in {
        diagnostic.code for diagnostic in result.diagnostics
    }


def test_runtime_accepts_free_to_free_without_a_pair_whitelist() -> None:
    result = run(
        plan=_plan(_source(state="suspension", output="filtrate")),
        driver=StubDriver(),
    )

    assert result.ok, [diagnostic.to_dict() for diagnostic in result.diagnostics]
    material_state = result.state.artifacts["material_state"]
    filtrate_id = material_state["indexed_bindings"]["result"]["0"]
    entries = material_state["containers"][filtrate_id]["component_entries"]
    assert entries[0]["relation"] == "free"
    assert entries[0]["amount"] == 100000.0
    assert entries[0]["relationship_source"] == "author_transition"


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


def test_frontend_accepts_every_author_settable_relation_enum() -> None:
    for relation in AUTHOR_SETTABLE_MATERIAL_RELATIONS:
        associated_with = (
            "0" if relation in COMPONENT_BOUND_MATERIAL_RELATIONS else None
        )
        _, semantic = _compile(
            _source(
                to=relation.value,
                associated_with=associated_with,
            )
        )
        assert semantic.ok, (
            relation,
            [diagnostic.to_dict() for diagnostic in semantic.diagnostics],
        )


def test_frontend_rejects_unknown_and_internal_relation_identifiers() -> None:
    _, unknown = _compile(_source(to="custom_state"))
    _, unresolved = _compile(_source(to=MaterialRelation.UNRESOLVED.value))

    assert "SEM_MATERIAL_TRANSITION_TARGET_INVALID" in {
        diagnostic.code for diagnostic in unknown.diagnostics
    }
    assert "SEM_MATERIAL_TRANSITION_TARGET_INVALID" in {
        diagnostic.code for diagnostic in unresolved.diagnostics
    }


@pytest.mark.parametrize(
    "target_relation",
    [
        MaterialRelation.BEAD_BOUND,
        MaterialRelation.MEMBRANE_BOUND,
        MaterialRelation.CELL_BOUND,
    ],
)
def test_frontend_requires_association_for_each_component_bound_target(
    target_relation: MaterialRelation,
) -> None:
    _, semantic = _compile(_source(to=target_relation.value))

    assert "SEM_MATERIAL_TRANSITION_ASSOCIATION_REQUIRED" in {
        diagnostic.code for diagnostic in semantic.diagnostics
    }


@pytest.mark.parametrize(
    "target_relation",
    [
        MaterialRelation.FREE,
        MaterialRelation.PELLET,
        MaterialRelation.PRECIPITATE,
    ],
)
def test_frontend_forbids_component_association_for_non_bound_targets(
    target_relation: MaterialRelation,
) -> None:
    _, semantic = _compile(
        _source(to=target_relation.value, associated_with="0")
    )

    assert "SEM_MATERIAL_TRANSITION_ASSOCIATION_FORBIDDEN" in {
        diagnostic.code for diagnostic in semantic.diagnostics
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
