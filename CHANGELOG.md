# Changelog

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
