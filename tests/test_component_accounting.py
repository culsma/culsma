"""Component-aware provenance uses the committed transfer composition."""

import pytest

from culsma.runtime.material.accounting import InputLot, MaterialAccounting, MaterialQuantity
from culsma.runtime.material.movements import (
    native_component_quantities, component_quantity_increase, derive_material_movements,
)


def test_native_component_quantities_preserves_units_and_axes():
    raw = {"component_quantities": {
        "liquid":{"value":0.5,"unit":"mL"},
        "protein":{"value":50,"unit":"ug"},
        "cells":{"value":300,"unit":"cells"},
        "unknown":{"value":None,"unit":"mg"},
    }}
    assert native_component_quantities(raw) == {
        "liquid":{"volume_uL":500}, "protein":{"mass_mg":0.05}, "cells":{"count_cells":300},
    }
    assert native_component_quantities(None) == {}
    assert native_component_quantities({"component_quantities":None}) == {}


def test_component_quantity_increase_uses_actual_target_change():
    before = {"component_quantities":{"A":{"value":1,"unit":"mL"},"B":{"value":3,"unit":"mg"}}}
    after = {"component_quantities":{"A":{"value":1500,"unit":"uL"},"B":{"value":3,"unit":"mg"},"C":{"value":10,"unit":"cells"}}}
    assert component_quantity_increase(before,after) == {"A":{"volume_uL":500},"C":{"count_cells":10}}


@pytest.fixture
def source_accounting():
    accounting = MaterialAccounting()
    for lot_id, content_id, volume in (("a1","A",100),("a2","A",200),("b","B",300)):
        accounting.register_input_lot(InputLot(lot_id, "source", content_id, "load_content",
                                              MaterialQuantity(volume_uL=volume), content_id))
    return accounting


def test_withdraw_filters_content_then_apportions_same_content_lots(source_accounting):
    moved = source_accounting.withdraw(source="source", quantity=MaterialQuantity(volume_uL=60), content_id="A")
    assert moved == {"a1":MaterialQuantity(volume_uL=20), "a2":MaterialQuantity(volume_uL=40)}
    assert source_accounting.container_allocation("source")["b"].volume_uL == 300


def test_withdraw_components_does_not_apply_bulk_mixture_ratios(source_accounting):
    moved = source_accounting.withdraw_components(
        source="source", quantity=MaterialQuantity(volume_uL=150),
        component_quantities={"A":{"volume_uL":30},"B":{"volume_uL":120}},
    )
    assert moved == {"a1":MaterialQuantity(volume_uL=10),"a2":MaterialQuantity(volume_uL=20),"b":MaterialQuantity(volume_uL=120)}


def test_legacy_accounting_without_component_evidence_is_preserved(source_accounting):
    moved = source_accounting.withdraw_components(source="source", quantity=MaterialQuantity(volume_uL=150), component_quantities=None)
    assert moved == {"a1":MaterialQuantity(volume_uL=25),"a2":MaterialQuantity(volume_uL=50),"b":MaterialQuantity(volume_uL=75)}


def test_legacy_carrier_quantified_lot_does_not_lose_provenance(source_accounting):
    moved = source_accounting.withdraw_components(
        source="source", quantity=MaterialQuantity(volume_uL=150),
        component_quantities={"A":{"mass_mg":0.5}},
    )
    assert moved == {"a1":MaterialQuantity(volume_uL=25),"a2":MaterialQuantity(volume_uL=50),"b":MaterialQuantity(volume_uL=75)}


def test_mass_component_allocation_uses_native_mass_lots():
    accounting = MaterialAccounting()
    for content_id, mass in (("A",2),("B",8)):
        accounting.register_input_lot(InputLot(content_id,"s",content_id,"load_content",
                                              MaterialQuantity(mass_mg=mass),content_id))
    accounting.record_movement(step_id="move",source="s",destination="t",quantity=MaterialQuantity(mass_mg=2),
                               component_quantities={"A":{"mass_mg":1.5},"B":{"mass_mg":0.5}})
    assert accounting.container_allocation("t") == {"A":MaterialQuantity(mass_mg=1.5),"B":MaterialQuantity(mass_mg=0.5)}


def test_derive_movements_preserves_per_transfer_and_explicit_evidence():
    composition = {"A":{"volume_uL":10}}
    raw = {"source":"s","dest":"t","moved_uL":10,"component_quantities":composition}
    for delta in ({"movements":[raw]}, {"op":"Mutation","target":"t","sources":[raw]},
                  {"op":"Mutation","target":"t","sources":[{"transfer_delta":raw,"component_quantities":composition}]}):
        movements = derive_material_movements(delta=delta,before_state={},after_state={})
        assert len(movements) == 1
        assert movements[0].component_quantities == composition


def test_returned_fraction_group_movements_use_output_composition():
    after = {"containers":{"out":{"volume_uL":10,"component_quantities":{"A":{"value":10,"unit":"uL"}}}}}
    movements = derive_material_movements(delta={"op":"frac","source":"s","slots":{"0":"out"}},before_state={},after_state=after)
    assert movements[0].component_quantities == {"A":{"volume_uL":10}}
