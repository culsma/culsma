from __future__ import annotations

import ast
from pathlib import Path

from culsma.pipeline.plan_nodes import PlanStep
from culsma.pipeline.program_registry import SEPARATION_SLOT_CONTRACTS
from culsma.runtime.material.compute import MaterialCompute
from culsma.runtime.material.contents_state import (
    ContentsPartitionTransition,
    ContentsPartSelection,
    MaterialIndexedPartsStateManager,
)
from culsma.runtime.material.result import MaterialUpdateResult
from culsma.runtime.material.state import MaterialStateChangePlan, MaterialStateManager
from culsma.runtime.material.separation import separation_slot_contract


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MATERIAL_DIR = PROJECT_ROOT / "src" / "culsma" / "runtime" / "material"
SCIENTIFIC_MODEL_DIR = PROJECT_ROOT / "src" / "culsma" / "scientific_model"


def _material_modules() -> list[Path]:
    return sorted(path for path in MATERIAL_DIR.glob("*.py") if path.name != "__init__.py")


def _contents_ref(name: str = "tube", slot: int = 1) -> dict[str, object]:
    return {
        "kind": "IRIndex",
        "base": {
            "kind": "IRMember",
            "base": {"kind": "IRIdentifier", "name": name, "span": None},
            "member": "contents",
            "span": None,
        },
        "index": {"kind": "IRQuantity", "value": float(slot), "unit": None, "span": None},
        "span": None,
    }


def _step(*, field: str | None = None) -> PlanStep:
    gate = {"env": {"field": field}} if field is not None else None
    return PlanStep(step_id="p0.s1", op="Mutation", args={}, deps=[], gate=gate, span=None)


def _material_step(op: str, *, step_id: str = "p0.s1") -> PlanStep:
    return PlanStep(step_id=step_id, op=op, args={}, deps=[], gate=None, span=None)


def test_pipeline_and_runtime_share_separation_output_meanings() -> None:
    assert {
        program_kind: separation_slot_contract(program_kind)
        for program_kind in SEPARATION_SLOT_CONTRACTS
    } == SEPARATION_SLOT_CONTRACTS


def test_material_compute_rejects_quantity_change_without_movement_contract():
    class MissingMovementManager:
        def plan_material_state_change(self, *, step, state):
            return object()

        def apply_change(self, change_plan, state):
            state["containers"]["A"]["volume_uL"] -= 10.0
            state["containers"]["B"]["volume_uL"] += 10.0
            return MaterialUpdateResult(
                material_state=state,
                delta={
                    "op": "FutureTransfer",
                    "source": "A",
                    "destination": "B",
                    "moved_uL": 10.0,
                },
            )

    result = MaterialCompute(state_manager=MissingMovementManager()).apply_step(
        _material_step("FutureTransfer"),
        {
            "containers": {
                "A": {"volume_uL": 100.0, "mass_mg": 0.0},
                "B": {"volume_uL": 0.0, "mass_mg": 0.0},
            }
        },
    )

    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == [
        "MAT_MOVEMENT_CONTRACT_MISSING"
    ]


def _partitioned_state(*, valid: bool = True, preservation_contract: bool = False) -> dict[str, object]:
    record = {
        "kind": "partitioned",
        "producer_op": "sep",
        "program_kind": "magnetic_program",
        "source": "Tube",
        "slot_contract": {"0": "retained", "1": "flowthrough"},
        "parts": {
            "0": {
                "volume_uL": 40.0,
                "mass_mg": 40.0,
                "components": {"beads": 20.0},
                "metadata": {},
            },
            "1": {
                "volume_uL": 160.0,
                "mass_mg": 160.0,
                "components": {"buffer": 160.0},
                "metadata": {},
            },
        },
        "valid": valid,
        "step_id": "p0.s0",
    }
    if preservation_contract:
        record["preservation_contract"] = {
            "kind": "field_retention",
            "field": "magnetic_rack",
            "retained_slot": "0",
            "default_incoming_slot": "1",
        }
    return {
        "bindings": {"tube": "Tube"},
        "containers": {
            "Tube": {
                "volume_uL": 200.0,
                "mass_mg": 200.0,
                "components": {"beads": 20.0, "buffer": 180.0},
                "metadata": {},
            }
        },
        "contents_states": {
            "Tube": record,
        },
    }


def test_material_support_module_removed() -> None:
    assert not (MATERIAL_DIR / "support.py").exists()


def test_material_modules_do_not_import_removed_support_module() -> None:
    offenders: list[str] = []
    for path in _material_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "culsma.runtime.material.support":
                offenders.append(path.name)
            elif isinstance(node, ast.Import):
                offenders.extend(alias.name for alias in node.names if alias.name == "culsma.runtime.material.support")

    assert offenders == []


def test_material_modules_do_not_import_private_sibling_helpers() -> None:
    offenders: list[tuple[str, str, list[str]]] = []
    prefix = "culsma.runtime.material."
    for path in _material_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module is None or not node.module.startswith(prefix):
                continue
            private_names = [alias.name for alias in node.names if alias.name.startswith("_")]
            if private_names:
                offenders.append((path.name, node.module, private_names))

    assert offenders == []


def test_scientific_model_core_logic_has_no_private_functions() -> None:
    paths = sorted(SCIENTIFIC_MODEL_DIR.rglob("*.py")) + [
        MATERIAL_DIR / "partition.py",
        MATERIAL_DIR / "separation.py",
        MATERIAL_DIR / "scientific_model_adapter.py",
    ]
    offenders: list[tuple[str, str]] = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_") and not node.name.startswith("__"):
                offenders.append((str(path.relative_to(PROJECT_ROOT)), node.name))

    assert offenders == []


def test_partition_does_not_construct_scientific_model_dependencies() -> None:
    path = MATERIAL_DIR / "partition.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constructed_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "create_default_scientific_model_resolver" not in constructed_names
    assert "ScientificModelPartitionAdapter" not in constructed_names


def test_partition_is_not_the_scientific_model_boundary() -> None:
    path = MATERIAL_DIR / "partition.py"
    source = path.read_text(encoding="utf-8")

    assert "ScientificModelPartitionAdapter" not in source
    assert "ResolvedMaterialEffect" not in source
    assert "SCIENTIFIC_MODEL_SEPARATION_PROGRAMS" not in source
    assert ".resolve(" not in source


def test_separation_owns_the_scientific_model_application_boundary() -> None:
    path = MATERIAL_DIR / "separation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function_names = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }

    assert {
        "apply_separation_material",
        "project_resolved_material_effect",
        "commit_separation_candidate",
    }.issubset(function_names)


def test_runtime_separation_callers_do_not_bypass_separation_module() -> None:
    offenders: list[str] = []
    for filename in ("contents_state.py", "mutation.py"):
        path = MATERIAL_DIR / filename
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "culsma.runtime.material.partition"
            ):
                offenders.append(filename)

    assert offenders == []


def test_partition_does_not_duplicate_program_slot_contracts() -> None:
    path = MATERIAL_DIR / "partition.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    duplicate_slot_contracts = []
    for class_node in (
        node for node in tree.body if isinstance(node, ast.ClassDef)
    ):
        for assignment in class_node.body:
            if not isinstance(assignment, (ast.Assign, ast.AnnAssign)):
                continue
            targets = (
                assignment.targets
                if isinstance(assignment, ast.Assign)
                else [assignment.target]
            )
            if any(
                isinstance(target, ast.Name) and target.id == "slot_contract"
                for target in targets
            ):
                duplicate_slot_contracts.append(assignment.lineno)

    assert duplicate_slot_contracts == []


def test_migrated_separation_programs_have_no_runtime_strategy_classes() -> None:
    path = MATERIAL_DIR / "partition.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    class_names = {
        node.name for node in tree.body if isinstance(node, ast.ClassDef)
    }

    assert {
        "CentrifugePartitionStrategy",
        "FiltrationPartitionStrategy",
        "CentrifugalFiltrationPartitionStrategy",
    }.isdisjoint(class_names)


def test_material_compute_routes_material_changes_through_state_manager() -> None:
    class RecordingStateManager:
        def __init__(self) -> None:
            self.planned = False
            self.applied = False

        def plan_material_state_change(
            self,
            *,
            step: PlanStep,
            state: dict[str, object],
        ) -> MaterialStateChangePlan:
            self.planned = True
            return MaterialStateChangePlan(kind="partition_or_index", step=step)

        def apply_change(
            self,
            change_plan: MaterialStateChangePlan,
            state: dict[str, object],
        ) -> MaterialUpdateResult:
            self.applied = True
            return MaterialUpdateResult(material_state=state, diagnostics=[], delta={"mode": change_plan.kind})

    manager = RecordingStateManager()
    result = MaterialCompute(state_manager=manager).apply_step(_material_step("sep"), {"containers": {}})

    assert result.ok
    assert result.delta == {"mode": "partition_or_index"}
    assert manager.planned is True
    assert manager.applied is True


def test_material_compute_skips_state_apply_when_step_has_no_material_change() -> None:
    class RecordingStateManager:
        def __init__(self) -> None:
            self.planned = False
            self.applied = False

        def plan_material_state_change(
            self,
            *,
            step: PlanStep,
            state: dict[str, object],
        ) -> None:
            self.planned = True
            return None

        def apply_change(
            self,
            change_plan: MaterialStateChangePlan,
            state: dict[str, object],
        ) -> MaterialUpdateResult:
            self.applied = True
            raise AssertionError("state apply should not run without a material-state plan")

    manager = RecordingStateManager()
    result = MaterialCompute(state_manager=manager).apply_step(_material_step("Wait"), {"containers": {}})

    assert result.ok
    assert result.delta == {}
    assert manager.planned is True
    assert manager.applied is False


def test_material_handler_module_removed() -> None:
    assert not (MATERIAL_DIR / "handler.py").exists()


def test_material_organization_transform_module_removed() -> None:
    assert (MATERIAL_DIR / "separation.py").exists()
    assert not (MATERIAL_DIR / "organization.py").exists()


def test_mutation_dispatcher_does_not_handle_contents_state_sources_directly() -> None:
    path = MATERIAL_DIR / "mutation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden_classes = {"QuantifiedContentsStateHandler", "ContentsStateSourceHandler"}
    class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}

    assert forbidden_classes.isdisjoint(class_names)


def test_material_state_manager_plans_partition_changes_before_contents_manager() -> None:
    manager = MaterialStateManager()

    plan = manager.plan_material_state_change(step=_material_step("sep"), state={"containers": {}})

    assert isinstance(plan, MaterialStateChangePlan)
    assert plan.kind == "partition_or_index"


def test_indexed_parts_state_manager_resolves_indexed_part_without_material_mutation() -> None:
    state = _partitioned_state()
    manager = MaterialIndexedPartsStateManager()

    result = manager.resolve_indexed_part(step=_step(), state=state, contents_ref=_contents_ref(slot=1))

    assert isinstance(result, ContentsPartSelection)
    assert result.source_id == "Tube"
    assert result.slot == "1"
    assert result.part["volume_uL"] == 160.0
    assert state["containers"]["Tube"]["volume_uL"] == 200.0
    assert state["contents_states"]["Tube"]["parts"]["1"]["volume_uL"] == 160.0


def test_indexed_parts_state_manager_reports_stale_state_as_diagnostic() -> None:
    state = _partitioned_state(valid=False)
    manager = MaterialIndexedPartsStateManager()

    result = manager.resolve_indexed_part(step=_step(), state=state, contents_ref=_contents_ref(slot=1))

    assert isinstance(result, MaterialUpdateResult)
    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["MAT_CONTENTS_STATE_NOT_INDEXED"]


def test_indexed_parts_state_manager_requires_preservation_context_for_indexed_part() -> None:
    state = _partitioned_state(preservation_contract=True)
    manager = MaterialIndexedPartsStateManager()

    result = manager.resolve_indexed_part(step=_step(), state=state, contents_ref=_contents_ref(slot=1))

    assert isinstance(result, MaterialUpdateResult)
    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["MAT_CONTENTS_STATE_PRESERVATION_NOT_SATISFIED"]
    assert state["contents_states"]["Tube"]["valid"] is False
    assert state["contents_states"]["Tube"]["invalid_reason"] == "preservation_contract_not_satisfied"


def test_indexed_parts_state_manager_accepts_indexed_part_when_preservation_context_matches() -> None:
    state = _partitioned_state(preservation_contract=True)
    manager = MaterialIndexedPartsStateManager()

    result = manager.resolve_indexed_part(step=_step(field="magnetic_rack"), state=state, contents_ref=_contents_ref(slot=1))

    assert isinstance(result, ContentsPartSelection)
    assert result.source_id == "Tube"
    assert result.slot == "1"


def test_indexed_parts_state_manager_records_sep_transition() -> None:
    state = {
        "containers": {
            "Tube": {
                "volume_uL": 200.0,
                "mass_mg": 200.0,
                "components": {"beads": 20.0, "buffer": 180.0},
                "metadata": {},
            }
        },
    }
    manager = MaterialIndexedPartsStateManager()

    result = manager.record_sep_transition(
        step=_material_step("sep"),
        state=state,
        source_id="Tube",
        program={"kind": "IRCall", "name": "magnetic_program", "args": []},
        keep_source=None,
        explicit_fates={},
    )

    assert isinstance(result, ContentsPartitionTransition)
    assert result.contents_state == {
        "source": "Tube",
        "kind": "partitioned",
        "program_kind": "magnetic_program",
        "slots": ["0", "1"],
    }
    assert result.partition["slot_contract"] == {"0": "bound", "1": "flowthrough"}
    assert result.partition["preservation_contract"]["field"] == "magnetic_rack"
    assert state["contents_states"]["Tube"]["kind"] == "partitioned"
    assert "p0.s1::0" not in state["containers"]
    assert "p0.s1::1" not in state["containers"]


def test_indexed_parts_state_manager_records_frac_transition() -> None:
    state = {
        "containers": {
            "Tube": {
                "volume_uL": 120.0,
                "mass_mg": 120.0,
                "components": {"S1": 120.0},
                "metadata": {},
            }
        },
    }
    manager = MaterialIndexedPartsStateManager()

    result = manager.record_frac_transition(
        step=_material_step("frac"),
        state=state,
        source_id="Tube",
        bins=3,
        program_kind="density_gradient_program",
    )

    assert isinstance(result, ContentsPartitionTransition)
    assert result.contents_state == {
        "source": "Tube",
        "kind": "fractionated",
        "program_kind": "density_gradient_program",
        "slots": ["0", "1", "2"],
    }
    assert result.slot_ids == {"0": "p0.s1::0", "1": "p0.s1::1", "2": "p0.s1::2"}
    assert result.split_ratio == 1.0 / 3
    assert state["contents_states"]["Tube"]["kind"] == "fractionated"
    assert state["contents_states"]["Tube"]["slot_contract"] == {
        "0": "fraction_0",
        "1": "fraction_1",
        "2": "fraction_2",
    }
    assert round(state["contents_states"]["Tube"]["parts"]["1"]["volume_uL"], 6) == 40.0
    assert "p0.s1::0" not in state["containers"]
    assert "p0.s1::1" not in state["containers"]
    assert "p0.s1::2" not in state["containers"]
