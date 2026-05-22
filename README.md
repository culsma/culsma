<p align="center">
  <img src="https://raw.githubusercontent.com/culsma/culsma/main/docs/assets/culsma-wordmark.png" alt="Culsma" width="720">
</p>

<p align="center">
  <a href="https://pypi.org/project/culsma/"><img alt="PyPI" src="https://img.shields.io/pypi/v/culsma.svg"></a>
  <a href="https://pypi.org/project/culsma/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/culsma.svg"></a>
  <a href="https://github.com/culsma/culsma/actions/workflows/release-check.yml"><img alt="Release check" src="https://github.com/culsma/culsma/actions/workflows/release-check.yml/badge.svg"></a>
  <a href="https://doi.org/10.64898/2026.05.07.723509"><img alt="bioRxiv" src="https://img.shields.io/badge/bioRxiv-10.64898%2F2026.05.07.723509-B31B1B.svg"></a>
  <a href="https://doi.org/10.5281/zenodo.20059616"><img alt="Software DOI" src="https://zenodo.org/badge/DOI/10.5281/zenodo.20059616.svg"></a>
  <a href="https://doi.org/10.5281/zenodo.20059696"><img alt="Reference DOI" src="https://zenodo.org/badge/DOI/10.5281/zenodo.20059696.svg"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/License-Apache--2.0-blue.svg"></a>
</p>

Culsma is the public reference implementation of the current Culsma language and execution stack.
The public release is distributed as a Python-based CLI.

This repository intentionally contains only the executable core:

- `src/culsma/parser/`
- `src/culsma/pipeline/`
- `src/culsma/runtime/`
- `src/culsma/driver/`
- `src/culsma/stdlib/`
- `examples/`
- `tests/`

It intentionally leaves out manuscript sources, MCP tooling, editor
integrations, and internal design-workspace documents.

## Install

For the current public release, install from PyPI:

```bash
python -m pip install culsma
```

The runnable examples live in the source repository. If you install from PyPI,
use the GitHub source checkout or copy an example file locally before running
the example commands below.

You can also install directly from the `v1.0.2` tag:

```bash
python -m pip install "culsma @ git+https://github.com/culsma/culsma.git@v1.0.2"
```

Release notes are in [CHANGELOG.md](CHANGELOG.md).

The public language reference is maintained in the companion
`culsma-reference` repository/worktree.

## Repository Layout

```text
src/culsma/parser/    grammar, AST, and source loading
src/culsma/pipeline/  compile, validate, typecheck, and plan lowering
src/culsma/runtime/   execution state, events, and material compute
src/culsma/driver/    backend boundary and concrete drivers
src/culsma/stdlib/    bundled standard-library source
examples/             current protocol examples
tests/                regression and runtime tests
```

## Quick Run

```bash
culsma examples/flow_cytometry_protocol.culs
```

This runs a representative protocol and prints a compact terminal result,
including the returned tube/container state.

The explicit run form is equivalent:

```bash
culsma run examples/flow_cytometry_protocol.culs
```

If you want the machine-readable run output on stdout:

```bash
culsma run examples/flow_cytometry_protocol.culs --json
```

The run output separates the protocol return from the generated lab report:
`returns` is the program output, while `report` is the execution/reporting
summary.

If you want to save the machine-readable run output explicitly:

```bash
culsma run examples/flow_cytometry_protocol.culs --output tmp/result.json
```

If you want intermediate and debug artifacts as well:

```bash
culsma run \
  examples/flow_cytometry_protocol.culs \
  --artifacts-dir tmp/run
```

If you are running from a source checkout without the console entrypoint on
`PATH`, use:

```bash
python -m culsma examples/flow_cytometry_protocol.culs
```

You can also replay a saved run artifact:

```bash
culsma replay --run-json tmp/run/run.json --out tmp/replayed_state.json
```

## Run Tests

```bash
python -m pytest -q
```

## More

- Documentation: [culsma.dev](https://culsma.dev/)
- Paper and citation: [Culsma: A Formal Language for Laboratory Protocols](https://doi.org/10.64898/2026.05.07.723509)
  (bioRxiv preprint)
- Software DOI: [10.5281/zenodo.20059616](https://doi.org/10.5281/zenodo.20059616)
- Reference DOI: [10.5281/zenodo.20059696](https://doi.org/10.5281/zenodo.20059696)
- Latest GitHub release: [github.com/culsma/culsma/releases/latest](https://github.com/culsma/culsma/releases/latest)
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Release process: [RELEASE.md](RELEASE.md)
- Support policy: [SUPPORT.md](SUPPORT.md)

## Release Boundary

- This repository is the public code boundary for Culsma v1.0.x.
- The `examples/` directory contains the runnable CLI example used for public
  smoke validation.
- This repository is licensed under Apache-2.0. See `LICENSE`.

## Support and Maintenance Policy

Culsma is a public open-source reference implementation of the Culsma language
and execution stack.

The repository is published as-is. Maintainer review is limited to narrowly
scoped, reproducible defects in the current public baseline. General support,
custom integration help, roadmap requests, and broad feature requests are out
of scope for the public issue tracker.
