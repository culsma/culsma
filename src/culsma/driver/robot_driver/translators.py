"""Translator implementations for the robot driver."""

from __future__ import annotations

from culsma.driver.framework.mapping_core import value_to_text
from culsma.driver.framework.models import DriverProjection, MappingRecord


class GenericRobotTranslator:
    def translate(self, record: MappingRecord, binding: dict[str, object]) -> DriverProjection:
        return DriverProjection(
            step_id=record.step_id,
            semantic_op=record.semantic_op,
            channel="robot",
            label=f"{record.semantic_op} command",
            summary=f"Dispatch {record.semantic_op} to robot backend.",
            category="command",
            binding=dict(binding),
            payload={"semantic_args": _serialize_args(record.semantic_args)},
        )


class MutationRobotTranslator:
    def translate(self, record: MappingRecord, binding: dict[str, object]) -> DriverProjection:
        target = value_to_text(record.semantic_args.get("target"))
        sources = value_to_text(record.semantic_args.get("sources"))
        return DriverProjection(
            step_id=record.step_id,
            semantic_op=record.semantic_op,
            channel="robot",
            label="Mutation command",
            summary=f"Dispatch material transfer into {target}.",
            details=(f"Sources: {sources}.",),
            category="command",
            binding=dict(binding),
            payload={"target": target, "sources": sources},
        )


class EnvironmentRobotTranslator:
    def translate(self, record: MappingRecord, binding: dict[str, object]) -> DriverProjection:
        targets = value_to_text(record.env_targets)
        return DriverProjection(
            step_id=record.step_id,
            semantic_op=record.semantic_op,
            channel="robot",
            label="Environment command",
            summary=f"Dispatch environment hold for {targets}.",
            category="command",
            binding=dict(binding),
            payload={"targets": targets, "env": dict(binding.get("env_summary", {}))},
        )


class ObservationRobotTranslator:
    def translate(self, record: MappingRecord, binding: dict[str, object]) -> DriverProjection:
        sample = value_to_text(record.semantic_args.get("sample"))
        return DriverProjection(
            step_id=record.step_id,
            semantic_op=record.semantic_op,
            channel="robot",
            label="Observation command",
            summary=f"Dispatch {record.semantic_op} readout for {sample}.",
            category="command",
            binding=dict(binding),
            payload=_serialize_args(record.semantic_args),
        )


def _serialize_args(args: dict[str, object]) -> dict[str, str]:
    return {key: value_to_text(value) for key, value in sorted(args.items())}
