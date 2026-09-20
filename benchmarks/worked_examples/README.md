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
checkout at `42b562bce488d25bdc00af82c62fdb5d4cc52b8b`, then install its CLI:

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

The material-state and relationship checks use the archived implementation
`ab06a04446b51d208b6a8b6eb2b36853e67d0d7b`, an ancestor retained in the runtime
repository. The compact outputs use the installed CLI at `42b562b`. These are
two explicitly identified execution paths; the four-example checks are not the
modular benchmark runner. A full clone retains the required implementation
history; if using a shallow clone, fetch that history before running.

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
