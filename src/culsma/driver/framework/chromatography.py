"""Capability gate for registered chromatography extensions, before driver execution."""
from culsma.domains.fractionation import ACTIVE_CHROMATOGRAPHY_REGISTRY


class ChromatographyCapability:
    @staticmethod
    def required_types(value):
        registry = ACTIVE_CHROMATOGRAPHY_REGISTRY.get()
        if registry.is_extension(value):
            entry = registry.registration(value)
            return {(entry.stable_id, entry.version)}
        if isinstance(value, dict):
            return set().union(*(ChromatographyCapability.required_types(item) for item in value.values()))
        if isinstance(value, (list, tuple)):
            return set().union(*(ChromatographyCapability.required_types(item) for item in value))
        return set()

    @staticmethod
    def require_support(arguments, driver):
        required = ChromatographyCapability.required_types(arguments)
        supported = getattr(driver, 'supported_chromatography_types', frozenset())
        missing = required - set(supported)
        if missing:
            raise ValueError(f'Driver does not support chromatography types: {sorted(missing)}')
