"""Language domains and their source-type composition, independent of execution.

Initialize the complete built-in catalog before exposing any domain registry.
This keeps direct Python domain imports consistent with frontend imports.
"""
from .registry import EXTERNAL_CALL_CONTRACTS, EXTERNAL_ENUM_TYPES
