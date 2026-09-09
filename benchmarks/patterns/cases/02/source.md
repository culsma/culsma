# RNA-to-qPCR Gene-Expression Workflow

## Workflow

### A. Column RNA Purification

1. Accept one treated adherent-cell well and one reference adherent-cell well, each containing 1 x 10^6 mammalian cells in 2 mL complete culture medium.

2. For each adherent-cell well, aspirate and discard the removable culture medium while preserving the cell layer on the well surface.

3. Wash each adherent-cell well twice with fresh phosphate-buffered saline. For each wash, add 1 mL phosphate-buffered saline to the well, then aspirate and discard the removable wash liquid while preserving the adherent cell layer.

4. Add 600 uL RNA lysis buffer directly to each washed adherent-cell well.

5. Incubate each lysed well at 25 C for 5 min.

6. Transfer 600 uL lysate from each well to a 2 mL lysate tube with low carryover. Represent the theoretical total-RNA content as 20 ug per lysate, based on 1 x 10^6 cells and an average of 20 pg total RNA per mammalian cell.

7. Add 600 uL RNA binding buffer to each lysate tube.

8. Mix each lysate-binding mixture by pipette mixing 5 times using 960 uL per mix.

9. Transfer 1200 uL lysate-binding mixture to a silica column.

10. Centrifuge each silica column at 8000 x g for 1 min. Discard the filtrate and retain the column-bound material.

11. Add 500 uL RNA wash buffer to each retained column state.

12. Centrifuge each silica column at 8000 x g for 1 min. Discard the filtrate and retain the column-bound material.

13. Prepare a DNase working mix in a fresh tube by combining 40 uL DNase reagent with 160 uL DNase reaction buffer.

14. Mix the DNase working mix by pipette mixing 5 times using 160 uL per mix.

15. Add 80 uL DNase working mix to each retained column state.

16. Incubate each column at 25 C for 15 min.

17. Wash each column twice after DNase treatment. For each wash, add 600 uL RNA wash buffer to the column, centrifuge at 8000 x g for 2 min, discard the filtrate, and retain the column-bound material.

18. Add 40 uL nuclease-free water to each retained column state.

19. Centrifuge each silica column at 8000 x g for 1 min to elute RNA.

20. Collect the filtrate as purified RNA. Discard the retained column material.

21. Record RNA quantity and purity readouts for each purified RNA sample, including sample identity, RNA concentration, A260/A280, and A260/A230.

### B. Reverse Transcription

22. For each purified RNA sample, prepare a reverse-transcription reaction by combining 8 uL purified RNA, 12 uL nuclease-free water, and 10 uL reverse-transcription mix in a cDNA reaction tube.

23. Incubate each reverse-transcription reaction at 25 C for 10 min.

24. Incubate each reverse-transcription reaction at 42 C for 45 min.

25. Incubate each reverse-transcription reaction at 85 C for 5 min.

26. Hold each reverse-transcription reaction at 4 C for 5 min.

27. Return the reverse-transcription reactions as treated cDNA and reference cDNA.

### C. qPCR Plate Setup and Run

28. Declare one 96-well qPCR plate for the treated cDNA, reference cDNA, and shared no-template controls.

29. Assign wells A1:A3 to treated cDNA with target-primer mix.

30. Assign wells B1:B3 to treated cDNA with housekeeping-primer mix.

31. Assign wells C1:C3 to reference cDNA with target-primer mix.

32. Assign wells D1:D3 to reference cDNA with housekeeping-primer mix.

33. Assign wells E1:E2 to no-template control with target-primer mix.

34. Assign wells F1:F2 to no-template control with housekeeping-primer mix.

35. Load each treated target well with 2 uL treated cDNA, 1 uL target-primer mix, 10 uL qPCR master mix, and 7 uL nuclease-free water.

36. Load each treated housekeeping well with 2 uL treated cDNA, 1 uL housekeeping-primer mix, 10 uL qPCR master mix, and 7 uL nuclease-free water.

37. Load each reference target well with 2 uL reference cDNA, 1 uL target-primer mix, 10 uL qPCR master mix, and 7 uL nuclease-free water.

38. Load each reference housekeeping well with 2 uL reference cDNA, 1 uL housekeeping-primer mix, 10 uL qPCR master mix, and 7 uL nuclease-free water.

39. Load each target-primer no-template-control well with 1 uL target-primer mix, 10 uL qPCR master mix, and 9 uL nuclease-free water.

40. Load each housekeeping-primer no-template-control well with 1 uL housekeeping-primer mix, 10 uL qPCR master mix, and 9 uL nuclease-free water.

41. Activate the qPCR reactions at 95 C for 2 min.

42. Run 40 qPCR cycles. Each cycle consists of 95 C for 15 s, then 60 C for 30 s, with fluorescence collected from all qPCR wells during each cycle.

43. Run a melt-curve ramp from 65 C to 95 C over 5 min.

44. Record a structured qPCR readout for all assay wells, including well identity, sample identity, gene identity, replicate identity, Ct value, melt-peak temperature, no-template-control detection status, replicate CV, and QC pass status.
