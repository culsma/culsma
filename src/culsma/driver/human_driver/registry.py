"""Translator registry for the human driver."""

from __future__ import annotations

from dataclasses import dataclass, field

from culsma.driver.framework.registry import TranslatorRegistry

from .translators import (
    EnvironmentHoldTranslator,
    GenericTranslator,
    MutationTranslator,
    ObservationTranslator,
    SeparationTranslator,
    SetupTranslator,
)


def build_default_registry() -> TranslatorRegistry:
    return TranslatorRegistry(
        translators={
            "Mutation": MutationTranslator(),
            "env_hold": EnvironmentHoldTranslator(),
            "sep": SeparationTranslator(),
            "frac": SeparationTranslator(),
            "img": ObservationTranslator(),
            "ecp": ObservationTranslator(),
            "phy": ObservationTranslator(),
            "AllocContainer": SetupTranslator(),
            "DefineContent": SetupTranslator(),
            "LoadContent": SetupTranslator(),
            "AnnotateContent": SetupTranslator(),
            "FinalizeContainerContents": SetupTranslator(),
        },
        default_translator=GenericTranslator(),
    )
