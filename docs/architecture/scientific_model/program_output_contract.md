# Program-Owned Output Contract

Every concrete separation program owns its output enumeration. Frontend
validation and runtime resolution use the same `ProgramOutput` member; there is
no global material-output alias table.

| `ProgramSpec.output_type` | `part_id = "0"` | `part_id = "1"` |
|---|---|---|
| `CentrifugeProgramOutput` | `SUPERNATANT` | `PELLET` |
| `MagneticProgramOutput` | `BOUND` | `FLOWTHROUGH` |
| `DisruptProgramOutput` | `LYSATE` | `DEBRIS_OR_RESIDUE` |
| `FieldProgramOutput` | `TARGET_BAND_FRACTION` | `NON_TARGET_FRACTION` |
| `FiltrationProgramOutput` | `FILTRATE` | `RETENTATE` |
| `CentrifugalFiltrationProgramOutput` | `FILTRATE` | `RETENTATE` |
| `PhasePartitionProgramOutput` | `TARGET_PHASE` | `OTHER_PHASE` |
| `PrecipitationProgramOutput` | `PRECIPITATE` | `SUPERNATANT` |
| `SepProgramOutput` | `FRACTION_A` | `FRACTION_B` |

```mermaid
classDiagram
    direction LR

    class ProgramRegistryModule["pipeline.program_registry"] {
        +get_program_spec(kind) ProgramSpec?
        +get_program_outputs(kind) tuple~ProgramOutput~
        +resolve_program_output(program_kind, enum_type_name, member_name) ProgramOutputResolution
    }
    class ProgramSpec {
        +kind : string
        +output_type : type~ProgramOutput~
    }
    class ProgramOutputResolution {
        +output : ProgramOutput?
        +code : string?
        +message : string?
    }
    class ProgramOutput {
        <<abstract enumeration base>>
        +part_id : string
        +semantic_role : string
    }
    class FieldProgramOutput {
        <<enumeration>>
        TARGET_BAND_FRACTION
        NON_TARGET_FRACTION
    }
    class MagneticProgramOutput {
        <<enumeration>>
        BOUND
        FLOWTHROUGH
    }
    class FiltrationProgramOutput {
        <<enumeration>>
        FILTRATE
        RETENTATE
    }

    ProgramRegistryModule --> ProgramSpec : get_program_spec()
    ProgramRegistryModule --> ProgramOutputResolution : resolve_program_output()
    ProgramOutputResolution --> ProgramOutput : output
    ProgramSpec --> ProgramOutput : output_type
    ProgramOutput <|-- FieldProgramOutput
    ProgramOutput <|-- MagneticProgramOutput
    ProgramOutput <|-- FiltrationProgramOutput
```
