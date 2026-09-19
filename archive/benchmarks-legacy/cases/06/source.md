# CRISPR Knockout Validation Workflow

## 1. CRISPR-Cas9 RNP Editing

1. Seed HEK293T-GENE-X-positive cells into a 24-well plate as three editing groups: WT control in well A1, non-targeting control in well A2, and deletion-editing sample in well A3.
2. Use 1.0 x 10^5 cells in 1 mL culture volume per well.
3. Incubate the 24-well plate for 18 h at 37 C with 5% CO2, until cells reach approximately 60-70% confluency.
4. Image or inspect the editing wells and record confluence and QC status before RNP delivery.
5. Prepare one 10 uL deletion RNP reaction by combining 2 uL Cas9 protein, 2 uL sgRNA-1, 2 uL sgRNA-2, and 4 uL RNP assembly buffer / Opti-MEM.
6. Use 6 pmol Cas9 protein, approximately 1.0 ug, 3 pmol sgRNA-1, and 3 pmol sgRNA-2 per deletion RNP reaction.
7. Prepare one 10 uL non-targeting RNP reaction by combining 2 uL Cas9 protein, 4 uL non-targeting sgRNA, and 4 uL RNP assembly buffer / Opti-MEM.
8. Use 6 pmol Cas9 protein, approximately 1.0 ug, and 6 pmol non-targeting sgRNA per non-targeting RNP reaction.
9. Incubate the deletion RNP and non-targeting RNP reactions for 10 min at room temperature.
10. Prepare one 60 uL deletion delivery mixture by combining 10 uL deletion RNP with 50 uL preconfigured lipid delivery mix.
11. Prepare one 60 uL non-targeting delivery mixture by combining 10 uL non-targeting RNP with 50 uL preconfigured lipid delivery mix.
12. Incubate both delivery mixtures for 15 min at room temperature.
13. Add the full 60 uL non-targeting delivery mixture dropwise to the non-targeting control well.
14. Add the full 60 uL deletion delivery mixture dropwise to the deletion-editing well.
15. Incubate WT, non-targeting, and deletion-editing wells for 72 h at 37 C with 5% CO2.
16. At 72 h, collect the edited bulk population from the deletion-editing well.
17. Count viable cells in the edited bulk population.
18. For this benchmark case, use a counted edited bulk pool of 1.0 mL at 2.0 x 10^5 viable cells/mL and 100% viability, giving 2.0 x 10^5 total viable cells.

## 2. Isolation of Candidate Clones by Limiting Dilution

1. Use the counted edited bulk pool as input material.
2. Prepare a 1:40,000 limiting-dilution suspension by combining 1 uL counted edited bulk pool with 39.999 mL limiting-dilution culture medium.
3. Use the resulting 40 mL suspension at an expected density of 5 cells/mL.
4. Seed 100 uL limiting-dilution suspension into each well of a 96-well plate.
5. Use the expected average seeding density of 0.5 cell per well, calculated as 5 cells/mL x 0.1 mL/well.
6. Incubate the 96-well plate for 14 days at 37 C with 5% CO2 for this benchmark run.
7. Image or inspect the 96-well plate to identify wells with single-colony outgrowth.
8. Manually select single-colony wells for expansion.
9. For this benchmark case, select well A3 as Clone A, well A4 as Clone B, and well A5 as Clone C, then label the expanded outputs Clone A, Clone B, and Clone C.

## 3. Prepare Genomic DNA Inputs from Candidate Clones

1. Prepare genomic DNA from WT control cells, non-targeting control cells, Clone A, Clone B, and Clone C using the same cultured-cell silica spin-column workflow for each sample.
2. Collect each cell sample by centrifuging at 300 x g for 5 min and retain the cell pellet.
3. Add 200 uL PBS and 20 uL Proteinase K to each retained cell pellet.
4. Add 200 uL genomic-DNA lysis buffer AL to each sample.
5. Incubate each sample for 10 min at 56 C.
6. Add 200 uL 96-100% ethanol to each lysed sample.
7. Load each sample onto a silica spin column.
8. Centrifuge each silica spin column at 6000 x g for 1 min to bind genomic DNA to the membrane; discard the flowthrough and retain the column.
9. Add 500 uL wash buffer AW1 to each retained column.
10. Centrifuge each column at 6000 x g for 1 min; discard the flowthrough and retain the column.
11. Add 500 uL wash buffer AW2 to each retained column.
12. Centrifuge each column at 20000 x g for 3 min; discard the flowthrough and retain the column.
13. Add 50 uL elution buffer AE to each retained column and incubate for 1 min at room temperature.
14. Centrifuge each column at 6000 x g for 1 min to collect 50 uL genomic DNA.
15. Label the outputs WT gDNA, non-targeting gDNA, Clone A gDNA, Clone B gDNA, and Clone C gDNA.
16. Use 1 uL of each gDNA output as template for PCR screening.

## 4. PCR Screening of the Target Locus

Use primers outside the two CRISPR cut sites.

```text
Forward primer --- sgRNA-1 cut site --- 120 bp target fragment --- sgRNA-2 cut site --- Reverse primer
```

Expected PCR products:

| Allele | Expected band |
|---|---:|
| Wild-type allele | 620 bp |
| Deletion allele | 500 bp |

PCR reaction, 25 uL per sample:

| Component | Volume |
|---|---:|
| 2x PCR master mix | 12.5 uL |
| Forward primer, 10 uM | 0.5 uL |
| Reverse primer, 10 uM | 0.5 uL |
| Genomic DNA | 1 uL |
| Nuclease-free water | 10.5 uL |
| Total | 25 uL |

PCR cycling conditions:

| Step | Temperature | Time | Cycles |
|---|---:|---:|---:|
| Initial denaturation | 95 C | 3 min | 1 |
| Denaturation | 95 C | 15 sec | 35 |
| Annealing | 60 C | 20 sec | 35 |
| Extension | 72 C | 30 sec | 35 |
| Final extension | 72 C | 5 min | 1 |
| Hold | 4 C | 10 min benchmark hold | 1 |

Agarose gel setup:

| Parameter | Value |
|---|---:|
| Agarose concentration | 2% |
| Agarose powder | 2 g |
| 1x TBE running buffer for gel | 100 mL |
| Melt agarose | 95 C for 5 min |
| Cool molten agarose | 60 C for 10 min |
| Fluorescent DNA stain added to molten agarose | 5 uL |
| Gel solidification | 30 min at room temperature |
| PCR product loaded | 5 uL |
| DNA loading dye loaded | 1 uL |
| DNA ladder | 5 uL 100 bp ladder plus 1 uL DNA loading dye in lane A6 |
| Run condition | 120 V for 35 min |

## 5. Record Initial PCR Readout

Record expected control results:

| Sample | Expected PCR band |
|---|---:|
| WT control | 620 bp |
| Non-targeting control | 620 bp |

Record candidate clone PCR results:

| Candidate clone | PCR band result | Initial interpretation |
|---|---|---|
| Clone A | 500 bp only | possible homozygous deletion clone |
| Clone B | 620 bp + 500 bp | possible heterozygous or mixed clone |
| Clone C | 620 bp only | likely unedited clone |

## 6. Genotype Readout and Clone Classification

Use the PCR result to determine which samples proceed to genotype confirmation.

```text
if clone shows 500 bp only:
    send PCR product for genotype confirmation
    keep clone as strong candidate

if clone shows 620 bp + 500 bp:
    send both bands or PCR product for genotype confirmation
    keep clone as conditional candidate

if clone shows 620 bp only:
    classify as not edited
    do not continue to protein validation
```

Record genotype readout results:

| Clone | PCR result | Genotype readout | Classification | Next action |
|---|---|---|---|---|
| Clone A | 500 bp only | deletion/deletion | biallelic deletion candidate | proceed to protein validation |
| Clone B | 620 bp + 500 bp | WT/deletion | heterozygous deletion candidate | archive; do not use as knockout clone |
| Clone C | 620 bp only | WT/WT | unedited clone | discard from validation workflow |

Proceed with Clone A as the genotype-qualified knockout candidate.

## 7. Protein-Level Validation of Genotype-Qualified Clone

1. Use WT control cells, non-targeting control cells, and genotype-qualified Clone A as protein-validation inputs.
2. Prepare one flow-cytometry acquisition sample from each input using 500 uL cell suspension per sample.
3. Stain or acquire each sample with a panel containing GENE-X and a live/dead marker.
4. Acquire single-cell flow-cytometry events for WT control, non-targeting control, and Clone A.
5. Record GENE-X surface staining status for each sample.

For this benchmark case, use the following protein-level readout:

| Sample | GENE-X surface staining result | Interpretation |
|---|---|---|
| WT control | positive | normal GENE-X expression |
| Non-targeting control | positive | delivery did not remove GENE-X |
| Clone A | negative | loss of GENE-X protein expression |

```text
if genotype-qualified clone is protein-negative:
    proceed to functional validation

if genotype-qualified clone remains protein-positive:
    classify as genotype-edited but not protein-null
    do not call it a validated knockout clone
```

Proceed with Clone A to functional validation.

## 8. Functional Validation of Protein-Negative Clone

1. Use WT control cells, non-targeting control cells, and protein-negative Clone A as functional-validation inputs.
2. Prepare one stimulation sample from each input using 500 uL cell suspension per sample.
3. Stimulate each sample with Ligand-X at a target final concentration of 100 ng/mL.
4. Incubate stimulated samples for 30 min at 37 C with 5% CO2.
5. Measure pSignal-X readout for each stimulated sample.

For this benchmark case, use the following functional readout:

| Sample | pSignal-X after Ligand-X stimulation | Interpretation |
|---|---|---|
| WT control | induced | pathway functional in WT cells |
| Non-targeting control | induced | delivery control retains response |
| Clone A | not induced | GENE-X-dependent response is lost |

```text
if protein-negative clone also loses expected function:
    classify as validated knockout clone

if protein-negative clone retains function:
    classify as protein-negative but functionally inconclusive
```

## 9. Record Final Clone Status

Record final material classification:

| Clone | Genotype status | Protein status | Functional status | Final decision |
|---|---|---|---|---|
| Clone A | deletion/deletion | GENE-X negative | Ligand-X response lost | validated knockout clone |
| Clone B | WT/deletion | not tested | not tested | edited heterozygous clone; archive |
| Clone C | WT/WT | not tested | not tested | unedited clone; discard |

Record final validated material:

```text
GENE-X knockout Clone A
```

## 10. Minimal Validation Criteria

A candidate clone is considered a validated knockout clone only if all required evidence is concordant:

1. The clone carries a disruptive biallelic genomic edit.
2. The clone lacks detectable GENE-X protein expression.
3. The clone loses the expected GENE-X-dependent functional response.
4. Control samples behave as expected.
