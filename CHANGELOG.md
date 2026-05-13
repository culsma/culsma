# Changelog

## Unreleased

### Maintenance

- Add README badges for PyPI, Python versions, release checks, software DOI,
  reference DOI, and license.
- Update the public paper/citation status from an arXiv placeholder to the
  current bioRxiv screening state.
- Clarify that repository examples are available from the source checkout when
  installing the package from PyPI.
- Remove a stale package-data declaration for a nonexistent pipeline operation
  catalog.
- Expose `culsma.__version__` for lightweight runtime version checks.

## Culsma v1.0.1

### Scope

This release prepares the first PyPI distribution for the public Culsma
execution-kernel baseline.

It includes:

- explicit Python package license metadata for Apache-2.0
- bundled third-party notice files in package metadata
- PyPI-friendly project URLs and README install instructions
- the public roadmap and paper/citation placeholder links

### Install

PyPI install:

```bash
python -m pip install culsma
```

Source tag install:

```bash
python -m pip install "culsma @ git+https://github.com/culsma/culsma.git@v1.0.1"
```

### Notes

- Requires Python 3.11+
- Runtime dependency: `lark>=1.1.0`
- This is a packaging and public metadata release; no source-language semantic
  change is intended.

### Verified

- `python -m pytest -q`
  - result: `522 passed`
- `python -m build --sdist --wheel --outdir /tmp/culsma-v1.0.1-dist --no-isolation`
  - result: `culsma-1.0.1.tar.gz` and `culsma-1.0.1-py3-none-any.whl` built
    successfully
- `python -m twine check /tmp/culsma-v1.0.1-dist/*`
  - result: passed

## Culsma v1.0.0

### Scope

This is the first formal public release of the current Culsma execution stack.

It includes:

- parser, compile, validate, typecheck, plan, runtime, and driver structure
  aligned to the current architecture
- runtime scheduler and driver framework cleanup
- install and CLI usage updated to the current package layout

### Install

Source install:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Wheel install:

```bash
python -m pip install culsma-1.0.0-py3-none-any.whl
```

### Run

```bash
culsma run --input examples/minimal/public_minimal.culs --artifacts-dir tmp/run
```

### Verified

Release candidate verification:

- `python -m pytest -q`
  - result: full test suite passed
- `python -m culsma.cli run --input examples/minimal/public_minimal.culs`
  - result: CLI smoke test passed and emitted the primary run result JSON
- `python -m pip wheel . -w /tmp/culsma-dist --no-deps --no-build-isolation`
  - result: `culsma-1.0.0-py3-none-any.whl` built successfully

### Notes

- Requires Python 3.11+
- Runtime dependency: `lark>=1.1.0`
- Offline wheel installs still require dependency availability for `lark`
