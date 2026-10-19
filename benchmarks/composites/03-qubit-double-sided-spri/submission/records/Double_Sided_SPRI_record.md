# E01 Double-Sided SPRI Record

## Current Protocol

- `input_dna` is a formal input: the caller's existing 0.2 mL tube containing 50 uL DNA solution after Qubit sampling.
- `dna_concentration_ng_per_uL` carries the corresponding Qubit result. It does not change the fixed reagent volumes or provide unknown fraction masses.
- First material-entry contract: the input's first material is its volume-defined DNA solution, matching the current Qubit input.
- First selection: 30 uL SPRI suspension. After incubation, `materials.replace` exposes `ROUND1_BOUND_FRAGMENT` and `ROUND1_FREE_FRAGMENT`, both `unknown(dimension = mass)`, together with the existing 50 uL liquid carrier.
- Retain 75 uL first-round supernatant. The bound fraction and uncollected liquid remain in the original tube for disposal.
- Second selection: add 10 uL SPRI suspension. After incubation, replace only the transferred `ROUND1_FREE_FRAGMENT` with `ROUND2_BOUND_FRAGMENT` and `ROUND2_FREE_FRAGMENT`, both unknown mass.
- Retain the second-round bound fraction in the same second-selection tube; discard its free fraction.
- Wash twice with 180 uL 85% ethanol. Add 50 uL nuclease-free water, incubate, and transfer 50 uL eluate to the returned product tube.

## Material Semantics

- Bound/free are round-specific author-declared classes. The 100% class fates specify their qualitative destinations, not measured binding efficiencies or quantitative recoveries.
- No numerical bp cutoffs, class abundances, DNA masses or Qubit concentration were invented.
- Each dispensed bead suspension is exposed as unknown-mass solid support plus its known carrier volume: 30 uL in round one and 10 uL in round two. This preserves suspension volume instead of treating it entirely as solid bead volume.
- Replacement provenance records that both second-round DNA classes originate from the transferred first-round free class. The runtime labels the replacements `mass_balance: not_quantified`; this is not a numerical mass-conservation calculation.
- During washing, the second-round bound DNA is routed with the beads. Following water elution, that same DNA identity is routed into the liquid product. Its code identifies the fraction selected during round two, rather than asserting a continuing bound relationship in the eluate.
- No explicit bead-association transition is added. This version verifies separation-output routing and provenance, not an independently declared bead-bound molecular relationship.

## Verification Before Adding Spin-Down

Run with local Culsma 1.0.8 using a separate temporary executable fixture containing 50 uL input DNA solution and an unset Qubit concentration field. The production protocol remains parameterized for a later composite caller.

- Semantic errors: 0; type errors: 0; plan diagnostics: 0.
- Runtime: 44/44 steps completed, 0 failed, 0 skipped, 0 diagnostics.
- Product volume: 50 uL.
- Active product constituents: `ROUND2_BOUND_FRAGMENT` with unknown mass and 50 uL `NUCLEASE_FREE_WATER`.
- Active `ROUND1_BOUND_FRAGMENT` stays in the original input tube; active `ROUND2_FREE_FRAGMENT` goes to liquid waste; second-round beads stay in the second-selection tube.
- The original tube retains 5 uL uncollected liquid. Stock has 10 uL bead suspension left. Waste contains 445 uL, and the product contains 50 uL. Total liquid volume is 510 uL, matching 50 uL input + 50 uL stock + 360 uL ethanol + 50 uL water.
- Zero-quantity historical entries remain visible in some runtime container records; they were excluded when checking active constituents.

## Remaining Source Boundaries

All 21 source steps and the storage note are annotated in the Culsma file.

- S3: the author specified a 30 s vortex duration for the SPRI bead stock. The timed action does not independently verify the fully-mixed endpoint.
- S4 and S9: use the author-approved 3000g for 5s brief-spin convention, represented by standalone sep inside env(thermal = 22C, duration = 5s), per PM #78. These values are an explicit authoring convention, not supplied by the source.
- S6, S11 and S20: timed magnetic holds do not verify the clear-solution endpoint. High rack position is execution-layer information.
- S16: no extra residual-ethanol aliquot is invented. The modeled separated liquid is transferred in full.
- S17: the 30 s hold represents a drying interval; it does not compute evaporation or verify cracking/dryness.
- S18: the author specified 10 self-transfer mixing strokes of 40 uL (80% of the 50 uL water addition). This is now executable immediately after adding water and outside the magnetic-rack environment. These parameters supplement the source and are not claimed as vendor-specified values.
- Storage after return remains a note, not an active hold.

The complete test does not resolve the previously identified Qubit calibration/readout limitations and does not claim a measured numeric concentration.

## Material Selector Update

- The author chose to keep the liquid carriers as separate bookkeeping entries rather than merge them. Their unchanged fates send all carriers to the liquid phase.
- Replaced the three materials.get(...) selectors with positional selectors. First-round input entries before replacement: [0] DNA solution, [1] SPRI bead suspension. Second-round entries before replacement: [0] ROUND1_FREE_FRAGMENT, [1] DNA_INPUT_CARRIER, [2] ROUND1_SPRI_BINDING_SOLUTION, [3] newly added SPRI bead suspension. These orders are documented beside the replacement statements and depend on the existing input/transfer contract.
- A focused test of the original materials.get("SPRI_BEAD_SLURRY") replacement passed 6/6 steps with zero diagnostics on Culsma 1.0.8. The get selector has actual runtime support and was not the cause of PM #140.
- A focused two-round index-selector test, independent of spin-down, passed 16/16 steps with zero diagnostics. The second-round tube contained 85 uL; both second-round DNA products retained ROUND1_FREE_FRAGMENT as their replacement source, and the second-round beads/carrier retained SPRI_BEAD_SLURRY as their source.
- These focused tests do not bypass or resolve the full protocol's spin-down/replace blocker. Production spin-down steps remain unchanged while PM #140 awaits a response.

## Spin-Down Update and Current Execution Blocker

PM #78's final reply confirms standalone sep with centrifuge_program as the executable non-fractionating spin-down convention:
https://github.com/culsma/culsma-pm/issues/78#issuecomment-5583775117

Both S4 and S9 now use this form without binding or transferring separation outputs. The spin-down/replacement blocker is tracked in PM #140: https://github.com/culsma/culsma-pm/issues/140 . The subsequent S18 resuspension update does not alter or bypass this blocker.

Local Culsma 1.0.8 verification of the updated executable fixture:

- Semantic errors: 0; type errors: 0; plan diagnostics: 0.
- Runtime: 23/46 steps completed, 1 failed, 22 skipped, 3 diagnostics.
- First blocking diagnostic: MAT_MATERIAL_REPLACE_ACTIVE_PARTS at the first-round materials.replace after S5: Collect material into a container before replacing its components.
- The standalone spin-down establishes active parts; the subsequent constituent replacement is rejected. No extra mixing, transfers, or source-order changes were added to bypass this interaction.
- The earlier 44/44 result above applies only to the version without the two executable spin-down operations, not to the current file.

## S18 Author-Specified Resuspension Update

- Added 10 self-transfer strokes of 40 uL immediately after the 50 uL water addition; the physical tube identity is unchanged.
- Retested with Culsma 1.0.8: 0 semantic errors, 0 type errors, 0 plan diagnostics; runtime 23/56 completed, 1 failed, 32 skipped, 3 diagnostics.
- Execution still stops at the first-round materials.replace with MAT_MATERIAL_REPLACE_ACTIVE_PARTS, before reaching S18. This is not a successful full-run verification of the newly added resuspension step. No workaround was added while PM #140 awaits a response.

## 2026-10-19: Adopt the Resolved Non-Fractionating Centrifuge Mode

- PM #140 now specifies agit(sample = ..., mode = AgitationMode.CENTRIFUGE, drive = 3000g, duration = 5s) for non-fractionating spin-down. See https://github.com/culsma/culsma-pm/issues/140#issuecomment-6259914944 .
- Replaced both S4/S9 standalone centrifugation separations with this action. Retained an enclosing env(thermal = 22C); the 5 s duration now belongs to agit itself, not the environment.
- No new source comments were added. All other executable statements remain unchanged, including both materials.replace calls. The Qubit composite imports the updated SPRI module without needing its own spin-down changes.
- Parsing the updated module succeeds with the installed Culsma 1.0.8 parser, but that runtime does not implement AgitationMode.CENTRIFUGE. No local semantic/type/runtime pass is claimed for this updated file.
- The issue reports implementation commit 8eb2624 on the unreleased 1.0.9 development line and 81 targeted tests passing. Those are developer-reported results, not a local complete-SPRI validation. The older execution results above are historical and do not describe the current authoring form.

## 2026-10-19: Released 1.0.9 Installation and Full Composite Verification

- Installed the official GitHub v1.0.9 wheel into /Users/mengsun/.venvs/culsma, verifying its published SHA256: 73a3f4a2e9857f76fcac7977531562e9446a3af58b868c84c04f8bef3a737e91. Installed version is 1.0.9, and AgitationMode.CENTRIFUGE is available.
- Executed the actual Qubit_to_Double_Sided_SPRI_composite.culs with /Users/mengsun/Documents/Labword as its import library root. No protocol steps were omitted, and both new non-fractionating centrifuge actions remained in the imported SPRI module.
- Result: 86/86 steps completed, 0 failed, 0 skipped, 0 semantic errors, 0 type errors, 0 plan diagnostics and 0 runtime diagnostics.
- Six non-blocking SEM_RETURNS_HEADER_DEPRECATED warnings flag the older returns(...) declaration syntax. No protocol changes were made to suppress these warnings.
- Material snapshots confirm that the same DnaSample tube starts at 51 uL and contains 50 uL after the Qubit aliquot. Final SizeSelectedDNA volume is 50 uL, with active constituents ROUND2_BOUND_FRAGMENT (unknown mass) and NUCLEASE_FREE_WATER (50 uL).
- This full local run resolves the prior verification blocker for the adopted CENTRIFUGE form. It does not establish actual laboratory recovery, provide a numeric Qubit concentration, or remove the previously documented source-coverage boundaries.
- Saved evidence: /Users/mengsun/Documents/Labword/validation-library/Qubit_SPRI_1.0.9_20261019/ (summary.json, validate.json, run.json, plan.json).
