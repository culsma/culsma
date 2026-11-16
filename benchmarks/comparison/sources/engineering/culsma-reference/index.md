# Culsma Reference

Reference Snapshot: 2026.0908
Reference Track: Working semantic updates for Culsma 1.0.7; base snapshot 2026.0908
Snapshot Date: 2026-09-08

Canonical public site: [reference.culsma.dev](https://reference.culsma.dev/)

For installation, tutorials, and runnable examples, see the
[Culsma documentation](https://culsma.dev/). Archived reference snapshots are
available under the stable
[Reference DOI](https://doi.org/10.5281/zenodo.20059696).

The archived base snapshot aligns with Culsma 1.0.6. This working revision
adds accepted language contracts for material declarations and replacement,
transfer and hold requirements, and protocol composition. Citation and package
metadata still identify the base snapshot until a new reference archive is issued.
The website and a prepared Zenodo draft do not by themselves establish DOI
publication; consult the linked Zenodo record for published archive status.

This reference is the normative presentation layer for Culsma language rules.
Within the public baseline, the reference set is the source of truth for
language, semantic, diagnostic, and conformance claims.

Implementations and conformance tests must be aligned to this reference. They
are evidence of conformance, not independent replacements for reference
semantics.

When conflicts appear, apply [Reference Governance](./reference_governance.md):
reconcile current reference artifacts first, then align implementation and
tests to the accepted reference state.

Current public baseline notes:

1. For public source-level authoring, Chapter 4 is the public source-surface baseline.
2. Core reference chapters `1 / 2 / 3 / 4 / 5 / 6 / 7 / 8 / 9 / 10 / 11 / 12` are the active public reading path.
3. Archived design notes may remain in the repository, but they are not part of the current public baseline.
4. Internal freeze material may exist in the repository, but it is not part of the public presentation path.
5. User-facing run/report payloads are documented as derived execution projections in Chapter 9 rather than as source-language return contracts.
6. Implementation-facing architecture notes are outside this public reference; this reference remains language/user-facing.
7. Stdlib portal contracts are current only within the portal boundary declared by [Stdlib Portals](./11_stdlib_portals.md).

## Chapters

0. [Reference Governance](./reference_governance.md) - document roles, authority levels, and chapter responsibilities
1. [Notation](./01_notation.md) - current public baseline
2. [Lexical Structure](./02_lexical_structure.md) - current public baseline
3. [Programs and Source Files](./03_programs_and_source_files.md) - current public baseline
4. [Surface Grammar and Statement Forms](./04_surface_grammar_and_statement_forms.md) - current public surface baseline
5. [Names and Bindings](./05_names_and_bindings.md) - current public baseline
6. [Core Atomic Operators and Call Contracts](./05_operation_vocabulary_and_call_contracts.md) - current public baseline
7. [Operational Semantics (Core Atomic Runtime Effects)](./06_operational_semantics.md) - current public baseline
8. [Validation and Diagnostics](./06_validation_and_diagnostics.md) - current public baseline
9. [Execution Model](./07_execution_model.md) - current public baseline
10. [Configuration and Modes](./08_configuration_and_modes.md) - current public baseline
11. [Type and Units](./09_type_and_units.md) - current public baseline
12. [Conformance and Test Mapping](./10_conformance_and_test_mapping.md) - current public baseline

## Scientific Model Extensions

Scientific calculation and inference are defined behind a stable extension
boundary rather than as fixed core-language behavior:

1. [Scientific Model Extension Contract](./extensions/scientific_model/README.md) - stable capability, provider, typed-decision, validation, provenance, and commit-authority boundary shared by replaceable scientific-model implementations
2. [Built-in Material Rulebook](./extensions/scientific_model/builtin_material_rulebook.md) - current specification of the official built-in provider; binding for that provider only and not for other conforming providers

Core chapters define the source syntax, operation contracts, typed decision
boundary, kernel invariants, and diagnostics. Provider specifications define
how one scientific-model implementation resolves decisions behind that
boundary.

## Supporting Current Artifacts

1. [Appendix A. Unified Statement Matrix](./appendix_a_unified_statement_matrix.md) - current compact source/API matrix
2. [Stdlib Portals](./11_stdlib_portals.md) - current portal-boundary contracts

Reading suggestion:

1. For current source-level authoring, read Chapter 4 first.
2. Then use Chapters 5/6/7/8/9/10/11/12 for call contracts, semantics, diagnostics, execution, configuration, type rules, and conformance mapping.

## Scope

This reference focuses on language-level conformance:

1. Surface tokens and lexical rules
2. Grammar and parser-facing constraints
3. Static and dynamic semantic constraints
4. Diagnostics and conformance requirements
5. Placement rule: source forms are maintained in Chapter 4, and operator parameter contracts are maintained in Chapter 6.

Non-normative narratives (motivation, roadmap, positioning) remain in separate whitepaper/project documents.

## Change Notes

1. Protocol parameterization is implemented in parser/IR/plan lowering.
2. Cross-file protocol calls support named arguments with explicit call-frame binding.
3. Domain built-in chapter now includes full per-operation input type and return type contracts.
4. Surface sugar and domain built-in boundary for `container/content` is defined in Chapters 4 and 5.
5. Content taxonomy concerns are split by responsibility: Chapter 6 defines constructor vocabulary and call contracts, Chapter 8 defines staged diagnostic mapping, Chapter 10 defines mode switches, Chapter 11 defines type-level consequences, and Chapter 12 defines conformance evidence.
