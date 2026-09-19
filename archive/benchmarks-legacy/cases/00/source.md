# 00 GFP Lysate Clarification Fluorescence Readout

Source class: canonical textbook-style workflow, independently authored for the Culsma paper teaching example.

This case models a short fluorescent microbial-cell lysate preparation. A GFP-expressing microbial-cell suspension is mixed with lysis buffer, incubated, clarified by centrifugation, and read by fluorescence. The completed run retains the clarified lysate and discards the debris pellet.

The source is intentionally not copied from any proprietary or published protocol. It is a compact canonical description of common teaching-lab and molecular-biology-lab assay structure, written to demonstrate material mutation, environmental hold, centrifugation slot semantics, explicit route assignment, object continuity, and terminal optical readout.

## Parameters

| Parameter | Default value | Meaning |
| --- | --- | --- |
| cell_suspension_volume | 80 uL | Volume of the washed GFP-expressing microbial-cell suspension in lysis-compatible resuspension buffer. |
| cell_count | 100000 cells | Number of GFP-expressing microbial cells carried by the suspension. |
| lysis_buffer_volume | 80 uL | Volume of 2x lysis buffer added to produce a 1x final lysis condition. |
| clarified_volume | 100 uL | Volume of clarified supernatant routed to the clarified-lysate output tube after centrifugation. |

## Materials And Containers

1. Prepare 100000 washed GFP-expressing microbial cells in 80 uL lysis-compatible resuspension buffer.
2. Prepare at least 80 uL 2x lysis buffer.
3. Prepare one 1.5 mL lysis tube.
4. Prepare one 1.0 mL clarified-lysate output tube.
5. Prepare one 1.0 mL debris-waste tube.

## Canonical Workflow

1. Transfer 80 uL washed GFP-expressing microbial-cell suspension containing 100000 cells and 80 uL 2x lysis buffer into the 1.5 mL lysis tube.
2. Mix the lysis mixture by pipetting 10 times.
3. Incubate the lysis mixture at 37 C for 30 min.
4. Centrifuge the lysate at 12000 x g and 22 C for 10 min to resolve a clarified supernatant fraction and a debris-pellet fraction.
5. Transfer 100 uL clarified supernatant fraction to the clarified-lysate output tube.
6. Discard the debris-pellet fraction.
7. Record a fluorescence readout from the clarified lysate.

## Source Notes

- This example uses centrifugation slot semantics: slot 0 is the clarified supernatant and slot 1 is the pellet/debris fraction.
- Fluorescence intensity interpretation, normalization, and pass/fail thresholds are downstream analysis or data-validation concerns, not inferred by the wet-lab execution kernel.
- The case is deliberately short so it can be reused as a teaching example in prose, semantic-model discussion, and object-continuity audit tables.
