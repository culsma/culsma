# Four worked manuscript examples

This directory provides the exact programs displayed in Sections 3.1–3.4,
independent checks, and recorded results. These illustrations are separate from
the seven modules and composite used for Section 3.5 coverage.

| Section | Program | Focus |
| --- | --- | --- |
| 3.1 | `programs/pcr.culs` | PCR composition and applied conditions |
| 3.2 | `programs/flow.culs` | Staining, washing, and flow-cytometry observation |
| 3.3 | `programs/magnetic.culs` | Magnetic separation and component relationships |
| 3.4 | `programs/fractions.culs` | Ordered fractions and parameterized plate analysis |

## Reproduce

Use Python 3.12 and Lark 1.3.1. Follow the parent README to obtain a runtime
checkout at `5364676bc2437b4981a00ce0133c730af243e469`, then install its CLI:

```sh
python3.12 -m venv /path/to/culsma-runtime/.venv
/path/to/culsma-runtime/.venv/bin/python -m pip install -e /path/to/culsma-runtime 'lark==1.3.1'
```

From this directory, use a fresh output directory:

```sh
/path/to/culsma-runtime/.venv/bin/python scripts/check_manuscript_examples.py \
  --culsma-repo /path/to/culsma-runtime \
  --culsma-cli /path/to/culsma-runtime/.venv/bin/culsma \
  --program-dir programs \
  --output /tmp/culsma-worked-example-results \
  --tex-output-dir /tmp/culsma-worked-example-results/listings
```

The material-state checks and compact CLI exports use the same implementation,
`5364676bc2437b4981a00ce0133c730af243e469` (package version 1.0.7).
The four-example checks remain separate from the modular benchmark runner.
A full clone retains the pinned implementation required by the checker.

`results/summary.json` records implementation, dependency and source identities,
completed-step counts, and the checked outcomes. Per-example files retain
material states, observations, events, reports, and compact outputs. Unset
observation fields remain unset: these software runs do not supply laboratory
measurements. The script also emits TeX listings without compiling a PDF.

## Maintain

The manuscript TeX is the source for the displayed programs. After changing a
listing, export its exact contents to `programs/`, synchronize the checker with
`scripts/check_manuscript_examples.py` in the manuscript workspace, rerun the
command, and update the recorded results. Keep these results outside the
modular coverage denominator.
