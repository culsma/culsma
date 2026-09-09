# Translation Record

- Status: reviewed local case revision
- Coverage: single-sample magnetic-bead cDNA capture mainline plus batch execution wrapper
- Source class: anonymized vendor-manual excerpt
- Product/vendor names: intentionally omitted
- Reviewed date: 2026-06-03

## Revision Notes

- Made the public benchmark wording standalone: source-step text now refers to barcoded lysate input material and the next template-switch reaction module instead of external manual sections.
- Added `EvercodeWTMegaV3_RunSection2_1Batch(selected_lysate_count = 1)` as an outer execution wrapper that repeats the single-lysate module.
- Kept `EvercodeWTMegaV3_Section2_1_cDNACapture_Reviewed` as the single-lysate wet-lab module.
- Updated brief spin-down annotations to the reviewed convention `3000g for 5s` where no material partition is intended.
- Updated the bead-safe post-binding brief spin-down annotation to the protocol-specific tested condition `100g for 8s`.
- Retained `magnetic_program(duration = 2min)` for timed magnetic separations.
- Retained the reviewed `80% volume x 10` self-transfer convention for under-specified resuspension.

## Validation Note

The current file has one explicit top-level wrapper invocation. The wrapped
single-sample protocol is a subprotocol and is not independently invoked. The
full file passed parse, resolve, compile, validate, typecheck, and run with
127/127 generated active steps completed and no diagnostics.
