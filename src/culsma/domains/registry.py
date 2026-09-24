"""Read-only aggregation of domain-owned external parameter contracts."""
from types import MappingProxyType
from .chromatography import CHROMATOGRAPHY_AXIS, CHROMATOGRAPHY_ORDER, ChromatographyParameter, ExternalTypeCatalog
from .agitation import AGITATION_MODE
from .fractionation import DENSITY_GRADIENT_AXIS, DENSITY_GRADIENT_ORDER
from .labware import PLATE_FORMAT
from .readout import READOUT_QUANTITIES
from .scheduling import SCHEDULE_MODE
from .separation import CENTRIFUGE_KEEP_SOURCE, DISRUPTION_METHOD

EXTERNAL_PARAMETERS = MappingProxyType({
    ('chromatography_program', 'axis'): CHROMATOGRAPHY_AXIS,
    ('chromatography_program', 'order'): CHROMATOGRAPHY_ORDER,
    ('plate', 'format'): PLATE_FORMAT,
    ('centrifuge_program', 'keep_source'): CENTRIFUGE_KEEP_SOURCE,
    ('disrupt_program', 'method'): DISRUPTION_METHOD,
    ('density_gradient_program', 'axis'): DENSITY_GRADIENT_AXIS,
    ('density_gradient_program', 'order'): DENSITY_GRADIENT_ORDER,
    ('agit', 'mode'): AGITATION_MODE,
    ('schedule', 'mode'): SCHEDULE_MODE,
    **{(operation, 'quantity'): contract for operation, contract in READOUT_QUANTITIES.items()},
})
EXTERNAL_ENUM_TYPES = ExternalTypeCatalog({contract.enum_type.__name__: contract.enum_type
    for contract in EXTERNAL_PARAMETERS.values() if not isinstance(contract, ChromatographyParameter)})
