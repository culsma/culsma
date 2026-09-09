# Patterns benchmark reproduction

This directory is a self-contained, fixed-input reproduction package for the
paper's three benchmark tables. It contains the fourteen evaluated workflows
(`cases/01`–`cases/14`) and the separate worked example (`worked-example/00`).
Case 00 is **excluded from all corpus totals**.

Snapshot: `patterns-benchmark-2026-09-09` (local submission candidate).
The exact files are identified by `checksums.json`; upstream commits, case
titles and the implementation version are recorded in `manifest.json`.
**Culsma 1.0.6 is already a published stable release**, available at
[the Culsma v1.0.6 release](https://github.com/culsma/culsma/releases/tag/v1.0.6).
The separate benchmark snapshot has not yet been assigned its own release URL
or DOI; that does not refer to the release status of Culsma itself.

The package is maintained at `benchmarks/patterns/` in the Culsma repository,
separately from `src/culsma/`. It has been moved there locally; the repository
push and benchmark Release are still pending. After publication, a repository
checkout or the standalone benchmark ZIP will contain the same runnable package.
The private manuscript repository is not required for reproduction.

## Install and reproduce

Use a **stable Python 3.11, 3.12 or 3.13** release. For a new installation,
we recommend **Python 3.13**, using the latest available patch in that series.
An existing Python 3.11 or 3.12 installation is also supported; you do not need
to install Python 3.12.8 specifically. The original baseline used 3.12.8;
`VERIFICATION.md` lists the versions actually tested. Other minor series and
Python prereleases are not currently accepted by this package.

The package contains the public, platform-independent wheels for the released
**Culsma 1.0.6** and **Lark 1.3.1**. These two package versions and wheel hashes
remain fixed. Installation after obtaining Python requires no network, author
account, or checkout of another repository. The Culsma wheel's 145 source/data
files match implementation commit `0a5393c33151663566fe3d81d4fe01f29f98e274`.

### Obtain Python

- **macOS or Windows:** open the [official Python downloads page](https://www.python.org/downloads/),
  choose a stable **3.13.x** release, and install the installer for your system.
  Select the 3.13 series explicitly rather than the site's newest overall release.
  On macOS, verify with `python3.13 --version`; on Windows, use `py -3.13 --version`.
- **Linux:** use a Python 3.11, 3.12 or 3.13 installation supplied by your system
  or package manager. Ensure its `venv` support is installed, then verify with
  `python3 --version`. The exact package name depends on the distribution.
- **Already have a supported Python?** Use it directly. In the commands below,
  replace `python3.13` with `python3.12`, `python3.11`, or `python3` after checking
  its version. No project-level Python version-manager pin is required.

### Create an environment and run

From this directory, on macOS/Linux with Python 3.13:

```sh
python3.13 --version
python3.13 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links vendor --require-hashes -r requirements.lock
.venv/bin/python reproduce.py all
```

On Windows, from this directory in PowerShell or Command Prompt:

```text
py -3.13 --version
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install --no-index --find-links vendor --require-hashes -r requirements.lock
.venv\Scripts\python.exe reproduce.py all
```

For an existing Windows Python 3.11 or 3.12, replace `-3.13` accordingly.
The end-to-end validation was performed on macOS; Windows and Linux instructions
have not been independently validated. See the [Python virtual-environment guide](https://docs.python.org/3/library/venv.html)
for platform-specific setup. The runner checks the supported Python series and
exact Culsma/Lark versions, and records the actual Python patch version in each
run's `environment.json`.

The command runs all fifteen programs using the default **StubDriver**, without
instrument access or external inventory reconciliation. Declared default inputs
and predefined readout values are used; no parameter overrides are supplied.
Completion verifies these modeled executions, not the biological outcome of an
experiment or execution on physical laboratory equipment.

Expect several minutes and allow a few GB of free disk space for transient
runtime artifacts. Each case's JSON artifacts are losslessly compressed after
execution. The runner refuses to overwrite an existing results directory. For
another run, choose a new directory:

```sh
.venv/bin/python reproduce.py all --results results/second-run
```

## What to open afterwards

- `results/tables.md`: the three recalculated, human-readable tables.
- `results/tables.json`: the same per-case counts and totals as structured data.
- `results/comparison.json`: pass/fail and any count or material-record differences.
- `results/05/output.json` (for example): the CLI's original result, including
  execution status, material consumption, final materials and formal returns.
- `results/05/artifacts/run.json.gz`: the detailed runtime events and state.
- `results/05/stderr.txt` and `invocation.json`: errors, actual command and exit code.

Exit code 0 means the snapshot files verified, all programs completed without
runtime diagnostics, every table count matched, and the consumption, final
material, touched-container and formal-return records matched the frozen
baseline. Nonzero exit means a failure or difference; the runner does not adjust
inputs or annotations to obtain matching numbers.

To inspect the published expected result without running Culsma, open
`expected/tables.md` or decompress `expected/runtime/05/output.json.gz` with any
gzip-capable tool. The complete raw runtime baseline is also provided there.
To recalculate from an existing local run:

```sh
.venv/bin/python reproduce.py summarize --results results
```

## Where each number comes from

| Paper measure | Calculation input and rule |
| --- | --- |
| Source workflow steps | Number of entries in `source.steps.json` |
| Descriptor items | Sum of the lengths of each step's `descriptors` list in `action_descriptors.json` |
| Tracked reused objects | Number of reviewed rows in `object_reuse.json`; a grouped row counts once |
| Later-use links | Number of distinct later source steps in each row's `used_in`; excludes the introduction step |
| Generated active steps | Runtime `execution.total_steps - execution.skipped_steps` |
| Completed steps | Runtime `execution.completed_steps` |
| Sample/reagent count | Number of runtime `materials.reagent_consumption` records |
| Labware count | Number of runtime `resource_summary.containers.touched_names` entries, checked against `touched_count` |
| End-of-run material states | Number of runtime `materials.final_products` records, the implementation's reported terminal experimental material footprint |

The first four are **counts of manually reviewed evidence**, not quantities
inferred automatically from prose or execution. Grouped descriptors and grouped
objects keep their reviewed boundaries. The script counts the detailed entries;
it does not read the cached total fields in those annotation files. Runtime
display names may repeat for separate container allocations, so labware records
are not deduplicated by name. The runtime field `final_products` is distinct from
formal protocol returns and from every internal container in the full state.

`expected/tables.json` is the comparison target, transcribed/extracted from the
current manuscript tables. It is never an input to the count calculations.
`expected/manuscript-tables.tex` preserves those table excerpts. The runtime
comparison also checks complete consumption/final-material rows and formal
returns, so matching counts alone do not hide changed quantities.

## Contents and source interpretation

Each case includes `protocol.culs`, any accompanying `.culs` files, `source.md`,
the source-step record, descriptor list and object-reuse list. Where supplied by
the existing evidence package, `alignment.json` and `record.md` retain the
step mappings and modeling notes. Some step records are deliberate aggregations
of a longer original workflow. See `SOURCES.md` and `references.bib` for source
attribution and the distinction between canonical syntheses and adaptations.
The source text is copied without rewriting it.

The inputs were frozen from the website's published-artifact working tree to
match the paper. They are not downloaded dynamically when the reader runs the
package. Fourteen of the fifteen main program files also match the current
protocol repository byte-for-byte. Case 05's website program uses the qualified
enum forms `CentrifugeProgramOutput.PELLET` and `MaterialRelation.CELL_BOUND`;
the protocol repository currently uses the corresponding short forms. This
snapshot retains the website's qualified-enum program, already used in the
paper's recorded run. No other program logic is changed by packaging.

Historical upstream metadata labels such as `vendor_manual_anonymized` describe
the source collection's old naming and do not impose a special reviewer-access
or permission-approval workflow. Cases 10–13 are included in this same package.
Upstream historical audit/availability summaries are not used as live release
instructions or as calculation inputs.

## Tests and integrity

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python reproduce.py check-files
```

`checksums.json` covers the programs, sources, annotations, scripts, expected
outputs and installation wheels. New runtime directories are not part of that
frozen file set. Checksums identify bytes and detect changes; they are not a
cryptographic signature. Runtime comparison is semantic at the documented
record level, not byte-for-byte equality of event logs or host-specific paths.

This package neither generates nor updates benchmark website pages. Updates to
the reviewed evidence, manuscript tables or release snapshot require a separate
review. The maintainer assembly utility is `tools/prepare_snapshot.py`.
Creating a new snapshot requires the maintainer to provide `--paper`,
`--artifacts` and `--wheels` explicitly; readers do not need this utility or
access to the manuscript. For example, maintainers can refresh file checksums
after a reviewed documentation change with `python tools/prepare_snapshot.py --seal`.

Local runs (`results/`), virtual environments (`.venv/`) and ZIP builds (`dist/`)
are ignored by Git and excluded from snapshot checksums. The frozen `expected/`
records and `vendor/` wheels remain part of the versioned reproduction material.
