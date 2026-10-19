# Qubit 1X dsDNA High-Sensitivity Quantification of One DNA Sample

Measure the concentration of one double-stranded DNA sample using the ready-to-use Qubit 1X dsDNA High-Sensitivity Assay. Start with 51 uL of DNA solution in the original sample tube. This protocol uses 1 uL of the undiluted DNA sample, leaving 50 uL in the original tube for downstream double-sided SPRI bead size selection, and prepares a new two-standard calibration.

## Steps

1. Set up three clear, thin-wall 0.5 mL assay tubes: Standard 1, Standard 2, and DNA Sample. Label the lids rather than the sides of the tubes.
2. Add 10 uL of Qubit 1X dsDNA HS Standard 1, supplied at 0 ng/uL, to the Standard 1 tube.
3. Add 10 uL of Qubit 1X dsDNA HS Standard 2, supplied at 10 ng/uL, to the Standard 2 tube.
4. Add 1 uL of the DNA sample to the DNA Sample tube.
5. Add 190 uL of ready-to-use Qubit 1X dsDNA HS Working Solution to each standard tube and 199 uL to the DNA Sample tube. The final assay volume is 200 uL per tube.
6. Vortex all three tubes vigorously for 3-5 seconds without creating bubbles.
7. Incubate all three tubes at room temperature for 2 minutes.
8. On the Qubit fluorometer, select the 1X dsDNA High Sensitivity assay and start a new standard calibration.
9. Insert the Standard 1 tube, close the instrument lid, and read Standard 1. Remove the tube when the reading is complete.
10. Insert the Standard 2 tube, close the instrument lid, and read Standard 2. Remove the tube when the reading is complete.
11. Select the sample-reading mode. Set the sample volume to 1 uL and the output concentration unit to ng/uL.
12. Insert the DNA Sample tube, close the instrument lid, and read the sample. Remove the tube when the reading is complete.
13. Record and return the calculated concentration of the DNA sample in ng/uL as the protocol result.

## Source and coverage review

Source: Thermo Fisher Scientific, *Qubit 1X dsDNA HS Assay Kits User Guide*,
publication MAN0017455, revision C.0. The submitted wording is retained in
[the original source](../../composites/03-qubit-double-sided-spri/submission/sources/Qubit_source.md).

S8 is uncovered: the schema labels the calibration readouts and the grouped
`img` reads both standards, but neither configures selection of the named assay
or starts a new instrument calibration. A result schema declares fields, not an
instrument program. S9 and S10 correspond to the two ordered standard readouts.
S11 has a sample-volume field assignment; the assay/unit context is described by
the schema and source comments rather than a complete instrument configuration.

The remaining matches use the shared structural correspondence rule: allocations
represent tube setup, transfers represent additions, agitation and timed holds
represent mixing and incubation, and custom readouts and return statements
represent acquisition and result handoff. They do not verify bubble avoidance,
physical lid handling, calibration success, or a measured concentration. Stub
result fields remain unset except for the declared 1 uL assay input. No numeric
concentration is invented. See the preserved [author record](../../composites/03-qubit-double-sided-spri/submission/records/Qubit_record.md).
