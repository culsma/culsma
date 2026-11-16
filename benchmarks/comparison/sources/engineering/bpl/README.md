# BPL — Biology Programming Language

> A domain-specific language for describing, validating, and executing biology laboratory protocols.

[中文版本 (Chinese Version)](README_CN.md)

---

## Motivation

Standard Operating Procedures (SOPs) in life-science laboratories are typically maintained as natural-language documents.
This creates well-known problems:

- **Ambiguity** — free-text instructions admit multiple interpretations.
- **No validation** — unit errors, volume overflows, and reagent mismatches are discovered only at the bench.
- **Poor reproducibility** — re-executing a protocol on a different instrument or by a different operator introduces silent variation.
- **Weak auditability** — tracing exactly what happened during execution requires manual record-keeping.

**BPL** addresses these problems by encoding laboratory protocols as programs in a purpose-built language with biology-native types, dimensional analysis, deterministic compilation, and multi-target execution backends.

## Publication Repository Scope

This clean repository contains the public software and lightweight benchmark
artifacts needed for the paper's Code availability and Data availability
sections. It intentionally excludes raw source articles, private SOP files,
large training run outputs, model checkpoints, manuscript drafts, and generated
figure/API-response artifacts. See
[`docs/CODE_AND_DATA_AVAILABILITY.md`](docs/CODE_AND_DATA_AVAILABILITY.md) for
manuscript-ready wording.

## Key Capabilities

| Capability | Description |
|---|---|
| **Biology-native type system** | First-class units (`mL`, `g/mol`, `degC`, `mM`), dimensional analysis, and MW-aware concentration conversions |
| **Deterministic compiler** | Source → AST → Plan IR → Scheduled DAG — same input always produces the same execution plan |
| **Multi-target execution** | Compile once, run on human (step-by-step worklist), robot (Biomek i7), or simulation |
| **Staged validation** | Six gates: syntax → semantic → plan/DAG → experiment-parameter → capability → backend preflight |
| **Audit & trust model** | Hash-chained state history with three trust tiers: Declared, Calibrated, Verified |
| **SOP-to-BPL generation** | Agentic workflow that translates natural-language SOPs into validated BPL programs |
| **Export** | CSV/XLSX worklists, workflow graphs (Mermaid/JSON/ReactFlow) |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     BPL Compiler Pipeline                       │
├─────────┬──────────┬──────────┬──────────┬──────────┬──────────┤
│  Parse  │ Semantic │  Lower   │ Schedule │ Execute  │  Export  │
│         │  Check   │          │          │          │          │
│ .bpl →  │ units,   │ Intent → │ DAG      │ human /  │ CSV /   │
│   AST   │ types,   │ Plan IR  │ resolve  │ robot /  │ XLSX /  │
│         │ state    │ (prims)  │ + order  │ simulate │ graph   │
└─────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
  grammar/    types/     lowering/  scheduler/  runtime/   export/
  parser/     state/                             simulation/ graph/
  transformer/validation/                        audit/
```

## Language Example — LB Media Preparation

```bpl
reagent Tryptone  { physical_form: Solid, cas: "91079-40-2" }
reagent NaCl      { physical_form: Solid, MW: 58.44 g/mol   }
reagent ROWater   { physical_form: Liquid                    }

stock LB_Base {
    reagent: Tryptone
    concentration: 10 g/L
    solvent: ROWater
}

labware Beaker1L      { footprint: Custom, well_volume: 1200 mL }
labware GlassBottle1L { footprint: Custom, well_volume: 1000 mL }

@target(human)
@expected_time(2 h)
protocol PrepareLBMedia(final_volume: Volume = 1000 mL) {
    @step(1, "Add RO water to beaker")
    add_reagent(ROWater, volume: 800 mL, to: Beaker1L)

    @step(2, "Add Tryptone")
    add_reagent(Tryptone, mass: 10 g, to: Beaker1L)

    @step(3, "Add NaCl")
    add_reagent(NaCl, mass: 10 g, to: Beaker1L)

    @step(4, "Adjust volume")
    add_reagent(ROWater, volume: 200 mL, to: Beaker1L)

    @step(5, "Transfer to bottle")
    transfer(from: Beaker1L, volume: final_volume, to: GlassBottle1L)

    @step(6, "Autoclave")
    incubate(target: GlassBottle1L, temperature: 121 degC, time: 20 min)
}
```

## Repository Layout

```
bpl/                      Core implementation (~32 000 lines of Python)
├── grammar/bpl.lark        Lark parser grammar (v2.4)
├── parser/                 Lark → parse tree
├── transformer/            Parse tree → typed AST
├── ast/                    AST node definitions
├── types/                  Unit engine, dimensions, concentration logic
├── state/                  State model, trust tiers, hash-chain history
├── lowering/               Intent → Plan IR (DAG of primitives)
├── scheduler/              DAG dependency resolution & scheduling
├── simulation/             Virtual deck dry-run simulation
├── validation/             Experiment-parameter & setup validation
├── runtime/
│   ├── human/              Human-executable step generation + data capture
│   └── robot/biomek/       Biomek i7 translation & code generation
├── export/                 CSV/XLSX worklist exporter
├── graph/                  Workflow graph rendering (Mermaid/JSON/ReactFlow)
├── audit/                  Compliance audit trail with hash-chain integrity
├── agentic/                SOP → BPL agentic generation workflow
├── capabilities/           Backend primitive support registry
├── errors/                 Structured diagnostic types
├── cli/                    CLI entrypoint (bplc)
└── orchestrator.py         Unified orchestration layer

tests/                    Test suite (~17 000 lines, 1 150+ tests)
├── phase0_cli/             CLI contract & vertical-slice tests
├── phase1_parser/          Grammar, AST, transformer tests
├── phase2_state/           State model & trust tier tests
├── phase3_lowering/        Plan IR & intent lowering tests
├── phase4_scheduler/       DAG scheduling tests
├── phase5_errors/          Error handling & recovery tests
├── phase6_simulation/      Virtual deck simulation tests
├── phase7_human/           Human runtime tests
├── phase8_robot/           Biomek backend tests
├── phase9_audit/           Audit trail & compliance tests
├── conformance/            End-to-end protocol tests (LB media, heat shock, HTS)
└── export/                 Export format tests

docs/                     Protocol corpus & reference materials
├── BPL_STRUCTURE.md        Public structural overview
├── BPL_Syntax_Reference.md Language reference
├── CODE_AND_DATA_AVAILABILITY.md  Manuscript-ready availability statement
├── BPL_EVAL_DATASET.md     How to use the full BPL-EVAL dataset from HF
├── PAPER_REPRODUCIBILITY.md       One-command reproducibility guide
└── column_*.md                    Chromatography conversion documentation

tools/bpl_eval/           Paper evaluation pipeline (digest → variant rewrite
                          → batch BPL compile → LLM-judge → figures), with
                          all shipped paper-grade artifacts inside the same
                          folder:
├── data/                    Frozen artifacts: variant_report.json,
│                            per_paper/*.json, consistency_report.md,
│                            structural_features.json, determinism_results.json
├── figures/publication_redraw/  Frozen paper figures (regenerable)
└── *.py                     Pipeline scripts (read-only when running offline)

tools/corpus/             Synthetic corpus generation utilities
scripts/                  Documentation/helper scripts
                          (e.g. `scripts/gen_column_docs.py` regenerates
                          `docs/column_catalog.md`; `scripts/reproduce_paper.py`
                          runs the offline paper-reproduction workflow)
examples/                 Minimal runnable public examples
```

## Getting Started

### Prerequisites

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) package manager

### System Requirements

- Tested release environment: macOS 26.5.1 on Apple M4 Pro (arm64), 64 GB RAM,
  CPython 3.13.7, and uv 0.8.10.
- Runtime dependencies are declared in `pyproject.toml` and pinned in
  `uv.lock`; `uv sync --dev` installs the full development/test environment.
- No non-standard hardware is required to install BPL, run the public example,
  run the offline paper-reproducibility workflow, or regenerate the shipped
  figures from the frozen artifacts.
- The upstream from-scratch data-generation and wet-lab stages are outside the
  public offline workflow. They require external inputs such as the raw article
  corpus, user-provided API credentials, and, for wet-lab/robot experiments, the
  relevant laboratory instruments described in `tools/bpl_eval/README.md`.

Measured runtimes below were recorded on the tested release environment above
from a temporary clean checkout on 2026-06-26. Install time was measured with an
empty `UV_CACHE_DIR`, so it includes dependency downloads but not `git clone`.

| Task | Command | Measured wall time |
|---|---|---:|
| Install development environment | `uv sync --dev` | 29.08 s |
| Run the minimal public example commands in "Reproducible Quick Start" | six `uv run bplc ...` commands | 8.19 s |
| Run the fast paper smoke workflow | `uv run python scripts/reproduce_paper.py --skip-tests --skip-pyright --skip-build --skip-eval-figs` | 4.38 s |
| Run the full offline paper workflow | `uv run python scripts/reproduce_paper.py` | 59.04 s |

### Install

```bash
git clone https://gitlab.com/bota-biosciences-public/bpl-code.git
cd bpl-code
uv sync --dev
```

### Verify

```bash
# Paper-level offline reproducibility workflow
uv run python scripts/reproduce_paper.py
```

This generates compiler artifacts, recomputes the shipped benchmark summary,
re-renders the eight paper figures from the frozen evaluation artifacts
(`tools/bpl_eval/figures/publication_redraw/fig{1,2,2a,3,4,5,6,7}_*.{pdf,png}`),
runs the full tests/type check/build, and writes
`paper_artifacts/reproducibility_manifest.json`. For a faster local smoke
run, use `uv run python scripts/reproduce_paper.py --skip-tests --skip-pyright --skip-build --skip-eval-figs`.
See [`docs/PAPER_REPRODUCIBILITY.md`](docs/PAPER_REPRODUCIBILITY.md) and
[`tools/bpl_eval/README.md`](tools/bpl_eval/README.md).

Expected terminal output for a passing paper workflow ends with:

```text
PASS paper reproducibility workflow: paper_artifacts/reproducibility_manifest.json
Benchmark: 301 papers, identical_all_runs=98.34%, match_vs_digest=99.40%, mean_range=0.186
```

The full generated evaluation dataset is hosted separately on Hugging Face at
[`BotaBio/BPL-EVAL`](https://huggingface.co/datasets/BotaBio/BPL-EVAL). See
[`docs/BPL_EVAL_DATASET.md`](docs/BPL_EVAL_DATASET.md) for download and
analysis commands.

## CLI Reference (`bplc`)

```bash
# Syntax check
# Examples below use the public fixture protocol shipped at
# examples/minimal_protocol.bpl — replace with your own .bpl path.
uv run bplc check examples/minimal_protocol.bpl

# Parse to AST
uv run bplc parse examples/minimal_protocol.bpl --format json --out ast.json

# Lower to execution plan
uv run bplc lower examples/minimal_protocol.bpl --target human --out plan.json

# Staged validation
uv run bplc validate examples/minimal_protocol.bpl --target human

# Dry-run simulation
uv run bplc simulate --input-bpl examples/minimal_protocol.bpl --trace trace.json

# Export worklist
uv run bplc export --input-bpl examples/minimal_protocol.bpl --format csv --out worklist.csv

# Compose human-readable markdown protocol
uv run bplc compose --input-plan plan.json --out protocol.md

# Workflow graph
uv run bplc graph --input-bpl examples/minimal_protocol.bpl --format mermaid --out graph.md

# Backend capability report
uv run bplc capabilities --target biomek

# SOP-to-BPL generation (requires API key; supply any markdown SOP)
uv run bplc sop-generate --sop path/to/sop.md --out generated.bpl
```

## Reproducible Quick Start

Use the fixture inputs shipped with the repository:

```bash
INPUT=examples/minimal_protocol.bpl

mkdir -p examples/generated
uv run bplc parse    "$INPUT" --format json --out examples/generated/minimal.ast.json
uv run bplc lower    "$INPUT" --target human --out examples/generated/minimal.plan.json
uv run bplc validate "$INPUT" --target human
uv run bplc simulate --input-bpl "$INPUT" --trace examples/generated/minimal.trace.json
uv run bplc export   --input-bpl "$INPUT" --format csv --out examples/generated/minimal.csv
uv run bplc graph    --input-bpl "$INPUT" --format json --out examples/generated/minimal.graph.json
```

Expected output: each command prints a compact JSON success record. The commands
write `examples/generated/minimal.ast.json`,
`examples/generated/minimal.plan.json`,
`examples/generated/minimal.trace.json`, `examples/generated/minimal.csv`, and
`examples/generated/minimal.graph.json`; `validate` also writes diagnostics under
`artifacts/validate/`.

**Determinism guarantee:** `parse`, `lower`, `validate`, `export`, and `graph` are deterministic — running the same command twice on the same input produces byte-identical output. `simulate --trace` records wall-clock `started_at` / `completed_at` / per-step `timestamp` and `duration_ms` fields, so its output varies between runs by design (the underlying plan hash is still deterministic; see Design Principle 5 below).

## Design Principles

1. **Protocols are programs.** A `.bpl` file is a complete, self-contained description of a laboratory protocol — not a script, not a template.
2. **Intent over instruction.** Users write high-level intents (`transfer`, `add_reagent`, `incubate`); the compiler lowers them to backend-specific primitives (`aspirate`, `dispense`, `pick_tips`).
3. **Dimensional safety.** The type system catches `mL + g` at compile time, not at the bench.
4. **Human as first-class backend.** Manual steps (centrifuge, visual inspection, operator signature) are part of the execution plan, not comments.
5. **Deterministic compilation.** Same source + same options → same plan hash. Non-deterministic metadata (timestamps, UUIDs) is isolated.
6. **Trust is explicit.** Every state value carries a trust tier (Declared / Calibrated / Verified) and an auditable change history.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 2 | CLI usage / argument error |
| 10 | Parse failure |
| 11 | Semantic validation failure |
| 20 | Lowering failure |
| 30 | Simulation / runtime failure |
| 40 | Strict capability failure |
| 99 | Internal error |

## Citation

If you use BPL in your research, please cite:

```
[Citation to be added upon publication]
```

## License

MIT. See [LICENSE](LICENSE).

## Contact

Contact information will be added with the public repository URL.
