# Changelog

## Culsma v1.0.2

### Scope

This release aligns content taxonomy semantics, source authoring examples, and
material partition diagnostics for the current public Culsma execution kernel.

It includes:

- canonical content taxonomy normalization for `kind` and `type`
- compatibility warnings for legacy content sugar and deprecated taxonomy values
- source-level `attrs = { ... }` record literal support for content metadata
- runtime preservation of canonical and original content classification fields
- updated material partition classes and conservative fallback diagnostics
- frontend conformance tests covering current source syntax end to end
- a representative flow-cytometry protocol example using current source syntax
- public documentation updates for content taxonomy, attrs, examples,
  diagnostics, artifacts, replay, and navigation

### Compatibility

- Legacy content forms such as `blood(...)`, `reagent(...)`, `buffer(...)`, and
  old taxonomy tokens are still accepted in compatibility mode.
- Compatibility normalization emits warnings instead of failing the run.
- Current examples use `content(kind = ..., type = ..., attrs = { ... })`.
- The repository example path changed to
  `examples/flow_cytometry_protocol.culs`.

### Install

PyPI install:

```bash
python -m pip install culsma
```

Source tag install:

```bash
python -m pip install "culsma @ git+https://github.com/culsma/culsma.git@v1.0.2"
```

### Notes

- Requires Python 3.11+
- Runtime dependency: `lark>=1.1.0`
- This is a patch release. It does not intentionally remove legacy source
  compatibility, but it does update the recommended public authoring surface.

### Verified

- `python -m pytest -q`
  - result: `544 passed`
- `python -m culsma.cli run examples/flow_cytometry_protocol.culs`
  - result: `46/46 steps completed, 0 diagnostics`
- `npm --prefix ../culsma-docs run build`
  - result: passed
- `python -m pip wheel . -w /private/tmp/culsma-v1.0.2-dist --no-deps --no-build-isolation`
  - result: `culsma-1.0.2-py3-none-any.whl` built

Not run locally:

- `twine check`
  - reason: `twine` is not installed in the current virtual environment

## Unreleased

### Maintenance

- No unreleased changes.

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
culsma run --input examples/flow_cytometry_protocol.culs --artifacts-dir tmp/run
```

### Verified

Release candidate verification:

- `python -m pytest -q`
  - result: full test suite passed
- `python -m culsma.cli run --input examples/flow_cytometry_protocol.culs`
  - result: CLI smoke test passed and emitted the primary run result JSON
- `python -m pip wheel . -w /tmp/culsma-dist --no-deps --no-build-isolation`
  - result: `culsma-1.0.0-py3-none-any.whl` built successfully

### Notes

- Requires Python 3.11+
- Runtime dependency: `lark>=1.1.0`
- Offline wheel installs still require dependency availability for `lark`
