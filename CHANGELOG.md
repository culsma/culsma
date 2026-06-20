# Changelog

## Culsma v1.0.4

### Scope

This release extends the public execution kernel with durable container
contents-state tracking, indexed contents-state reads, field-retention
preservation, and updated `with env(...)` / `hold(...)` authoring semantics.

It includes:

- durable container contents-state records for standalone `sep(...)` and
  `frac(...)`
- indexed contents-state reads in mutation sources using
  `container.contents[i]`
- stale/mixed contents-state handling for ordinary mutation and agitation
- source-local `source.partition(program)[i]` compatibility preservation
- a narrowed magnetic `field_retention` preservation hook for compatible
  operations under matching field context
- material runtime module split into smaller services for arguments,
  conservation, contents state, ledger, mutation, refs, results, separation,
  and units
- material architecture documentation for the contents-state manager boundary
- direct `hold(...)` target markers may appear anywhere in the immediate
  `with env(...)` body
- active scalar thermal environment blocks may omit `duration` when they contain
  executable work
- pure scalar thermal holds still require explicit `duration`
- release workflow cleanup so normal public GitHub Releases remain manual
  after PyPI publication

### Compatibility

- Existing named `sep(...)` / `frac(...)` group behavior remains compatible.
- Existing `source.partition(program)[i]` remains a transfer-local selector and
  is not redefined as a prior-state reader.
- `container.contents[i]` is valid only where a current indexed contents state
  exists and remains valid.
- Existing direct `hold(...)` uses remain valid. `hold(...)` remains invalid
  outside a direct `with env(...)` body or inside nested `if`, `repeat`, or
  `with constraint` blocks.
- `with env(thermal = ..., duration = ...) { action; hold(target); }` is valid;
  the duration is the author-provided environment window for the executable
  body and declared target.

### Install

PyPI install:

```bash
python -m pip install culsma
```

Source tag install:

```bash
python -m pip install "culsma @ git+https://github.com/culsma/culsma.git@v1.0.4"
```

### Verified

- `python -m pytest -q`
  - result: `723 passed`
- `python -m build --outdir /private/tmp/culsma-1.0.4-dist`
  - result: `culsma-1.0.4.tar.gz` and
    `culsma-1.0.4-py3-none-any.whl` built
- `python -m twine check /private/tmp/culsma-1.0.4-dist/*`
  - result: passed
- local wheel install check
  - result: installed package reports `culsma.__version__ == "1.0.4"`

## Culsma v1.0.3

### Scope

This release extends the current public execution kernel with container target
views, source-local partition selectors, formal-parameter handling fixes, and
return projection fixes.

It includes:

- container structure target views for thermal holds, including
  `container.structure.top`, `container.structure.bottom`, and
  `container.structure.sidewall`
- source-local partition selectors in mutation sources, using
  `source.partition(program)[0]` and `source.partition(program)[1]`
- sep-family program ownership for partition selectors without replacing
  named/indexed `sep(...)` groups
- static-control support for formal protocol parameters
- canonical duration units and compatibility aliases for day-scale durations
- program registry alignment with the reference readout surface
- return projection fixes for container groups and selector-derived well groups
- a tag-driven release workflow for normal `v*` releases
- removal of bundled example files from the public code package; CLI smoke
  checks now generate protocol source during validation

### Compatibility

- Existing `hold(...)` uses remain valid. The recommended current spelling is
  `hold(target)` without the legacy `sample = ...` parameter name.
- Container structure facets are target views for environment/thermal exposure;
  they are not material contents and cannot be used as mutation targets or
  readout samples.
- `source.partition(program)[i]` is valid only inside mutation source items and
  currently supports static indices `0` and `1`.
- `sep(...)` remains the construct for materializing named or indexed separated
  groups. Source-local partition selectors consume a separation result from a
  source expression without creating a group binding.

### Install

PyPI install:

```bash
python -m pip install culsma
```

Source tag install:

```bash
python -m pip install "culsma @ git+https://github.com/culsma/culsma.git@v1.0.3"
```

### Notes

- Requires Python 3.11+
- Runtime dependency: `lark>=1.1.0`
- This is a patch release. It keeps legacy accepted syntax while updating the
  recommended public authoring surface.

### Verified

- `python -m pytest -q`
  - result: `668 passed`
- `python -m culsma.cli run /private/tmp/cli_smoke.culs`
  - result: `3/3 steps completed, 0 diagnostics`
- `python -m pip wheel . -w /private/tmp/culsma-v1.0.3-dist --no-deps --no-build-isolation`
  - result: `culsma-1.0.3-py3-none-any.whl` built
- `python -m twine check /private/tmp/culsma-v1.0.3-dist/*`
  - result: passed

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
