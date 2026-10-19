# Composite 03: Qubit Quantification and Double-Sided SPRI Selection

## Context

This composite is adapted from [PM #142](https://github.com/culsma/culsma-pm/issues/142)
and its [2026-10-19 submission](submission/manifest.json). The three steps below
state the composition contract from that submission; they are an editorial
summary, not a newly supplied vendor procedure. The submitted module procedures
retain their original 13 Qubit and 21 SPRI source steps:
[Qubit source](submission/sources/Qubit_source.md) and
[SPRI source](submission/sources/Double_Sided_SPRI_source.md).

## Steps

1. Prepare two Qubit standards in their declared order and one original DNA tube containing 51 uL of DNA solution.
2. Run the Qubit 1X dsDNA HS module with the two standards and the original DNA tube, using 1 uL of DNA and returning its concentration readout while leaving 50 uL in that same tube.
3. Pass the same original tube and its Qubit concentration result field to the double-sided SPRI module; use the declared fixed bead additions, perform both ethanol washes, and return the 50 uL eluate in a new tube without assigning a quantitative DNA recovery.

## Execution and representation boundaries

The two brief spins use non-fractionating `AgitationMode.CENTRIFUGE` at 3000g
for 5 s. The SPRI module explicitly declares unknown-mass DNA classes and their
separation fates. These fates do not predict physical binding efficiency or
quantitative recovery. The concentration result field is passed between modules;
the Stub driver leaves it unset, and SPRI uses fixed reagent volumes.

The shared checker evaluates these three composition steps separately from
Module 08's 13 Qubit steps and Module 09's 21 SPRI steps. The additional-workflow
manifest includes all three entries. Their counts must not be presented as only
three source steps for the complete workflow.

## Packaging

`protocol.culs` is the entry point, with reusable definitions in Modules 08 and 09.
Source-relative `include` paths follow the other benchmark composites and work
without a configured library root. The submitted `import` statements and
qualified calls are adapted accordingly. The Qubit module's standalone example
call is excluded from the reusable definition file, as in the existing modules.
Module source-step markers correspond to their own numbered source inventories.
All experimental statements, parameters, return declarations and separation
fates are retained. The six deprecated header-return warnings remain visible.

`submission/` preserves all 11 original files and their manifest byte for byte,
including historical discussion and the author's 1.0.9 validation artifacts.
Current locally reproduced records use the normal `results/run.json`,
`results/results.json` and `results/coverage.json` layout. Historical source
paths in the submitted records describe the author's machine.
