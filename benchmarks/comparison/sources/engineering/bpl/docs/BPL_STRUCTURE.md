# BPL (Biology Programming Language) — Structural Overview

> 30,604 lines of Python · 463-line Lark PEG grammar · 1,175 tests across 10 phases
> CLI tool: `bplc` with 10 subcommands

---

## 1. Repository Layout

```
BPL/
├── bpl/                          # Compiler & runtime source (30K lines)
│   ├── grammar/
│   │   └── bpl.lark              # 463-line Lark PEG grammar (v2.4)
│   ├── parser/                   # Stage 1: Lexing & parsing
│   ├── ast/                      # Stage 2: AST node definitions (9 modules)
│   ├── transformer/              # Stage 2→3: Grammar tree → typed AST
│   ├── types/                    # Stage 3: Dimensional analysis & unit engine
│   ├── state/                    # Stage 4: Container state tracking & trust model
│   ├── validation/               # Stage 4: Semantic validation & setup checks
│   ├── lowering/                 # Stage 5: Intent → execution primitives
│   ├── location/                 # Address normalization (well IDs, plates)
│   ├── scheduler/                # Stage 6: DAG scheduling & resource management
│   ├── graph/                    # Workflow graph (Mermaid/ReactFlow)
│   ├── simulation/               # Virtual deck simulation
│   ├── export/                   # Worklist export (CSV, Excel, Markdown)
│   ├── runtime/
│   │   ├── human/                # Human-readable protocol generation
│   │   └── robot/
│   │       └── biomek/           # Beckman Biomek robotic codegen
│   ├── audit/                    # GxP audit trail & compliance
│   ├── capabilities/             # Target capability registry
│   ├── errors/                   # Error types, recovery, batch errors
│   ├── agentic/                  # LLM-driven SOP→BPL generation workflow
│   ├── cli/                      # CLI entrypoint (`bplc`)
│   ├── stdlib/                   # Standard library (reserved)
│   └── orchestrator.py           # Pipeline orchestration (three-gate validation)
│
├── tests/                        # 1,175 tests
│   ├── phase0_cli/               # CLI contract tests & vertical slices
│   ├── phase1_parser/            # Grammar, lexer, declarations, expressions
│   ├── phase2_state/             # State model & trust system
│   ├── phase3_lowering/          # Intent lowering, plan IR, well sets
│   ├── phase4_scheduler/         # DAG scheduling
│   ├── phase5_errors/            # Error policy, recovery, batch errors
│   ├── phase6_simulation/        # Virtual deck simulation
│   ├── phase7_human/             # Human runtime backend
│   ├── phase8_robot/             # Robotic runtime backend (Biomek)
│   ├── phase9_audit/             # Audit trail & compliance
│   ├── conformance/              # End-to-end protocol conformance tests
│   ├── export/                   # Worklist export tests
│   └── fixtures/                 # Shared test fixtures
│
├── tools/                        # Development tooling
│   └── corpus/                   # Training corpus generation pipeline
│       └── prompts/              # LLM prompts for corpus generation
│
├── artifacts/                    # Generated outputs
│   ├── check/                    # Validation artifacts
│   ├── dashergfp_pipeline/       # DasherGFP experimental validation
│   └── validate/                 # Validation run outputs
│
├── docs/
│   ├── publication/              # Nature Machine Intelligence manuscript
│   ├── spec/                     # Language specification documents
│   ├── corpus/                   # Corpus documentation
│   └── compressed/               # Compressed reference docs
│
├── openspec/                     # OpenSpec change management
│   ├── config.yaml
│   ├── specs/                    # 12 capability specifications
│   └── changes/                  # Active and archived changes
│
└── data/                         # Historical run data
```

---

## 2. Compiler Pipeline Architecture

The BPL compiler is a six-stage, three-gate deterministic pipeline. Each gate produces typed `Diagnostic` objects (code, severity, message, source location, hint) for targeted repair.

```
Source Code (.bpl)
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  GATE 1: PARSE                                              │
│                                                             │
│  ┌──────────────┐    ┌───────────────┐    ┌──────────────┐  │
│  │ Stage 1:     │───▶│ Stage 2:      │───▶│ Stage 3:     │  │
│  │ Lark PEG     │    │ AST           │    │ Typed AST    │  │
│  │ Parser       │    │ Transformer   │    │ (Dimensions) │  │
│  │ (463 lines)  │    │ (9 modules)   │    │              │  │
│  └──────────────┘    └───────────────┘    └──────────────┘  │
│  bpl/parser/         bpl/transformer/     bpl/types/        │
│  bpl/grammar/        bpl/ast/                               │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  GATE 2: SEMANTIC                                           │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Stage 4: Semantic Analysis                           │   │
│  │  • Unit consistency checking                         │   │
│  │  • Container state tracking (volume, capacity)       │   │
│  │  • Identifier resolution & type safety               │   │
│  │  • Trust model: Declared → Calibrated → Verified     │   │
│  └──────────────────────────────────────────────────────┘   │
│  bpl/state/          bpl/validation/                        │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  GATE 3: PLAN / VALIDATE                                    │
│                                                             │
│  ┌──────────────┐    ┌───────────────┐    ┌──────────────┐  │
│  │ Stage 5:     │───▶│ Stage 6:      │───▶│ Output:      │  │
│  │ Intent       │    │ DAG           │    │ Validated    │  │
│  │ Lowering     │    │ Scheduler     │    │ Plan IR      │  │
│  │ (~15 → ~20)  │    │               │    │              │  │
│  └──────────────┘    └───────────────┘    └──────────────┘  │
│  bpl/lowering/       bpl/scheduler/       bpl/export/       │
│                      bpl/capabilities/    bpl/runtime/      │
└─────────────────────────────────────────────────────────────┘
```

### Orchestration entry point: `bpl/orchestrator.py`

The orchestrator wires the three gates together with deterministic exit codes:

| Exit Code | Meaning |
|-----------|---------|
| 0  | `EXIT_SUCCESS` |
| 2  | `EXIT_USAGE_ERROR` |
| 10 | `EXIT_PARSE_FAILURE` (Gate 1 failed) |
| 11 | `EXIT_SEMANTIC_FAILURE` (Gate 2 failed) |
| 20 | `EXIT_LOWERING_FAILURE` (Gate 3 failed) |
| 30 | `EXIT_SIMULATION_FAILURE` |
| 40 | `EXIT_STRICT_CAPABILITY_FAILURE` |
| 99 | `EXIT_INTERNAL_ERROR` |

---

## 3. Language Components

### 3.1 Grammar (`bpl/grammar/bpl.lark`)

463-line Lark PEG specification defining:

| Declaration Type | Keyword | Purpose |
|-----------------|---------|---------|
| `reagent_decl` | `reagent` | Physical materials with MW, CAS, physical form |
| `stock_decl` | `stock` | Prepared solutions with concentration/fold |
| `labware_decl` | `labware` | Containers with footprint, well count, capacity |
| `protocol_decl` | `protocol` | Executable protocol blocks with annotations |
| `deck_model_decl` | `deck_model` | Robotic deck layout with positions |
| `target_decl` | `target` | Execution targets (human/robot) with capabilities |
| `resource_decl` | `resource` | Shared resources with booking/cooldown |
| `pcr_profile_decl` | `pcr_profile` | PCR thermocycler profiles |
| `type_decl` | `type` | User-defined sum/product types |
| `function_decl` | `function` | User-defined functions |
| `intent_decl` | `intent` | High-level laboratory intent signatures |
| `primitive_decl` | `primitive` | Low-level execution primitive signatures |
| `recovery_decl` | `recovery` | Error recovery handlers |
| `invariant_decl` | `invariant` | Runtime invariant assertions |
| `import_decl` | `import`/`from` | Module imports with versioning |
| `module_decl` | `module` | Namespace modules |

### 3.2 AST (`bpl/ast/` — 9 modules)

| Module | Content |
|--------|---------|
| `base.py` | `SourceSpan`, base AST node class |
| `program.py` | `Program` root node |
| `declarations.py` | All declaration AST nodes (reagent, stock, labware, protocol, etc.) |
| `statements.py` | `CallStmt`, `LetStmt`, `IfStmt`, `ForStmt`, `WhileStmt`, `ParallelBlock`, `SequenceBlock`, `StampStmt`, `CherrypickStmt`, `SerialDiluteStmt` |
| `expressions.py` | Arithmetic, logical, comparison, field access, method calls, lambdas |
| `literals.py` | `NumberLit`, `StringLit`, `BoolLit` |
| `types.py` | Type expression nodes (sum types, product types, constrained types) |
| `units.py` | Unit-annotated quantity nodes |
| `annotations.py` | `@step`, `@target`, `@expected_time`, `@on_error`, etc. |

### 3.3 Type System (`bpl/types/`)

**Compile-time dimensional analysis across 9 base dimensions:**

| Dimension | Units | Examples |
|-----------|-------|---------|
| Volume | `mL`, `uL`, `nL`, `L` | `transfer(... volume: 100 uL)` |
| Mass | `kg`, `g`, `mg`, `ug`, `ng`, `pg` | `add(NaCl, mass: 10 g, ...)` |
| Temperature | `degC`, `K` | `incubate(... temperature: 37 degC)` |
| Time | `h`, `min`, `s`, `ms` | `wait(duration: 30 s)` |
| Concentration | `M`, `mM`, `uM`, `nM`, `pM` | Molar concentrations |
| Amount | `mol`, `mmol`, `umol`, `nmol`, `pmol` | Molar amounts |
| Pressure | `atm`, `psi`, `kPa`, `bar` | Equipment settings |
| Speed | `rpm`, `rcf` | `centrifuge(... speed: 3000 rpm)` |
| Length | `cm`, `mm`, `um`, `nm`, `bp`, `kb`, `Mb` | DNA lengths |

**Compound dimensions (derived automatically):**
- Mass concentration: `g/L`, `mg/mL`, `ug/mL`, `ng/uL`
- Molar concentration: `mol/L`, `mmol/L`, `umol/L`
- Flow rate: `uL/s`, `mL/min`
- Temperature rate: `degC/min`
- Molar mass: `g/mol`
- Fold factors: `100X`, `1000X`
- Percent: `%`, `percent`

**Implementation:**
- `dimensions.py` — `Dimension` enum + `DimensionVector` (algebraic exponent vectors)
- `unit_engine.py` — `Unit` (name + dimension + SI scale), `Quantity` (value + unit), unit arithmetic & conversion
- `builtin_types.py` — Built-in type definitions
- `concentration.py` — Concentration-specific logic

### 3.4 Container State Tracking (`bpl/state/`)

Every container is a stateful entity tracked from declaration through every operation:
- **`state_model.py`** — `StateProperty[T]` (value + unit + uncertainty + trust + timestamp), `PlateContents` (sparse plate representation), `StateTransition` (hash-based state changes), `StateDelta` (incremental changes for audit trail)
- Volume accounting: `transfer` decrements source, increments destination; capacity violations are compile-time errors

### 3.5 Trust Model (`bpl/state/trust.py`)

Three-tier provenance tracking for GxP compliance:

| Tier | Confidence | When Required | Source |
|------|-----------|---------------|--------|
| `Declared` | Low | Research context | User/compiler assertion |
| `Calibrated` | Medium | GLP critical properties | Instrument measurement (balance, pipette, plate reader, pH meter, etc.) |
| `Verified` | High | GMP all changes | Calibrated + operator sign-off with `ComplianceSignature` (21 CFR Part 11) |

Trust propagation: `concentration.trust = min(mass.trust, volume.trust)`

Regulatory contexts: `RESEARCH`, `GLP`, `GMP` — each enforces different minimum trust levels.

### 3.6 Laboratory Intents & Primitive Lowering (`bpl/lowering/`)

**~15 high-level intents (user-facing):**

| Category | Intents |
|----------|---------|
| Liquid handling | `transfer`, `add`, `distribute`, `consolidate`, `serial_dilute` |
| Plate operations | `stamp` (1:1 plate copy), `cherrypick` (selective wells) |
| Physical processes | `mix`, `incubate`, `centrifuge`, `wait` |
| Specialized | `run_pcr`, `pick_colonies`, `adjust_ph`, `heat_shock`, `on_ice` |
| Manual/control | `manual` (with `StateDelta`), `checkpoint` |

**~20 execution primitives (machine-level):**

| Category | Primitives |
|----------|-----------|
| Liquid handling | `ASPIRATE`, `DISPENSE`, `MIX` |
| Tip handling | `PICK_TIPS`, `DROP_TIPS` |
| Plate handling | `MOVE_LABWARE`, `SEAL_PLATE`, `UNSEAL_PLATE` |
| Measurement | `READ_ABSORBANCE`, `READ_FLUORESCENCE`, `WEIGH` |
| Temperature | `SET_TEMPERATURE`, `INCUBATE` |
| Centrifugation | `CENTRIFUGE` |
| Human steps | `HUMAN_STEP`, `PAUSE`, `RESUME` |
| Control flow | `WAIT`, `CHECKPOINT` |
| Specialized | `PICK_COLONIES`, `ADJUST_PH`, `HEAT_SHOCK`, `ON_ICE`, `RUN_PCR` |

**Implementation:**
- `intent_lowerer.py` — Converts intents → primitive sequences with `LoweringContext` (target, tip policy, flow rate)
- `plan_ir.py` — `ExecutionPlan`, `PlanStep`, all primitive dataclasses, `StepStatus` (PENDING→READY→RUNNING→COMPLETED→FAILED)
- `collection_semantics.py` — Expands plate-level operations to individual well transfers
- `well_sets.py` — Well ID manipulation (ranges, columns, exclusion)

### 3.7 Scheduler (`bpl/scheduler/`)

- `scheduler.py` — DAG-based dependency scheduling, parallel step grouping
- `resource_manager.py` — Shared resource allocation (instruments, deck positions)
- `deck_state.py` — Deck position occupancy tracking
- `tip_optimizer.py` — Tip usage optimization (minimize tip rack changes)
- `deadlock.py` — Deadlock detection in resource graphs

### 3.8 Workflow Graph (`bpl/graph/`)

- `builder.py` — Builds workflow DAGs from execution plans
- `model.py` — Graph data model (nodes, edges, metadata)
- `renderers.py` — Renders to Mermaid diagrams and ReactFlow HTML
- `plan_io.py` — Serializes/deserializes execution plans to/from JSON

### 3.9 Simulation (`bpl/simulation/`)

Virtual deck simulation for protocol validation without physical execution:
- `simulator.py` — Main simulation engine
- `virtual_deck.py` — Virtual deck with containers, volumes, states
- `assertions.py` — Simulation assertions (volume bounds, concentrations)
- `breakpoints.py` — Debugging breakpoints during simulation
- `checkpoint.py` — Simulation state snapshots
- `validation.py` — Post-simulation validation
- `sim_logging.py` — Simulation event logging

### 3.10 Export (`bpl/export/`)

- `worklist_exporter.py` — Main export engine
- `formats.py` — `CSVFormatter`, `ExcelFormatter`
- `markdown_composer.py` — Human-readable Markdown protocols (dual-target: human + robot views)
- `transfer_modes.py` — Transfer volume splitting, multi-dispense optimization
- `volume_constraints.py` — Volume constraint validation for export

### 3.11 Runtime Backends (`bpl/runtime/`)

**Human runtime** (`runtime/human/`):
- `protocol_generator.py` — Human-readable step-by-step protocol generation
- `step_renderer.py` — Step formatting with quantities and annotations
- `execution_ir.py` — Human execution intermediate representation
- `checkpoint_ui.py` — Interactive checkpoint UI
- `data_capture.py` — Data capture forms for operator input
- `signatures.py` — Electronic signature collection
- `timer.py` — Step timing

**Robot runtime** (`runtime/robot/biomek/`):
- `biomek_codegen.py` — Beckman Biomek method file generation
- `biomek_ir.py` — Biomek intermediate representation
- `biomek_translator.py` — Plan IR → Biomek IR translation
- `hybrid.py` — Hybrid human+robot execution

### 3.12 Audit Trail (`bpl/audit/`)

GxP compliance and 21 CFR Part 11:
- `audit_trail.py` — Hash-chained audit trail (SHA-256)
- `chain_hash.py` — Hash chain implementation
- `amendments.py` — Protocol amendments with reason tracking
- `compliance.py` — Compliance checks (signature requirements, audit completeness)
- `export.py` — Audit trail export (CSV, JSON)

### 3.13 Agentic SOP→BPL Generation (`bpl/agentic/`)

LLM-driven generation pipeline:
- `workflow.py` — Core generate–validate–repair loop (pydantic-ai + OpenRouter)
- `sop.py` — SOP document parsing & normalization
- `lab_catalog.py` — Laboratory resource catalog matching (Excel, bilingual aliases)
- `http_client.py` — HTTP client with exponential backoff

### 3.14 Error System (`bpl/errors/`)

- `error_types.py` — Typed error categories
- `error_policy.py` — Error severity policies (fail-fast vs. collect-all)
- `recovery.py` — Error recovery strategies
- `batch_errors.py` — Batch error accumulation

---

## 4. CLI Tool: `bplc`

Entry point: `bpl/cli/main.py`

| Subcommand | Description |
|-----------|-------------|
| `check` | Parse + validate a `.bpl` file through all three gates; report diagnostics |
| `parse` | Parse only (Gate 1); output AST as JSON |
| `lower` | Parse + semantic check + lower to execution plan (Gates 1-3) |
| `validate` | Full validation with experiment setup checking |
| `simulate` | Run virtual deck simulation |
| `export` | Export execution plan to worklist format (CSV/Excel/Markdown) |
| `compose` | Compose dual-target Markdown (human + robot views) |
| `graph` | Generate workflow graph (Mermaid/ReactFlow) |
| `capabilities` | Report target capability compatibility |
| `sop-generate` | Generate BPL from natural-language SOP (agentic workflow) |

---

## 5. Test Organization (1,175 tests)

| Phase | Directory | Focus |
|-------|-----------|-------|
| Phase 0 | `tests/phase0_cli/` | CLI contracts, vertical slices, SOP generation |
| Phase 1 | `tests/phase1_parser/` | Grammar, lexer, declarations, expressions, types, annotations |
| Phase 2 | `tests/phase2_state/` | State model, trust system |
| Phase 3 | `tests/phase3_lowering/` | Intent lowering, plan IR, well sets, location addressing |
| Phase 4 | `tests/phase4_scheduler/` | DAG scheduling |
| Phase 5 | `tests/phase5_errors/` | Error policy, recovery, batch errors |
| Phase 6 | `tests/phase6_simulation/` | Virtual deck simulation |
| Phase 7 | `tests/phase7_human/` | Human runtime backend |
| Phase 8 | `tests/phase8_robot/` | Robot runtime backend (Biomek) |
| Phase 9 | `tests/phase9_audit/` | Audit trail, compliance |
| — | `tests/conformance/` | End-to-end protocol tests (LB media, heat shock, 96-well HTS, etc.) |
| — | `tests/export/` | Worklist export, Markdown composition, volume constraints |

---

## 6. OpenSpec Specifications

12 capability specifications under `openspec/specs/`:

| Spec | Scope |
|------|-------|
| `ast-diagnostics` | AST node structure and diagnostic types |
| `cli-orchestration` | CLI command routing and pipeline orchestration |
| `location-addressing` | Well ID normalization and plate addressing |
| `plan-lowering` | Intent-to-primitive lowering rules |
| `runtime-backends` | Human and robot runtime contracts |
| `scheduler` | DAG scheduling algorithms |
| `simulation` | Virtual deck simulation engine |
| `state-trust-audit` | State model, trust tiers, audit trail |
| `unit-engine` | Dimensional analysis and unit arithmetic |
| `version-governance` | Grammar versioning and compatibility |
| `worklist-export` | Export format specifications |

---

## 7. Key Design Principles

1. **Deterministic compilation** — Identical source → byte-identical outputs. No randomness, no timestamps in compilation artifacts.
2. **Domain-native types** — Physical units are first-class, not library additions. The compiler rejects `100 uL + 50 mg` at compile time.
3. **Intent–primitive separation** — High-level laboratory operations (~15 intents) lower to machine-level primitives (~20), enabling multi-target execution from single source.
4. **Stateful containers** — Every container's volume, concentration, and capacity are tracked through every operation. Capacity overflow = compile-time error.
5. **Trust provenance** — Three-tier trust model (Declared→Calibrated→Verified) with trust propagation through derived quantities. Maps directly to GLP/GMP regulatory requirements.
6. **Compiler as oracle** — The deterministic compiler serves as a verification oracle for LLM-generated code, forming a closed generate–validate–repair loop.
