"""Application assembly of syntax-owned contracts and shared enum services.

Import this entry point before activating default extension registries. Pure
language declarations remain importable without constructing these services.
"""
from types import MappingProxyType
from culsma.common.content_contracts import CONTENT_ENUM_TYPES
from culsma.common.enum_parameters import EnumParameter
from culsma.common.enum_type_table import EnumTypeTable
from culsma.common.type_names import SourceTypeNamespace
from culsma.common.type_name_contracts import TypeNamespace
from culsma.domains import agitation, content, constraints, data, fractionation, labware, readout, scheduling, separation, stream

CALL_PARAMETER_CONTRACTS = MappingProxyType({
    operation: contract
    for module in (agitation, content, data, fractionation, labware, readout, scheduling, separation, stream)
    for operation, contract in module.CALL_PARAMETER_CONTRACTS.items()
})
PARAMETER_CONTRACTS = MappingProxyType({
    (operation, name): field
    for operation, contract in CALL_PARAMETER_CONTRACTS.items()
    for name, field in contract.fields.items()
})

# Identity storage is technical; the accepted type rules remain in each syntax module.
ENUM_REGISTRATION_SOURCES = (
    ((separation.FiltrationDriveBase,), lambda: separation.FILTRATION_DRIVES.current),
    ((data.DataKindBase,), lambda: data.DATA_KINDS.current),
    ((stream.ObservationUnitBase,), lambda: stream.OBSERVATION_UNITS.current),
    ((constraints.ConstraintRequirementBase,), lambda: constraints.CONSTRAINT_REQUIREMENTS.current),
    ((content.ContentRoleBase,), lambda: content.CONTENT_ROLES.current),
    ((content.ContentStateBase,), lambda: content.CONTENT_STATES.current),
    ((content.BeadPropertyBase,), lambda: content.BEAD_PROPERTIES.current),
    ((fractionation.ChromatographyAxisBase, fractionation.ChromatographyOrderBase),
     fractionation.ACTIVE_CHROMATOGRAPHY_REGISTRY.get),
)
PARAMETER_ENUM_TYPES = EnumTypeTable(
    {field.enum_type.__name__: field.enum_type for field in PARAMETER_CONTRACTS.values()
     if isinstance(field, EnumParameter)}, ENUM_REGISTRATION_SOURCES)

source_type_names = SourceTypeNamespace()
source_type_names.configure(
    {**CONTENT_ENUM_TYPES, **separation.PROGRAM_OUTPUT_TYPES, **PARAMETER_ENUM_TYPES},
    reserved={'MaterialRelation', separation.ProgramOutput.__name__,
              *(base.__name__ for bases, current in ENUM_REGISTRATION_SOURCES for base in bases)},
)
SOURCE_TYPE_NAMES: TypeNamespace = source_type_names
for bases, current in ENUM_REGISTRATION_SOURCES:
    current().namespace.bind(SOURCE_TYPE_NAMES)
