# Controlled PCR variants

This supplement supports the Results subsection “Controlled Protocol Variants”
and reviewer comments R2-06–07. It is a software execution benchmark, with no
hardware connection or claim about physical PCR performance.

## Cases and expected outcomes

- `original.culs` is the PCR listing extracted from the working manuscript.
- `normal.culs` replaces the whole-container transfer with explicit quantities
  for all five inputs. Stocks, reaction composition and thermal conditions stay
  the same. All transfer inputs must use the same quantity style in this runtime.
- `overdraw.culs` differs from `normal.culs` only in requesting 2 uL of template
  instead of 1 uL. The source still contains 1 uL.
- `expected.json` specifies the 50 uL composition, the full 92-operation thermal
  sequence and the expected material error before thermal treatment. The
  reproduction script compares actual results with these expectations.

The original and quantitative baseline both completed with the same reaction
composition and ordered thermal conditions. The alternative passed validation,
type checking and planning, then failed during runtime material accounting with
`MAT_INSUFFICIENT_VOLUME` at line 14, column 3. The reaction vessel remained
empty, the template retained 1 uL, and all 92 thermal operations were skipped.
No thermal operation was started.

## Reproduction

The runtime is pinned to Culsma commit
`5364676bc2437b4981a00ce0133c730af243e469` (1.0.7), matching the manuscript's
worked-example evaluation. The recorded run used Python 3.12.8 and Lark 1.3.1.
Use a Python environment containing that Lark version and a local Culsma Git
repository containing the pinned commit:

```bash
python benchmarks/pcr_alternative/reproduce.py --culsma-repo /absolute/path/to/Culsma
```

Run from the Culsma repository. The script reads the pinned source through
`git archive`, without changing the Culsma checkout. The extracted runtime,
complete execution plans and raw run records are placed under
`output/pcr-alternative/` in this repository. No temporary clone or
development workspace is created. The script uses the deterministic reference
driver and performs no instrument operations.

`results/summary.json` records versions, source hashes, checks, material results,
step status counts and complete runtime diagnostics. The three thermal trace
files retain completed operation order, source lines, conditions and event
identifiers. Each condition is read from an actual completed execution event;
an empty alternative trace is checked against the absence of even a started
thermal operation. Raw records can be regenerated using the command above.

The manuscript table condenses the quantitative baseline trace into positions
1 (initial hold), 2–91 (30 three-stage cycles), and 92 (one final extension).
Material results and thermal conditions are software records, not measured
amplification, temperature attainment, precision, or carryover.
