"""Non-fractionating centrifuge handling through the agitation operator."""

from pathlib import Path

import pytest

from culsma.cli import execute_pipeline
from culsma.driver.human import HumanDriver
from culsma.driver.robot import RobotDriver
from culsma.frontend.resolver import resolve_program
from culsma.parser.parser import parse
from culsma.pipeline.compile import compile_ast
from culsma.pipeline.plan import lower_ir_to_plan
from culsma.pipeline.typecheck import typecheck
from culsma.pipeline.validate import validate
from culsma.runtime.executor import run


CENTRIFUGE = (
    "agit(sample = dna_tube, mode = AgitationMode.CENTRIFUGE, "
    "drive = 3000g, duration = 5s);"
)


def test_centrifuge_allows_later_whole_container_material_replacement(tmp_path: Path):
    source = tmp_path / "centrifuge_replace.culs"
    source.write_text(
        f'''let dna_tube = tube(label = "DNAInput", capacity = 200uL, load = [
  content(kind = ContentKind.BIO_MOLECULE_OR_VIRUS, type = ContentType.DNA, code = "DNA_SAMPLE"):50uL
]);
{CENTRIFUGE}
with env(thermal = 22C, duration = 5min) {{ hold(sample = dna_tube); }}
dna_tube.materials.replace({{dna_tube.materials[0]: [
  content(kind = ContentKind.BIO_MOLECULE_OR_VIRUS, type = ContentType.DNA, code = "ROUND1_BOUND_FRAGMENT"):unknown(dimension = mass),
  content(kind = ContentKind.BIO_MOLECULE_OR_VIRUS, type = ContentType.DNA, code = "ROUND1_FREE_FRAGMENT"):unknown(dimension = mass),
  content(kind = ContentKind.FORMULATION, type = ContentType.BUFFER, code = "DNA_INPUT_CARRIER"):50uL
]}});
return dna_tube;
''',
        encoding="utf-8",
    )

    bundle = execute_pipeline([source])

    assert bundle["run"]["ok"], bundle["run"]["diagnostics"]
    material = bundle["run"]["state"]["artifacts"]["material_state"]
    container_id, container = next(iter(material["containers"].items()))
    assert container["metadata"]["label"] == "DNAInput"
    assert container["volume_uL"] == 50.0
    assert container_id not in material.get("contents_states", {})
    assert {entry["content_ref"] for entry in container["component_entries"]} == {
        "ROUND1_BOUND_FRAGMENT", "ROUND1_FREE_FRAGMENT", "DNA_INPUT_CARRIER"
    }
    spin_events = [
        event for event in bundle["run"]["events"]
        if event["kind"] == "STEP_COMPLETED" and event["payload"].get("driver_payload", {}).get("op") == "agit"
    ]
    assert len(spin_events) == 1
    assert spin_events[0]["payload"]["material_delta"]["contents_state_impact"]["action"] == "none"


def test_true_standalone_separation_still_blocks_whole_container_replacement(tmp_path: Path):
    source = tmp_path / "separation_replace.culs"
    source.write_text('''let sample = tube(label = "Sample", capacity = 100uL, load = [
  content(kind = ContentKind.FORMULATION, type = ContentType.BUFFER, code = "BUFFER"):50uL
]);
sep(sample = sample, program = centrifuge_program(drive = 3000g));
sample.materials.replace({sample.materials[0]: [
  content(kind = ContentKind.FORMULATION, type = ContentType.BUFFER, code = "NEW_BUFFER"):50uL
]});
return sample;
''', encoding="utf-8")

    bundle = execute_pipeline([source])

    assert not bundle["run"]["ok"]
    assert "MAT_MATERIAL_REPLACE_ACTIVE_PARTS" in {
        diagnostic["code"] for diagnostic in bundle["run"]["diagnostics"]
    }


@pytest.mark.parametrize(
    ("arguments", "expected_code"),
    [
        ("mode=centrifuge,duration=5s", "SEM_MISSING_REQUIRED_ARG"),
        ("mode=centrifuge,drive=3000g", "SEM_AGIT_DURATION_REQUIRED"),
        ("mode=centrifuge,program=centrifuge_program(drive=3000g),duration=5s", "SEM_UNKNOWN_ARG"),
        ("mode=centrifuge,drive=3000g,duration=5s,motion=orbital", "SEM_AGIT_ARG_CONFLICT"),
        ("mode=shake,drive=3000g,duration=5s", "SEM_AGIT_ARG_CONFLICT"),
        ("mode=centrifuge,drive=3000g,duration=0s", "SEM_AGIT_QUANTITY_INVALID"),
        ("mode=centrifuge,drive=3min,duration=5s", "SEM_AGIT_QUANTITY_INVALID"),
        ("mode=centrifuge,drive=3mg,duration=5s", "SEM_AGIT_QUANTITY_INVALID"),
    ],
)
def test_centrifuge_rejects_invalid_drive_and_duration(arguments: str, expected_code: str):
    compiled = compile_ast(resolve_program(parse(
        f'protocol T {{ let s=tube(label="S"); agit(sample=s,{arguments}); }}'
    )).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    typed = typecheck(compiled.ir, analysis=compiled.analysis)
    codes = {diagnostic.code for diagnostic in [*semantic.diagnostics, *typed.diagnostics]}
    assert expected_code in codes


def test_shake_motion_still_reports_a_conflicting_centrifuge_drive():
    compiled = compile_ast(resolve_program(parse(
        'protocol T { let s=tube(label="S"); agit(sample=s,mode=shake,motion=rock,duration=5s,drive=3000g); }'
    )).prepared_program)
    semantic = validate(compiled.ir, analysis=compiled.analysis)
    assert any(
        diagnostic.code == 'SEM_AGIT_ARG_CONFLICT'
        and diagnostic.message == 'drive is only allowed with mode=centrifuge'
        for diagnostic in semantic.diagnostics
    )


def test_centrifuge_driver_projection_identifies_nonseparating_centrifuge_action():
    compiled = compile_ast(resolve_program(parse(
        f'protocol T {{ let dna_tube=tube(label="DNAInput"); {CENTRIFUGE} }}'
    )).prepared_program)
    plan = lower_ir_to_plan(compiled.ir, analysis=compiled.analysis)
    assert not plan.diagnostics

    human = run(plan=plan, driver=HumanDriver())
    robot = run(plan=plan, driver=RobotDriver())
    assert human.ok and robot.ok
    human_spin = next(event for event in human.events if event.kind == "STEP_COMPLETED" and event.payload["driver_payload"].get("op") == "agit")
    robot_spin = next(event for event in robot.events if event.kind == "STEP_COMPLETED" and event.payload["driver_payload"].get("op") == "agit")
    assert human_spin.payload["driver_payload"]["instruction"]["title"] == "Centrifuge Step"
    assert human_spin.payload["driver_payload"]["instruction_packet"]["section"]["title"] == "Material Handling"
    assert robot_spin.payload["driver_payload"]["binding"]["action"] == "device.centrifuge.run"
