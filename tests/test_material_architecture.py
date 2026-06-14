from __future__ import annotations

import ast
from pathlib import Path

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.contents_state import (
    ContentsPartSelection,
    MaterialContentsStateManager,
)
from culsma.runtime.material.result import MaterialUpdateResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MATERIAL_DIR = PROJECT_ROOT / "src" / "culsma" / "runtime" / "material"


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


def _step() -> PlanStep:
    return PlanStep(step_id="p0.s1", op="Mutation", args={}, deps=[], gate=None, span=None)


def _partitioned_state(*, valid: bool = True) -> dict[str, object]:
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
            "Tube": {
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


def test_contents_state_manager_resolves_indexed_part_without_material_mutation() -> None:
    state = _partitioned_state()
    manager = MaterialContentsStateManager()

    result = manager.resolve_indexed_part(step=_step(), state=state, contents_ref=_contents_ref(slot=1))

    assert isinstance(result, ContentsPartSelection)
    assert result.source_id == "Tube"
    assert result.slot == "1"
    assert result.part["volume_uL"] == 160.0
    assert state["containers"]["Tube"]["volume_uL"] == 200.0
    assert state["contents_states"]["Tube"]["parts"]["1"]["volume_uL"] == 160.0


def test_contents_state_manager_reports_stale_state_as_diagnostic() -> None:
    state = _partitioned_state(valid=False)
    manager = MaterialContentsStateManager()

    result = manager.resolve_indexed_part(step=_step(), state=state, contents_ref=_contents_ref(slot=1))

    assert isinstance(result, MaterialUpdateResult)
    assert not result.ok
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["MAT_CONTENTS_STATE_NOT_INDEXED"]
