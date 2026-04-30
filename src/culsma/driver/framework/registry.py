"""Translator registry shared by drivers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeAlias

from .contracts import Translator
from .models import MappingRecord

TranslatorKey: TypeAlias = str | tuple[str, str]


@dataclass
class TranslatorRegistry:
    translators: dict[TranslatorKey, Translator] = field(default_factory=dict)
    default_translator: Translator | None = None

    def select(self, record: MappingRecord) -> Translator:
        translator = None
        if record.program_kind is not None:
            translator = self.translators.get((record.semantic_op, record.program_kind))
        if translator is None:
            translator = self.translators.get(record.semantic_op, self.default_translator)
        if translator is None:
            if record.program_kind is not None:
                raise LookupError(
                    f"No translator registered for semantic op '{record.semantic_op}' "
                    f"with program kind '{record.program_kind}'"
                )
            raise LookupError(f"No translator registered for semantic op '{record.semantic_op}'")
        return translator
