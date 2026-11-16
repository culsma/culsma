# L3: repetition and conditional routing

12 November 2026. Pinned Culsma `5364676b`, LabOP `2e2bd88`, and BPL `4e505740`.
This check concerns protocol control structures, not the presence of control
keywords or a diagram alone. Source/graph construction, realized repetition,
and runtime branch selection are distinguished.

## Definition and basis

Can a protocol repeat operations and select the intended execution path from
a condition? Two control mechanisms are relevant: repetition and conditional
routing. Measurement-dependent routing is a particular input route for the
second mechanism, not a third control-flow construct.

Conceptual sources are van der Aalst et al., [Workflow Patterns](https://pure.tue.nl/ws/files/2053121/613310.pdf),
Pattern 4 (Exclusive choice) and Pattern 10 (Arbitrary cycles), and Russell
et al., [Workflow Data Patterns](https://www.vdaalst.com/publications/p220.pdf),
Pattern 39 (Data-based Routing). The bounded-count and measurement-fixture
checks are our operationalization; the cited patterns are not a claim that
every loop must have a particular source syntax.

## Retained observations

| Unit | Culsma | LabOP | BPL |
|---|---|---|---|
| L3a: changed repeat count | Two/three iterations transfer 20/30 uL respectively | Tested cyclic graph fails at MergeNode before entering its body; not a complete audit of bounded-count encodings | Two/three-element for loops both emit only the unrelated prefix Wait; body omitted |
| L3b: conditional routing | Same compiled plan selects only the intended transfer for two runtime values | Identical model with True/False runtime predicates executes both transfer arms | Both constant-True and constant-False if/else programs omit both arms in public lowering |
| L3c: measurement input route | Structured `img` results supplied by the released StubDriver select the correct arm | Predicate fixture is Boolean, not an actual measurement; measurement integration remains unassessed | No separate measurement-interface probe; basic conditional lowering already fails |

No real instrument measurements or hardware operations occur. These are scoped
findings, not universal language-conformance results. In particular, the
LabOP cycle probe uses a fixture-supplied Boolean sequence; it does not claim
that a native bounded-loop counter was available and tested.

## Culsma: native repeat expansion and runtime guards

[check_culsma_l3.py](check_culsma_l3.py) compiles, validates, type-checks and
executes the pinned language. It changes the bound in
`repeat i in schedule(start = 1, end = 3, step = 1)` from 2 to 3, with a
10-uL transfer body. The target receives 20 and 30 uL respectively.
This supplements the previously retained PCR loop rather than inferring all
control behavior from PCR alone.

For conditional routing, the source contains:

```culs
let obs = img(sample = source, quantity = fluorescence);
if obs.result.signal >= 1000 {
    target << [source:10uL];
} else {
    alternative << [source:20uL];
}
```

The same compiled plan is executed twice. The released `StubDriver` supplies
`img` result payloads with signal 1250 or 800 at runtime, following the pinned
`tests/test_kernel_runtime.py` observation-if tests. For 1250, source/target/
alternative volumes are 90/10/0 uL; for 800, they are 80/0/20 uL. The unselected
branch has skipped status. These are synthetic result payloads delivered
through the runtime result path, not measured fluorescence or authoring-time
Python selection of one branch.

`pipeline/compile/statements.py::IfHandler` distinguishes compile-time Boolean
conditions from supported runtime predicates and retains runtime conditional
structure. `RepeatHandler` uses the schedule expansion mechanism. The concrete
execution and branch-status records are in [results](results/l3/culsma/results.json),
with the [branch source](results/l3/culsma/runtime_branch.culs) and repeat sources.

## LabOP: defined guards are not applied by the tested execution path

[check_labop_l3.py](check_labop_l3.py) uses `Protocol.make_decision_node`,
True/False guarded outgoing edges, and the same test-predicate mechanism as
upstream `test/test_decision_nodes.py`. The Boolean fixture is set only after
the model is built and serialized. The two inputs have identical model hashes.
It supplies values; it does not decide which outgoing edge the engine takes.

The first contrast uses distinct no-output marker primitives. Both TrueBranch
and FalseBranch execute for either predicate value. A second contrast uses
standard material operations: starting with 100 uL, the True arm transfers
10 uL to target, and the False arm transfers 20 uL to alternative. For **both**
True and False, both transfers execute: final volumes are 70/10/20 uL.
This establishes actual material effects beyond the presence of node records.

The model validates without errors. The engine reports normal completion with
empty structured issues, so that flag is not treated as proof of correct routing.
`uml/decision_node.py::next_tokens_callback` contains guard selection code, but
the evaluated `ExecutionEngine.next_tokens` creates tokens for all outgoing
edges without dispatching to it. The observed two-arm execution agrees with
this mechanism. [Source hashes](results/l3/labop-source-check.json) confirm the
installed engine, DecisionNode, MergeNode and Protocol files match the pinned
source archive; no core or routing implementation was patched.

The material contrast enables the standard primitive output handlers, needed
by EmptyContainer. The earlier diagnostic attempt with those handlers disabled
failed during container setup and is retained in
[a separate setup record](results/l3/labop/material-setup-before-enabling-builtins.json).
That setup error is excluded from the control-flow verdict.

The loop probe constructs `initial -> merge -> decision`, a guarded body,
and a body-to-merge back edge using released UML nodes. Both supplied input
sequences fail before the body with `'MergeNode' object has no attribute 'protocol'`.
`MergeNode.enabled` calls that missing method. This is a failure of the tested
cycle route, not proof that no alternative loop encoding can exist. The fixture
sequence is not presented as a built-in counting mechanism.

All models, execution RDF, sample graphs, predicate inputs, calls, and exceptions
are retained in [LabOP results](results/l3/labop/results.json).

## BPL: control-block bodies are omitted by public execution-plan lowering

The grammar and AST support `for`, `while` and `if`. The existing public-CLI
runner was applied to [two](cases/l3/bpl/loop_2.bpl) and
[three](cases/l3/bpl/loop_3.bpl) loop iterations, and to constant
[True](cases/l3/bpl/branch_true.bpl) and [False](cases/l3/bpl/branch_false.bpl)
branches. Each has a separate one-second Wait before the tested construct, so
the resulting plan can be inspected even when the control block is omitted.

All programs parse and check successfully. For both `human` and `simulation`
targets, only the prefix Wait is emitted: no loop body, selected branch,
deferred control node, or referenced control-body representation is retained.
Changing the count or condition does not change the operational plan.
The [direct control](cases/l3/bpl/direct_3.bpl) emits Wait plus three
Aspirate/Dispense pairs. This result does not rely on a HumanStep label.

The evaluated `orchestrator.py::_emit_statement` has no handlers for ForStmt,
WhileStmt or IfStmt; unhandled statements return the incoming dependencies.
A separate `bplc graph` path in `cli/main.py` does traverse these AST nodes and
adds generic control steps for visualization. Its existence is not ignored,
but it is distinct from the inspected `lower`/execution-plan route and does
not establish executable iteration counts or guard selection. No universal
absence of control structures in BPL's representation is asserted.

[Public CLI commands, ASTs and plans](results/l3/bpl-cli/results.json) are retained.
The constant condition probes expose a prerequisite control failure; they are
not advertised as successful runtime-value or measurement-interface tests.

## Reproduce

From the manuscript root, using the existing pinned environments:

```sh
PYTHONPATH=benchmarks/local-results/comparison-runtime/culsma-source/src benchmarks/local-results/comparison-runtime/culsma-env/bin/python benchmarks/comparison/check_culsma_l3.py
benchmarks/local-results/comparison-runtime/labop-env/bin/python benchmarks/comparison/check_labop_l3.py
benchmarks/local-results/comparison-runtime/bpl-env/bin/python benchmarks/comparison/check_bpl_l1.py --cases-dir benchmarks/comparison/cases/l3/bpl --out benchmarks/comparison/results/l3/bpl-cli --skip-upstream-readme
```

The Boolean predicate and measurement-result provider are explicitly identified
fixtures. Standard execution, routing, material handling and compilation are
unchanged. LabOP Graphviz rendering alone is redirected to retained DOT files.
