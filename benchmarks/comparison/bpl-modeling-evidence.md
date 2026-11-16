# BPL M1–M4: mechanism audit

12 November 2026. Source: public BPL commit
`4e505740f5025d59ba655c6c955f83876f753007` (package metadata: 2.4.0).
The archive is retained under `benchmarks/local-results/comparison-runtime/`, extracted into
`bpl-source/`. No upstream source was modified. These findings apply to this
snapshot and the inspected routes, not every possible implementation of BPL.

[Probe](check_bpl_modeling.py) and [results](results/bpl-modeling/results.json)
retain nine source-to-plan witnesses and one simulator witness. Python 3.13.1
loaded the pure-Python Lark 1.3.1 package from the existing Culsma environment;
no Culsma modules were used by BPL. Reproduction from the manuscript root:

```sh
PYTHONPATH=benchmarks/local-results/comparison-runtime/bpl-source:benchmarks/local-results/comparison-runtime/culsma-env/lib/python3.12/site-packages /Users/yangchen/.pyenv/versions/3.13.1/bin/python benchmarks/comparison/check_bpl_modeling.py
```

The probe calls the parser, `run_semantic_gate`, and `lower_program_to_plan`.
These are the functions used by the CLI check/plan orchestration. It does not
claim to have run a hardware backend or every CLI validation configuration.

## M1 — Yes for the inspected entity/reference mechanism

`LabwareDecl` represents named labware, while `WellRef(plate_id, well_id)` and
`ContainerRef(container_id)` provide structured references. The witness declares
two labware objects with identical specifications, `TubeA` and `TubeB`; their
transfer endpoints lower to distinct references. Explicit `"plate_1:A1"` and
`"plate_1:A2"` references also remain distinct in the plan.

The generic named-endpoint route uses `_cached_location`: it assigns names to
synthetic wells, wrapping after 96 positions. Thus this Yes establishes a
reference mechanism for the inspected small case, not unbounded identity,
physical-layout fidelity, or all operation-product references.

Source: [AST declarations](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/ast/declarations.py),
[plan references](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/lowering/plan_ir.py#L109),
and [endpoint resolution](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/orchestrator.py#L1091).

## M2 — No on the inspected source-to-plan route

The unit engine **does** define dimension vectors, compatible-unit conversions,
and arithmetic dimension errors. However, the orchestration path reads transfer
quantities through `_numeric_value`, which extracts the number without checking
its dimension. `_duration_seconds` converts recognized time units but returns
the number unchanged for unrecognized units. The semantic gate uses these same
helpers. These paths do not invoke the unit engine's dimension checks.

Witnesses: `wait(duration: 10 min)` becomes `Wait(duration_s=600)`;
`wait(duration: 10 uL)` becomes `Wait(duration_s=10)`, with no semantic diagnostic.
Likewise, `transfer(..., volume: 10 min)` becomes 10-uL aspirate/dispense operations.
The No concerns enforcement at experimental-parameter use, not the absence of
dimension representations or unit arithmetic elsewhere in the package.

Source: [unit engine](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/types/unit_engine.py),
[semantic gate](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/orchestrator.py#L207),
and [numeric/duration helpers](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/orchestrator.py#L1141).

## M3 — No for continuous component accounting on the inspected route

BPL has state classes with component, quantity, temperature and history fields.
The simulator also implements volume arithmetic and proportionally reduces
source component volumes. These are real capabilities. However, its aspirate
handler passes only the removed volume to the pipette, and its dispense handler
calls `contents.add_volume(volume)` without a component payload. `VirtualContents.remove_volume` returns only the removed volume;
`add_volume` can accept a component, but this dispense call omits that argument.
Thus the released transfer path does not carry the source composition into the
destination. It does not clear components already present at the destination.

Witness: initialize A1 with 100 uL of a named `buffer` component and transfer
20 uL to empty A2. Simulation succeeds; A1 has 80 uL of buffer, while A2 has
20 uL total volume and an empty component list. State initialization uses the
simulator's public API and is not claimed to come from source reagent declarations.

The general call lowerer also turns a `centrifuge(...)` call into a `HumanStep`,
not a fraction-state calculation. This does not deny the separate `Centrifuge`
IR class or human-executable instructions. The transfer payload mechanism alone
already prevents a claim of continuous component accounting on this route.

Source: [state model](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/state/state_model.py),
[simulator handlers](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/simulation/simulator.py#L289),
[virtual contents](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/simulation/virtual_deck.py#L37),
and [call lowering](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/orchestrator.py#L873).

## M4 — No for implemented local-binding resolution on this route

The grammar and AST represent `let` declarations, parameters and nested blocks.
But `run_semantic_gate` skips `LetStmt`, and `_emit_statement` also has no
`LetStmt` handler or local-binding environment. `_duration_seconds` cannot resolve
an identifier; the wait lowerer substitutes 1 second when resolution returns
`None`. Named locations are allocated from a flat cache, not lexical declarations.

Witness: `let delay = 10 min; wait(duration: delay)` (newlines in actual BPL)
produces a one-second wait without a diagnostic. An undeclared `missing` name
does the same. A nested sequence declaration produces one-second waits both
inside and outside the block. This is **not** evidence that the language intends
leaking or shadowing: the more basic binding evaluation is absent on this route,
so its syntax alone cannot establish implemented visibility control.

Source: [grammar](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/grammar/bpl.lark#L250),
[statement lowering](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/orchestrator.py#L799),
and the semantic gate and helpers cited above. Being a standalone language does
not by itself establish that its implementation connects these mechanisms.
