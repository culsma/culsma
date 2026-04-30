"""Container and content constructor semantic contracts."""

from __future__ import annotations

import re
from typing import Any

from culsma.common.diagnostics import Diagnostic
from culsma.pipeline.ir_nodes import IRArg, IRCall, IRList, IRPair, IRStep

from .resolution import ExprResolver

_CONTENT_KIND_WHITELIST = {"biosample", "reagent", "buffer", "control", "fraction", "waste", "other"}
_CONTAINER_KIND_WHITELIST = {"tube", "well", "chamber", "surface"}
_CONTENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_CONTENT_TYPE_CUSTOM_PREFIX = "custom_"
_STANDARD_CONTENT_TYPES_BY_KIND: dict[str, set[str]] = {
    "biosample": {
        "whole_blood",
        "plasma",
        "serum",
        "cell_pellet",
        "cell_lysate",
        "cell_suspension",
        "dna_sample",
        "sample_dna",
        "dna",
        "dna_solution",
        "dna_lysate",
        "dna_stock",
        "purified_dna",
        "template_dna",
        "amplicon",
        "extract",
        "reaction_mix",
        "tissue_piece",
        "mixed_cells",
        "adherent_cells",
        "plasmid_vector",
        "dna_insert",
        "solution",
        "cell_or_tissue_sample",
        "molecular_extract",
    },
    "buffer": {
        "buffer",
        "water",
        "diluent",
        "lysis_buffer",
        "wash_buffer",
        "te_buffer",
        "binding_buffer",
        "elution_buffer",
        "resuspension_buffer",
        "ethanol_wash_buffer",
        "column_wash_buffer",
        "column_wash_buffer_1",
        "column_wash_buffer_2",
        "phosphate_buffer",
        "reaction_buffer",
        "culture_media",
        "culture_medium",
        "reaction_media",
        "media",
        "drug_stock",
        "nucleic_acid_extraction_buffer",
        "molecular_extraction_buffer",
        "sequencing_read_buffer",
        "test_buffer",
    },
    "reagent": {
        "taq_polymerase",
        "precipitation_reagent",
        "feed",
        "nutrient_feed",
        "qpcr_master_mix",
        "dna_stain",
        "anticoagulant",
        "enzyme",
        "magnetic_bead",
        "agarose_powder",
        "vehicle_control",
        "positive_control_compound",
        "compound_x_low",
        "compound_x_mid",
        "compound_x_high",
        "compound_x_max",
        "drug_x",
        "compound_x_stock",
        "standard_mix",
        "plate_stain",
        "fluor_quant_mix",
        "fluor_antibody",
        "fragmentation_reagent",
        "adapter_mix",
        "ligation_reagent",
        "cleanup_reagent",
        "amplification_reagent",
        "ionization_reagent",
        "powder",
    },
    "fraction": {
        "pellet",
        "supernatant",
        "retentate",
        "filtrate",
        "target_phase",
        "precipitate",
        "washed_dna_pellet",
    },
}


class ConstructorValidator:
    @staticmethod
    def validate_container_content_constructor_semantics(
        step: IRStep,
        literal_bindings: dict[str, Any],
        *,
        content_whitelist_mode: str,
        content_type_policy: str,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        if step.name == "AllocContainer":
            kind_arg = _find_arg(step, "kind")
            kind_value = ExprResolver.to_string(kind_arg.value, literal_bindings) if kind_arg is not None else None
            if kind_value is not None and kind_value not in _CONTAINER_KIND_WHITELIST:
                diagnostics.append(
                    Diagnostic(
                        code="SEM_INVALID_CONTAINER_KIND",
                        message=f"Unsupported container kind '{kind_value}'",
                        span=(kind_arg.span if kind_arg is not None else step.span),
                        node_id=step.id,
                    )
                )
            diagnostics.extend(
                ConstructorValidator.validate_surface_capacity_forbidden(
                    kind_value=kind_value,
                    capacity_arg=_find_arg(step, "capacity"),
                    span=step.span,
                    node_id=step.id,
                )
            )
            return diagnostics

        if step.name != "DefineContent":
            return diagnostics

        kind_arg = _find_arg(step, "kind")
        kind_value = ExprResolver.to_string(kind_arg.value, literal_bindings) if kind_arg is not None else None
        if kind_arg is None:
            diagnostics.append(
                Diagnostic(
                    code="SEM_MISSING_CONTENT_KIND",
                    message="DefineContent requires arg 'kind'",
                    span=step.span,
                    node_id=step.id,
                )
            )
            return diagnostics

        if kind_value is not None and kind_value not in _CONTENT_KIND_WHITELIST:
            diagnostics.append(
                Diagnostic(
                    code="SEM_INVALID_CONTENT_KIND",
                    message=f"Unsupported content kind '{kind_value}'",
                    span=kind_arg.span or step.span,
                    node_id=step.id,
                )
            )

        type_arg = _find_arg(step, "type")
        type_value = ExprResolver.to_text_token(type_arg.value, literal_bindings) if type_arg is not None else None
        if type_arg is None or type_value is None or not _CONTENT_TYPE_PATTERN.match(type_value):
            diagnostics.append(
                Diagnostic(
                    code="SEM_INVALID_CONTENT_TYPE_FORMAT",
                    message="content_type is required and must be a lowercase snake_case token",
                    span=(type_arg.span if type_arg is not None else step.span),
                    node_id=step.id,
                )
            )
            return diagnostics

        if type_arg is not None and type_value is not None and kind_value in _CONTENT_KIND_WHITELIST:
            if not _is_allowed_content_type_value(kind_value, type_value):
                diagnostics.append(
                    Diagnostic(
                        code="SEM_INVALID_CONTENT_TYPE_VALUE",
                        message=(
                            f"Unsupported content_type '{type_value}' for kind '{kind_value}'; "
                            "use a standard token or a custom_ prefixed token"
                        ),
                        span=type_arg.span or step.span,
                        node_id=step.id,
                    )
                )
        return diagnostics

    @staticmethod
    def validate_alloc_container_call(
        call: IRCall,
        *,
        literal_bindings: dict[str, Any],
        expr_bindings: dict[str, Any],
        node_id: str | None,
        content_whitelist_mode: str,
        content_type_policy: str,
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        kind_arg = _find_arg_by_name(call.args, "kind")
        kind_value = ExprResolver.to_string(kind_arg.value, literal_bindings) if kind_arg is not None else None
        if kind_arg is not None and kind_value is not None and kind_value not in _CONTAINER_KIND_WHITELIST:
            diagnostics.append(
                Diagnostic(
                    code="SEM_INVALID_CONTAINER_KIND",
                    message=f"Unsupported container kind '{kind_value}'",
                    span=kind_arg.span or call.span,
                    node_id=node_id,
                )
            )
        diagnostics.extend(
            ConstructorValidator.validate_surface_capacity_forbidden(
                kind_value=kind_value,
                capacity_arg=_find_arg_by_name(call.args, "capacity"),
                span=call.span,
                node_id=node_id,
            )
        )

        load_arg = _find_arg_by_name(call.args, "load")
        if load_arg is None:
            return diagnostics
        load_value = ExprResolver.resolve_bound_expr(load_arg.value, expr_bindings)
        if not isinstance(load_value, IRList):
            diagnostics.append(
                Diagnostic(
                    code="SEM_INVALID_LOAD_ITEM",
                    message="constructor load must be a list of content_spec:quantity items",
                    span=load_arg.span or call.span,
                    node_id=node_id,
                )
            )
            return diagnostics

        for item in load_value.elements:
            if not isinstance(item, IRPair) or not isinstance(item.left, IRCall) or item.left.name != "DefineContent":
                diagnostics.append(
                    Diagnostic(
                        code="SEM_INVALID_LOAD_ITEM",
                        message="constructor load items must be content_spec:quantity pairs",
                        span=item.span or load_arg.span or call.span,
                        node_id=node_id,
                    )
                )
                continue
            diagnostics.extend(
                ConstructorValidator.validate_define_content_call(
                    item.left,
                    literal_bindings=literal_bindings,
                    node_id=node_id,
                    content_whitelist_mode=content_whitelist_mode,
                    content_type_policy=content_type_policy,
                )
            )
        return diagnostics

    @staticmethod
    def validate_surface_capacity_forbidden(
        *,
        kind_value: str | None,
        capacity_arg,
        span,
        node_id: str | None,
    ) -> list[Diagnostic]:
        if kind_value != "surface" or capacity_arg is None:
            return []
        return [
            Diagnostic(
                code="SEM_SURFACE_CAPACITY_FORBIDDEN",
                message="surface constructor does not support volume capacity",
                span=(capacity_arg.span if getattr(capacity_arg, "span", None) is not None else span),
                node_id=node_id,
            )
        ]

    @staticmethod
    def validate_define_content_call(
        call: IRCall,
        *,
        literal_bindings: dict[str, Any],
        node_id: str | None,
        content_whitelist_mode: str,
        content_type_policy: str,
    ) -> list[Diagnostic]:
        step = IRStep(
            id=node_id or "<call>",
            name="DefineContent",
            args=call.args,
            span=call.span,
        )
        return ConstructorValidator.validate_container_content_constructor_semantics(
            step,
            literal_bindings,
            content_whitelist_mode=content_whitelist_mode,
            content_type_policy=content_type_policy,
        )


def _find_arg(step: IRStep, name: str):
    for arg in step.args:
        if arg.name == name:
            return arg
    return None


def _find_arg_by_name(args: list[IRArg], name: str) -> IRArg | None:
    for arg in args:
        if arg.name == name:
            return arg
    return None


def _is_allowed_content_type_value(kind_value: str, type_value: str) -> bool:
    if type_value.startswith(_CONTENT_TYPE_CUSTOM_PREFIX):
        return len(type_value) > len(_CONTENT_TYPE_CUSTOM_PREFIX)
    allowed = _STANDARD_CONTENT_TYPES_BY_KIND.get(kind_value, set())
    return type_value in allowed
