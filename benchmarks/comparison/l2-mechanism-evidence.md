# L2: composition across procedures

12 November 2026. Versions remain Culsma 1.0.7 (`5364676b`), LabOP 1.0a2
(`2e2bd88`), and BPL package metadata 2.4.0 (`4e505740`).

## Meaning and basis

**Criterion:** Can the output of one separately defined procedure become the
input of another through the protocol's defined input/output mechanism?

L1 concerns reusing a definition with different arguments. L2 additionally
requires returning a result across a procedure boundary and connecting that
result to another procedure. Calling A and B in sequence without passing A's
result, or chaining two built-in primitives, is not sufficient evidence.

The conceptual basis is Russell et al., [Workflow Data Patterns](https://www.vdaalst.com/publications/p220.pdf):
Pattern 8 covers task-to-task data interaction, Pattern 9 data entering a
sub-workflow, and Pattern 10 data returned from a sub-workflow to its caller.
This criterion and its experimental witness are our operationalization, not a
verbatim standard. The earlier two-fraction example is an illustration, not
a requirement that composition must involve separation or two outputs.

## Minimal witness

A producer returns a sample reference. A consumer receives that result and
uses it as the source of a 10-uL transfer. In the Culsma and LabOP executions,
the producer prepares 100 uL of buffer; the expected final quantities are
90 uL in the source and 10 uL in the target. BPL tests source-to-plan binding
of an existing declared container reference; it does not simulate preparation
or material quantities and is not a matched material execution.

| System and route | Observed result | Interpretation |
|---|---|---|
| Culsma compile and software execution | Producer-local sample returned, passed to consumer; final source/target 90/10 uL | Yes for this single-result composition witness |
| LabOP standard subprotocol calls | Model validation succeeds; consumer receives two `sample` parameter values and execution raises a cardinality error | No for successful execution of this connected-output witness; the model has genuine composition interfaces |
| LabOP with explicit final-node ordering | Same validation and execution outcome | Adding explicit final links does not resolve this failure |
| LabOP direct-operation control | Final source/target 90/10 uL | Setup and standard Provision/Transfer handling work |
| BPL public CLI, human and simulation targets | Parses/checks; `let prepared = prepare()` contributes no operations; consumer remains one HumanStep | No for realized return-to-input composition on this route |
| BPL direct-transfer control | One Aspirate/Dispense pair, 10 uL | Built-in transfer lowering works |

These are scoped implementation findings. They are not a universal guarantee
for Culsma or proof that every LabOP composition route fails.
The [upstream-example verification](upstream-examples-evidence.md) independently
confirms that BPL's published direct transfer simulates successfully and LabOP's
official top-level protocol-output test passes. These working paths do not
exercise the producer-subprotocol-to-consumer-subprotocol connection tested here.

## Mechanism evidence

**Culsma.** `pipeline/component_expander.py::_inline_component_call` resolves
the protocol definition, binds its parameters, renames local declarations,
and connects the returned expression to the caller's result name. A returned
local identifier can be bound directly to that name. Subsequent expansion
therefore uses the same declared sample. The retained execution supplies the
material-state check. The inspected compiler explicitly restricts let-binding
of named multi-return bundles; this single-result witness does not validate
that feature, cross-file composition, or every returned data type.

**LabOP.** `uml/activity.py::designate_output` defines an output parameter and
its ActivityParameterNode, connecting it to the chosen source. The producer
call's `output_pin("sample")` is passed to the consumer's `input_value("sample", ...)`
interface. This is protocol-model dataflow, not Python copying an execution
result. Upstream `test/test_protocol_outputs.py` demonstrates `designate_output`,
and `test/test_subprotocols.py` demonstrates calls to Protocol objects.

The retained partial execution identifies the consumer `TakeAliquot` as the
failing call. Its `sample` parameter contains both the returned SampleArray and
the string `uml.ControlFlow`; the required cardinality is one. The exception
is raised in `CallBehaviorExecution.check_next_tokens`. This locates an invalid
value in the executed return-to-input connection, rather than an absent output
declaration. Both standard and explicit-final variants exhibit it. The source reinspection below identifies the control-placeholder path that
accounts for this observed extra value. No patched engine or alternative
backend is claimed. Partial RDF and traceback are retained, rather than
treating a raised exception as successful execution.

**BPL.** The grammar/AST accept `return`, call expressions and local bindings.
The inspected `orchestrator.py::_emit_statement` does not process `LetStmt` or
`ReturnStmt`; `_emit_call_statement` leaves user-defined calls as HumanSteps.
Thus the AST contains the producer's return and the caller's assignment, but
the emitted plan has no producer-result binding. This is a distinct manifestation
of the call/variable integration gaps seen in L1 and M4; it is not counted as
an independent numerical score or inferred from L1 alone.

## A HumanStep label is not a failure criterion

`HumanStep` is a legitimate representation of an operation requiring human
intervention. Its presence, or the absence of robot-specific Aspirate/Dispense
instructions, does not by itself establish incorrect procedure composition.
A fully bound human instruction could preserve the callee's meaning; a later
interpreter could also realize a retained call. The relevant question is whether
the producer's returned value and consumer's body are actually consumed.

The [follow-up runner](check_bpl_l2_consumption.py) checks both public human
instruction generation and simulator handling, with unchanged call sites:

| Change | Expected semantic consequence | Observed consequence |
|---|---|---|
| Consumer body: 10 uL to 20 uL | Transfer volume changes | Operational plan unchanged; human instruction still prints the same unresolved call |
| Producer return: StockTube to TargetTube | Consumer source changes, or a relevant invalid-self-transfer check occurs | Operational plan unchanged; human instruction still prints the same unresolved call |
| Direct transfer: 10 uL to 20 uL | Transfer volume changes | Plan and human instructions change to 20 uL |

The operational comparison excludes source-file annotations; the instruction
documents differ in source-file locations but not in the unresolved action.
The source and destination columns and volume column remain empty for the
composed call. This result, together with the source handling of declarations,
supports the finding that these function bodies/returns are not realized.

The non-strict public simulator reports completion for the composed input, but
its trace explicitly records `unsupported_no_op`, one unsupported step and an
unchanged state hash. Strict simulation rejects the unsupported primitive
(exit 40). By itself, lack of simulation support for a manual operation is not
an L2 failure; here it rules out the proposed later simulation interpreter.
The composer returns the stored instruction string and does not resolve it
against function definitions. Direct transfer simulation remains successful.

Source locations: `lowering/plan_ir.py::HumanStep`,
`export/markdown_composer.py::_instruction_from_primitive`, and
`simulation/simulator.py::_execute_primitive` in the pinned BPL snapshot.
[Results](results/l2/bpl-consumption/results.json),
[generated human instructions](results/l2/bpl-consumption/base.md), and
[simulation trace](results/l2/bpl-consumption/base-simulate-trace.json) are retained.
Run `python3 benchmarks/comparison/check_bpl_l2_consumption.py`
from the manuscript root. No upstream code is modified.

## Reproduction and artifacts

Use the environments already specified in the [package README](README.md).
From the manuscript root:

```sh
PYTHONPATH=benchmarks/local-results/comparison-runtime/culsma-source/src benchmarks/local-results/comparison-runtime/culsma-env/bin/python -m culsma.cli run benchmarks/comparison/cases/l2/composition.culs --output benchmarks/comparison/results/l2/culsma/output.json --artifacts-dir benchmarks/comparison/results/l2/culsma
benchmarks/local-results/comparison-runtime/labop-env/bin/python benchmarks/comparison/check_labop_l2.py
benchmarks/local-results/comparison-runtime/bpl-env/bin/python benchmarks/comparison/check_bpl_l1.py --cases-dir benchmarks/comparison/cases/l2/bpl --out benchmarks/comparison/results/l2/bpl-cli --skip-upstream-readme
```

The generic CLI runner retains its L1 filename; the supplied input directory
selects the separate L2 cases. No upstream implementation or operation handler
was modified. LabOP Graphviz rendering alone is redirected to DOT files.

- [Culsma source](cases/l2/composition.culs), [execution](results/l2/culsma/run.json),
  [status](results/l2/culsma/summary.json), [output](results/l2/culsma/output.json).
- [LabOP runner](check_labop_l2.py), [results](results/l2/labop/results.json),
  [partial composition execution](results/l2/labop/composition/partial-execution.ttl).
- [BPL composition](cases/l2/bpl/composition.bpl), [direct control](cases/l2/bpl/direct.bpl),
  [CLI results](results/l2/bpl-cli/results.json).

## Control-placeholder mechanism (16 November 2026)

Reinspection of the same pinned source identifies the following path:

- `labop/execution/execution_engine.py::ExecutionEngine.next_tokens` adds
  `literal("uml.ControlFlow")` to the outgoing object flows of an activity
  call (lines 505–516), and separately routes child return values to parent
  nodes (lines 517–538).
- `ExecutionContext.invoke_activity` connects child output parameters to the
  corresponding parent call output pins. The placeholder and returned object
  can therefore enter the same output pin.
- `labop/activity_node_execution.py::ActivityNodeExecution.parameter_value_map`
  concatenates the values of consumed incoming flows without filtering control
  placeholders. `ExecutionEngine.get_pin_value` forwards that value.
- `labop/call_behavior_execution.py::CallBehaviorExecution.check_next_tokens`
  enforces the consumer parameter's cardinality. The retained partial execution
  records both a SampleArray and the `uml.ControlFlow` string for `sample`.

This source path explains the retained two-value/cardinality failure. It does
not establish that every possible subprotocol output connection always
receives exactly two values: aggregation also depends on which tokens are
consumed in a node execution. The conclusion remains scoped to the evaluated
standard and explicit-final-node connections. This is source reinspection
against retained traces, not a new execution or a patched-engine experiment.
