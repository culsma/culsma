# Composite 02: Magnetic-Bead Immunoprecipitation with Western Blot Readout

## Steps

1. Run Module 05 with 500 uL clarified protein lysate containing 1 mg total protein to obtain a 25 uL input fraction and a 30 uL denaturing IP eluate. Preserve both fraction identities. The target-protein mass in the IP eluate is not assumed or inferred.
2. Prepare a 25 uL input-lane sample containing 15 uL input fraction, 6.25 uL premixed 4x LDS sample buffer with reducing agent, and 3.75 uL deionized water. Mix by pipetting 10 times using 20 uL per stroke, heat at 98 C for 15 min, and spin at 3,000 x g for 5 s at 25 C.
3. Use 25 uL of the denaturing IP eluate produced by Module 05 as the IP-elution lane sample. Spin the IP-elution lane sample at 3,000 x g for 5 s at 25 C before loading; do not assign a protein mass to this lane.
4. Run the electrophoresis, membrane-transfer, membrane-treatment, and imaging portion of Module 06 as a two-sample configuration. Load the complete 25 uL input-lane sample and 25 uL IP-elution lane sample into separate lanes of the same 4-12% Bis-Tris SDS-PAGE gel, and load 10 uL prestained molecular-weight protein ladder into an adjacent lane.
5. Separate the gel at 180 V for 30 min and transfer proteins to a PVDF membrane at 100 V for 90 min at 4 C using transfer buffer containing 20% methanol.
6. Block and wash the membrane according to Module 06. Probe it with rabbit anti-GFP primary antibody diluted 1:1,000 in 10 mL primary-antibody dilution buffer, followed by goat anti-rabbit IgG Alexa Fluor 680 secondary antibody diluted 1:10,000 in 10 mL blocking buffer.
7. Acquire one Western blot image in the 680 nm fluorescence channel while preserving the lane identities `input_fraction`, `ip_eluate`, and `protein_ladder`.
