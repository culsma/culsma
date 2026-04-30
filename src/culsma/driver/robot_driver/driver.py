"""Robot driver implementation."""

from __future__ import annotations

from dataclasses import dataclass, field

from culsma.driver.framework.driver import ProjectionDriver
from culsma.driver.framework.registry import TranslatorRegistry

from .backend_emitter import RobotBackendEmitter
from .binding_resolver import RobotBindingResolver
from .receipt_normalizer import RobotReceiptNormalizer
from .registry import build_default_registry


@dataclass
class RobotDriver(ProjectionDriver):
    """Capability-aware robot driver with structured command output."""

    driver_kind: str = "robot"
    ok_code: str = "DRV_ROBOT_OK"
    translator_registry: TranslatorRegistry = field(default_factory=build_default_registry)
    binding_resolver: RobotBindingResolver = field(default_factory=RobotBindingResolver)
    backend_emitter: RobotBackendEmitter = field(default_factory=RobotBackendEmitter)
    receipt_normalizer: RobotReceiptNormalizer = field(default_factory=RobotReceiptNormalizer)
