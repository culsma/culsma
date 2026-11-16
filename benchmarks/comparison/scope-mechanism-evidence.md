# M4: scope and binding

12 November 2026. This replaces the earlier M4 interpretation as handling or
temporal requirements. It concerns visibility and reference resolution in the
protocol representation. The comparison does not require a particular syntax,
shadowing policy, implementation language, or object-storage representation.

## Basis and operational definition

[Russell et al., Workflow Data Patterns](https://www.vdaalst.com/publications/p220.pdf),
§2.2, Pattern 3 (Scope Data), printed pp. 9–10, concerns data visible to a subset
of workflow tasks. Its example makes X accessible to tasks A/B/C but not D/E.
This is a visibility concept, not a requirement about experimental environments.
The present criterion adapts that concept to protocol-local declarations and
references; it is not a verbatim criterion prescribed by the reference.

**M4. Scope and binding.** Does the protocol system define and implement where
declared names or data references can be used, including controlled access across
procedure or model boundaries?

A positive witness combines permitted use with rejection of a prohibited direct
reference. A negative witness is a declaration/reference syntax whose binding
or visibility rules are not implemented on the evaluated route. Source-local
name resolution and model-element ownership must be recorded separately:
support for one is not proof of the other. Explicit parameters and returns may
legitimately expose data without exposing its original local name.

## Culsma 1.0.7 — source binding

Frozen commit `5364676bc2437b4981a00ce0133c730af243e469`:
`pipeline/scope/analysis.py` constructs scope frames and slots;
`resolve_slot_from_frame` follows parent frames. `component_expander.py`
binds arguments and renames expanded local declarations per invocation.
`pipeline/validate/binding.py` diagnoses unbound names. Source-local uniqueness
checks forbid duplicate local names across a protocol: do not assume an
inner-scope shadowing policy merely because parent frames exist.

The [probe](check_scope.py), using `validate(..., enforce_binding=True)`, accepts
two calls to a procedure that returns its local tube. A direct use of that
procedure's `local` name in the caller is rejected as
`SEM_UNBOUND_NAME_REFERENCE`, at source line 7, column 11.

## LabOP 1.0a2 — host binding and model boundaries are separate

Frozen commit `2e2bd88150c71a440771fd369f40295dfd622324`:
Python governs Python local names. LabOP's UML activity model separately owns
nodes, input/output parameters and object flows. `uml/activity.py::use_value`
rejects a source or target owned by another activity. Its execution contexts
also distinguish activity invocations and their input/output mappings.

The probe creates a model input inside a Python helper. The input belongs to
the explicitly supplied parent protocol; the helper does not create a new
protocol scope and its name is absent from serialized RDF. Directly connecting
that input into another activity with `use_value` raises a membership error.

Consequently, LabOP is **Yes for the inspected model-boundary mechanism**.
This does not mean its protocol checker analyzes the Python helper's local
bindings. Conversely, the architecture difference does not justify saying
LabOP has no scope. Python visibility rules are defined in its
[execution-model reference, §4.2](https://docs.python.org/3/reference/executionmodel.html#resolution-of-names).

## BPL — syntax versus implemented binding

The pinned BPL source has local-declaration syntax but its inspected check/plan
route does not evaluate those bindings. See the
[BPL mechanism audit](bpl-modeling-evidence.md#m4--no-for-implemented-local-binding-resolution-on-this-route).
The current No is scoped to that implementation route, not a claim that BPL's
syntax cannot express blocks or that a future compiler could not implement scope.

## Reproduction

Run `benchmarks/local-results/comparison-runtime/culsma-env/bin/python benchmarks/comparison/check_scope.py`
from the manuscript root. [Recorded results](results/scope-mechanisms.json)
contain the accepted/rejected Culsma sources and LabOP ownership/error evidence.
These are construction and validation checks, not device executions.

## Packaged documented-syntax witness (16 November 2026)

The current manuscript's BPL witness uses local volume bindings in transfers,
not the earlier `wait` example. Unchanged copies of
[m4_let_10.bpl](results/bpl-m4/m4_let_10.bpl),
[m4_let_20.bpl](results/bpl-m4/m4_let_20.bpl), and the original
[CLI report](results/bpl-m4/result.json) are now in the submission evidence
package. Both cases report `SEMANTIC_MISSING_VOLUME` with exit 11 in check,
validate and simulation-plan lowering. The
[provenance note](results/bpl-m4/README.md) identifies the source audit,
unchanged-file hashes, and original message truncation. No rerun was made.
