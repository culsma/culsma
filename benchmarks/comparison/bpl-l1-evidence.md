# BPL L1: public CLI verification

12 November 2026. Evaluated source: BPL commit
`4e505740f5025d59ba655c6c955f83876f753007`, package metadata 2.4.0,
Python 3.13.1. The source was not patched. The installed `bplc` executable
was invoked in a fresh process for every command; no parser, semantic gate,
lowerer or CLI function was replaced. `pip check` passed.

**Decision: No on the evaluated public check/lowering route.** Formal
parameters and function declarations are represented in the AST, but this
route does not bind parameter values and instantiate the user-defined body.
This is an implementation finding, not a denial that BPL has a source language.

## Mechanism and public entry points

The upstream [project entry point](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/pyproject.toml)
registers `bplc = "bpl.cli.main:main"`.
[The CLI](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/cli/main.py#L369)
passes `lower` through `run_pipeline_for_plan`, including its validation gates.
There is no CLI argument-binding or protocol-selection option on these commands.

In the inspected [orchestrator](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/bpl/orchestrator.py):

- `run_semantic_gate` selects the first protocol (lines 212–225). For a
  transfer, it requires a numeric volume via `_numeric_value` (lines 384–396).
- `lower_program_to_plan` selects the first protocol and emits its body
  (lines 744–773). It does not build a parameter environment or expand a
  `FunctionDecl`/another `ProtocolDecl` at its call sites.
- `_emit_call_statement` handles recognized built-ins such as `transfer`
  and `wait`, then falls back to `HumanStep(instruction=...)` for other calls
  (lines 871–949). It does not resolve those calls against user declarations.
- `_numeric_value` accepts a numeric literal or a quantity containing a
  numeric literal; an identifier is not evaluated (lines 1141–1146).

The [README](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/README.md#L78)
shows `protocol PrepareLBMedia(final_volume: Volume = 1000 mL)` and uses
`volume: final_volume` in its transfer. The minimal default-parameter probes
retain this documented pattern. The source syntax reference §4.10 documents
`function` declarations. Its header says v2.5; that label is not substituted
for the evaluated package version or commit.

## Executed observations

[All inputs](cases/l1/bpl/README.md) and [command-by-command results](results/l1/bpl-cli/results.json)
are retained. Both lowering targets, `human` and `simulation`, give the same
operation-level outcomes below.

| Input | Parse | Check | Lowering result |
|---|---|---|---|
| Two direct transfers, 10/20 uL | Pass | Pass | `Aspirate(10)`, `Dispense(10)`, `Aspirate(20)`, `Dispense(20)` |
| Formal `amount: Volume = 10 uL`, body uses `volume: amount` | Pass | Exit 11: `SEMANTIC_MISSING_VOLUME` | Rejected by the semantic gate; no plan |
| Same body, default changed to 20 uL | Pass | Same error | No plan |
| One `function aliquot(...)`, two calls | Pass | Pass | Two `HumanStep` entries; no transfer operations |
| One `protocol aliquot(...)`, two calls | Pass | Pass | Two `HumanStep` entries; no transfer operations |
| Same calls with no declaration | Pass | Pass | The same two instruction strings; no transfer operations |

The AST artifacts retain both the function declaration and its transfer body.
Removing the declaration leaves the operational plan unchanged (source file
locations differ). The fallback therefore preserves the call text, not the
body's parameterized meaning. A human might interpret the text, but no such
interpretation or numerical transfer realization was verified here.

The `protocol`-call probe is retained as the original hypothesis, not as proof
that the documentation promises callable protocols. The conclusion instead
combines source inspection, the documented default-parameter pattern, the
function-call probe, and the successful built-in positive control.

The complete unchanged README block was also tried. It fails parsing at an
earlier material declaration (line 1, comma), before the protocol. This is
recorded but excluded from the L1 decision. The minimal default probes parse
successfully and isolate the binding issue without repairing that whole block.

## Follow-up: caller-local containers and a parameter-free control

The [endpoint-binding follow-up](cases/l1/bpl_endpoint_binding/README.md) tests
the suggestion to declare containers, bind them locally in Main, and pass those
references to the reusable procedure. BPL's grammar places `labware` declarations
at top level; Main uses `let` references to declared Tube-category labware.
Formal endpoint types are `Labware`, rather than the earlier `String` type.
Both named and locally referenced endpoints still give two HumanSteps.

Fixing the endpoints inside the function and passing only the amount gives the
same outcome. Removing **all** parameters, with literal endpoints and a literal
10-uL amount in the function body, also gives only HumanSteps. Writing that
constant body directly twice gives two 10-uL transfer pairs. Thus endpoint
binding cannot be the sole explanation: the call does not enter the declared
body even when there is nothing to bind. Eight cases were checked through the
unmodified public CLI; both targets agree.

The local-reference direct case produces transfer operations but does not
establish correct alias resolution. Binding both local names to the same tube
still gives the distinct-endpoint plan. The lowerer ignores `LetStmt` and maps
identifier spellings to synthetic wells; this is a separate binding limitation.
The [follow-up results](results/l1/bpl-endpoint-binding/results.json) retain
these controls without claiming physical tube placement or simulator execution.

## Reproduction

Use the source archive for the commit above in
`benchmarks/local-results/comparison-runtime/bpl-source/`. The original archive is downloaded from
the [pinned GitLab archive URL](https://gitlab.com/bota-biosciences-public/bpl-code/-/archive/4e505740f5025d59ba655c6c955f83876f753007/bpl-code-4e505740f5025d59ba655c6c955f83876f753007.tar.gz).
Create an isolated environment; install the recorded dependencies and the
unchanged package:

```sh
/path/to/python3.13 -m venv benchmarks/local-results/comparison-runtime/bpl-env
benchmarks/local-results/comparison-runtime/bpl-env/bin/python -m pip install -r benchmarks/comparison/bpl-cli-requirements.txt
benchmarks/local-results/comparison-runtime/bpl-env/bin/python -m pip install --no-deps -e benchmarks/local-results/comparison-runtime/bpl-source
benchmarks/local-results/comparison-runtime/bpl-env/bin/python benchmarks/comparison/check_bpl_l1.py
```

The runner accepts `--source`, `--cli`, and `--out` overrides. It saves source
SHA-256 hashes, Python and dependency versions, exact CLI arguments, exit codes,
stdout/stderr, ASTs and plans. Dependencies reflect this verification environment,
not a claim to reproduce the upstream authors' environment. No LLM or hardware
service is called. Lowering to the `simulation` target is not a simulator run,
and no final sample-volume calculation is claimed for BPL in this L1 check.
The CLI working directory is the result directory, so its automatically emitted
`artifacts/check/*.diagnostics.json` files are retained with the other evidence.
