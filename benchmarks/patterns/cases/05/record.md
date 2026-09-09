# Translation Record

- Status: validated local case
- Coverage: PBMC flow-cytometry immunophenotyping mainline
- Validation: parse / semantic validate / typecheck / runtime passed; 862/862 generated active steps completed
- Related PM issues: culsma/culsma-pm#14

## Step Alignment

| Source phase | Culsma representation | Coverage |
|---|---|---|
| S1 sample and control assignment | fully stained, unstained, isotype, and five single-antibody control roles | current |
| S2 PBMC aliquot | explicit cell concentration, 100 uL aliquot, and precision/carryover requirements | current |
| S3 initial wash | 2 mL wash, 300 x g centrifugation, and explicit supernatant/pellet routing | current |
| S4 Fc blocking | 65 uL resuspension, 5 uL Fc block, mixing, and ice incubation | current |
| S5 full-panel preparation | five antibodies and viability dye combined under precision and light-protection requirements | current |
| S6 control preparation | isotype, five single-antibody, and unstained-control reagents | current |
| S7 sample staining | assigned 30 uL reagent, mixing, and protected 30 min ice incubation | current |
| S8 stain washes | two explicit wash/centrifugation cycles with declared stain retention and cell-bound relationships | current |
| S9 fixation | fixation-buffer addition, resuspension, and protected room-temperature incubation | current |
| S10 acquisition preparation | post-fix wash with bound-stain retention, 500 uL acquisition-buffer resuspension, and protected cold hold | current |
| S11 event acquisition | eight identified single-cell event streams with sample and control roles | current |

## Remaining Boundaries

- Compensation matrices, gates, subset hierarchy, population calls, and percentages remain downstream analysis over observed events.
- Gates, population definitions, and derived percentages remain downstream analysis over the recorded event streams.

## Non-Gaps

- Marker identity is preserved with `markers([...])`, and the fixed stained PBMC material is explicitly connected to a `single_cell` stream.
- The first post-staining wash applies declared benchmark retention fractions, records retained antibodies and viability dye as `cell_bound` to PBMCs, and preserves those relationships through later washes.
- Acquisition results carry explicit sample identities and control roles for the full panel, isotype, unstained, and single-antibody controls.
- Staining, cold handling, light protection, wash cycles, fixation, and resuspension are represented through the core language.
- The program records observed event fields without claiming that compensation, gating, or biological population calls were inferred.
