# Changelog

## Internal 1.0.6rc6

### Scope

This internal GitHub prerelease moves material-state decisions behind the
pluggable Scientific Model boundary while keeping validation and atomic state
commit inside the runtime kernel.

It includes:

- a stable resolver/provider contract with capability, lifecycle, version, and
  provenance validation
- the built-in Material Rulebook provider for classification, separation fate,
  and relationship-state transitions
- one centralized separation application path used by `sep`, `frac`, and the
  compatibility `partition` entry point
- authoritative component-entry identity across repeated mixing, movement,
  separation, and recompression
- typed association targets that distinguish container identity from related
  component-entry identity
- correct release of container-local adherent state on cross-container movement
  and preservation of unaffected material relationships
- operation-level free-phase routing for adherent-cell-surface aspiration:
  every `free` entry follows the aspirated phase while surface-associated cells
  remain in the retained part
- inventory reconciliation as a post-result advisory calculation without
  synthetic top-up or mutation of runtime material state
- synchronized architecture diagrams and regression coverage for provider
  selection, proposal validation, state transitions, entry identity, repeated
  separations, and mixed free-phase aspiration

### Compatibility

- The published `internal-1.0.6rc5` tag and release remain unchanged.
- The built-in Material Rulebook is configured by default, so ordinary runtime
  construction continues to resolve supported material operations without an
  external provider.
- Existing `sep`, `frac`, `partition`, and `inventory_check` language/API
  surfaces remain available in this prerelease.
- External scientific-model providers may replace the built-in provider only
  through the same versioned resolver contract; invalid or incomplete
  proposals are rejected before runtime state mutation.
- Unsupported scientific cases return an explicit unresolved diagnostic rather
  than a guessed split or synthetic material.

### Install

After the GitHub prerelease assets are published:

```bash
python -m pip install https://github.com/culsma/culsma/releases/download/internal-1.0.6rc6/culsma-1.0.6rc6-py3-none-any.whl
```

Source tag install:

```bash
python -m pip install "culsma @ git+https://github.com/culsma/culsma.git@internal-1.0.6rc6"
```

### Verified

- `python -m pytest -q`
  - result: `976 passed`
- Case 09 mixed adherent-cell aspiration regression
  - result: surface-associated HEK293T retained; free medium, DNA, and PEI
    routed completely to the aspirated phase
- source CLI and isolated installed-wheel CLI smoke checks passed
- `python -m build`
  - result: `culsma-1.0.6rc6.tar.gz` and
    `culsma-1.0.6rc6-py3-none-any.whl` built
- `python -m twine check`
  - result: passed for both distributions
- isolated wheel install reports `culsma.__version__ == "1.0.6rc6"`

## Internal 1.0.6rc5

### Scope

This internal GitHub prerelease makes dimensioned component quantities the
single authoritative material ledger for separation and downstream movement.
Container-level volume and mass are now projections of routed component detail,
not independently partitioned quantities.

It includes:

- one normalized `component_quantities` ledger for count, volume, and mass
- API-boundary conversion of compatibility-only aggregate input into movable,
  provenance-bearing component detail
- rejection of invalid dimensions, units, negative values, and non-finite
  quantity or density values before material calculation
- component-fate routing of native-axis detail followed by aggregate volume and
  mass projection from each output slot
- removal of the independent conservative `50 / 50` aggregate split that could
  disagree with already-routed component detail
- detail-based transfer, capacity, contents-state, suspension, and estimate
  accounting through the same ledger
- preservation of authored `component_fates` and explicit uncertainty warnings
  when a component fate itself still requires conservative `50 / 50` fallback
- synchronized architecture, reference, conformance, and language-guide
  documentation

### Compatibility

- The published `internal-1.0.6rc4` tag and release remain unchanged.
- Aggregate-only compatibility input is accepted at the material-compute API
  boundary and converted to component detail before use.
- When complete component quantity detail exists, stale supplied aggregate
  volume or mass is discarded and reprojected from detail.
- Conservative `50 / 50` component-fate fallback remains available for unknown
  scientific routing and emits `MAT_CONTENT_PARTITION_FALLBACK`; it no longer
  creates an independent aggregate accounting path.

### Install

After the GitHub prerelease assets are published:

```bash
python -m pip install https://github.com/culsma/culsma/releases/download/internal-1.0.6rc5/culsma-1.0.6rc5-py3-none-any.whl
```

Source tag install:

```bash
python -m pip install "culsma @ git+https://github.com/culsma/culsma.git@internal-1.0.6rc5"
```

### Verified

- `python -m pytest -q`
  - result: `838 passed`
- canonical Case07 source run
  - result: `133/133` steps completed with documented fate/entry warnings
- vendor Case13 source run
  - result: `56/56` steps completed with `0 diagnostics`
- source CLI and isolated installed-wheel CLI smoke checks passed
- `python -m build`
  - result: `culsma-1.0.6rc5.tar.gz` and
    `culsma-1.0.6rc5-py3-none-any.whl` built
- `python -m twine check`
  - result: passed for both distributions
- isolated wheel install reports `culsma.__version__ == "1.0.6rc5"`

## Internal 1.0.6rc4

### Scope

This internal GitHub prerelease completes the cell-count material model started
in rc3 and makes separation fate depend on physical association and the full
operation description rather than quantity units or a program name alone.

It includes:

- constructor finalization after all load items, with explicit carrier
  preference and a recorded default `500 cells/uL` policy for free count-only
  cellular populations
- typed cell-material relationships covering suspension, adherent, pellet, and
  other non-homogeneous states, including concentration provenance and
  transferability
- concentration-resolved count aliquots that move the corresponding carrier
  volume through the ordinary transfer path instead of moving cells with zero
  bulk material
- shared count-transfer behavior for ordinary sources, source-local partition
  selectors, and indexed `container.contents[i]` sources
- atomic diagnostics for invalid suspension concentration, ambiguous cellular
  populations, non-suspension count transfer, implicit-carrier overflow,
  insufficient count, and cross-axis content merge conflicts
- complete separation program descriptors at material-fate resolution,
  association-aware retention/release, native count/volume/mass allocation,
  and inspectable fate provenance
- the optional public `sep(..., component_fates = {...})` override with semantic
  output names, ratio/conservation validation, and runtime source-content checks
- adherent-cell aspiration coverage using standalone `sep(...)` followed by
  `container.contents[0]`, while preserving cell count on the retained surface
- driver-facing pre-resolution fields for physical count-transfer volume and
  synchronized architecture, reference, and user-guide documentation

### Compatibility

- The published `internal-1.0.6rc3` tag and release remain unchanged.
- Existing volume- and mass-only material behavior remains compatible.
- A free count-only cellular constructor may now gain inferred carrier volume
  during finalization and may fail capacity validation if that physical volume
  does not fit.
- Adherent count remains count-only unless explicit liquid is loaded; direct
  count aliquots from adherent, pellet, or other non-homogeneous states are
  rejected.
- `source.partition(program)[i]` remains a compatibility selector and shares
  the same material model, while standalone `sep(...)` plus
  `container.contents[i]` is the preferred reusable contents-state path.
- `component_fates` describes conservative two-output allocation only. Explicit
  recovery loss and predictive scientific models remain outside this release.

### Install

After the GitHub prerelease assets are published:

```bash
python -m pip install https://github.com/culsma/culsma/releases/download/internal-1.0.6rc4/culsma-1.0.6rc4-py3-none-any.whl
```

Source tag install:

```bash
python -m pip install "culsma @ git+https://github.com/culsma/culsma.git@internal-1.0.6rc4"
```

### Verified

- `python -m pytest -q`
  - result: `830 passed`
- corrected canonical Case08 source run
  - result: `133/133` steps completed with `0 diagnostics`
- source CLI and isolated installed-wheel CLI smoke checks passed
- `python -m build`
  - result: `culsma-1.0.6rc4.tar.gz` and
    `culsma-1.0.6rc4-py3-none-any.whl` built
- `python -m twine check`
  - result: passed for both distributions
- isolated wheel install reports `culsma.__version__ == "1.0.6rc4"`

## Internal 1.0.6rc3

### Scope

This internal GitHub prerelease adds an independent cell-count quantity axis so
cell identity and quantity no longer need to be encoded as carrier-liquid
volume. It also makes count-aware separation bulk mass follow the partitioned
carrier-volume ratio when no explicit component mass is available.

It includes:

- the `count` quantity dimension with `cells` as the initial cellular unit
- constructor loads such as `RPE1:100000cells`, restricted to non-negative
  integer counts on `bio_cellular` content
- per-component `dimension`, `unit`, and `value` records that keep cell count
  independent from carrier volume and container capacity
- proportional cell-count carry-forward for volume/mass transfers plus direct
  count transfers such as `target << [source:25000cells]`
- count preservation through `sep`, `frac`, indexed contents, material
  movements, conservation checks, accounting, reports, CLI output, and public
  protocol returns
- count-aware separation volume derived from volume-bearing components, with
  source bulk mass distributed by the resulting carrier-volume ratio when no
  explicit mass-bearing component quantity is available
- inspectable separation bulk-quantity policy metadata and focused end-to-end
  centrifuge, filtration, fractionation, mixing, and downstream-transfer tests
- material-state and runtime architecture documentation aligned with the new
  quantity axis and bulk-mass fallback

### Compatibility

- Existing volume- and mass-only constructor loads and transfers retain their
  prior behavior.
- Count does not add container volume or consume volume capacity.
- `cells` is intentionally limited to cellular content in this prerelease;
  general piece, particle, copy, amount-of-substance, or scientific-model
  plugin support is not introduced.
- Legacy volume/mass-only separation retains conservative bulk accounting.
- The future injectable scientific-model gateway is tracked separately and is
  not part of this prerelease.

### Install

After the GitHub prerelease assets are published:

```bash
python -m pip install https://github.com/culsma/culsma/releases/download/internal-1.0.6rc3/culsma-1.0.6rc3-py3-none-any.whl
```

Source tag install:

```bash
python -m pip install "culsma @ git+https://github.com/culsma/culsma.git@internal-1.0.6rc3"
```

### Verified

- `python -m pytest -q`
  - result: `792 passed`
- canonical Case 08 source and strict-inventory CLI runs
  - result: `108/108` steps completed with `0 diagnostics` in both modes
- source CLI and installed-wheel CLI smoke checks passed
- `python -m build`
  - result: `culsma-1.0.6rc3.tar.gz` and
    `culsma-1.0.6rc3-py3-none-any.whl` built
- `python -m twine check`
  - result: passed for both distributions
- isolated wheel install reports `culsma.__version__ == "1.0.6rc3"`

## Internal 1.0.6rc2

### Scope

This internal GitHub prerelease fixes plate-selector well identity and capacity
handling found while validating paper benchmark Case 06.

It includes:

- inheritance of an explicit `plate(..., capacity = Q)` value by every concrete
  well synthesized from that plate's selectors
- static indexing of plate selector-derived container groups, with the indexed
  binding resolving to the original selected well rather than a reconstructed
  container
- early `SEM_INDEX_OUT_OF_RANGE` validation for statically known container
  group cardinality
- focused compiler, plan, validation, and runtime regression coverage for a
  24-well plate receiving 1 mL and for selected clone-well aliases
- synchronized reference and user-guide clarification that plate capacity is
  per well and static group indexing preserves container identity

### Compatibility

- No new constructor or indexing syntax is introduced.
- A plate without an explicit `capacity` retains the existing runtime default
  for synthesized wells; capacity is not inferred from manufacturer-dependent
  plate-format conventions.
- `group[index]` aliases the existing ordered group member. Explicit container
  constructors such as `well(...)` continue to allocate new containers.
- Separation and source-partition behavior is unchanged.

### Install

After the GitHub prerelease assets are published:

```bash
python -m pip install https://github.com/culsma/culsma/releases/download/internal-1.0.6rc2/culsma-1.0.6rc2-py3-none-any.whl
```

Source tag install:

```bash
python -m pip install "culsma @ git+https://github.com/culsma/culsma.git@internal-1.0.6rc2"
```

### Verified

- `python -m pytest -q`
  - result: `779 passed`
- source CLI and installed-wheel CLI smoke checks passed
- `python -m build`
  - result: `culsma-1.0.6rc2.tar.gz` and
    `culsma-1.0.6rc2-py3-none-any.whl` built
- `python -m twine check`
  - result: passed for both distributions
- isolated wheel install reports `culsma.__version__ == "1.0.6rc2"`

## Internal 1.0.6rc1

### Scope

This internal GitHub prerelease adds first-class centrifugal filtration while
keeping filtration, rather than sedimentation, as the material separation
semantics.

It includes:

- `centrifugal_filtration_program(...)` with required `membrane` and
  centrifugal `drive` fields plus optional action-local `duration`
- `g` and `rpm` validation through the existing centrifugal-setting type
- stable `filtrate` / `retentate` outputs using the filtration material
  partition strategy
- distinct human and robot driver bindings for centrifugal filtration
- validation, typecheck, runtime, material-compute, and driver regression tests
- architecture and material-strategy documentation aligned with the accepted
  reference ratios

### Compatibility

- `filtration_program(...)` remains the general filtration descriptor with a
  named text drive.
- `centrifuge_program(...)` remains a sedimentation-oriented separation with
  `supernatant` / `pellet` outputs.
- Existing separation partition ratios and fallback behavior are unchanged.

### Install

After the GitHub prerelease assets are published:

```bash
python -m pip install https://github.com/culsma/culsma/releases/download/internal-1.0.6rc1/culsma-1.0.6rc1-py3-none-any.whl
```

Source tag install:

```bash
python -m pip install "culsma @ git+https://github.com/culsma/culsma.git@internal-1.0.6rc1"
```

### Verified

- `python -m pytest -q`
  - result: `775 passed`
- source CLI and installed-wheel CLI smoke checks passed
- `python -m build`
  - result: `culsma-1.0.6rc1.tar.gz` and
    `culsma-1.0.6rc1-py3-none-any.whl` built
- `python -m twine check`
  - result: passed for both distributions
- isolated wheel install reports `culsma.__version__ == "1.0.6rc1"`

## Culsma v1.0.5

### Scope

This release makes entry-source scripts the explicit execution boundary,
strengthens runtime report material accounting, and includes focused compiler
and grouped-sample fixes while retaining the 1.0.5 compatibility adapter for
legacy single-protocol entry sources.

It includes:

- top-level entry-source statements as the executable script, with include and
  import dependencies contributing definitions without executing their scripts
- independent CLI batch runs for repeated input files
- a hard `ENTRY_NO_ENTRYPOINT` failure when an entry source has neither script
  statements nor an eligible legacy single-protocol entry
- repeat-body-local iterator validation so sibling repeats may reuse names
- grouped-sample agitation effects for explicit and let-bound sample groups
- structured runtime report models and complete input-lot material accounting
  across external inventory, protocol-created inputs, and material movements
- complete, untruncated reagent-consumption output that excludes generated
  intermediate material from input consumption
- runtime rejection of quantity changes without an auditable material-movement
  contract

### Compatibility

- Existing accepted single-protocol entry files continue to run through the
  isolated 1.0.5 compatibility adapter and emit a deprecation diagnostic.
- Protocol return values remain separate from the generated execution report.
- Existing report serialization fields are preserved for this patch release.

### Verified

- `python -m pytest -q`
  - Python 3.11: `763 passed`
  - Python 3.12: `763 passed`
  - Python 3.13: `763 passed`
- CLI source and installed-wheel smoke checks passed.
- Wheel and source distribution builds passed `twine check`.

## Culsma v1.0.5rc2

### Scope

This second 1.0.5 prerelease keeps the entry-source release-candidate surface
from `v1.0.5rc1` and adds two focused compiler/runtime fixes found during
canonical protocol verification.

It includes:

- repeat iterator bindings are validated as repeat-body-local names so sibling
  repeat blocks may reuse an iterator name without changing protocol semantics
- `agit(sample = group([...]))` and `agit(sample = let_bound_group)` apply the
  agitation material-state effect independently to each grouped sample
- regression coverage for repeat-binding shadowing boundaries and grouped
  agitation over explicit and let-bound groups

### Verified

- `python -m pytest -q`
  - result: `750 passed`

## Culsma v1.0.5rc1

### Scope

This prerelease separates entry-source script execution from protocol
definitions while preserving a temporary 1.0.5 compatibility adapter for
single entry-source protocol files.

It includes:

- entry-source top-level script statements compiled as a first-class script
  entry
- imported and included dependency files load definitions without executing
  their top-level scripts
- protocol definitions no longer become default run entries by name
- repeated CLI input files now run as independent batch items instead of one
  merged entry program
- isolated 1.0.5 fallback for legacy single entry-source protocol files
- parser, IR, plan, scope, validation, typecheck, runtime, and architecture
  diagram updates for the entry boundary

### Verified

- `python -m pytest -q`
  - result: `744 passed`

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
