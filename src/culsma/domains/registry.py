"""Read-only aggregation of domain-owned external parameter contracts."""
from types import MappingProxyType
from culsma.common.content_contracts import CONTENT_ENUM_TYPES
from .separation import PROGRAM_OUTPUT_TYPES, ProgramOutput
from .chromatography import ChromatographyAxisBase, ChromatographyOrderBase
from .namespaces import SourceTypeNamespace
from .namespace_contracts import TypeNamespace
from .chromatography import STANDARD_CHROMATOGRAPHY_REGISTRY
from .observation import OBSERVATION_UNITS
from .constraints import CONSTRAINT_REQUIREMENTS
from .vocabularies import VocabularyDomain, VocabularyCatalog
from .chromatography import CHROMATOGRAPHY_AXIS, CHROMATOGRAPHY_ORDER, ChromatographyParameter, ExternalTypeCatalog, ChromatographyPairRule
from .contracts import CallParameterContract, RecordParameterContract
from .content_attributes import CONTENT_ATTRIBUTES, CONTENT_ATTRIBUTE_DOMAINS
from .agitation import AGITATION_MODE, AgitationArgumentsRule
from .fractionation import DENSITY_GRADIENT_AXIS, DENSITY_GRADIENT_ORDER
from .labware import PLATE_FORMAT
from .readout import READOUT_QUANTITIES, ReadoutQuantityRule
from .scheduling import SCHEDULE_MODE
from .separation import CENTRIFUGE_KEEP_SOURCE, DISRUPTION_METHOD

EXTERNAL_CALL_CONTRACTS = MappingProxyType({
    **{name: CallParameterContract({'attrs': CONTENT_ATTRIBUTES}) for name in ('content', 'DefineContent')},
    'stream': CallParameterContract({'unit': OBSERVATION_UNITS}),
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
EXTERNAL_ENUM_TYPES = VocabularyCatalog(ExternalTypeCatalog({contract.enum_type.__name__: contract.enum_type
    for contract in EXTERNAL_PARAMETERS.values() if not isinstance(contract, (ChromatographyParameter, VocabularyDomain, RecordParameterContract))}), (OBSERVATION_UNITS, CONSTRAINT_REQUIREMENTS, *CONTENT_ATTRIBUTE_DOMAINS))


# Composition root: all built-in source types are available before activation.
# The domains package initializes this once, even for a direct domain import.

source_type_namespace = SourceTypeNamespace()
source_type_namespace.configure(
    {**CONTENT_ENUM_TYPES, **PROGRAM_OUTPUT_TYPES, **EXTERNAL_ENUM_TYPES},
    reserved={'MaterialRelation', ProgramOutput.__name__, ChromatographyAxisBase.__name__,
              ChromatographyOrderBase.__name__,
              *(domain.enum_type.__name__ for domain in EXTERNAL_ENUM_TYPES.domains)},
)

SOURCE_TYPE_NAMES: TypeNamespace = source_type_namespace
STANDARD_CHROMATOGRAPHY_REGISTRY.namespace.bind(SOURCE_TYPE_NAMES)
for vocabulary_domain in EXTERNAL_ENUM_TYPES.domains:
    vocabulary_domain.namespace.bind(SOURCE_TYPE_NAMES)
