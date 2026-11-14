"""PM #162 acceptance includes input-lot accounting, not only material state."""

from pathlib import Path

import pytest

from culsma.driver.stub import StubDriver
from culsma.runtime.executor import run
from culsma.runtime.replay import replay_events
from test_kernel_runtime import _build_plan_from_source, _container_id_by_label


FIXTURE = Path(__file__).parent / "fixtures_material" / "fractionation_allocation.culs"
EXPECTED = {
    "Upper": {"PLASMA":9500, "PBS_FBS":12000},
    "Middle": {"PLASMA":500, "PBS_FBS":500, "PBMC":300},
    "Lower": {"FICOLL":15000, "RBC":2500, "GRANULOCYTES":800, "PLATELETS":2000},
}


@pytest.mark.parametrize("form", ["scoped", "standalone", "group"])
@pytest.mark.parametrize("partial", [False, True])
def test_pm162_material_return_and_input_lots_agree(form, partial):
    source = FIXTURE.read_text()
    if partial:
        source = source.replace("middle << [sample.contents[1]:1mL];",
                                "middle << [sample.contents[1]:0.5mL, sample.contents[1]:0.5mL];")
    if form != "scoped":
        source = source.replace("with frac(", "let fractions = frac(" if form == "group" else "frac(")
        source = source.replace("  ) {", "  );").replace("  }\n  return", "  return")
        if form == "group":
            source = source.replace("sample.contents[", "fractions[")
    result = run(_build_plan_from_source(source), StubDriver())
    assert result.ok, result.diagnostics
    material = result.state.artifacts["material_state"]
    returned = result.state.artifacts["protocol_outputs"]["FractionAllocation"]["value"]
    accounting = result.material_accounting
    for label, expected in EXPECTED.items():
        container_id = _container_id_by_label(material["containers"], label)
        actual = material["containers"][container_id]
        assert actual["components"] == pytest.approx(expected)
        returned_container = returned[label.lower()]
        assert material["containers"][returned_container["id"]]["components"] == pytest.approx(expected)
        if "component_quantities" in returned_container:
            assert {key:q["value"] for key,q in returned_container["component_quantities"].items()} == pytest.approx(expected)
        lots = accounting.container_allocation(container_id)
        assert {accounting.input_lots[key].content_id for key in lots} == set(expected)
        for lot_id, quantity in lots.items():
            content_id = accounting.input_lots[lot_id].content_id
            if content_id in {"PBMC", "GRANULOCYTES", "PLATELETS"}:
                assert quantity.count_cells == pytest.approx(expected[content_id])
                assert quantity.volume_uL == 0
            else:
                assert quantity.volume_uL == pytest.approx(expected[content_id])
                assert quantity.count_cells == 0
    # Every input lot is conserved across the final destinations.
    for lot_id, lot in accounting.input_lots.items():
        for axis in ("volume_uL", "mass_mg", "count_cells"):
            total = sum(getattr(lots[lot_id],axis) for lots in accounting.container_allocations.values() if lot_id in lots)
            assert total == pytest.approx(getattr(lot.initial,axis))
    assert replay_events(result.events).artifacts["material_state"] == material


def test_returned_middle_fraction_preserves_composition_on_further_transfer():
    source = FIXTURE.read_text() + '''
let products = FractionAllocation();
let aliquot = tube(label="Aliquot", capacity=1mL);
aliquot << [products.middle:0.5mL];
return aliquot;
'''
    result = run(_build_plan_from_source(source), StubDriver())
    assert result.ok, result.diagnostics
    material = result.state.artifacts["material_state"]
    aliquot_id = _container_id_by_label(material["containers"], "Aliquot")
    assert material["containers"][aliquot_id]["components"] == pytest.approx({"PLASMA":250,"PBS_FBS":250,"PBMC":150})
    lots = result.material_accounting.container_allocation(aliquot_id)
    quantities = {result.material_accounting.input_lots[key].content_id:value for key,value in lots.items()}
    assert set(quantities) == {"PLASMA","PBS_FBS","PBMC"}
    assert quantities["PLASMA"].volume_uL == 250
    assert quantities["PBS_FBS"].volume_uL == 250
    assert quantities["PBMC"].count_cells == 150
