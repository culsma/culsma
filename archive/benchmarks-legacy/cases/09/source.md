# Cell culture and Western blot

Source: Andrea Dickey and rabrisch, *Cell culture and Western blot*, protocols.io,
version 1, 12 April 2023. [Original protocol](https://doi.org/10.17504/protocols.io.kxygx9bozg8j/v1)
([PDF](https://www.protocols.io/view/cell-culture-and-western-blot-csqcwdsw.pdf)).
Reproduced with formatting and wording normalization under the source's Creative
Commons Attribution license. Original section and step numbers are retained.
The S1–S7 labels are additional benchmark groupings, not original step numbers.
Program-specific operating choices are not inserted into the source instructions below.

## Cell culture and transfection

### 1. Day 1 — S1

Split 293T cells into 6-well dishes 24 h before transfection, at 200,000 cells per
well in 2 mL DMEM with FBS and penicillin-streptomycin (P/S).

### 2. Day 2: Transfection — S2

**2.1.** Warm PEI and Opti-MEM at room temperature for 15 min. Label a tube for each well.

**2.2.** Add 500 ng GFP-Rab7 DNA and 1 ug of the LRRK1 construct of interest to
150 uL Opti-MEM. Gently vortex for 5 s.

**2.3.** Add 3 uL room-temperature PEI to each tube containing the Opti-MEM/DNA
mixture. Mix gently by pipetting and incubate the mixture at room temperature
in the hood for 15 min.

**2.4.** During that incubation, remove the medium from the 6-well dish containing
the cells and replace it with 1 mL fresh DMEM with FBS and without P/S. Return
the dish to the 37 C incubator until ready to add the transfection mixture.

**2.5.** After the 15 min incubation, add 150 uL DNA/Opti-MEM/PEI mixture dropwise
to each well. Give the plate a light swirl before returning it to the incubator.

## Cell lysis

### 3. Begin cell lysis 36 h after transfection — S3–S4

**3.1. — S3.** Wash the plate on ice with cold PBS (1x).

**3.2. — S3.** Add 300 uL RIPA buffer (0.5% Triton, 50 mM Tris pH 7.5,
150 mM NaCl, 0.1% SDS) with protease and phosphatase inhibitors
(cOmplete mini EDTA-free and PhosSTOP tablets).

**3.3. — S3.** Lift with cell lifters on ice.

**3.4. — S3.** Pipette up the lysate, place it in an Eppendorf tube, and shake
for 15 min in the cold room.

**3.5. — S3.** Centrifuge at MAX at 4 C for 15 min.

**3.6. — S3: supernatant collection; S4: sample preparation.** Remove the
supernatant and prepare the sample, heating at 95 C for 10 min; store at -80 C.
The source author also describes storing the lysate and taking an aliquot to
prepare a sample, using 65 uL lysate, 10 uL 10x Reducing Agent, and 25 uL
4x NuPAGE LDS sample buffer.

## Western blot

### 4. SDS-PAGE with Bis-Tris gel and MOPS running buffer — S5–S7

**4.1. — S5.** Load 25 uL prepared lysate in sample buffer onto a 4–12% Bis-Tris
gel. Run at 180 V for approximately 50 min, or until the dye front reaches
the bottom of the gel.

**4.2. — S6.** Assemble the gel with an Immobilon-FL PVDF membrane for transfer
according to the instructions for the Western blot transfer apparatus. For
fluorescence detection, use a low-fluorescence-background membrane
(Immobilon-FL or equivalent). Activate the membrane with methanol and rinse
with water. Transfer in Tris/glycine Western transfer buffer containing 20%
methanol at 200 mA for 4 h at 4 C.

**4.3. — S6.** After transfer, rinse the membrane with water and allow it to dry
between sheets of Whatman paper.

**4.4. — S7.** Block in 5% milk in TBS without Tween 20.

**4.5. — S7.** Dilute primary antibodies in 5% milk in TBST with Tween 20:

- Rabbit anti-Rab7 phospho-S72 (MJF-38), 1:1,000.
- Mouse anti-GFP (Santa Cruz), 1:2,500, for total Rab quantification.
- Rabbit anti-LRRK1 (ab228666), 1:500.
- Rabbit anti-GAPDH (Cell Signaling Technology), 1:3,000.

**4.6. — S7.** Rock overnight at 4 C.

**4.7. — S7.** Rinse three times with TBST for 5 min each.

**4.8. — S7.** Rinse once with 5% milk in TBST.

**4.9. — S7.** Add Li-Cor anti-mouse and anti-rabbit IRDye secondary antibodies,
diluted 1:5,000 in 5% milk in TBST. Incubate at room temperature for 1 h.

**4.10. — S7.** Rinse three times with TBST for 5 min each.

**4.11. — S7.** Image on a Li-Cor Odyssey CLx.

## Benchmark mapping and execution choices (not original instructions)

| Benchmark group | Original steps |
| --- | --- |
| S1 | 1 |
| S2 | 2.1–2.5 |
| S3 | 3.1–3.5 and supernatant collection in 3.6 |
| S4 | Sample preparation in 3.6 |
| S5 | 4.1 |
| S6 | 4.2–4.3 |
| S7 | 4.4–4.11 |

These groups connect the source to the program and evaluation; they do not
replace the original numbering. The 36 h interval in step 3 is implemented
at the end of the program's S2, before lysis begins.

The program selects continuous processing without the storage branch in 3.6,
and schedules medium replacement sequentially rather than during mixture
incubation. Its additional working volumes, mixing settings, room-temperature
and cold-room set points, numeric centrifuge setting for MAX, and 16 h
interpretation of overnight are benchmark choices, not source-specified values.
Likewise, the source lists primary antibodies without specifying combined or
separate probing; the program's combined preparation is an explicit modeling
assumption. Source handling instructions remain above even where the program
currently represents them only in comments.
