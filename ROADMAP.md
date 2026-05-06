# Culsma Roadmap

This roadmap describes the intended direction for the public Culsma codebase. It
is directional rather than a promise of exact dates or complete feature lists.
Items may move between releases as the public baseline stabilizes. Version
labels below are planning anchors, not release commitments.

Public maintainer review remains governed by [SUPPORT.md](SUPPORT.md). Roadmap
items do not imply support for custom integrations, broad feature requests, or
requests to prioritize a particular backend or workflow family.

## Development Vision

Culsma is developed as a formal execution kernel for laboratory protocols. The
near-term roadmap focuses on making the current public language and execution
stack easier to write, inspect, reproduce, and project to execution contexts
before expanding workflow coverage through a larger bundled standard library.

The development path is therefore staged:

1. stabilize the public language and executable core;
2. improve authoring, diagnostics, and public examples around that core;
3. make execution evidence easier to audit and reproduce;
4. clarify how the existing driver architecture projects protocols to human and
   robot execution contexts;
5. grow the standard library as a later workflow layer on top of the stabilized
   execution kernel.

In short, Culsma grows outward from the execution semantics. The standard
library is important, but it should not outrun the public kernel, artifact, and
projection boundaries it depends on.

## Release Policy

Culsma uses semantic versioning for the public Python package.

- Patch releases (`v1.0.1`, `v1.0.2`) are for compatible fixes, documentation
  corrections, diagnostics polish, and release maintenance.
- Minor releases (`v1.1.0`, `v1.2.0`) are for compatible improvements to the
  existing public language, CLI, diagnostics, execution evidence, and backend
  boundaries.
- Major releases (`v2.0.0`) are reserved for breaking changes to public source
  syntax, runtime semantics, protocol return contracts, or public output schemas,
  or for a deliberate next public baseline with a substantially larger standard
  library surface.

Patch releases may happen as needed. Minor releases are planned around coherent
themes rather than fixed dates.

## Phase 1: Public Kernel Stabilization (`v1.x`)

The `v1.x` line focuses on the current public execution kernel: source language,
CLI, diagnostics, runtime artifacts, replay, and execution projection. It is not
intended to make the bundled standard library a complete workflow catalogue.

### Current Baseline: `v1.0.x`

Goal: keep the first public release stable and reproducible.

Focus:

- Keep the current public source surface stable.
- Preserve the boundary between protocol return values, runtime state, and
  derived reports.
- Keep examples, docs, reference text, and tests synchronized.
- Fix public-release defects without changing language semantics.
- Maintain a reliable smoke path: install, run the minimal protocol, inspect
  artifacts, and replay a saved run.

Typical releases:

- `v1.0.1`: public-release polish and defect fixes.
- `v1.0.2+`: additional compatible fixes if needed.

### Next: `v1.1.0` Authoring UX

Goal: make it easier to write, validate, and debug Culsma protocols.

Planned direction:

- Add or refine validation-focused CLI workflows.
- Improve terminal diagnostics and source-location reporting.
- Expand starter examples beyond the minimal transfer protocol.
- Improve quickstart and authoring documentation.
- Smooth common source-authoring patterns where the language surface is already
  semantically clear.
- Keep machine-readable output compatible with the `v1.0.x` boundary unless a
  clear bug fix is required.

Success criteria:

- A new user can write a small protocol, run it, and understand validation or
  runtime failures without reading internal artifacts first.
- Existing `v1.0.x` examples continue to run unchanged.

### Later: `v1.2.0` Reproducible Execution

Goal: make Culsma runs easier to audit, compare, and reproduce.

Planned direction:

- Document public artifact schemas more completely.
- Improve run-bundle export and reproducibility workflows.
- Clarify provenance, replay, and event-log expectations.
- Strengthen conformance evidence for runtime state, protocol returns, reports,
  and artifacts.
- Keep `returns` and derived `report` outputs explicitly separated.

Success criteria:

- A run can be packaged with enough artifacts to explain what executed, what
  returned, what report was derived, and how replay reconstructs state.
- Public tests and docs make artifact compatibility expectations clear.

### Later: `v1.3.0` Execution Projection

Goal: document and harden how the existing driver architecture projects Culsma
protocols to execution contexts without changing protocol semantics.

Planned direction:

- Document the human-driver and robot-driver responsibilities.
- Define backend receipt and failure-reporting expectations.
- Clarify driver capability and projection contracts as public extension points.
- Explore run-sheet or execution-sheet outputs for human execution.
- Keep backend-specific behavior separate from source-language semantics.

Success criteria:

- Culsma protocols can be projected to different execution backends without
  changing protocol return semantics or runtime truth.
- Driver failures and receipts are auditable through stable runtime artifacts.
- Backend work defines boundaries and artifacts; it does not imply custom
  backend integration support.

## Phase 2: Standard Library Expansion (`v2.x`)

The `v2.x` line is the place to turn the bundled standard library from a small
set of current executable protocol helpers into a more systematic workflow
layer. This does not imply that all core language semantics must change in
`v2.0.0`; the version is a marker for a larger public baseline.

### Next Major: `v2.0.0` Standard Library

Goal: develop the bundled standard library into a stable workflow library for
realistic runnable laboratory workflows.

Planned direction:

- Define the standard-library development model, including portal naming,
  parameter contracts, return contracts, maturity labels, and conformance hooks.
- Stabilize and document selected public stdlib workflow portals.
- Provide runnable workflow examples for representative patterns such as PCR, DNA
  extraction, electrophoresis/readout, and related preparation flows.
- Include expected terminal output and artifact expectations for each workflow.
- Use workflow examples to harden diagnostics, material accounting, and return
  contracts.

Success criteria:

- Culsma can demonstrate more than minimal transfer: it can express and execute
  representative multi-step protocols using the public source surface and bundled
  standard library.
- Each public workflow example is runnable in CI or a documented smoke path.
- Workflow coverage remains example-driven; it is not a commitment to support
  arbitrary laboratory workflows through the public issue tracker.

## Longer-Term Themes

These themes may span multiple releases.

- Authoring tools: formatting, linting, richer validation, editor integration.
- Standard-library coverage: more protocol families and stronger public examples.
- Execution evidence: better provenance, replay, and conformance bundles.
- Backend integration: clearer driver APIs and backend-specific projections.
- Reference alignment: keep the public reference, docs, examples, and tests in
  lockstep with implementation behavior.

## Roadmap Boundaries

The roadmap grows Culsma outward from the current execution kernel. To keep that
direction clear, the near-term roadmap does not include:

- Expanding the bundled standard library into a complete workflow catalogue
  during the `v1.x` line.
- Treating backend-specific behavior as source-language semantics.
- Exposing internal canonical operations as user-facing source examples.
- Adding large language features without reference updates, conformance hooks,
  and tests.
- Changing core container/content/reference semantics merely to simplify
  authoring or implementation.
