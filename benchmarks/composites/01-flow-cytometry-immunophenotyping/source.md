# Composite 01: Suspension-Cell Staining and Flow-Cytometry Acquisition

## Steps

1. Run Module 04 with anti-CD45-FITC, anti-CD3-PE, and anti-CD4-Cy5 to prepare six fixed cell suspensions: a fully stained sample, an unstained control, an isotype-control panel, and one single-antibody control for each antibody.
2. Define one acquisition panel containing CD45-FITC, CD3-PE, CD4-Cy5, and the viability signal, and use the same acquisition configuration for all six tubes.
3. Assign each tube a stable sample identity and one of the following control roles: experimental sample, autofluorescence control, isotype control, or single-stained control.
4. Acquire each tube as a single-cell event stream and record event identity, sample identity, control role, FSC-A, FSC-H, SSC-A, raw CD45, CD3, CD4, and viability signals, acquisition configuration identity, and acquisition quality status.
5. Return the six acquisition readouts as one ordered result group for downstream compensation, gating, and population analysis; do not perform those downstream analyses in this protocol.
