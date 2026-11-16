# L1 follow-up: caller-local container references

Question: are the earlier missing transfers caused specifically by binding
source/destination formal parameters or by reconnecting the destination?

The pinned grammar permits `labware` declarations at declaration level, not
inside a protocol body. The documented container declaration is therefore used:
`labware StockTube { ... category: Tube }`, plus a second `TargetTube`.
`Main` binds local references using `let source: Labware = StockTube` and
`let destination: Labware = TargetTube`. These are declaration/reference tests,
not a claim of runtime object allocation, copying, or correct tube placement.
No undocumented `tube(...)`, `Tube(...)` or `Container(...)` constructor is used.

All eight inputs pass the public CLI parser and semantic check. Lowering to
both `human` and `simulation` targets returns success with the following plans:

| Case | What changes | Observed operations |
|---|---|---|
| [tubes_direct.bpl](tubes_direct.bpl) | Direct 10/20-uL transfers between the two named containers | Two aspirate/dispense pairs |
| [tubes_local_direct.bpl](tubes_local_direct.bpl) | Direct transfers use local references in Main | Two aspirate/dispense pairs; see alias caveat below |
| [tubes_named_calls.bpl](tubes_named_calls.bpl) | Named containers are passed to the function | Two `HumanStep` entries; no transfer primitives |
| [tubes_local_calls.bpl](tubes_local_calls.bpl) | Main's local references are passed to `Labware` formal parameters | Two `HumanStep` entries; no transfer primitives |
| [fixed_endpoints_amount.bpl](fixed_endpoints_amount.bpl) | Function fixes both endpoints and takes only the amount | Two `HumanStep` entries; no transfer primitives |
| [no_parameters.bpl](no_parameters.bpl) | Function takes no parameters; endpoints and amount are literal constants | Two `HumanStep` entries; no transfer primitives |
| [no_parameters_direct.bpl](no_parameters_direct.bpl) | Same constant transfer body written directly twice | Two 10-uL aspirate/dispense pairs |
| [alias_same_tube.bpl](alias_same_tube.bpl) | Both Main-local names are bound to StockTube | Still the same A1-to-A2 plan as the distinct-container local case |

**Finding.** The loss of the body persists without any formal parameter,
container argument, or destination rebinding. The inspected call emitter never
resolves `aliquot` to its user-defined body. A parameter-free call is outside
the positive L1 witness, but provides a diagnostic control for this cause.
The result is scoped to this implementation and these public CLI routes.

**Local-binding caveat.** Producing transfer operations from the local-variable
direct case does not prove that the local variables were resolved correctly.
Changing `destination = TargetTube` to `destination = StockTube` leaves the
operational plan unchanged. Source inspection explains this: `_emit_statement`
does not process `LetStmt`; `_location_from_expression` maps an identifier's
spelling through `_cached_location`, which allocates synthetic well references.
The plan still transfers from A1 to A2 even when both names refer to StockTube.
This corroborates the existing M4 binding finding, and is not presented as
correct tube allocation or material simulation.

## Reproduce

From the manuscript root, with the pinned BPL CLI environment already installed:

```sh
output/labop-comparison/bpl-env/bin/python supplementary/comparison_examples/check_bpl_l1.py \
  --cases-dir supplementary/comparison_examples/cases/l1/bpl_endpoint_binding \
  --out supplementary/comparison_examples/results/l1/bpl-endpoint-binding \
  --skip-upstream-readme
```

[Recorded results](../../../results/l1/bpl-endpoint-binding/results.json) include
all input hashes, ASTs, plans, commands, diagnostics, versions and source hashes.
See the [main BPL L1 audit](../../../bpl-l1-evidence.md) for the pinned source
links and installation instructions. No hardware or simulator was run.
