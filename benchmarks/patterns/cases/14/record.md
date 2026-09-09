# Translation Record

- Status: validated current case
- Coverage: magnetic-bead immunoprecipitation with Western blot readout
- Source class: independently authored stress workflow
- Runtime result: 265/265 generated active steps completed with no diagnostics
- Reviewed date: 2026-09-02

## Step Alignment

| Source step | Culsma representation | Coverage |
|---|---|---|
| S1 prepare input and antibody-conjugated beads | capture-antibody binding subprotocol and typed material transition | current |
| S2 add lysate and binding buffer | declared container transfers | current |
| S3 rotate at 4 C | cold environment and agitation | current |
| S4 collect flowthrough and retain captured beads | magnetic separation, explicit component fates, and typed transition | current |
| S5 wash bead-bound target three times | scheduled magnetic washes with explicit component routing | current |
| S6 denature and elute the target | heated hold, magnetic separation, and typed release transition | current |
| S7 prepare input, flowthrough, and eluate samples | tube allocation, transfers, heat, and separation | current |
| S8 load lanes and run electrophoresis | wells, field separation, and explicit component fates | current |
| S9 activate PVDF and transfer proteins | membrane preparation, field separation, and explicit component fates | current |
| S10 block, probe, and wash the membrane | scheduled transfers, environmental conditions, and dark protection | current |
| S11 acquire the Western blot readout | structured data schema and image acquisition | current |

## Modeling Note

The current program makes bead binding, capture, washing, elution, electrophoresis, and membrane-transfer relationships explicit through composed core operations and typed material transitions. It therefore records the intended material routing without requiring dedicated immunoprecipitation or Western blot primitives.

## Scope

Band identity, enrichment ratio, transfer efficiency, and quality-control interpretation are structured observations or downstream analysis fields. The runtime does not infer experimental success from those fields.
