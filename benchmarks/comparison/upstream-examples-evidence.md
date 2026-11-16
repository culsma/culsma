# Working upstream routes and their relation to L1/L2

12 November 2026. This follow-up tests the objection that failed L1/L2
witnesses might imply that ordinary protocols cannot run. They do not.
The upstream source snapshots and environments are unchanged.

## BPL: the published minimal protocol runs

The upstream file `examples/minimal_protocol.bpl` contains exactly:

```bpl
protocol MinimalProtocol {
  transfer(from: source, to: dest, volume: 10 uL)
}
```

The installed public `bplc lower --target simulation` and `bplc simulate`
commands both return exit code 0 on that unchanged file. The simulator trace
has status `COMPLETED`, two successful steps, no failed steps, and no unsupported
steps: aspirate 10 uL from `plate_1/A1`, then dispense 10 uL to `plate_1/A2`.
This is actual software simulation, beyond the plan generation in the L1/L2
probes. It is not physical execution or evidence for parameterized functions.

The CLI's `_seed_deck_for_plan` constructs a synthetic deck and supplies stock
for aspirates. Thus this success does not validate author-declared starting
materials or physical container allocation. The point is narrower: built-in
transfer lowering and simulation work without invoking any user-defined body.

Source: [pinned official example](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/examples/minimal_protocol.bpl).
Retained [exact input](results/upstream-examples/upstream_minimal_protocol.bpl),
[plan](results/upstream-examples/bpl-plan.json), and [simulation trace](results/upstream-examples/bpl-trace.json).

## LabOP: the official top-level protocol-output test passes

The actual upstream `TestProtocolOutputs.test_protocol_outputs` was run through
its own ProtocolHarness. Only its output directory and Graphviz rendering were
redirected. The test passes (one test, zero failures/errors). Execution records
contain `EmptyContainer`, `PlateCoordinates`, and `MeasureAbsorbance`. The
top-level `measurements` output resolves to a `Dataset`, as asserted by the
upstream test. Structured execution issues are empty.

The upstream construction connects these primitives in one Protocol:

```python
plate = protocol.primitive_step("EmptyContainer", specification=plate_spec)
target_wells = protocol.primitive_step(
    "PlateCoordinates",
    source=plate.output_pin("samples"),
    coordinates=f"A1",
)
measure_absorbance = protocol.primitive_step(
    "MeasureAbsorbance",
    samples=target_wells.output_pin("samples"),
    wavelength=sbol3.Measure(600, tyto.OM.nanometer),
)
```

It then designates the measurement output as a protocol output. This proves a
working primitive-to-primitive connection and top-level return on that path.
It does not exercise the L2 witness's producer-subprotocol output being passed
as a consumer-subprotocol input. Nor does the generated Dataset establish an
actual instrument measurement or populated experimental observations.

Source: [pinned upstream test](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/test/test_protocol_outputs.py).
[Test result](results/upstream-examples/protocol_outputs_test/unittest.txt) and
[execution summary](results/upstream-examples/protocol_outputs_test/summary.json)
are retained alongside the harness artifacts.

## LabOP LUDOX: normal-completion flag is insufficient

The unchanged upstream `examples/protocols/ludox/LUDOX_protocol.py` entry point
was also run through its own harness. Its protocol-building helpers are Python
functions (`create_plate`, `provision_h2o`, etc.) that add primitives to the same
Protocol; they are not nested LabOP Protocol calls in the resulting execution.
This is a real authoring reuse route and must not be described as no reuse at all.

The run reports `completed_normally = true` and no structured issues, but its
records contain only EmptyContainer (1), PlateCoordinates (3), and Provision
(2), with no MeasureAbsorbance execution and no returned output. Therefore this
run is **not** counted as a complete successful LUDOX workflow. Its missing
measurement has not been independently diagnosed in this follow-up. The working
official output test above, not the LUDOX completion flag, is the positive witness.

Source: [pinned LUDOX program](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/examples/protocols/ludox/LUDOX_protocol.py).
[Recorded summary](results/upstream-examples/ludox/summary.json).

## Interpretation and reproduction

An ordinary sequence of supported built-ins can run without user-defined
procedure invocation, argument binding or return-to-input composition.
Conversely, a failure of one L1 argument path does not logically establish
failure of every L2 path. The L2 observations were collected separately.
The marks concern the named protocol-level mechanism and implementation route;
they do not rank an entire project or erase other working authoring mechanisms.

Run from the manuscript root:

```sh
python3 benchmarks/comparison/check_upstream_examples.py
```

The [runner](check_upstream_examples.py) invokes the installed environments,
retains upstream input hashes, commands, logs, simulation/harness artifacts,
and [combined results](results/upstream-examples/results.json). It calls no
hardware or LLM service and modifies no upstream implementation.
The harness's numerous tiny MarkdownSpecialization JSON artifacts are preserved
losslessly in `MarkdownSpecialization.json-artifacts.zip` within each harness
artifact directory; the runner verifies every archived byte before removing
the loose copies. Execution summaries, logs, graphs and other artifacts remain
directly readable.
