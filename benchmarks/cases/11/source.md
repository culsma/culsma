# 2.2. cDNA Template Switch

Source: Parse Biosciences, *Evercode WT Mega v3 User Manual*, version 1.5,
November 2024, document UMWT3500, Section 2.2, printed pages 41-43.
[Original manual](https://support.parsebiosciences.com/hc/en-us/article_attachments/31841833600532).

Original section and procedure numbers are retained below. Parenthesized S labels
are benchmark subdivisions; multiple S labels can refer to one original step.
Tables and instructions are formatted for reading, with program choices separated
at the end. Preparation steps outside the numbered S sequence remain included.

After an additional wash, the Template Switch Master Mix is added to the captured cDNA. The template switch reaction adds a 5-prime adapter to the cDNA.

#### Original step 1: Reagents

| Item | Source | Quantity | Handling and storage |
| --- | --- | --- | --- |
| Wash Buffer 3 | -20C Reagents | 1 | Thaw and store at room temperature. Mix by inverting 3x. |
| Template Switch Buffer | -20C Reagents | 1 | Thaw at room temperature, then place on ice. Mix by inverting 3x. Briefly centrifuge before use. |
| Template Switch Primer | -20C Reagents | 1 | Thaw at room temperature, then place on ice. Mix by inverting 3x. Briefly centrifuge before use. |
| Template Switch Enzyme | -20C Reagents | 1 | Keep on ice. Briefly centrifuge before use. |

Ensure there is no precipitate in the Template Switch Buffer before proceeding.

#### Original step 2: Template Switch Master Mix

Prepare the Template Switch Master Mix in a new 2 mL tube according to the number of sublibraries being processed. Mix by pipetting 10x and store on ice.

| Number of samples | Template Switch Buffer | Template Switch Primer | Template Switch Enzyme | Total |
| --- | --- | --- | --- | --- |
| 1 | 101.75 uL | 2.75 uL | 5.5 uL | 110 uL |
| 16 | 1628 uL | 44 uL | 88 uL | 1760 uL |

## Procedure (original numbering)

**3. (S1, S2)** Place each tube of captured cDNA from Section 2.1 on the high position of the magnetic rack.

Incubate until the solution clears, about 2 minutes.

**4. (S3)** While still on the magnetic rack, remove and discard the supernatant.

**5. (S4)** While still on the magnetic rack, add 125 uL of Wash Buffer 3 to each tube. Do not discard the Wash Buffer 3 as it will be used in another step.

**6. (S5)** Incubate for 1 minute at room temperature.

**7. (S6)** While still on the magnetic rack, remove and discard Wash Buffer 3.

**8. (S7, S8)** Remove the tube(s) from the magnetic rack.

Fully resuspend each bead pellet with 100 uL of the Template Switch Master Mix. Because the mix is viscous, full resuspension may take time.

**9. (S9)** Briefly centrifuge without letting beads collect at the bottom of the tube(s).

**10. (S10)** Incubate for 30 minutes at room temperature.

**11. (S11)** Fully resuspend each bead pellet by mixing 5x with a P200 set to 75 uL.

**12. (S12)** Place the tube(s) into a thermocycler and run the Template Switch program.

| Run time | Lid temperature | Sample volume |
| --- | --- | --- |
| 60 min | 70C | 100 uL |

| Step | Time | Temperature |
| --- | --- | --- |
| 1 | 60 min | 42C |
| 2 | Hold | 4C |

**13. (S13)** Proceed immediately to Section 2.3, or proceed to original step 14 below for storage before cDNA amplification.

**14. (S14)** For optional storage, place the tube(s) on the high position of the magnetic rack and incubate until the solution clears, about 2 minutes. Beads may need to be resuspended if settled.

**15. (S15)** While still on the magnetic rack, remove and discard the supernatant.

**16. (S16, S17)** Remove the tube(s) from the magnetic rack.

Fully resuspend each bead pellet with 125 uL Wash Buffer 2.

**Safe stopping point after step 16 (S18)** Template-switched cDNA can be stored at 4C for up to 18 hours. Do not freeze.

## Benchmark mapping and execution choices (not original instructions)

The standalone program supplies captured cDNA from Section 2.1. The declared
0.4mg bead and 0.1ug cDNA inputs are benchmark assumptions, not measured yields.
The DNA keeps its `CAPTURED_CDNA` identity. `TemplateSwitchWorkflowStatus` records
the source section, material code and completed processing stage; completing the
thermal program does not establish biochemical conversion or a new DNA identity.
Case12 remains an independent input boundary rather than an automatic handoff.

The WB3 reminder above follows the manual. The program separately interprets it
as retaining unused WB3 reagent for the later step; the WB3 wash in the sample
is still discarded at original step 7. This interpretation is not inserted into
the original reminder as an invented “until directed” instruction.

| Reviewed requirement | Executable treatment / boundary |
| --- | --- |
| Prepared reagents and cold handling | Inputs are supplied thawed. A readout confirms WB3 at room temperature and the buffer, primer, enzyme and prepared master mix on ice. The three specified inversions and brief reagent spins are executable; the source gives no thaw or spin durations. Ice is modeled at 0C, refrigerated spins at 4C, and room temperature at 25C. |
| Brief reagent centrifugation | Three standalone spins at authored 3000g for 5s retain all reagent in the same tube. No fraction is withdrawn. |
| Buffer precipitate | `TemplateSwitchBufferPrecipitation` must report no precipitate before making master mix. The source gives no recovery recipe, so a failed check stops dependent operations for intervention. |
| Magnetic clearing | Initial clearing, WB3 wash removal and storage clearing each require `TemplateSwitchSupernatantClarity`. An authored extra one-minute magnetic wait and recheck is allowed; persistent cloudiness prevents discard. The WB3 wash check is an additional execution safeguard rather than an additional source instruction. |
| Full resuspension | Four `TemplateSwitchBeadSuspension` checks cover master-mix resuspension, post-room-temperature mixing, pre-storage separation and WB2 resuspension. A failed check triggers one authored ten-stroke mix and recheck; continued failure stops dependent steps. Stroke volumes are 80, 75, 80 and 100uL, respectively. |
| Sample brief centrifugation | S9 uses authored 100g for 8s with all material in the supernatant and `keep_source = "supernatant"`. Explicit relationships release beads from field retention while retaining cDNA as bead-bound. The empty pellet output is not withdrawn. These settings and relationships are authored assumptions, not experimental validation. |
| Rack position and thermal lid | Explicit confirmation records gate high-position magnetic handling, removal from the rack, and the 70C thermocycler lid with the 100uL sample setting. No unsupported lid parameter is added to `thermal_program`. |
| Common 4C Hold | The thermal program ends with 4C Hold before either immediate continuation or optional storage. The finite ten-minute hold is an author choice, not a source-specified dwell time. |
| Storage | The storage branch includes magnetic cleanup and 125uL WB2, followed by 4C for the source maximum of 18 hours. A confirmation preserves the “do not freeze” requirement. |
| Output accounting | Initial magnetic separation operates in the original physical tube, with capacity aligned to the source 0.2mL specification. Explicit bound fates and existing material rules preserve the cDNA-bead relation. The return points to that allocated tube and is included by the existing final-material-record extractor; no change to metric counting rules was needed. |
| Volume projection | Liquid recipe volumes remain 100/125uL. Runtime totals remain 100.4001/125.4001uL because declared masses also contribute to the current volume projection. Recipes and input masses are not adjusted to force integer totals. |

Self-transfers encode pipetting actions; they are not a physical suspension model.
The recorded suspension observations govern continuation. In particular, the
storage output can retain the runtime `field_retained` label after its final
pipette mix even though the suspension check passes; this remains a model boundary.

The default invocation uses explicitly declared passing fixture inputs. Set
`use_fixture_inputs = false` to consume driver/operator results without fixture
overrides. `fixture_precipitate_present`, `fixture_unclear_check` (1-3),
`fixture_clear_after_retry`, `fixture_unsettled_check` (1-4), and
`fixture_suspended_after_retry` exercise failed checks and recovery. Preparation
and equipment confirmations use `fixture_reagents_ready` and
`fixture_equipment_ready`. Status flags distinguish completed thermal processing,
readiness for amplification, successful storage, and a need for intervention.

The review and step-map notes were updated on 2026-09-14; S1-S18 are retained.
The three checked-in metric JSON files and archived runtime evidence describe
the earlier program. Regeneration remains pending in the matching locked
environment under [PM #115](https://github.com/culsma/culsma-pm/issues/115).
The local editable distribution reports 0.1.0, whereas the benchmark lock requires
1.0.7rc1. Local source tests are not published as pinned benchmark evidence.
