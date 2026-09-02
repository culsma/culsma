# Material Transition Semantics

The author supplies the subject, one program-owned output member, and the target
`MaterialRelation`. The current relation is read from the selected live entry;
the author does not repeat a `from` precondition.

| Target relation | Association category | Author supplies `associated_with` | Resolved target |
|---|---|---|---|
| `FREE` | none | no | association cleared |
| `CONTAINER_SURFACE` | output container | no | concrete output container |
| `PELLET` | output container | no | concrete output container |
| `PRECIPITATE` | output container | no | concrete output container |
| `DISRUPTED` | output-container-scoped state | no | concrete output container |
| `FIELD_RETAINED` | output-container-scoped retention | no | concrete output container |
| `BEAD_BOUND` | component entry | material selector required | selected bead entry in the same output |
| `MEMBRANE_BOUND` | component entry | material selector required | selected membrane entry in the same output |
| `CELL_BOUND` | component entry | material selector required | selected cell entry in the same output |
| `UNRESOLVED` | internal sentinel | invalid | transition rejected |

```mermaid
stateDiagram-v2
    direction TB

    state "Resolve one live material entry" as ResolveEntry
    state EntryResolved <<choice>>
    state "Read its current MaterialRelation" as ReadCurrent
    state "Validate the requested target enum and association shape" as ValidateTarget
    state TargetValid <<choice>>
    state "Verify a positive routed fraction for the requested output" as ValidateFraction
    state FractionPositive <<choice>>
    state "Build and validate the complete relationship-state decision" as BuildDecision
    state "Return one diagnostic without changing committed material" as Reject
    state "Project the accepted decision into the separation candidate" as Project

    [*] --> ResolveEntry
    ResolveEntry --> EntryResolved
    EntryResolved --> Reject : missing or invalid selector
    EntryResolved --> ReadCurrent : selected
    ReadCurrent --> ValidateTarget
    ValidateTarget --> TargetValid
    TargetValid --> Reject : invalid enum or association target
    TargetValid --> ValidateFraction : valid
    ValidateFraction --> FractionPositive
    FractionPositive --> Reject : zero routed quantity
    FractionPositive --> BuildDecision : positive quantity
    BuildDecision --> Project
    Project --> [*]
    Reject --> [*]
```

The author-settable state vocabulary is closed by `MaterialRelation`; transitions
between valid members are not restricted by a pair whitelist.
