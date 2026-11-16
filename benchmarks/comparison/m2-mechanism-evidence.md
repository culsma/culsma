# M2 evidence: quantity representation and dimensional enforcement

**Current evidence index (15 November 2026):** M2 is Culsma **Yes** for the
inspected duration rule, LabOP **No** at the tested validation entry point,
and BPL **No** on the inspected source-to-plan path. The BPL finding is
established by the subsequent [BPL mechanism audit](bpl-modeling-evidence.md#m2--no-on-the-inspected-source-to-plan-route)
and `results/bpl-modeling/results.json`. The earlier BPL pending/not-run entries
and I1 labels below describe the historical paired-check stage, not the current
M2 verdict or an additional active indicator.

**12 November amendment:** the active M2 criterion now evaluates dimensional consistency for experimental parameters. Its current duration-rule verdict is Culsma **Yes**, LabOP **No** at the tested `document.validate()` entry point, and BPL **pending**. The representation-only findings below remain historical evidence, not the current M2 table verdict. I1 reports diagnostic details from the same check.

Original decision date: 11 November 2026. The earlier M2 scope covered the common volume witness and representation mechanisms; this scope has now been expanded as stated above. See [active definition](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/comparison_indicator_spec.md) and [architecture argument record](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/comparison_language_architecture_notes.zh.md).

| Scope | Culsma 1.0.7 | LabOP 1.0a2 | BPL public snapshot |
|---|---|---|---|
| Numeric value, unit, and defined volume dimension | 1 | 1 | 1 |

## Mechanism evidence

- Culsma commit `5364676bc2437b4981a00ce0133c730af243e469`: [AST Quantity](https://github.com/culsma/culsma/blob/5364676bc2437b4981a00ce0133c730af243e469/src/culsma/parser/ast_nodes.py) separates value and unit; [unit definitions](https://github.com/culsma/culsma/blob/5364676bc2437b4981a00ce0133c730af243e469/src/culsma/common/quantity_arithmetic.py) map uL/mL/L to volume. [GFP witness](gfp.culs) and retained accepted run supply protocol evidence.
- LabOP commit `2e2bd88150c71a440771fd369f40295dfd622324`, with pinned `sbol3==1.2.0.post0` and `tyto==1.4`: `sbol3.Measure` has a numeric value and unit URI. The bundled OM vocabulary defines microlitre through a prefix and litre reference and supplies its volume dimension. [GFP authoring witness](gfp_labop_extended.py) and [retained RDF model](results/labop/protocol.ttl) use this mechanism. [SBOL 3.0.1 Appendix A.2.1](https://sbolstandard.org/docs/SBOL3.0.1.pdf) defines the measure structure; dimensions come from the unit vocabulary rather than an inferred Python class name.
- BPL commit `4e505740f5025d59ba655c6c955f83876f753007`: inspected [grammar](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/grammar/bpl.lark), [QuantityExpr](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/ast/expressions.py), [unit registry](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/types/unit_engine.py), and [dimension representation](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/types/dimensions.py). Value/unit syntax is mapped to units with dimensional definitions, including uL volume. Evidence is source inspection of the acceptance/representation mechanism, not a new BPL parser or runtime run. No equivalence of internal dimensional bases is claimed.

These decisions do not establish exhaustive unit coverage, correct compound-unit arithmetic, temperature conversion, or operation-specific dimension rejection.

## Pre-run fault check: revised M2, with I1 diagnostic details

Expected rule fixed by the experimental meaning of duration: accept 10 min; reject 10 µL as a duration. The positive and negative cases within each system differ only in the duration unit. The Culsma case uses the existing GFP source and changes its environment duration. The LabOP case constructs a minimal standard Spin with an input sample and fixed acceleration. No fractionation extension is used.

| Entry point / stage | Valid input | Invalid input | Scoped I1 outcome |
|---|---|---|---|
| Culsma parsing/resolution/compilation followed by typecheck, before protocol execution | Accepted | `TYPE_ENV_DURATION_DIMENSION_MISMATCH`, line 12, column 36 | 1 — detected and localized |
| LabOP protocol construction followed by `document.validate()`, before protocol execution | No errors or warnings | No errors or warnings | 0 — rejection absent at this entry point |
| BPL | Not run | Not run | NE |

Reproduce using the existing environments prepared by [reproduce.sh](reproduce.sh):

```bash
python3 benchmarks/comparison/check_duration_units.py \
  --output benchmarks/comparison/results/duration-unit-check.json
```

[The observer](check_duration_units.py) retains diagnostic locations, messages, environment versions, selected input/source hashes and raw subprocess logs in [the report](results/duration-unit-check.json). It does not supply missing experimental semantics to either system. Reported commit pins are the prepared environment provenance, not a new independent verification of every installed file.

The [standard Spin declaration](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop/lib/plate_handling.py) types duration as `sbol3.OM_MEASURE` with a time comment. Culsma's [environment quantity check](https://github.com/culsma/culsma/blob/5364676bc2437b4981a00ce0133c730af243e469/src/culsma/pipeline/typecheck/expressions.py) requires the time dimension and carries source spans. These inspected paths explain the observed difference at the named entry points.

This is a matched rule/fault comparison, not matched complete protocol executions. No claims concern equipment behavior, all LabOP validators/backends, or inability to add a validator. The result demonstrates an implementation difference and motivates distinguishing modeling from validation; it does not establish that standalone syntax necessarily causes better checking.

## Parameter-contract clarification (15 November 2026)

The manuscript now leads with the parameter-contract mechanism rather than
with `Spin`. In the pinned source, `uml/behavior.py::Behavior.add_parameter`
records a type URI, direction, cardinality and optional default. The inspected
`plate_handling.py` and `liquid_handling.py` libraries use `sbol3.OM_MEASURE`
for parameters requiring different dimensions; time/volume annotations in
comments do not add dimensional restrictions. These signatures do not provide
the parameter-specific dimensional contract needed by the tested document
validation path. The accepted `Spin` fault is a retained manifestation of this
boundary. It does not establish absence of dimensional checking in every
execution specialization. Culsma's counterpart uses the shared
`validate_quantity_dimensions` validator with parameter-specific expected
dimensions; BPL's evaluated lowering uses `_numeric_value` without consuming
its separate unit engine's dimensional checks. No new execution was made.

## Enforcement-boundary check (16 November 2026)

In the pinned BPL `bpl/` tree, imports of `unit_engine` / `dimensions` are
confined to `bpl/types/`; the inspected source-to-plan orchestration extracts
numeric quantity values through `_numeric_value` instead of calling this
engine. The import search corroborates that concrete call-path finding; it
is not a proof about all possible tools or dynamically loaded integrations.

LabOP's `SampleProvenanceObserver.standardize` normalizes volume-compatible
units to microlitres and otherwise returns the quantity in its existing unit.
It takes no expected parameter dimension. This function is therefore not a
parameter-dimension validator, but that fact does not establish absence of
checks in every execution handler or specialization. The manuscript's M2 No
remains scoped to the evaluated document-validation path.
