"""Material operation handlers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from culsma.pipeline.plan_nodes import PlanStep
from culsma.runtime.material.container_content import (
    apply_alloc_container,
    apply_annotate_content,
    apply_define_content,
    apply_load_content,
)
from culsma.runtime.material.mutation import apply_mutation
from culsma.runtime.material.organization import apply_agit
from culsma.runtime.material.separation import apply_frac, apply_sep
from culsma.runtime.material.result import MaterialUpdateResult


class MaterialOpHandler(ABC):
    ops: frozenset[str] = frozenset()

    def handles(self, op: str) -> bool:
        return op in self.ops

    @abstractmethod
    def apply(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        raise NotImplementedError


class ContainerContentHandler(MaterialOpHandler):
    ops = frozenset({"AllocContainer", "DefineContent", "LoadContent", "AnnotateContent"})

    def apply(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        if step.op == "AllocContainer":
            return apply_alloc_container(step, state)
        if step.op == "DefineContent":
            return apply_define_content(step, state)
        if step.op == "LoadContent":
            return apply_load_content(step, state)
        if step.op == "AnnotateContent":
            return apply_annotate_content(step, state)
        return MaterialUpdateResult(material_state=state, diagnostics=[], delta={})


class MutationHandler(MaterialOpHandler):
    ops = frozenset({"Mutation"})

    def apply(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        return apply_mutation(step, state)


class SeparationHandler(MaterialOpHandler):
    ops = frozenset({"sep", "frac"})

    def apply(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        if step.op == "sep":
            return apply_sep(step, state)
        if step.op == "frac":
            return apply_frac(step, state)
        return MaterialUpdateResult(material_state=state, diagnostics=[], delta={})


class OrganizationResetHandler(MaterialOpHandler):
    ops = frozenset({"agit"})

    def apply(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        return apply_agit(step, state)


class NoopMaterialOpHandler(MaterialOpHandler):
    ops = frozenset()

    def handles(self, op: str) -> bool:
        return True

    def apply(self, step: PlanStep, state: dict[str, Any]) -> MaterialUpdateResult:
        return MaterialUpdateResult(material_state=state, diagnostics=[], delta={})
