"""Human driver implementation."""

from __future__ import annotations

from dataclasses import dataclass, field

from culsma.driver.framework.driver import ProjectionDriver

from .backend_emitter import HumanBackendEmitter
from .binding_resolver import HumanBindingResolver
from .receipt_normalizer import HumanReceiptNormalizer
from .registry import TranslatorRegistry, build_default_registry


@dataclass
class HumanDriver(ProjectionDriver):
    """Capability-aware human driver with structured instruction output."""

    driver_kind: str = "human"
    ok_code: str = "DRV_HUMAN_OK"
    translator_registry: TranslatorRegistry = field(default_factory=build_default_registry)
    binding_resolver: HumanBindingResolver = field(default_factory=HumanBindingResolver)
    backend_emitter: HumanBackendEmitter = field(default_factory=HumanBackendEmitter)
    receipt_normalizer: HumanReceiptNormalizer = field(default_factory=HumanReceiptNormalizer)
