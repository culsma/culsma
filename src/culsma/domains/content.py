"""Open content metadata vocabularies; member identity grants no material behavior."""
from enum import Enum
from dataclasses import dataclass
from types import MappingProxyType
from culsma.common.enum_registration import EnumTypeRegistry
from culsma.common.content_contracts import ContentKind, ContentType, ContentClassification
from culsma.common.enum_parameters import EnumParameter, CallParameterContract
from culsma.common.enum_parameters import RecordParameterContract

class ContentRoleBase(Enum):
    pass


class ContentRole(ContentRoleBase):
    MATERIAL = 'material'
    SAMPLE = 'sample'
    TEMPLATE = 'template'
    PRIMER = 'primer'
    PROBE = 'probe'
    MARKER = 'marker'
    STANDARD = 'standard'
    VECTOR = 'vector'
    GUIDE = 'guide'
    ANTIBODY = 'antibody'
    ENZYME = 'enzyme'
    CYTOKINE = 'cytokine'
    ANTIGEN = 'antigen'
    SUBSTRATE = 'substrate'
    INHIBITOR = 'inhibitor'
    ACTIVATOR = 'activator'
    FIXATIVE = 'fixative'
    SELECTION = 'selection'
    PRECIPITATION = 'precipitation'
    CROWDING_AGENT = 'crowding_agent'
    MATRIX_COMPONENT = 'matrix_component'
    SALT = 'salt'
    PH_ADJUSTER = 'pH_adjuster'
    ION_SOURCE = 'ion_source'
    COFACTOR = 'cofactor'
    SOLVENT = 'solvent'
    CARRIER = 'carrier'
    EXTRACTION = 'extraction'
    LYSIS = 'lysis'
    PERMEABILIZATION = 'permeabilization'
    WASHING = 'washing'
    SOLUBILIZATION = 'solubilization'
    STAIN = 'stain'
    DETECTION = 'detection'
    TRACKING = 'tracking'
    CAPTURE = 'capture'
    CLEANUP = 'cleanup'
    PURIFICATION = 'purification'
    ENRICHMENT = 'enrichment'
    AFFINITY_PURIFICATION = 'affinity_purification'
    CHROMATOGRAPHY = 'chromatography'
    LABELING = 'labeling'
    CALIBRATION = 'calibration'
    CULTURE = 'culture'
    MAINTENANCE = 'maintenance'
    WASH = 'wash'
    ELUTION = 'elution'
    BINDING = 'binding'
    STORAGE = 'storage'
    REACTION_ENVIRONMENT = 'reaction_environment'
    SUPPLEMENT = 'supplement'
    GROWTH_FACTOR = 'growth_factor'
    REACTION_MIX = 'reaction_mix'
    DENSITY_GRADIENT_SEPARATION = 'density_gradient_separation'


class ContentStateBase(Enum):
    pass


class ContentState(ContentStateBase):
    SUSPENSION = 'suspension'
    SOLUTION = 'solution'
    STOCK = 'stock'
    EXTRACT = 'extract'
    REACTION_ASSEMBLED = 'reaction_assembled'


class BeadPropertyBase(Enum):
    pass


class BeadProperty(BeadPropertyBase):
    MAGNETIC = 'magnetic'


@dataclass(frozen=True)
class ContentAttributeContract:
    """A typed value of one content attrs field; unrelated attrs remain open."""
    field_name: str
    registry: EnumTypeRegistry
    allow_legacy_text = True
    preserve_legacy_values = True

    @property
    def enum_type(self):
        return self.registry.base_type

    @property
    def standard(self):
        return self.registry.standard_type

    @property
    def standard_registry(self):
        return self.registry

    @property
    def current(self):
        return self.registry.current

    @property
    def wire_values(self):
        return tuple(member.value for member in self.standard)

    def validate(self, value):
        if not isinstance(value, self.enum_type):
            raise TypeError(f'Expected a content {self.field_name} member')
        self.current.registration(type(value))
        return value

    def decode(self, value):
        if type(value) is not str:
            raise TypeError(f'Expected a content {self.field_name} spelling')
        return self.standard(value)


CONTENT_ROLES = ContentAttributeContract('role', EnumTypeRegistry.create(ContentRoleBase, ContentRole, 'content_role'))
CONTENT_STATES = ContentAttributeContract('state', EnumTypeRegistry.create(ContentStateBase, ContentState, 'content_state'))
BEAD_PROPERTIES = ContentAttributeContract('bead_property', EnumTypeRegistry.create(BeadPropertyBase, BeadProperty, 'bead_property'))
CONTENT_ATTRIBUTE_CONTRACTS = (CONTENT_ROLES, CONTENT_STATES, BEAD_PROPERTIES)
CONTENT_ATTRIBUTES = RecordParameterContract({contract.field_name: contract for contract in CONTENT_ATTRIBUTE_CONTRACTS})


class ContentContract:
    """The content constructor's typed fields, using the shared classification."""
    fields = MappingProxyType({'kind': EnumParameter(ContentKind), 'type': EnumParameter(ContentType), 'attrs': CONTENT_ATTRIBUTES})

    @staticmethod
    def classification(kind, content_type):
        return ContentClassification(kind, content_type)


CONTENT_CONTRACT = ContentContract()
# Classification diagnostics retain their existing owning content path.
CALL_PARAMETER_CONTRACTS = MappingProxyType({name: CallParameterContract({'attrs': CONTENT_CONTRACT.fields['attrs']})
                                 for name in ('content', 'DefineContent')})
