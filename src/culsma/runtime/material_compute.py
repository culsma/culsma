"""Compatibility facade for deterministic material-state compute."""

from __future__ import annotations

from culsma.runtime.material.args import MaterialArgReader
from culsma.runtime.material.conservation import MaterialConservation
from culsma.runtime.material.compute import MaterialCompute, MaterialOpDispatcher, apply_step
from culsma.runtime.material.handler import (
    ContainerContentHandler,
    MaterialOpHandler,
    MutationHandler,
    NoopMaterialOpHandler,
    OrganizationResetHandler,
    SeparationHandler,
)
from culsma.runtime.material.partition import (
    CentrifugePartitionStrategy,
    ContentClassResolver,
    DisruptPartitionStrategy,
    FieldPartitionStrategy,
    FiltrationPartitionStrategy,
    MagneticPartitionStrategy,
    PartitionClass,
    PhasePartitionStrategy,
    PrecipitationPartitionStrategy,
    SepPartitionStrategy,
    SepPartitionStrategyRegistry,
)
from culsma.runtime.material.ledger import MaterialLedger
from culsma.runtime.material.refs import MaterialRefResolver
from culsma.runtime.material.result import MaterialUpdateResult

__all__ = [
    "MaterialCompute",
    "MaterialOpDispatcher",
    "MaterialOpHandler",
    "ContainerContentHandler",
    "MutationHandler",
    "SeparationHandler",
    "OrganizationResetHandler",
    "NoopMaterialOpHandler",
    "SepPartitionStrategy",
    "SepPartitionStrategyRegistry",
    "ContentClassResolver",
    "PartitionClass",
    "CentrifugePartitionStrategy",
    "PhasePartitionStrategy",
    "PrecipitationPartitionStrategy",
    "FiltrationPartitionStrategy",
    "MagneticPartitionStrategy",
    "DisruptPartitionStrategy",
    "FieldPartitionStrategy",
    "MaterialArgReader",
    "MaterialRefResolver",
    "MaterialLedger",
    "MaterialConservation",
    "MaterialUpdateResult",
    "apply_step",
]
