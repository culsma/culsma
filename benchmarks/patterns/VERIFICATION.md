# Local verification — 9 September 2026

Status: **passed**. This is a locally verified submission candidate, not a
published release or DOI archive.

## End-to-end check

1. Copied the frozen program, source and detailed annotation files into this package.
2. Verified the public Culsma 1.0.6 wheel against implementation commit
   `0a5393c33151663566fe3d81d4fe01f29f98e274`: all 145 packaged source/data files match.
3. Installed the bundled wheels into a fresh Python 3.12.8 virtual environment.
4. Ran all 15 programs and derived the tables from their outputs and annotations.
5. Checked the derived values against the manuscript, then froze the raw baseline.
6. Created a ZIP, extracted it outside every project repository, created another
   empty virtual environment and installed using `--no-index --require-hashes`.
7. Ran all 15 programs again from the extracted package. Every process exited 0;
   all active steps completed and every runtime diagnostic count was 0.
8. Recomputed all table entries and compared full sample/reagent-consumption,
   terminal-material, touched-container and formal-return records against the
   baseline. **No differences were reported.**

The test did not import the author's editable Culsma installation or require
access to the protocol/docs repositories. It used the default StubDriver and no
external inventory reconciliation. This is computational reproduction of the
specified programs, not physical laboratory validation.

## Confirmed totals

| Measure | Cases 01–14 | Separate worked example 00 |
| --- | ---: | ---: |
| Source steps | 208 | 7 |
| Descriptor items | 948 | 23 |
| Tracked reused objects | 114 | 3 |
| Later-use links | 281 | 8 |
| Completed/generated active steps | 4663/4663 | 27/27 |
| Sample/reagent records | 229 | 2 |
| Touched-container records | 633 | 5 |
| End-of-run material-state records | 287 | 3 |

This includes the newly repeated Cases 10–13: respectively 127, 64, 99 and 55
completed active steps. Per-case figures are in `expected/tables.md`.

## Additional checks

- All 15 `source.md` files match the corresponding protocol-repository files byte-for-byte.
- Fourteen main programs also match byte-for-byte; Case 05 differs only by its
  qualified enum spelling, as recorded in the README and manifest.
- Sixteen regression tests pass, covering Python-series acceptance, exact package-version checks, prerelease rejection, annotation-based counts, grouped rows,
  invalid links, skipped steps, failed/incomplete executions, repeated display
  names, quantity changes hidden by equal counts, missing fields and file tampering.
- Programs and annotations were not edited to match expected totals.

Public upload, a final immutable release identifier and DOI assignment remain
separate publication steps. This verification makes no claim that those steps
have already occurred.

## Python compatibility update

Culsma 1.0.6 is the published stable implementation release from 7 September
2026: https://github.com/culsma/culsma/releases/tag/v1.0.6 . Only this benchmark
snapshot is still a local publication candidate.

The original Python 3.12.8 baseline is retained. The runner now accepts stable
Python 3.11, 3.12 and 3.13 patch releases while keeping Culsma 1.0.6 and
Lark 1.3.1 pinned. Python 3.13 is recommended for new installations.
The exact `.python-version` pin was removed to avoid requiring 3.12.8 before
users can follow the documented installation steps.

Fresh isolated environments installed the bundled wheels without network
access and each ran all fifteen programs:

| Python | Programs passing | Corpus completed/active | Counts and full material/return records | Regression tests |
| --- | ---: | ---: | --- | ---: |
| 3.11.11 | 15/15 | 4663/4663 | Match | 16/16 |
| 3.12.11 | 15/15 | 4663/4663 | Match | 16/16 |
| 3.13.1 | 15/15 | 4663/4663 | Match | 16/16 |

Case 00 additionally completed 27/27 steps and remains outside corpus totals.
The detailed environments and observed totals are recorded in
`expected/python-compatibility.json`. The actual patch version is recorded for
every new run. Supporting a minor series does not claim that every patch or
operating system has been tested; the rows above list the tested versions,
all on macOS. No programs, annotation files, expected table counts or frozen
runtime baselines were changed for this compatibility update.

## Repository relocation check

The package was moved from the private manuscript workspace to the Culsma
repository's `benchmarks/patterns/`. Only hosting/path documentation, manifest
location metadata and the maintainer assembly entry point changed; programs,
source text, reviewed annotations and frozen runtime outputs were retained.

A new Python 3.12.8 virtual environment was installed offline at the destination.
All fifteen programs were rerun there: 4663/4663 formal-corpus steps and 27/27
worked-example steps completed, with all table counts and full material/return
record comparisons matching. The sixteen regression tests also passed through
both unittest and the Culsma repository's pytest entry point. Snapshot checksums
were refreshed for the reviewed path/documentation changes.

The repository push and benchmark Release remain pending. The package's `dist/`
directory contains only local distribution builds and is excluded from Git.
