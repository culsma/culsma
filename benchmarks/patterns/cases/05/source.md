# TB-05 PBMC Flow-Cytometry Immunophenotyping Workflow

## Sample and Control Assignment

1. Start with a PBMC suspension in flow-cytometry staining buffer.
2. Adjust the PBMC suspension to 1 x 10^7 cells/mL.
3. Assign eight 5 mL flow-cytometry tubes as follows:
   - one fully stained sample tube;
   - one unstained autofluorescence-control tube;
   - one isotype-control-panel tube;
   - five single-antibody compensation-control tubes, one for each antibody fluorophore in the panel.
4. Aliquot 100 uL PBMC suspension, corresponding to 1 x 10^6 cells, into each assigned tube.

## Initial Wash and Fc Receptor Blocking

5. Add 2 mL staining buffer to each tube.
6. Centrifuge all tubes at 300 x g for 5 min at 4°C.
7. Remove and discard each supernatant without disturbing the cell pellet.
8. Add 65 uL staining buffer to each cell pellet and pipette 10 times using 52 uL per stroke to fully resuspend the cells.
9. Add 5 uL human Fc receptor blocking reagent to each tube.
10. Pipette each 70 uL suspension 10 times using 56 uL per stroke, then incubate for 10 min on ice.

## Staining Reagent Assignment

11. Use anti-CD45, anti-CD3, anti-CD4, anti-CD8, and anti-CD19 stocks at an author-specified concentration of 5 mg/mL each. Prepare 30 uL full staining panel per fully stained sample, containing 5 uL (25 ug antibody) of each stock and 5 uL viability dye.
12. Use each of the five fluorophore-matched isotype-control antibody stocks at 5 mg/mL. Prepare 30 uL isotype-control panel containing 5 uL (25 ug antibody) of each isotype control corresponding to anti-CD45, anti-CD3, anti-CD4, anti-CD8, and anti-CD19, plus 5 uL viability dye.
13. For each of the five single-antibody compensation controls, prepare 30 uL staining reagent containing 5 uL (25 ug antibody) of the assigned 5 mg/mL antibody stock and 25 uL staining buffer.
14. Prepare 30 uL unstained-control reagent containing staining buffer only.

## Sample and Control Staining

15. Add the 30 uL full staining panel to the fully stained sample tube.
16. Add the 30 uL isotype-control panel to the isotype-control tube.
17. Add each 30 uL single-antibody reagent to its assigned compensation-control tube.
18. Add 30 uL staining buffer to the unstained autofluorescence-control tube.
19. Pipette each 100 uL staining suspension 10 times using 80 uL per stroke, then incubate for 30 min on ice protected from light.

## Post-Staining Wash

20. Add 2 mL staining buffer to each tube.
21. Centrifuge all tubes at 300 x g for 5 min at 4°C.
22. Remove and discard each supernatant without disturbing the cell pellet.
23. Add 2 mL fresh staining buffer to each tube.
24. Pipette each 2 mL cell suspension 10 times using 1.6 mL per stroke to fully resuspend the cells.
25. Centrifuge all tubes at 300 x g for 5 min at 4°C.
26. Remove and discard each supernatant without disturbing the cell pellet.

## Fixation and Acquisition Preparation

27. Add 300 uL fixation buffer diluted in PBS to each cell pellet.
28. Pipette each 300 uL suspension 10 times using 240 uL per stroke, then incubate for 10 min at room temperature protected from light.
29. Add 2 mL staining buffer to each tube.
30. Centrifuge all tubes at 300 x g for 5 min at 4°C.
31. Remove and discard each supernatant without disturbing the cell pellet.
32. Add 500 uL acquisition buffer to each fixed cell pellet and pipette 10 times using 400 uL per stroke to fully resuspend the cells.
33. Keep all tubes at 4°C protected from light until acquisition.

## Acquisition

34. Acquire the unstained control, five single-antibody compensation controls, isotype-control panel, and fully stained sample under the same acquisition configuration.
35. Record a separate event stream for every tube, including event identity, sample identity, control role, forward scatter, side scatter, raw fluorescence-channel signals, acquisition metadata, and run-level quality fields.
36. Return the eight event streams and their acquisition metadata for downstream compensation, gating, and population analysis.
