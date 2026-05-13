"""Compatibility facade for deterministic material-state compute."""

from __future__ import annotations

from culsma.runtime.material.compute import MaterialCompute, MaterialOpDispatcher, apply_step
from culsma.runtime.material.handler import (
    ContainerContentHandler,
    MaterialOpHandler,
    MutationHandler,
    NoopMaterialOpHandler,
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
from culsma.runtime.material.support import (
    MaterialArgReader,
    MaterialConservation,
    MaterialLedger,
    MaterialRefResolver,
    MaterialUpdateResult,
)

__all__ = [
    "MaterialCompute",
    "MaterialOpDispatcher",
    "MaterialOpHandler",
    "ContainerContentHandler",
    "MutationHandler",
    "SeparationHandler",
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
