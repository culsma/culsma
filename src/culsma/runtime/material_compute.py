"""Compatibility facade for deterministic material-state compute."""

from __future__ import annotations

from culsma.runtime.material.args import MaterialArgReader
from culsma.runtime.material.conservation import MaterialConservation
from culsma.runtime.material.compute import MaterialCompute, apply_step
from culsma.runtime.material.partition import (
    ContentClassResolver,
    DisruptPartitionStrategy,
    FieldPartitionStrategy,
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
from culsma.runtime.material.state import MaterialStateChangePlan, MaterialStateManager

__all__ = [
    "MaterialCompute",
    "MaterialStateManager",
    "MaterialStateChangePlan",
    "SepPartitionStrategy",
    "SepPartitionStrategyRegistry",
    "ContentClassResolver",
    "PartitionClass",
    "PhasePartitionStrategy",
    "PrecipitationPartitionStrategy",
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
