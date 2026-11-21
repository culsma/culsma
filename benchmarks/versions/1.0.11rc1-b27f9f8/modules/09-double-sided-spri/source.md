# Double-Sided SPRI Bead Size Selection of Fragmented and End-Prepared DNA

Inputs:

- DNA sample: 50 uL of fragmented and end-prepared DNA solution in a 0.2 mL tube.
- DNA concentration: the `dna_concentration_ng_per_uL` value returned by the preceding Qubit protocol for this same DNA sample, in ng/uL. Receive this measured value as an input; do not assign a new concentration in this protocol.

## Steps

1. Gather freshly prepared 85% ethanol.
2. Gather room-temperature SPRI beads, approximately 50 uL per DNA sample. Ensure that the SPRI beads have equilibrated to room temperature for at least 30 minutes.
3. Vortex the SPRI beads until fully mixed. Add 30 uL of SPRI beads to the tube containing 50 uL of fragmented and end-prepared DNA solution.
4. Vortex the tube for 5 seconds, then briefly centrifuge.
5. Incubate for 5 minutes at room temperature.
6. Place the tube on the high position of a magnetic rack for 0.2 mL tubes. Incubate until the solution clears, approximately 2 minutes.
7. While the tube remains on the magnetic rack, transfer 75 uL of supernatant containing the fragmented and end-prepared DNA into a new 0.2 mL tube. Discard the tube containing the bead pellet.
8. Add 10 uL of SPRI beads to the retained supernatant.
9. Vortex the tube for 5 seconds, then briefly centrifuge.
10. Incubate for 5 minutes at room temperature.
11. Place the tube on the high position of the magnetic rack. Incubate until the solution clears, approximately 3 minutes. Ensure that the solution is completely clear before proceeding.
12. While the tube remains on the magnetic rack, remove and discard the supernatant.
13. While the tube remains on the magnetic rack, add 180 uL of 85% ethanol.
14. Incubate for 1 minute at room temperature.
15. While the tube remains on the magnetic rack, remove and discard the supernatant.
16. Repeat steps 13-15 once for a total of two ethanol washes. Remove any residual ethanol with a P20 pipette.
17. While the tube remains on the magnetic rack, air-dry the SPRI beads for approximately 30 seconds. Do not over-dry the beads because this can substantially reduce yield. Cracking of the beads indicates over-drying.
18. Remove the tube from the magnetic rack. Fully resuspend the bead pellet with 50 uL of nuclease-free water.
19. Incubate for 5 minutes at room temperature.
20. Place the tube on the high position of the magnetic rack. Incubate until the solution clears, approximately 2 minutes.
21. While the tube remains on the magnetic rack, transfer 50 uL of supernatant into a new 0.2 mL tube.

## Storage note

The size-selected fragmented and end-prepared DNA may be stored at 4 C for up
to 18 hours or at -20 C for up to 2 weeks. Storage after return remains a note.

## Source and coverage review

The 21 source steps retain the submitted wording; see [the original source](../../composites/03-qubit-double-sided-spri/submission/sources/Double_Sided_SPRI_source.md)
and [author record](../../composites/03-qubit-double-sided-spri/submission/records/Double_Sided_SPRI_record.md).
Source-step matches use the same structural rule as the existing collection,
not a claim that every clause or physical endpoint is verified.

S3 includes the author's 30 s vortex convention. S4/S9 use the adopted
non-fractionating centrifuge action at 3000g for 5 s. S6/S11/S20 correspond to
timed magnetic separation; rack height and observed clarity are not executable
checks. S7 transfers 75 uL and leaves the original tube with its retained
fraction and 5 uL liquid; disposal remains an instruction in the source.
S16 matches the second wash via the repeat loop; no additional residual-ethanol
aliquot is invented. S17 uses a 30 s hold without an evaporation or dryness
model. S18 includes the author's ten 40 uL self-transfer mixing strokes.

Unknown DNA masses and explicit class fates describe the declared constituent
routing, not measured efficiencies or quantitative recovery. The supplied Qubit
concentration field is unused by the fixed-volume procedure. The standalone
entry point supplies an unset local result field; the composite instead passes
its actual Qubit readout field. No concentration or DNA recovery is fabricated.
