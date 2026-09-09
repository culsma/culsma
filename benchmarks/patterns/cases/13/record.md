# Review Record

Section 2.4 was reviewed as a standalone post-amplification cDNA purification module. Section 2.5 was intentionally excluded because it is an external quantification/QC workflow using manufacturer assay methods rather than part of this purification protocol.

Key authoring decisions:

- Make the public benchmark wording standalone: source-step text starts from amplified cDNA input material and points to a downstream quantification or analysis module instead of external manual sections.
- Encode the initial source-defined corrective bead mix as a required preventive self-transfer: 3x at 40 uL before the first magnetic separation.
- Use `magnetic_program(duration = 2min)` for magnetic separations; [0] is bead-bound/retained material and [1] is flowthrough/supernatant.
- Use `with env(field = magnetic_rack)` only where source requires persistent on-rack handling across transfers or washes.
- Keep high/low magnet position in annotation as execution-layer mapping.
- Represent brief centrifuge as an annotation-only spin-down convention, 3000g for 5s, not as `sep`.
- Keep residual ethanol removal with P20 in annotation because Culsma currently lacks a structured residual-liquid cleanup primitive or `no_residual_liquid` / `avoid_bead_disturbance` constraint.
- Represent air drying structurally as 25C for about 2 min, while keeping the over-drying/cracking warning in annotation as a state-boundary caution.
- Use 80% of elution volume, 20 uL, for 10 self-transfer resuspension cycles where source says fully resuspend but does not define stroke count or volume.
- Treat post-return 4C/-20C storage as storage metadata, not an active execution hold in Section 2.4.

Validation note: the intermediate supernatant tube capacity is widened to 1000 uL to avoid current runtime material-model overflow artifacts during repeated in-place magnetic separations. Source annotations still preserve the intended 0.2 mL tube context.
