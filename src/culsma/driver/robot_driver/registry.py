"""Translator registry for the robot driver."""

from __future__ import annotations

from culsma.driver.framework.registry import TranslatorRegistry

from .translators import EnvironmentRobotTranslator, GenericRobotTranslator, MutationRobotTranslator, ObservationRobotTranslator


def build_default_registry() -> TranslatorRegistry:
    generic = GenericRobotTranslator()
    return TranslatorRegistry(
        translators={
            "Mutation": MutationRobotTranslator(),
            "env_hold": EnvironmentRobotTranslator(),
            "sep": generic,
            "frac": generic,
            "img": ObservationRobotTranslator(),
            "ecp": ObservationRobotTranslator(),
            "phy": ObservationRobotTranslator(),
            "agit": generic,
            "AllocContainer": generic,
            "DefineContent": generic,
            "LoadContent": generic,
            "AnnotateContent": generic,
        },
        default_translator=generic,
    )
