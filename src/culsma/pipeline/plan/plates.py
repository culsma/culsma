"""Bound plate description snapshots and well allocation."""
from dataclasses import dataclass
from typing import Any

from culsma.common.quantity_arithmetic import UNIT_TO_DIMENSION, require_finite_number
from culsma.domains.labware import (
    PLATE_FORMAT, PlateGeometry, plate_dimensions, plate_default_well_capacity,
)
from culsma.pipeline.external_boundary import DEFAULT_EXTERNAL_PARAMETER_NORMALIZER
from culsma.pipeline.ir_nodes import IRArg, IRCall, IRIdentifier, IRQuantity, IRString
from .static_eval import PlanStaticEvaluator
from .serialization import DEFAULT_PLAN_EXPRESSION_SERIALIZER


@dataclass(frozen=True)
class ResolvedPlateDescriptor:
    geometry: PlateGeometry
    carrier_id: str
    capacity: IRQuantity | None = None
    label: str | None = None

    def __post_init__(self):
        if not isinstance(self.geometry, PlateGeometry):
            raise TypeError('Plate geometry must be validated')
        if type(self.carrier_id) is not str or (self.label is not None and type(self.label) is not str):
            raise TypeError('Plate carrier id and label must be text')
        if self.capacity is not None:
            self.validate_capacity(self.capacity)

    @staticmethod
    def validate_capacity(capacity: IRQuantity) -> IRQuantity:
        if not isinstance(capacity, IRQuantity):
            raise TypeError('Plate capacity must be a volume quantity')
        require_finite_number(capacity.value)
        if capacity.value < 0 or UNIT_TO_DIMENSION.get(capacity.unit) != 'volume':
            raise ValueError('Plate capacity must be a nonnegative volume')
        return capacity

    def allocation(self, position: str, span=None) -> IRCall:
        self.geometry.validate_position(position)
        fields = {
            'kind': IRString('well', span=span),
            'carrier_kind': IRString('plate', span=span),
            'carrier_id': IRString(self.carrier_id, span=span),
            'carrier_position': IRString(position, span=span),
        }
        if self.label is not None:
            fields['label'] = IRString(f'{self.label}_{position}', span=span)
        if self.capacity is not None:
            fields['capacity'] = self.capacity
        return IRCall(name='AllocContainer', args=[
            IRArg(name=name, value=value, span=span) for name, value in fields.items()
        ], span=span)


class PlateDescriptorResolver:
    """Resolve each bound descriptor without retaining an environment or cache."""

    def __init__(self, serializer=DEFAULT_PLAN_EXPRESSION_SERIALIZER, evaluator=None,
                 normalizer=DEFAULT_EXTERNAL_PARAMETER_NORMALIZER):
        self.serializer = serializer
        self.evaluator = evaluator if evaluator is not None else PlanStaticEvaluator()
        self.normalizer = normalizer

    def resolve(self, plate: IRIdentifier, env: dict[str, Any]) -> ResolvedPlateDescriptor:
        descriptor = self.serializer.serialize_expr(plate, env)
        if not isinstance(descriptor, dict) or descriptor.get('kind') != 'IRCall' or descriptor.get('name') != 'plate':
            raise ValueError(f"Plate '{plate.name}' has no bound descriptor")
        args = {arg['name']: arg['value'] for arg in descriptor['args']}
        format_value = None
        rows = cols = None
        if 'format' in args:
            format_value = self.normalizer.require_member(args['format'], PLATE_FORMAT)
            rows, cols = plate_dimensions(format_value)
        if 'rows' in args:
            rows = self.resolve_dimension(args['rows'], 'rows')
        if 'cols' in args:
            cols = self.resolve_dimension(args['cols'], 'cols')
        if rows is None or cols is None:
            raise ValueError('Plate must provide a bound format or rows/cols')
        geometry = PlateGeometry(rows, cols)
        carrier_id = self.resolve_text(args['carrier_id'], 'carrier_id') if 'carrier_id' in args else plate.name
        label = self.resolve_text(args['label'], 'label') if 'label' in args else None
        capacity = None
        if 'capacity' in args:
            capacity = self.resolve_capacity(args['capacity'])
        elif format_value is not None:
            default = plate_default_well_capacity(format_value)
            if default is not None:
                capacity = IRQuantity(value=default[0], unit=default[1], span=plate.span)
        return ResolvedPlateDescriptor(geometry, carrier_id, capacity, label)

    def resolve_dimension(self, value: Any, name: str) -> int:
        number = self.evaluator.try_eval_numeric_expr(value)
        if number is None or isinstance(number, bool):
            raise ValueError(f'Plate {name} must be a bound positive integer')
        require_finite_number(number)
        if number < 1 or int(number) != number:
            raise ValueError(f'Plate {name} must be a positive integer')
        return int(number)

    def resolve_text(self, value: Any, name: str) -> str:
        if isinstance(value, dict) and value.get('kind') == 'IRString':
            value = value.get('value')
        if type(value) is not str:
            raise ValueError(f'Plate {name} must be bound text')
        return value

    def resolve_capacity(self, value: Any) -> IRQuantity:
        if not isinstance(value, dict) or value.get('kind') != 'IRQuantity':
            raise ValueError('Plate capacity must be a bound volume quantity')
        return ResolvedPlateDescriptor.validate_capacity(
            IRQuantity(value=value.get('value'), unit=value.get('unit'))
        )
