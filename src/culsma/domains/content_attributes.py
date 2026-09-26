"""Open content metadata vocabularies; member identity grants no material behavior."""
from enum import Enum
from .vocabularies import VocabularyDomain
from .contracts import RecordParameterContract

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


CONTENT_ROLES = VocabularyDomain("content_role", ContentRoleBase, ContentRole, preserve_legacy_values=True)
CONTENT_STATES = VocabularyDomain("content_state", ContentStateBase, ContentState, preserve_legacy_values=True)
BEAD_PROPERTIES = VocabularyDomain("bead_property", BeadPropertyBase, BeadProperty, preserve_legacy_values=True)
CONTENT_ATTRIBUTE_DOMAINS = (CONTENT_ROLES, CONTENT_STATES, BEAD_PROPERTIES)
CONTENT_ATTRIBUTES = RecordParameterContract({"role": CONTENT_ROLES, "state": CONTENT_STATES, "bead_property": BEAD_PROPERTIES})
