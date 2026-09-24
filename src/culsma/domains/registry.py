"""Read-only aggregation of domain-owned external parameter contracts."""
from types import MappingProxyType
from .chromatography import CHROMATOGRAPHY_AXIS, CHROMATOGRAPHY_ORDER, ChromatographyParameter, ExternalTypeCatalog, ChromatographyPairRule
from .contracts import CallParameterContract
from .agitation import AGITATION_MODE, AgitationArgumentsRule
from .fractionation import DENSITY_GRADIENT_AXIS, DENSITY_GRADIENT_ORDER
from .labware import PLATE_FORMAT
from .readout import READOUT_QUANTITIES, ReadoutQuantityRule
from .scheduling import SCHEDULE_MODE
from .separation import CENTRIFUGE_KEEP_SOURCE, DISRUPTION_METHOD

EXTERNAL_CALL_CONTRACTS = MappingProxyType({
    'chromatography_program': CallParameterContract(
        {'axis': CHROMATOGRAPHY_AXIS, 'order': CHROMATOGRAPHY_ORDER}, (ChromatographyPairRule(),)),
    'plate': CallParameterContract({'format': PLATE_FORMAT}),
    'centrifuge_program': CallParameterContract({'keep_source': CENTRIFUGE_KEEP_SOURCE}),
    'disrupt_program': CallParameterContract({'method': DISRUPTION_METHOD}),
    'density_gradient_program': CallParameterContract(
        {'axis': DENSITY_GRADIENT_AXIS, 'order': DENSITY_GRADIENT_ORDER}),
    'agit': CallParameterContract({'mode': AGITATION_MODE}, (AgitationArgumentsRule(),)),
    'schedule': CallParameterContract({'mode': SCHEDULE_MODE}),
    **{operation: CallParameterContract({'quantity': contract}, (ReadoutQuantityRule(operation),))
       for operation, contract in READOUT_QUANTITIES.items()},
})
EXTERNAL_PARAMETERS = MappingProxyType({
    (operation, name): field
    for operation, contract in EXTERNAL_CALL_CONTRACTS.items()
    for name, field in contract.fields.items()
})
EXTERNAL_ENUM_TYPES = ExternalTypeCatalog({contract.enum_type.__name__: contract.enum_type
    for contract in EXTERNAL_PARAMETERS.values() if not isinstance(contract, ChromatographyParameter)})
