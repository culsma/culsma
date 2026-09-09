# Translation Record

## Current benchmark evidence

The published case has 12 source steps and completes 344/344 generated active steps. See [step alignment](alignment.json), [run summary](runtime_summary.json), and the [case page](https://culsma.dev/papers/patterns-benchmark/cases/02.html) for the current program and evidence.

## Historical authoring record

The notes below document an earlier 10-step, 254-step draft. Their step labels, syntax examples, and development-status statements are historical, not the current benchmark measurements or language-support status.

- Status: validated draft
- Coverage: mainline canonical workflow
- Local validation: parse / semantic validate / typecheck / runtime passed; plan lowering produced 254 steps
- MCP validation: not stored
- Related PM issues: culsma/culsma-pm#14

## Step Alignment

| Source phase | Culsma representation | Coverage |
|---|---|---|
| S1 sample setup | `well(...)`, `tube(...)`, `chamber(...)`, content constructors | current |
| S2 lysis | PBS material movement, lysis-buffer collection into lysate tubes, environment hold | current |
| S3 column loading and filtration | `sep(... filtration_program(membrane = "silica", drive = "centrifuge"))` with filtrate routed to waste and retained column state preserved | current as declared routing |
| S4 DNase cleanup | wash transfers, on-column DNase mix, `with env` incubation, repeated filtration washes | current as declared operations |
| S5 RNA elution and QC | elution via filtration split, `phy(quantity = customized, schema_ref = RNAQualityReadout)` | bridge |
| S6 reverse transcription | reverse-transcription reaction assembly and staged thermal holds | current |
| S7 qPCR layout | `plate(...)` plus selectors for sample/gene/replicate/control groups | current |
| S8 qPCR loading | grouped well mutations with registered `high_precision` and `low_carryover` constraints | current |
| S9 qPCR cycling | activation hold, `repeat ... schedule(...)`, denaturation/annealing-extension holds, fluorescence imaging | current as declared operations |
| S10 qPCR result | customized `img` schema for well/gene/replicate/Ct/melt/normalization fields | current readout shell; downstream analysis out of scope |

## Resolved During Authoring

- Plate layout uses the registered plate-selector pattern from 04: declare a plate descriptor, bind logical well groups with selectors, and load groups directly.
- qPCR fluorescence is represented through the current readout family (`img(quantity = fluorescence)` during cycles and `img(quantity = customized, schema_ref = ...)` for final structured output).
- RNA cleanup uses current material-flow semantics: column loading, washing, filtration, retained-state routing, and eluate collection are represented as explicit material transfers and `sep` slots rather than hidden kit-specific operators.
- Execution requirements reuse registered vocabulary: `high_precision` and `low_carryover`.
- Strict content-type validation was satisfied by using `custom_` prefixes for local extension reagent labels such as `custom_dnase_i`, `custom_reverse_transcription_mix`, `custom_qpcr_master_mix`, and `custom_primers`.
- RNA collection tubes were sized to match the current filtration-routing model. This is a container-capacity accommodation, not a claim about selective RNA recovery or eluate composition.

## Remaining Gaps

- Replicate relationships are encoded by well-group naming and schema fields, not by first-class replicate metadata.

## Non-Gaps

- Primer identity, target gene identity, housekeeping gene identity, and no-template-control identity can be preserved as reagent names, well-group names, and schema fields without requiring new execution-kernel semantics.
- Reverse-transcription and qPCR temperature programs can be represented with `with env` and `thermal_program(...)`; a dedicated RT/qPCR primitive is not required for this benchmark draft.
- Ct calling, baseline correction, melt-curve peak calling, replicate aggregation, outlier rules, delta-Ct, delta-delta-Ct, and fold-change are downstream analysis/dataflow concerns rather than wet-lab execution-kernel requirements.
- qPCR amplification, silica retention, impurity removal, and elution success are not inferred by the runtime. The protocol only declares the operations, routing, and observations.

## Boundary Notes

This case intentionally separates wet-lab execution from downstream quantitative analysis and scientific mechanism. Culsma records declared material state, plate grouping, thermal execution, routing, and structured observations. It does not infer selective molecular binding, reaction success, Ct values, or normalized gene-expression estimates unless those are provided as observed data or handled by a separate analysis layer.
