"""Translator implementations for the human driver."""

from __future__ import annotations

from typing import Any

from culsma.driver.framework.mapping_core import value_to_text
from culsma.driver.framework.models import DriverProjection as HumanProjection
from culsma.driver.framework.models import MappingRecord as HumanMappingRecord


class GenericTranslator:
    def __init__(self, *, category: str = "instruction") -> None:
        self._category = category

    def translate(self, record: HumanMappingRecord, binding: dict[str, Any]) -> HumanProjection:
        detail_lines = list(_requirement_details(binding))
        return HumanProjection(
            step_id=record.step_id,
            semantic_op=record.semantic_op,
            channel="human",
            label=f"{record.semantic_op} Step",
            summary=f"Carry out the {record.semantic_op} step.",
            details=tuple(detail_lines),
            category=self._category,
            binding=dict(binding),
            payload={"semantic_args": dict(record.semantic_args)},
        )


class MutationTranslator:
    def translate(self, record: HumanMappingRecord, binding: dict[str, Any]) -> HumanProjection:
        target = value_to_text(record.semantic_args.get("target"))
        rendered_sources, source_names, source_amounts = _render_mutation_sources(record.semantic_args.get("sources"))
        pipette_label = binding.get("pipette_label", binding.get("tool_label", "single-channel micropipette"))
        tip_label = binding.get("tip_label", "filtered pipette tip")
        strategy_kind = binding.get("strategy_kind", "pipette_transfer")
        amount_text = ", then ".join(f"transfer {text}" for text in rendered_sources) if rendered_sources else "transfer the prepared material"
        details = [
            f"Use {pipette_label} with a {tip_label}.",
            *_strategy_detail_lines(binding),
            *_requirement_details(binding),
            *_env_detail(binding),
        ]
        return HumanProjection(
            step_id=record.step_id,
            semantic_op=record.semantic_op,
            channel="human",
            label="Pipette Transfer Step",
            summary=f"Using {pipette_label}, {amount_text} into {target}.",
            details=tuple(_dedupe(details)),
            category="material",
            binding=dict(binding),
            payload={
                "target": target,
                "sources": source_names,
                "source_amounts": source_amounts,
                "strategy_kind": strategy_kind,
                "pipette_label": pipette_label,
                "tip_label": tip_label,
            },
        )


class EnvironmentHoldTranslator:
    def translate(self, record: HumanMappingRecord, binding: dict[str, Any]) -> HumanProjection:
        env_summary = binding.get("env_summary") or "the specified environment conditions"
        targets = value_to_text(record.env_targets)
        details = [f"Keep {targets} under {env_summary}.", *_requirement_details(binding)]
        return HumanProjection(
            step_id=record.step_id,
            semantic_op=record.semantic_op,
            channel="human",
            label="Environment Hold",
            summary=f"Keep {targets} under {env_summary}.",
            details=tuple(_dedupe(details)),
            category="environment",
            binding=dict(binding),
            payload={"targets": targets, "env_summary": env_summary},
        )


class SeparationTranslator:
    def translate(self, record: HumanMappingRecord, binding: dict[str, Any]) -> HumanProjection:
        sample = value_to_text(record.semantic_args.get("sample"))
        summary = _render_program_aware_separation_summary(record, sample)
        details = [*_requirement_details(binding), *_env_detail(binding)]
        return HumanProjection(
            step_id=record.step_id,
            semantic_op=record.semantic_op,
            channel="human",
            label="Separation Step" if record.semantic_op == "sep" else "Fractionation Step",
            summary=summary,
            details=tuple(_dedupe(details)),
            category="separation",
            binding=dict(binding),
            payload={
                "sample": sample,
                "program_kind": record.program_kind,
                "program_args": dict(record.program_args),
            },
        )


class ObservationTranslator:
    def translate(self, record: HumanMappingRecord, binding: dict[str, Any]) -> HumanProjection:
        sample = value_to_text(record.semantic_args.get("sample"))
        quantity = value_to_text(record.semantic_args.get("quantity"))
        details = [*_requirement_details(binding), *_env_detail(binding)]
        return HumanProjection(
            step_id=record.step_id,
            semantic_op=record.semantic_op,
            channel="human",
            label="Observation Step",
            summary=_render_observation_summary(record, sample, quantity),
            details=tuple(_dedupe(details)),
            category="observation",
            binding=dict(binding),
            payload={
                "sample": sample,
                "quantity": quantity,
                "program_kind": record.program_kind,
                "program_args": dict(record.program_args),
            },
        )


class SetupTranslator:
    def translate(self, record: HumanMappingRecord, binding: dict[str, Any]) -> HumanProjection:
        category, label, summary, details, payload = _render_setup_text(record)
        return HumanProjection(
            step_id=record.step_id,
            semantic_op=record.semantic_op,
            channel="human",
            label=label,
            summary=summary,
            details=tuple(details),
            category=category,
            binding=dict(binding),
            payload=payload,
        )


def _requirement_details(binding: dict[str, Any]) -> list[str]:
    raw_notes = binding.get("requirement_notes")
    if not isinstance(raw_notes, tuple):
        return []
    return [note for note in raw_notes if isinstance(note, str)]


def _render_mutation_sources(raw_sources: Any) -> tuple[list[str], list[str], list[str]]:
    if not isinstance(raw_sources, list):
        return [], [], []
    rendered: list[str] = []
    source_names: list[str] = []
    source_amounts: list[str] = []
    for item in raw_sources:
        if isinstance(item, dict) and item.get("kind") == "IRPair":
            source_name = value_to_text(item.get("left"))
            amount_text = value_to_text(item.get("right"))
            rendered.append(f"{amount_text} from {source_name}")
            source_names.append(source_name)
            source_amounts.append(amount_text)
            continue
        text = value_to_text(item)
        rendered.append(text)
        source_names.append(text)
    return rendered, source_names, source_amounts


def _env_detail(binding: dict[str, Any]) -> list[str]:
    env_summary = binding.get("env_summary")
    if isinstance(env_summary, str) and env_summary:
        return [f"Follow environment condition: {env_summary}."]
    return []


def _render_program_aware_separation_summary(record: HumanMappingRecord, sample: str) -> str:
    program_args = record.program_args
    if record.semantic_op == "sep" and record.program_kind == "centrifuge_program":
        drive = value_to_text(program_args.get("drive"))
        keep_source = value_to_text(program_args.get("keep_source"))
        if keep_source != "null":
            return f"Run centrifuge on {sample} at {drive}, keeping the {keep_source} fraction in the source container."
        return f"Run centrifuge on {sample} at {drive}."
    if record.semantic_op == "sep" and record.program_kind == "filtration_program":
        membrane = value_to_text(program_args.get("membrane"))
        drive = value_to_text(program_args.get("drive"))
        return f"Separate {sample} across a {membrane} membrane using {drive} drive."
    if record.semantic_op == "sep" and record.program_kind == "centrifugal_filtration_program":
        membrane = value_to_text(program_args.get("membrane"))
        drive = value_to_text(program_args.get("drive"))
        duration = value_to_text(program_args.get("duration"))
        duration_suffix = f" for {duration}" if duration != "null" else ""
        return f"Run centrifugal filtration on {sample} across a {membrane} membrane at {drive}{duration_suffix}."
    if record.semantic_op == "sep" and record.program_kind == "phase_partition_program":
        solvent = value_to_text(program_args.get("solvent"))
        return f"Separate {sample} by solvent partition using {solvent}."
    if record.semantic_op == "frac" and record.program_kind == "density_gradient_program":
        bins = value_to_text(program_args.get("bins"))
        axis = value_to_text(program_args.get("axis"))
        order = value_to_text(program_args.get("order"))
        return f"Collect {bins} ordered fractions from {sample} along the {axis} axis ({order})."
    if record.semantic_op == "frac" and record.program_kind == "chromatography_program":
        bins = value_to_text(program_args.get("bins"))
        axis = value_to_text(program_args.get("axis"))
        order = value_to_text(program_args.get("order"))
        return f"Collect {bins} carrier-mediated fractions from {sample} along the {axis} axis ({order})."
    action = "Separate" if record.semantic_op == "sep" else "Collect fractions from"
    return f"{action} {sample} using the configured {record.semantic_op} workflow."


def _render_observation_summary(record: HumanMappingRecord, sample: str, quantity: str) -> str:
    if quantity == "temperature":
        return f"Measure the temperature of {sample}."
    if record.semantic_op == "img" and quantity != "null":
        return f"Capture a {quantity} image of {sample}."
    return f"Record the requested {record.semantic_op} observation from {sample}."


def _render_setup_text(
    record: HumanMappingRecord,
) -> tuple[str, str, str, tuple[str, ...], dict[str, str]]:
    args = {key: value_to_text(value) for key, value in sorted(record.semantic_args.items())}
    op = record.semantic_op
    if op == "AllocContainer":
        bind_name = args.get("bind", "the container")
        kind = args.get("kind", "container")
        capacity = args.get("capacity")
        label = args.get("label")
        parts = [f"Prepare {bind_name} as a {kind}"]
        if capacity and capacity != "null":
            parts.append(f"with a working capacity of {capacity}")
        if label and label != "null":
            parts.append(f'and label it "{label}"')
        return (
            "setup",
            "Container Preparation",
            " ".join(parts) + ".",
            (),
            args,
        )
    if op == "LoadContent":
        amount = args.get("amount", "the specified amount")
        content = args.get("content", "the prepared content")
        container = args.get("container", "the destination container")
        return (
            "setup",
            "Initial Loading",
            f"Load {amount} of {content} into {container}.",
            (),
            args,
        )
    if op in {"DefineContent", "AnnotateContent"}:
        content = args.get("code") or args.get("content") or "the material definition"
        return (
            "internal_setup",
            "Content Definition",
            f"Register {content} for downstream execution.",
            (),
            args,
        )
    detail_lines = tuple(f"{key}: {value}." for key, value in args.items())
    return (
        "setup",
        "Setup Step",
        f"Prepare setup action {op}.",
        detail_lines,
        args,
    )


def _strategy_detail_lines(binding: dict[str, Any]) -> list[str]:
    if binding.get("multi_aspirate"):
        return ["Split this transfer into repeated pipetting cycles because the requested volume exceeds one stroke."]
    return []


def _dedupe(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        if isinstance(line, str) and line and line not in result:
            result.append(line)
    return result
