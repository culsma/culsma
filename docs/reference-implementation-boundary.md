# Language contracts and implementation representation

The language reference defines accepted source forms, material identities and
quantities, operation results, and failure behavior. It does not prescribe the
Python classes or execution-plan representation used by this implementation.

In this implementation, material transfer passes through `MutationStmt`,
`IRMutation`, and a `PlanStep` whose operation is `Mutation`. Constructor
initialization uses canonical operations such as `AllocContainer`,
`DefineContent`, `LoadContent`, and `AnnotateContent`; these names are not
protocol-authoring APIs. Container records store aggregate quantities and
component quantities together with metadata.

A component-bound relationship uses an `AssociationTarget` with a
`component_entry` kind and the selected entry ID. The source-level contract
instead specifies which material entry is bound to which other entry and
requires a valid association within the same output.

Execution requirements are carried through plan and driver projection. Their
language contract is preservation of the requirement through execution and
rejection before the action when support is explicitly unavailable. The
internal field or flag used to carry a requirement is not source syntax.

## 1.0.7 reference baseline

The release was checked against reference revision
[`ae7d00beb1145031de5de8df317da4f778ff4ca3`](https://github.com/culsma/culsma-reference/tree/ae7d00beb1145031de5de8df317da4f778ff4ca3).
The frozen content contract is in `conformance/content_reference.json`.
`python -m conformance.content_contract --check` checks that snapshot and its
implementation-owned evidence hooks. This check covers the stated content
contract; it is not a claim of complete language conformance.
