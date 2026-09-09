# Translation Record

- Status: validated local case
- Coverage: representative fixed-cell RPE1 imaging mainline
- Runtime status: 133/133 generated active steps completed with no runtime diagnostics
- Source: protocols.io 96916, CC BY 4.0 adaptation

## Step Alignment

| Source section | Culsma construct | Status | Notes |
|---|---|---|---|
| S1 cell seeding | well allocation with cell count and medium, followed by a CO2/thermal hold | current | The representative chamber capacity and initial culture conditions are explicit. |
| S2 transfection | transfection-mixture construction, transfer, and timed holds | bridge | Transfection is represented as declared material exposure rather than predicted biological effect. |
| S3 serum starvation | aspiration with retained adherent cells, medium replacement, and CO2/thermal hold | current | Liquid removal and retained-cell continuity are explicit. |
| S4 fixation | PFA transfer, timed hold, and three aspiration-style PBS washes | bridge | Fixation is represented operationally. |
| S5 permeabilization, quenching, and blocking | reagent transfers, timed holds, and aspiration removals | bridge | Chemical cell-state transitions are not predicted. |
| S6 primary antibody | antibody transfer, overnight cold hold, and three PBS washes | bridge | Antibody specificity and binding are not predicted. |
| S7 secondary antibody | antibody transfer, room-temperature hold, and three PBS washes | bridge | Antibody specificity and binding are not predicted. |
| S8 DAPI and imaging | stain, wash, mounting solution, `data_schema`, and `img(...)` | bridge | Image acquisition fields are recorded; hardware control and image interpretation remain outside the program. |

## Main Boundaries

- Transfection, fixation, permeabilization, antibody binding, and staining specificity are represented as declared operations, not predicted biological state transitions.
- Confocal hardware settings, deconvolution, and image interpretation remain acquisition metadata or downstream analysis.

## Translator Notes

- The same `rpe1_cells` well is preserved through transfection, serum starvation, fixation, staining, and imaging.
- Aspiration uses the adherent-cell filtration program; removed liquid is routed through `contents[0]` to waste while the original well retains the adherent-cell state.
- This benchmark mainline intentionally selects the fixed-cell RPE1 workflow from the broader public protocol.
