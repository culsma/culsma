"""Online material input provenance and consumption accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.result import MaterialUpdateResult
from culsma.runtime.material.ledger import container_count_cells
from culsma.runtime.material.units import COUNT_TO_CELLS, MASS_TO_MG, VOLUME_TO_UL


EPSILON = 1e-9


@dataclass(frozen=True)
class MaterialQuantity:
    volume_uL: float = 0.0
    mass_mg: float = 0.0
    count_cells: float = 0.0


@dataclass(frozen=True)
class InputLot:
    lot_id: str
    container_id: str
    name: str
    origin: str
    initial: MaterialQuantity
    content_id: str | None = None


@dataclass(frozen=True)
class MaterialMovement:
    step_id: str
    source: str
    destination: str | None
    quantity: MaterialQuantity
    lot_allocations: dict[str, MaterialQuantity]


@dataclass
class MaterialAccounting:
    input_lots: dict[str, InputLot] = field(default_factory=dict)
    container_allocations: dict[str, dict[str, MaterialQuantity]] = field(default_factory=dict)
    movements: list[MaterialMovement] = field(default_factory=list)
    consumed_allocations: dict[str, MaterialQuantity] = field(default_factory=dict)

    def register_input_lot(self, lot: InputLot) -> None:
        self.input_lots[lot.lot_id] = lot
        allocations = self.container_allocations.setdefault(lot.container_id, {})
        current = allocations.get(lot.lot_id, MaterialQuantity())
        allocations[lot.lot_id] = MaterialQuantity(
            volume_uL=current.volume_uL + lot.initial.volume_uL,
            mass_mg=current.mass_mg + lot.initial.mass_mg,
            count_cells=current.count_cells + lot.initial.count_cells,
        )

    def record_movement(
        self,
        *,
        step_id: str,
        source: str,
        destination: str | None,
        quantity: MaterialQuantity,
    ) -> None:
        lot_allocations = self._withdraw(source=source, quantity=quantity)
        if not lot_allocations:
            return
        if destination is not None:
            target = self.container_allocations.setdefault(destination, {})
            for lot_id, allocation in lot_allocations.items():
                current = target.get(lot_id, MaterialQuantity())
                target[lot_id] = MaterialQuantity(
                    volume_uL=current.volume_uL + allocation.volume_uL,
                    mass_mg=current.mass_mg + allocation.mass_mg,
                    count_cells=current.count_cells + allocation.count_cells,
                )
        self.movements.append(
            MaterialMovement(
                step_id=step_id,
                source=source,
                destination=destination,
                quantity=quantity,
                lot_allocations=lot_allocations,
            )
        )

    def list_input_lots(self) -> list[InputLot]:
        return sorted(self.input_lots.values(), key=lambda lot: (lot.name, lot.lot_id))

    def consumption_by_input(self) -> dict[str, MaterialQuantity]:
        return dict(self.consumed_allocations)

    def container_allocation(self, container_id: str) -> dict[str, MaterialQuantity]:
        return dict(self.container_allocations.get(container_id, {}))

    def _withdraw(self, *, source: str, quantity: MaterialQuantity) -> dict[str, MaterialQuantity]:
        allocations = self.container_allocations.get(source)
        if not allocations:
            return {}
        total_volume = sum(item.volume_uL for item in allocations.values())
        total_mass = sum(item.mass_mg for item in allocations.values())
        total_cells = sum(item.count_cells for item in allocations.values())
        moved: dict[str, MaterialQuantity] = {}
        for lot_id, current in list(allocations.items()):
            moved_volume = (
                min(current.volume_uL, quantity.volume_uL * current.volume_uL / total_volume)
                if total_volume > EPSILON and quantity.volume_uL > EPSILON
                else 0.0
            )
            moved_mass = (
                min(current.mass_mg, quantity.mass_mg * current.mass_mg / total_mass)
                if total_mass > EPSILON and quantity.mass_mg > EPSILON
                else 0.0
            )
            moved_cells = (
                min(current.count_cells, quantity.count_cells * current.count_cells / total_cells)
                if total_cells > EPSILON and quantity.count_cells > EPSILON
                else 0.0
            )
            if moved_volume <= EPSILON and moved_mass <= EPSILON and moved_cells <= EPSILON:
                continue
            allocation = MaterialQuantity(volume_uL=moved_volume, mass_mg=moved_mass, count_cells=moved_cells)
            moved[lot_id] = allocation
            remaining = MaterialQuantity(
                volume_uL=max(0.0, current.volume_uL - moved_volume),
                mass_mg=max(0.0, current.mass_mg - moved_mass),
                count_cells=max(0.0, current.count_cells - moved_cells),
            )
            if (
                remaining.volume_uL <= EPSILON
                and remaining.mass_mg <= EPSILON
                and remaining.count_cells <= EPSILON
            ):
                allocations.pop(lot_id, None)
            else:
                allocations[lot_id] = remaining
            lot = self.input_lots.get(lot_id)
            if lot is not None and lot.container_id == source:
                consumed = self.consumed_allocations.get(lot_id, MaterialQuantity())
                self.consumed_allocations[lot_id] = MaterialQuantity(
                    volume_uL=min(lot.initial.volume_uL, consumed.volume_uL + moved_volume),
                    mass_mg=min(lot.initial.mass_mg, consumed.mass_mg + moved_mass),
                    count_cells=min(lot.initial.count_cells, consumed.count_cells + moved_cells),
                )
        if not allocations:
            self.container_allocations.pop(source, None)
        return moved


class MaterialAccountingRecorder:
    def initialize(self, initial_material_state: dict[str, Any] | None) -> MaterialAccounting:
        accounting = MaterialAccounting()
        containers = _containers(initial_material_state)
        for container_id, raw in sorted(containers.items()):
            quantity = _container_quantity(raw)
            if not _has_quantity(quantity) or "::" in container_id:
                continue
            accounting.register_input_lot(
                InputLot(
                    lot_id=f"initial:{container_id}",
                    container_id=container_id,
                    name=_container_name(container_id, raw),
                    origin="initial_state",
                    initial=quantity,
                )
            )
        return accounting

    def record(
        self,
        *,
        step: PlanStep,
        result: MaterialUpdateResult,
        accounting: MaterialAccounting,
    ) -> None:
        if not result.ok:
            return
        delta = result.delta
        if delta.get("op") == "LoadContent":
            self._record_load(step=step, delta=delta, state=result.material_state, accounting=accounting)
            return
        for movement in result.movements:
            accounting.record_movement(
                step_id=step.step_id,
                source=movement.source,
                destination=movement.destination,
                quantity=MaterialQuantity(
                    volume_uL=movement.volume_uL,
                    mass_mg=movement.mass_mg,
                    count_cells=movement.count_cells,
                ),
            )

    def _record_load(
        self,
        *,
        step: PlanStep,
        delta: dict[str, Any],
        state: dict[str, Any],
        accounting: MaterialAccounting,
    ) -> None:
        container_id = delta.get("container")
        amount = delta.get("amount")
        unit = delta.get("unit")
        if not isinstance(container_id, str) or not isinstance(amount, (int, float)) or not isinstance(unit, str):
            return
        quantity = _quantity_from_amount(float(amount), unit)
        if quantity is None:
            return
        raw_container = _containers(state).get(container_id)
        accounting.register_input_lot(
            InputLot(
                lot_id=f"load:{step.step_id}:{container_id}",
                container_id=container_id,
                name=_container_name(container_id, raw_container),
                origin="load_content",
                initial=quantity,
                content_id=delta.get("content_id") if isinstance(delta.get("content_id"), str) else None,
            )
        )

def _containers(state: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(state, dict):
        return {}
    containers = state.get("containers")
    return containers if isinstance(containers, dict) else {}


def _container_quantity(raw: Any) -> MaterialQuantity:
    if not isinstance(raw, dict):
        return MaterialQuantity()
    return MaterialQuantity(
        volume_uL=float(raw.get("volume_uL", 0.0)),
        mass_mg=float(raw.get("mass_mg", 0.0)),
        count_cells=container_count_cells(raw),
    )


def _quantity_from_amount(amount: float, unit: str) -> MaterialQuantity | None:
    if unit in VOLUME_TO_UL:
        return MaterialQuantity(volume_uL=amount * VOLUME_TO_UL[unit])
    if unit in MASS_TO_MG:
        return MaterialQuantity(mass_mg=amount * MASS_TO_MG[unit])
    if unit in COUNT_TO_CELLS:
        return MaterialQuantity(count_cells=amount * COUNT_TO_CELLS[unit])
    return None


def _container_name(container_id: str, raw: Any) -> str:
    if isinstance(raw, dict):
        metadata = raw.get("metadata")
        if isinstance(metadata, dict):
            label = metadata.get("label")
            if isinstance(label, str) and label:
                return label
    return container_id


def _has_quantity(quantity: MaterialQuantity) -> bool:
    return quantity.volume_uL > EPSILON or quantity.mass_mg > EPSILON or quantity.count_cells > EPSILON
