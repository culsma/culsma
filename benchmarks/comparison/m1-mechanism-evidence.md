# M1: entity distinction and reference mechanisms

Decision date: 11 November 2026. This is a source review with retained protocol witnesses, not a new execution test. The active definition is in [the indicator specification](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/comparison_indicator_spec.md). Its conceptual basis is [ITU-T X.902 (2009)](https://www.itu.int/rec/dologin_pub.asp?id=T-REC-X.902-200910-I%21%21PDF-E&lang=e&type=items), §§6.1, 8.1 and 12.1–12.8. The experimental scope is our operationalization.

| Check and scope | Culsma | LabOP | BPL |
|---|---|---|---|
| M1a: distinguishable declared containers/sample locations | 1, released, source and retained witness | 1, released, source and retained witness | 1, public repository mechanism, source and upstream witness inspection |
| M1b: distinct operation-product reference mechanism | 1, released separation slots and retained witness | 1, released output parameters/pins and ObjectFlow binding; custom separation supplies a witness of the existing mechanism | NE — mechanism not assessed |

## Current manuscript witness (15 November 2026)

LabOP M1 now cites the released-only program [gfp_labop.py](gfp_labop.py):
`EmptyContainer` and `PlateCoordinates` return `output_pin("samples")`
references consumed by later transfers. The retained [native result](results/gfp-labop-native/location_continuation/results.json)
and adjacent `protocol.ttl` / `execution.ttl` support this witness. The source
mechanism for declared outputs remains the one indexed below. The extended
fraction example below is historical supporting evidence, not the primary
M1 witness; separation-material semantics are assessed separately under M3.

## Culsma 1.0.7

Pinned commit: `5364676bc2437b4981a00ce0133c730af243e469`.

- [Plan construction](https://github.com/culsma/culsma/blob/5364676bc2437b4981a00ce0133c730af243e469/src/culsma/pipeline/plan/statements.py): the constructor allocation path carries the declaration binding, protocol namespace and declaration name into `AllocContainer` (allocation block around lines 248–265).
- [Allocation](https://github.com/culsma/culsma/blob/5364676bc2437b4981a00ce0133c730af243e469/src/culsma/runtime/material/container_content.py): `apply_alloc_container` and `allocation_container_id` derive an allocation identifier from namespace, allocation-step identifier and name. Label and barcode are metadata on this path.
- [Reference resolution](https://github.com/culsma/culsma/blob/5364676bc2437b4981a00ce0133c730af243e469/src/culsma/runtime/material/refs.py): `bind_name` maps names to container IDs; `resolve_container_ref` resolves against bindings and the container store; structured indexed references use indexed bindings.
- Witness: [gfp.culs](gfp.culs), with separate lysate, buffer and resuspension containers and downstream references; accepted/consumed in the [retained run](results/culsma/run.json). M1b uses `lysate.contents[0]` and `[1]` under the centrifugation slot contract.

This supports the declared-container mechanism and the retained product case. It does not establish uniqueness under every invocation pattern or identity for every component entry.

## LabOP 1.0a2

Pinned commit: `2e2bd88150c71a440771fd369f40295dfd622324`.

- [Sample-array primitives](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop/lib/sample_arrays.py): `EmptyContainer` returns a `SampleArray`; `PlateCoordinates` takes a collection plus coordinates and returns selected samples.
- [SampleArray](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop/sample_array.py): collection state includes container/location coordinates and sample identifiers. `new_sample_id` uses the collection name and a counter; this review does not claim collision-free sample IDs under duplicate-name variants.
- Witness: the container/select helpers in [gfp_labop_extended.py](gfp_labop_extended.py) connect distinct collection outputs to operations. These declaration/reference mechanisms are released library features even though the later fractionation step is extended. [Retained execution status](results/labop/run-status.json).
- [Spin](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop/lib/plate_handling.py) declares `location`, `duration` and `acceleration` inputs and no outputs. This is a standard-operation inventory gap for the fractionation task, not a negative M1b mechanism verdict.
- [ClarifyLysate](fractionation.py) adds `supernatant` and `pellet` outputs and their interpretation. The [retained comparison](results/comparison.json) supports M1b for this extension.

### Corrected M1b mechanism judgment

The initial table mixed a released-library signature finding with a system-level modeling question. Source inspection establishes that LabOP already provides the relevant general mechanism:

1. [Behavior.add_output](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/uml/behavior.py#L85) adds named output parameters. Its parameter list supports multiple outputs.
2. [Activity.add_call_behavior_action](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/uml/activity.py#L366) creates a separate OutputPin for each declared output parameter and connects it to the producing action.
3. [Action.output_pin](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/uml/action.py#L121) resolves a pin by name and rejects missing or ambiguous matches.
4. [Activity.call_behavior/use_value](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/uml/activity.py#L232) connects these output references to later input pins through ObjectFlow.

The [retained authoring program](gfp_labop_extended.py) calls `output_pin("supernatant")` and `output_pin("pellet")` separately and supplies them to downstream transfers. The [successful retained execution](results/labop/run-status.json) records both fraction outputs. These use the released mechanisms above. The custom primitive and its updater supply the task's separation semantics and computation; they do not implement a new general multi-output reference system.

Therefore **LabOP M1b = 1 at the product-reference mechanism level**. No claim follows that every released operation supplies all required products, that arbitrary output names imply distinct physical materials, or that every output-state computation is correct. A defined operation contract must identify its material products; the mechanism carries their separate references. BPL remains unassessed here, not unsupported. This correction uses inspected source and retained evidence, not a new execution.

## BPL public source snapshot

Official repository: [bota-biosciences-public/bpl-code](https://gitlab.com/bota-biosciences-public/bpl-code). Pinned commit: `4e505740f5025d59ba655c6c955f83876f753007`, dated 26 June 2026. This is a public repository snapshot, not an inferred numbered release or a claim about the preprint's exact implementation version.

- [Declarations](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/ast/declarations.py): named `LabwareDecl`, distinct from reagent/type descriptions.
- [Plan IR](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/lowering/plan_ir.py#L109): `WellRef(plate_id, well_id)` and `ContainerRef(container_id)` explicitly represent locations/containers.
- [Orchestrator](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/orchestrator.py#L1091): `_location_from_expression` and `_cached_location` map names to reusable `WellRef` values; distinct initial names receive distinct positions. This path uses a synthetic 96-position mapping that wraps after 96 allocated names; no unbounded uniqueness or physical-layout fidelity is claimed by M1a.
- [State model](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/state/state_model.py#L269) has `ContainerContents.container_id`; [virtual deck](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/simulation/virtual_deck.py#L285) stores and retrieves labware by `labware_id`. These additional structures are source evidence, not proof that every frontend path uses each structure.
- Witness: [upstream LB protocol and parser tests](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/tests/conformance/test_lb_media_prep.py) declare `Beaker1L` and `GlassBottle1L`, then transfer between them. The protocol and test assertions were inspected, not executed here. No new acceptance or runtime pass is claimed.

M1a is 1 for the small declared-container witness and inspected resolution mechanism. BPL's fraction products, aliases, repeated invocations and runtime identity-preservation variants remain unassessed.

## Interpretation and amendment record

The previous M1a NE entries required an equal-description runtime contrast to decide a modeling property. They are superseded by these explicitly scoped mechanism decisions. Matching descriptive attributes are an illustrative distinction, not a requirement to duplicate an identifier that a language defines as unique. Component-level distinctions require their own task-specific audit. Runtime mutation isolation, renaming, reference swaps and scale are separate implementation/validity checks; their absence does not negate the established modeling mechanism.

Culsma's formal lowering and ordered-binding arguments motivate inspecting preservation across layers, but do not constitute a proof of the complete implementation or a requirement that competitors use the same representation.

## Domain structure alongside identity (12 November 2026)

The revised M1 row also describes domain object kinds and constituent structure.
This supplements, rather than reverses, the scoped M1a/M1b reference decisions.
ITU-T X.902 §9.9 supplies the type concept alongside §8.1 object distinctness
and §12 naming. It does not require distinct implementation classes or an
independent source language for each domain type.

- Culsma's retained [source](gfp.culs) declares `tube(...)` and `plate(...,
  format = "96well")`, selects `assay[A1]`, and uses `lysate.contents[0]`
  and `[1]` under the centrifugation product contract. The existing plan and
  allocation paths above support the reference mechanism. This does not
  establish every container-type or selector-validation rule.
- LabOP's pinned [model vocabulary](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop/inner/labop.ttl)
  defines `SampleArray` as a logical sample collection linked to a
  `ContainerSpec`; its logical dimensions need not equal physical container
  layout. The pinned [container ontology](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop/container-ontology.ttl)
  defines `MicrofugeTube1.5mL` and `Plate96Well`, including a 96-well
  restriction for the latter. [The retained authoring code](gfp_labop_extended.py)
  uses these specifications and `PlateCoordinates` to select wells.
  A shared SampleArray class and its array/JSON content storage therefore
  do not imply absent domain types or structure. This source inspection
  does not establish complete ontology enforcement or physical-layout fidelity.
- BPL's previously inspected `LabwareDecl`, `ContainerRef`, and `WellRef`
  supply evidence of labware declarations and structured internal references.
  Complete structure/applicability rules and operation products remain unassessed.

These are descriptions of inspected modeling mechanisms, not new execution
results or an aggregate structure score. The meaningful contrast is what the
protocol model defines and exposes, not whether its implementation uses Python.
