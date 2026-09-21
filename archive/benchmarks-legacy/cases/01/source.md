# TB01 Protocol: PCR Amplification, Restriction Cloning into pUC19, Transformation into E. coli DH5alpha, and Screening of Recombinant Colonies

## 1. PCR Amplification of Insert

Use a forward primer with the structure:

```text
5'-GCGCGAATTC + insert-specific sequence-3'
```

Use a reverse primer with the structure:

```text
5'-GCGCAAGCTT + insert-specific reverse-complement sequence-3'
```

Thaw template DNA, forward primer, reverse primer, 2x high-fidelity PCR master mix, and nuclease-free water on ice.

### PCR Reaction, 50 uL

| Component | Volume |
|---|---:|
| Template DNA | 1 uL |
| Forward primer, 10 uM | 2.5 uL |
| Reverse primer, 10 uM | 2.5 uL |
| 2x high-fidelity PCR master mix | 25 uL |
| Nuclease-free water | 19 uL |
| Total | 50 uL |

### PCR Cycling Conditions

| Step | Temperature | Time | Cycles |
|---|---:|---:|---:|
| Initial denaturation | 98°C | 30 sec | 1 |
| Denaturation | 98°C | 10 sec | 30 |
| Annealing | 55-65°C | 20 sec | 30 |
| Extension | 72°C | 30 sec | 30 |
| Final extension | 72°C | 5 min | 1 |
| Hold | 4°C | Hold | - |

### PCR Product Check

1. Prepare a 1% agarose gel using agarose, 1x TBE buffer, and DNA stain.
2. Insert a comb during gel casting to form sample wells.
3. Mix 5 uL PCR product with DNA loading dye.
4. Load the PCR product sample onto the agarose gel.
5. Load a DNA ladder covering the 800 bp size range in a separate lane.
6. Run the gel at 120 V for 45 min.
7. Visualize the gel using UV or blue-light illumination.
8. Confirm the presence of a single band at approximately 800 bp.
9. If the band is specific, purify the remaining PCR product.
10. If nonspecific bands are present, excise the correct 800 bp band and purify by gel extraction.

Assumed purified insert concentration:

```text
Insert concentration = 25 ng/uL
```

## 2. Digestion of pUC19 Vector

Assemble the reaction on ice.

### Reaction Setup, 50 uL

| Component | Volume |
|---|---:|
| pUC19 DNA, 500 ng/uL | 2 uL |
| 10x restriction enzyme buffer | 5 uL |
| EcoRI | 1 uL |
| HindIII | 1 uL |
| Nuclease-free water | 41 uL |
| Total | 50 uL |

### Procedure

1. Mix gently by pipetting.
2. Incubate at 37°C for 1 hour.
3. Run the digest on a 1% agarose gel with a DNA ladder covering the 2686 bp size range.
4. Excise and purify the linearized pUC19 band.
5. Measure DNA concentration.

Expected vector band:

```text
2686 bp linearized pUC19
```

Assumed purified digested vector concentration:

```text
Digested pUC19 vector concentration = 20 ng/uL
```

## 3. Digestion of Insert

Assemble the reaction on ice.

### Reaction Setup, 50 uL

| Component | Volume |
|---|---:|
| Purified PCR insert, 25 ng/uL | 20 uL |
| 10x restriction enzyme buffer | 5 uL |
| EcoRI | 1 uL |
| HindIII | 1 uL |
| Nuclease-free water | 23 uL |
| Total | 50 uL |

### Procedure

1. Mix gently by pipetting.
2. Incubate at 37°C for 1 hour.
3. Purify the digested insert by column purification or gel extraction.
4. Measure DNA concentration.

Assumed purified digested insert concentration:

```text
Digested insert concentration = 15 ng/uL
```

## 4. Ligation of Insert into pUC19

Use a 3:1 insert-to-vector molar ratio.

Use approximately 45 ng insert with 50 ng vector.

Required volumes:

```text
Vector volume = 2.5 uL
Insert volume = 3 uL
```

Thaw digested pUC19 vector, digested insert, 10x T4 DNA ligase buffer, T4 DNA ligase, and nuclease-free water on ice.

### Ligation Reaction, 10 uL

| Component | Volume |
|---|---:|
| Digested pUC19 vector, 20 ng/uL | 2.5 uL |
| Digested insert, 15 ng/uL | 3 uL |
| 10x T4 DNA ligase buffer | 1 uL |
| T4 DNA ligase | 0.5 uL |
| Nuclease-free water | 3 uL |
| Total | 10 uL |

### Procedure

1. Assemble ligation reaction on ice.
2. Mix gently by pipetting.
3. Incubate at 16°C overnight.
4. Use ligation reaction directly for transformation.

## 5. Ligation and Transformation Controls

Prepare the following controls:

| Control | Composition | Expected Result |
|---|---|---|
| Recombinant ligation | Digested vector + digested insert + ligase | White and blue colonies |
| Vector-only control | Digested vector + ligase, no insert | Few colonies, mostly blue |
| No-ligase vector control | Digested vector only, no ligase | Very few or no colonies |
| Positive transformation control | Uncut pUC19 plasmid | Many blue colonies |
| No-DNA control | Competent cells only | No colonies |

## 6. Transformation into Chemically Competent DH5alpha

### Transformation Setup

| Component | Amount |
|---|---:|
| Chemically competent DH5alpha cells | 50 uL |
| Ligation reaction or control DNA | 2 uL |

### Procedure

1. Thaw chemically competent DH5alpha cells on ice.
2. Add 2 uL ligation reaction or control DNA to 50 uL competent cells.
3. Flick the tube gently to mix. Do not vortex.
4. Incubate on ice for 30 min.
5. Heat shock at 42°C for 45 sec.
6. Immediately place the tube back on ice for 2 min.
7. Add 450 uL SOC medium.
8. Recover at 37°C for 1 hour with shaking.
9. Plate 100 uL on LB agar containing ampicillin, X-gal, and IPTG.
10. Incubate overnight at 37°C.

## 7. Colony Inspection and Blue-White Screening

1. Inspect plates after overnight incubation.
2. Record colony counts.
3. Record colony color.
4. Pick 8-12 white colonies from the recombinant ligation plate for further screening.

Expected colony results:

| Plate | Expected Result |
|---|---|
| Recombinant ligation plate | Dozens to hundreds of colonies; white colonies are candidate recombinant clones |
| Vector-only control plate | Few colonies, usually blue |
| Positive control plate | Many blue colonies |
| No-DNA control plate | No colonies |

## 8. Colony PCR Screening

Use primers flanking the pUC19 multiple cloning site, such as M13 Forward primer and M13 Reverse primer.

Expected PCR product:

```text
Correct recombinant clone: approximately 900 bp
Empty pUC19 vector: small product from the empty MCS region
```

### Colony PCR Reaction, 20 uL

| Component | Volume |
|---|---:|
| 2x PCR master mix | 10 uL |
| M13 Forward primer, 10 uM | 0.5 uL |
| M13 Reverse primer, 10 uM | 0.5 uL |
| Sterile water | 9 uL |
| Colony template | Touch with sterile tip |
| Total | 20 uL |

### Procedure

1. Pick a single white colony using a sterile pipette tip or toothpick.
2. Touch the colony into the PCR reaction mix.
3. Streak the same colony onto a fresh LB-ampicillin plate or inoculate into LB-ampicillin broth for backup culture.
4. Run PCR using cycling conditions suitable for an approximately 900 bp product.
5. Analyze PCR products on a 1% agarose gel with a DNA ladder covering the 900 bp size range.

Expected colony PCR result:

| Clone Type | Expected Band |
|---|---:|
| Correct recombinant clone | Approximately 900 bp |
| Empty vector | Small MCS-sized band |
| Failed PCR | No band |
| Incorrect clone | Unexpected size band |

Select 3-4 colony PCR-positive clones for overnight culture and plasmid miniprep.

## 9. Miniprep and Diagnostic Restriction Digest

### Overnight Culture

1. Pick colony PCR-positive clones.
2. Inoculate each clone into 3-5 mL LB broth containing ampicillin.
3. Grow overnight at 37°C with shaking.
4. Isolate plasmid DNA using a miniprep kit.

### Diagnostic Digest

1. Digest purified plasmid DNA with EcoRI and HindIII.
2. Run the diagnostic digest on a 1% agarose gel with a DNA ladder covering both the 800 bp insert and 2686 bp vector backbone size ranges.

Expected bands for a correct recombinant clone:

| Fragment | Size |
|---|---:|
| pUC19 vector backbone | 2686 bp |
| Insert | 800 bp |

## 10. Sanger Sequencing Confirmation

1. Submit miniprep plasmid DNA for Sanger sequencing using primers flanking the insert.
2. Use M13 Forward primer and M13 Reverse primer.
3. Confirm that the insert is present.
4. Confirm that the insert is in the correct orientation.
5. Confirm that EcoRI and HindIII junctions are correct.
6. Confirm that no PCR-introduced mutations are present.
7. Confirm that no deletion or rearrangement is present.

## 11. Final Clone Confirmation

The clone is considered confirmed if it passes all of the following checks:

1. Growth on ampicillin-containing plate.
2. White colony phenotype on X-gal/IPTG plate.
3. Colony PCR band at approximately 900 bp.
4. EcoRI/HindIII diagnostic digest showing 2686 bp and 800 bp bands.
5. Sanger sequencing confirming the correct insert sequence.

Record the final confirmed product:

```text
pUC19-insert800 recombinant plasmid in E. coli DH5alpha
```
