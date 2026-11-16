# L4: extensibility within declared scope

Decision: 12 November 2026. This is a source-mechanism assessment plus an existing
LabOP execution witness. No new program, simulation, or regression run was made.
The previously packaged replay covers M1–M4/L1–L3; this later L4 assessment is not
represented as a newly executable check in that frozen package.

## Predicate

Does the system provide an explicit extension point that integrates extensions
within its declared scope? Identify both registration/supply and consumption.
One established point suffices for this predicate; the extension area must be
reported, so Yes does not imply equal breadth across systems. Unrelated missing
extension categories do not negate the named mechanism.

This supersedes the earlier, broader common-new-capability/regression criterion.
The scope principle follows Kazman, Echeverría and Ivers, *Extensibility*,
CMU/SEI-2022-TR-002, §§3–4:
https://sei.cmu.edu/library/file_redirect/2022_005_001_876979.pdf/ .
The binary existence-and-integration check is our operationalization, not a
complete application of that report's cost, risk and quality analysis.

## Culsma 1.0.7 — Yes

Pinned source: `5364676bc2437b4981a00ce0133c730af243e469`.
`src/culsma/scientific_model/registry.py` defines `register_and_bind(provider)`.
`resolver.py` selects a provider for a capability/contract-version pair and invokes
`provider.resolve(request)`, checking the result and provenance.
`scientific_model/__init__.py` contains an actual registration:

```python
registry.register_and_bind(BuiltinMaterialRulebookProvider())
```

The table uses `provider` as the API argument placeholder, not a newly executed
custom model. The scope is provider implementation within supported contracts;
it does not establish arbitrary new capability types or open registration of
all experimental program kinds.

## LabOP 1.0a2 — Yes

Pinned source: `2e2bd88150c71a440771fd369f40295dfd622324`.
The retained `gfp_labop_extended.py` registers the implementation in `fractionation.py`:

```python
engine.prov_observer.handlers[fractionation.identity] = FractionationUpdater
```

LabOP's paper explicitly supports custom operation libraries and execution
specializations; its upstream pH example also customizes output computation.
The specific provenance registration above is available in source, without an
equivalent public API documentation guarantee established here. This Yes is
about demonstrated integration, not documentation completeness.

The retained extended GFP execution and `results/comparison.json` demonstrate consumption
of this updater. It versions fraction sample states and supplies ancestry edges
under the stipulated model. This does not establish native solid-component
accounting, arbitrary scientific-model coverage or a full regression assessment.

### Current table example (15 November 2026)

The manuscript now leads with the custom-primitive mechanism:
`labop.Primitive("ClarifyLysate")` in `fractionation.py`, together with its
output-computation callback. The retained extended execution in
`results/labop/run-status.json` records the two outputs used downstream.
Custom operation libraries and execution specializations are described by
the LabOP paper; the pinned README's **Protocol Execution** section also
explicitly documents `BehaviorSpecialization`. The latter is documentation
of another extension mechanism, not a claim that this GFP run uses a custom
`BehaviorSpecialization`. The provenance handler registration above remains
an additional source-level mechanism needed for this example's material
updates, not the primary table example. No new execution was performed.

## BPL — Yes

Pinned source: `4e505740f5025d59ba655c6c955f83876f753007`.
`bpl/simulation/simulator.py::Simulator.add_step_callback` appends the supplied
callback to `_step_callbacks`. `simulate` invokes the registered callbacks after
a step has executed and its trace has been added:

```python
for callback in self._step_callbacks:
    callback(step, self.deck_state)
```

The table's `simulator.add_step_callback(callback)` is an API usage excerpt;
no new callback run is claimed. Its declared scope is post-step processing with
access to the step and deck state. This is not evidence of a replaceable
scientific-model dispatcher or an external backend registration API. The fixed
CLI target table therefore does not negate this scoped L4 Yes.
