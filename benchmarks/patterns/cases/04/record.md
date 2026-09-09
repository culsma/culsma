# Translation Record

## Current benchmark evidence

The published case has 10 source steps and completes 778/778 generated active steps. See [step alignment](alignment.json), [run summary](runtime_summary.json), and the [case page](https://culsma.dev/papers/patterns-benchmark/cases/04.html) for the current program and evidence.

## Historical authoring record

The notes below document an earlier 672-step draft. Their syntax examples and development-status statements are historical, not the current benchmark measurements or language-support status.

- Status: validated draft
- Coverage: mainline canonical workflow
- Local validation: parse / compile / semantic validate / typecheck passed; plan lowering produced 672 steps
- MCP validation: validate_before_store passed remotely when stored
- Authoring lesson: tracked in culsma/culsma-pm#7
- QC helper backlog: tracked in culsma/culsma-pm#11

## Step Alignment

| Source phase | Culsma representation | Coverage |
| --- | --- | --- |
| Plate layout | `plate(...)` plus selectors for standards, unknowns, controls, and blanks | covered |
| Coating | `assay_wells << [capture_antibody:100uL] with constraint(high_precision, low_carryover)` plus `with env(...)` | covered |
| Washing | wash buffer addition, `agit(...)`, `sep(... filtration_program(...))`, waste routing | covered |
| Blocking | constrained blocking-buffer load, incubation, repeated wash | covered |
| Standard curve loading | constrained `series(...)` over `standard_wells` | covered for loading, not curve fitting |
| Unknown sample loading | explicit constrained plate selector loads into `B1` and `B2` | covered |
| Blank/control loading | explicit constrained blank, positive-control, and negative-control well loads | covered as content/code and plate selector roles |
| Detection/enzyme/substrate | constrained additions and timed holds; substrate development uses `dark_protected` | covered |
| Absorbance readout | `img(... quantity = customized, schema_ref = absorbance_schema, save_raw = true)` | covered as generic readout |
| Simple QC gates | `if <readout>.result.absorbance_450nm ...` assigns QC pass flags | covered for threshold checks |

## Resolved During Authoring

1. ELISA wash removal is represented through existing `sep(... filtration_program(...))` semantics rather than a new wash-removal primitive.
2. Plate layout now uses existing `plate(...)` and selector syntax rather than manually declared wells.
3. Simple blank/control QC is expressible today with `data_schema`, `img`, `data_ref.result` fields, and `if` branches.
4. Constraint syntax is implemented; the authoring issue was vocabulary choice. `protect_from_light` maps to current `dark_protected`. Uniform loading is partly represented with current `high_precision` and `low_carryover`; `wash_step` is not a requirement and remains an operation sequence.

## Remaining Gaps

1. Replicate-group relationships are still not first-class assay layout metadata.
2. Standard curve fitting, concentration interpolation, and curve-quality metrics remain downstream analysis concerns, not current execution-kernel semantics.
3. Complex QC metrics such as mean blank, replicate CV, multi-control aggregation, and plate-level validity may need a future QC helper library or data-validation layer.
4. Absorbance is still represented as generic `customized` image/readout data rather than a technique-specific ELISA/readout operator.
5. A true `uniform_plate_loading` requirement is not currently in the frozen requirement vocabulary. Current use of `high_precision` and `low_carryover` is an approximation, not a full replacement.
6. Authoring boundary observed: trailing `with constraint(...)` on a let-bound readout can prevent later `data_ref.result` assignment from compiling. This case therefore leaves readout constraints off the let-bound readouts used by QC branches.

## Boundary Notes

The QC thresholds in this case are authored as protocol-level checks over observed data fields. They do not make the kernel infer biological truth. The kernel only records and branches over user-declared readout fields.

The current case intentionally avoids standard-curve regression and concentration interpolation because those require post-run analysis/dataflow semantics that are outside the current wet-lab execution kernel.
