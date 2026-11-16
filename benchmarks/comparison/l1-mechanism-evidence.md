# L1: parameterized procedure reuse

12 November 2026. Pinned Culsma `5364676bc2437b4981a00ce0133c730af243e469`,
LabOP `2e2bd88150c71a440771fd369f40295dfd622324`, and BPL
`4e505740f5025d59ba655c6c955f83876f753007`.

## Predicate and basis

One procedure definition is invoked with different arguments. The system binds
actual arguments to formal parameters and uses the unchanged body for each
invocation. Syntax alone is insufficient. Source inlining and runtime activity
invocation are both admissible implementations. This is distinct from L2's
output-to-input composition across different procedures.

Russell et al., [Workflow Data Patterns](https://www.vdaalst.com/publications/p220.pdf),
Pattern 9, explicitly discusses parameter passing into sub-workflows and multiple
block tasks sharing one sub-workflow implementation. It is more direct support
for L1 than Block Data alone. The concrete witness and verdict rules below are
this study's operationalization, not a checklist copied from the paper.

The witness defines an aliquot procedure once and requests 10 uL and 20 uL
from a common stock into two different destinations. Culsma and LabOP are run
in software; BPL is parsed, checked and lowered. The comparison requires the
parameterized body to be realized, not merely printed as a call name. Neither
recursion nor every argument-binding variant is assessed here.

## Culsma — Yes on the inspected source/expansion/runtime route

`pipeline/component_expander.py` builds a procedure lookup and resolves calls.
`_bind_component_params` handles positional/named arguments and defaults, and
rejects missing, unknown and duplicated arguments. `_build_rename_map` and
`_inline_component_call` give expanded parameters/local declarations call-specific
names before processing the body. The implementation uses inlining; a distinct
runtime call frame is not required by L1.

The retained [program](results/l1/reuse.culs) calls `Aliquot` twice with the
same stock, different destinations, and 10/20-uL arguments. The
[execution output](results/l1/culsma/output.json) reports final destination
volumes of 10 and 20 uL, with no semantic, type, or runtime errors in the
[summary](results/l1/culsma/summary.json). This check concerns the argument-driven
liquid transfers; it does not validate unrelated aggregate mass projections.

## LabOP — model mechanism present; No for the evaluated execution routes

LabOP's `Protocol` is an activity with formal parameters. `uml/activity.py`
provides `input_value` and `call_behavior`, creating distinct calls to the same
behavior with value pins or object-flow inputs. `ExecutionContext.invoke_activity`
creates a child context for the called activity. Thus LabOP has a genuine
protocol-level parameterized invocation mechanism; this is not merely a Python
function generating unrelated protocols.

However, the inspected execution path has a parameter-propagation gap.
`ExecutionEngine.record_parameter_values` includes literal value-pin values in
the call record. In contrast, `next_tokens` passes inputs into the child context
by iterating over `record.get_incoming_flows()` whose sources are pins. Literal
arguments without those incoming flows are not propagated by that code path.
The two mechanisms therefore do not cover the same sources of argument values.

The [literal-argument model](results/l1/labop_literal/protocol.ttl) contains two
calls to the same Aliquot protocol. Document validation reports no errors. In
the [execution trace](results/l1/labop_literal/execution.ttl), the first call has
its arguments recorded, and the child receives source/destination data, but the
amount input does not execute. Neither requested Transfer executes. The run
reports `completed_normally=true` and no issues; this flag does not establish
completion of the requested work.

A second variant passes quantities through formal parent-protocol input ports,
using `ParameterValue`/`LiteralIdentified` as in the upstream input test. It also
validates, but its recorded execution contains neither requested Transfer. See
the [model](results/l1/labop_input_flow/protocol.ttl) and
[trace](results/l1/labop_input_flow/execution.ttl). Both results are retained. The cause of the input-flow variant
has not been isolated; it is a supplementary observation rather than evidence
that the literal-argument mechanism also explains this variant.

The current mechanism-grounded No uses the literal-argument route,
not an assertion that LabOP lacks parameterized activities or that all possible
model-level argument-flow arrangements fail. Construction and execution must
be distinguished when explaining the cell. No core or domain-handler patch was
made to obtain the findings.

## BPL — No on the evaluated public CLI route

The [independent BPL CLI audit](bpl-l1-evidence.md) now supplements the initial
parser/orchestrator probe. The installed `bplc parse`, `check`, and `lower`
commands were run without patches, for both human and simulation targets.
Direct 10/20-uL transfers produce the expected aspirate/dispense operations.
Two calls to a declared function instead produce only two `HumanStep` entries;
removing its declaration leaves those operation instructions unchanged.

The README's protocol-default pattern was also isolated: a declared
`amount: Volume = 10 uL` (or 20 uL) parses, but using `volume: amount` is rejected
as `SEMANTIC_MISSING_VOLUME`. The semantic gate and lowerer do not bind formal
parameters; the call emitter does not resolve user declarations and instantiate
their bodies. These mechanisms, with the controls, ground the scoped No.

The earlier [protocol-call program](results/l1/reuse.bpl) remains evidence of
what that input produces, not proof that callable protocols are documented.
The full upstream README block encounters a separate earlier syntax error;
that error is retained but excluded from the L1 verdict. See the
[public CLI results](results/l1/bpl-cli/results.json) for all commands, ASTs,
plans, exit codes and logs. No BPL simulator or hardware execution is claimed.

A HumanStep label is not itself a failure criterion. The conclusion concerns
missing binding/body realization. The [L2 consumption follow-up](l2-mechanism-evidence.md#a-humanstep-label-is-not-a-failure-criterion)
checks callee-body changes, generated human instructions and later simulation
handling rather than relying on the primitive type alone.

## Reproduction and interpretation

Run `benchmarks/local-results/comparison-runtime/culsma-env/bin/python benchmarks/comparison/check_l1.py`
from the manuscript root. The [script](check_l1.py) uses existing pinned
environments and records the source files, models, traces, and
[combined results](results/l1/results.json). Its Graphviz replacement saves DOT
instead of rendering an image; it does not implement binding or execution.

LabOP and BPL have different reasons for the scoped No. LabOP represents and
attempts a formal invocation, but the inspected argument-token path fails to
realize it. BPL's inspected lowering route does not instantiate the user-defined
procedure at all. The mechanism difference matters more than identical marks.

## Focused LabOP reproduction with a positive control

The standalone [counterexample script](labop_l1_counterexample.py) was rerun on
12 November 2026. Its two procedure calls are written explicitly, rather than
hidden in a Python comprehension or abbreviated as `Aliquot(...)`. Run from the
manuscript root:

```sh
benchmarks/local-results/comparison-runtime/labop-env/bin/python benchmarks/comparison/labop_l1_counterexample.py
```

Both variants start with a 100-uL stock and two empty destinations. The
counterexample calls the parameterized subprotocol twice; the positive control
calls Transfer directly with the same amounts. No LabOP implementation or
operation handler was modified. The installed `execution_engine.py`,
`execution_context.py`, and `uml/activity.py` match the pinned source byte for byte.

| Observation | Subprotocol calls | Direct Transfer control |
|---|---|---|
| Document validation errors | 0 | 0 |
| Requested calls | 2 | 2 |
| Entered requested calls | First only; 10 uL recorded | Both; 10 and 20 uL |
| Executed child input nodes | source and destination; not amount | Not applicable |
| Executed Transfers | 0 | 2 |
| Latest recorded stock volume | 100 uL | 70 uL |
| Latest recorded destination buffer quantities | Missing | 10 and 20 uL |
| `completed_normally` | true | true |
| Structured execution issues | Empty | Empty |

Missing destination quantities remain JSON null, not calculated zero volumes.
Omitted execution is evidenced by absent Transfer execution records and unchanged
stock. The direct control verifies the setup, standard transfer handling and
observation method. Logs contain unhandled-behavior warnings for protocol-level
observer hooks; empty structured issues do not mean stderr is empty.

Read the [subprotocol summary](results/l1/labop-reproduction/subprotocol/summary.json),
[direct-control summary](results/l1/labop-reproduction/direct/summary.json),
[combined report](results/l1/labop-reproduction/comparison.json), and
[captured run log](results/l1/labop-reproduction/execution-log.txt).
Each variant also retains its protocol, execution RDF and sample graph.
This is a counterexample to faithful realized reuse on the tested argument path
in this version, not proof that the model cannot express parameterized procedures.

## Public API and official workflow verification

The upstream source explicitly uses the same subprotocol authoring API:

- [test/test_subprotocols.py, lines 14–24](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/test/test_subprotocols.py#L14)
  creates Protocol objects and calls `protocol.primitive_step(subprotocol1)`.
- [The pH calibration example, lines 379–386](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/examples/protocols/pH_calibration/pH_calibration.py#L379)
  calls `execute_primitive(adjust_subprotocol, ...)` with sample references and
  literal `sbol3.Measure` arguments, then connects control flow with `order`.
- [Protocol.primitive_step, lines 92–104](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop/protocol.py#L92)
  wraps `execute_primitive` and adds sequential ordering. The Protocol argument
  is therefore supported by upstream usage, despite the Primitive annotation.
- The [official quickstart](https://bioprotocols.github.io/labop/quickstart/)
  presents `primitive_step` as a client-facing authoring API. It does not itself
  document the full parameterized subprotocol case; the test and example above
  supply that evidence.

[check_labop_l1_public_api.py](check_labop_l1_public_api.py) additionally runs:

1. The actual upstream `TestSubprotocols.test_subexecutions` test, redirecting
   only its output directory and Graphviz rendering: **passes**, one test,
   zero failures/errors. This test contains basic subprotocols without inputs;
   it does not cover the quantity-parameter case.
2. The parameterized counterexample through upstream `ProtocolHarness`, using
   the document/protocol supplied to its entry point and the harness's own
   execution-engine construction: **zero Transfers**, normal-completion flag
   true, and an empty structured issue list.
3. The counterexample using `execute_primitive` with explicit call ordering
   and explicit final-node connections in both caller and callee: **zero
   Transfers**, stock still 100 uL, and the same completion/issue outcome.

These checks exclude an unsupported internal call API, bypassing the official
harness, and omitted explicit ordering/final-node links as explanations for
the observed result. They do not certify every backend or authoring variant.
The README describes default specialization as primarily a testing/development
facility; these findings concern that software execution/token/state path,
not physical instrument execution.

Reproduce with
`benchmarks/local-results/comparison-runtime/labop-env/bin/python benchmarks/comparison/check_labop_l1_public_api.py`.
Read the [results](results/l1/public-api-audit/results.json),
[upstream test transcript](results/l1/public-api-audit/upstream-test.txt), and
[full log](results/l1/public-api-audit/execution-log.txt).

## Authoring precedent and excluded variant (16 November 2026)

The pinned upstream pH-calibration source, indexed above, calls a subprotocol
with literal `sbol3.Measure` arguments. This supports the authoring form used
by the L1 witness; it is not offered as a successful execution of the complete
pH example. Execution evidence for the current No remains the retained
literal-argument probe and its controls.

Variant E from the earlier `notes/comparison/verification_2026-11-12/labop_l1_variants/`
audit is not used in the manuscript's L1 judgment. Its string/sample failure
has no isolated cause in the current evidence analysis. It is not an additional
mechanism witness or a submission-package dependency. The packaged input-flow
variant remains explicitly identified as a supplementary observation.
