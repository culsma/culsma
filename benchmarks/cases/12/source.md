# 2.3. cDNA Amplification

Source: Parse Biosciences, *Evercode WT Mega v3 User Manual*, version 1.5,
November 2024, document UMWT3500, Section 2.3, printed pages 43-45.
[Original manual](https://support.parsebiosciences.com/hc/en-us/article_attachments/31841833600532).

Original section and procedure numbers are retained below. Parenthesized S labels
are benchmark subdivisions; multiple S labels can refer to one original step.
Tables and instructions are formatted for reading, with program choices separated
at the end. Preparation steps outside the numbered S sequence remain included.

The captured cDNA is washed and amplified with Template Switch Primer and Illumina Truseq Read 2-specific primers.

#### Original step 1: Reagents

| Item | Source | Quantity | Handling and storage |
| --- | --- | --- | --- |
| cDNA Amp Mix | -20C Reagents | 1 | Thaw at room temperature, then place on ice. Mix by inverting 3x. Briefly centrifuge before use. |
| cDNA Amp Primers | -20C Reagents | 1 | Thaw at room temperature, then place on ice. Mix by inverting 3x. Briefly centrifuge before use. |

#### Original step 2: cDNA Amplification Master Mix

Prepare the cDNA Amplification Master Mix in a new 2 mL tube. Mix by pipetting 10x and store on ice.

| Number of sublibraries | cDNA Amp Mix | cDNA Amp Primers | Total |
| --- | --- | --- | --- |
| 1 | 60.5 uL | 60.5 uL | 121 uL |
| 16 | 968 uL | 968 uL | 1936 uL |

## Procedure (original numbering)

**3. (S1, S2)** Place each tube of template-switched cDNA from Section 2.2 on the high position of the Parse Biosciences magnetic rack.

Incubate until the solution clears, about 2 minutes. If beads have settled, pipette mix to resuspend them so they separate appropriately.

**4. (S3)** While still on the magnetic rack, remove and discard the supernatant.

**5. (S4)** While still on the magnetic rack, add 125 uL of Wash Buffer 3 to each tube.

**6. (S5)** Incubate for 1 minute at room temperature.

**7. (S6)** While still on the magnetic rack, remove and discard Wash Buffer 3.

**8. (S7, S8, S9)** Remove the tube(s) from the magnetic rack.

Fully resuspend each bead pellet with 100 uL of the Amplification Master Mix.

Store on ice.

**9. (S10)** Determine the number of PCR cycles required for cDNA amplification based on input cell or nuclei count and sample type. These recommendations apply to many cell types, but cycle numbers may need optimization for each sample type.

| Cells/nuclei in sublibrary | High RNA content, such as cell lines | Low RNA content, such as PBMCs | Nuclei |
| --- | --- | --- | --- |
| 200-1,000 | 11 | 13 | 12 |
| 1,000-2,000 | 9 | 11 | 10 |
| 2,000-6,000 | 7 | 9 | 8 |
| 6,000-12,500 | 6 | 8 | 7 |
| 12,500-25,000 | 4 | 6 | 5 |
| 25,000-62,500 | 3 | 5 | 4 |

**10. (S11)** Place the tube(s) into a thermocycler and run the cDNA Amplification program.

| Run time | Lid temperature | Sample volume |
| --- | --- | --- |
| 50-70 min | 105C | 100 uL |

| Step | Time | Temperature | Cycles |
| --- | --- | --- | --- |
| 1 | 3 min | 95C | 1 |
| 2 | 20 sec | 98C | Repeat steps 2-4 together, 5 cycles |
| 3 | 45 sec | 65C | Same cycle block |
| 4 | 3 min | 72C | Same cycle block |
| 5 | 20 sec | 98C | Repeat steps 5-7 together; variable count from table |
| 6 | 20 sec | 67C | Same cycle block |
| 7 | 3 min | 72C | Same cycle block |
| 8 | 5 min | 72C | 1 |
| 9 | Hold | 4C | 1 |

If processing sublibraries with different numbers of cells or nuclei, amplify them in separate thermocyclers according to the cycle recommendations above. Annealing steps 3 and 6 have different time and temperature settings.

**Safe stopping point (after original step 10):** Amplified cDNA can be stored at 4C for up to 18 hours.

## Benchmark mapping and execution choices (not original instructions)

The standalone program supplies the Section 2.2 output as its input and selects
a cycle count for a particular run. The full recommendation table remains above.
Explicit set points, unspecified mixing settings, partition ratios, and finite
representations of Hold are program choices. The cycle column expands the PDF's
merged cells: repeat each three-step block as a unit, not each row separately.
