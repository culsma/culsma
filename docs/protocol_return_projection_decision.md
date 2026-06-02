# Protocol Return Projection Decision

Status: current for ordered container-group projection; authoritative reference updated in
`/Users/yangchen/VsCodeProjects/labword-theroy/culsma-reference/07_execution_model.md`

Decision frozen for implementation. The public reference is the authoritative
source for protocol return projection semantics. This card tracks the
implementation plan for this repository. Composite list/record projection and
unresolved-return diagnostics remain follow-up compatibility work.

## Context

Culsma protocols already separate explicit protocol returns from derived runtime
reports. A return such as `return sample;` is not a report request and is not a
dump of internal runtime state. It is the protocol's declared output value,
projected into the public run-output schema.

The current implementation already projects single concrete containers into
their final material state. It does not yet consistently project ordered
container groups, so returning a well group or separation/fraction group can
collapse to `null` in machine output and `None` in terminal output.

## Decision

A protocol return projects the resolved runtime value of the return expression
into the public output schema.

Projection rules:

1. Literal scalar values remain literal public values.
2. Quantities project as structured quantity values with `kind`, `value`, and
   `unit`.
3. A concrete material container projects as `container_ref`.
4. An ordered concrete material container group projects as
   `container_group_ref`.
5. A data/readout handle projects as `data_ref`.
6. A grouped data/readout handle projects as `data_group_ref`.
7. Named returns only name output ports; they do not change value projection.
8. Composite list/record projection should recursively project member values,
   but this is not required for the first container-group implementation step.
9. Unresolved return values should be reported by runtime diagnostics rather
   than silently treated as successful `null` outputs. Tightening this behavior
   is a follow-up conformance step.

## Public Shapes

Single concrete container:

```json
{
  "kind": "container_ref",
  "id": "Prepared",
  "container_kind": "tube",
  "volume_uL": 100,
  "mass_mg": 100
}
```

Ordered concrete container group:

```json
{
  "kind": "container_group_ref",
  "member_count": 2,
  "members": [
    {
      "kind": "container_ref",
      "id": "A1",
      "container_kind": "well",
      "volume_uL": 20,
      "mass_mg": 20
    },
    {
      "kind": "container_ref",
      "id": "A2",
      "container_kind": "well",
      "volume_uL": 20,
      "mass_mg": 20
    }
  ]
}
```

Named return envelope:

```json
{
  "returns": ["sample_out", "readout_out"],
  "bindings": {
    "sample_out": {"kind": "container_ref"},
    "readout_out": {"kind": "data_ref"}
  }
}
```

## Invariants

1. `returns` is protocol output. `report` is derived execution summary.
2. Material return projection reads final runtime material state.
3. Data/readout return projection reads runtime data artifacts.
4. `container_group_ref.members` preserves source/runtime order.
5. A material group return remains a material endpoint, not a readout.
6. A readout group return remains a data endpoint, not a material group.
7. CLI formatting only renders already-projected public values; it does not
   decide return semantics.

## Ownership

1. Source syntax and return contract validation are owned by compile.
2. Runtime value resolution and public return projection are owned by runtime.
3. Human terminal rendering is owned by CLI formatting.
4. Public machine output compatibility is owned by `culsma_run_output_v1`
   documentation and regression tests.

## Implementation Order

1. Implement ordered concrete container-group return projection.
2. Add regression tests for named returns of a single container, multiple
   containers, direct `group(...)`, let-bound `group(...)`, `sep` groups, and
   `frac` groups.
3. Update CLI formatting to summarize `container_group_ref` without dumping
   excessive members.
4. Add or update public output-schema documentation for `container_group_ref`.
5. Follow up with recursive composite projection and unresolved-return
   diagnostics after the group behavior is stable.

## Conformance Hooks

- Req RETURN-PROJ-001: Returning a single concrete container projects a
  `container_ref`. Test: existing single-container return tests.
- Req RETURN-PROJ-002: Returning multiple named concrete containers preserves
  named bindings and projects each binding as `container_ref`. Test: existing
  named-container return tests plus CLI JSON regression.
- Req RETURN-PROJ-003: Returning direct `group([c1, c2])` projects
  `container_group_ref` with ordered `members` and `member_count`.
- Req RETURN-PROJ-004: Returning a let-bound `group([c1, c2])` projects
  `container_group_ref` with ordered `members` and `member_count`.
- Req RETURN-PROJ-005: Returning a `sep` group projects the two ordered
  material slots as `container_group_ref`.
- Req RETURN-PROJ-006: Returning a `frac` group projects all ordered material
  slots as `container_group_ref`.
- Req RETURN-PROJ-007: Returning `data_ref` and `data_group_ref` remains data
  projection and is not coerced into material projection.
- Req RETURN-PROJ-008: CLI output summarizes `container_group_ref` clearly and
  preserves existing single-container display.
