# Sources for the concise language and implementation examples

12 November 2026. The manuscript table now shows a short explanation and one
code/result example where evidence is available. This file identifies the
sources behind its L/I/D cells. Source inspection is not reported as a new
execution test. “Available” describes the inspected mechanism; a remaining
unassessed check is stated in the same cell.

The Culsma snapshot is `5364676bc2437b4981a00ce0133c730af243e469` (1.0.7),
and the LabOP snapshot is `2e2bd88150c71a440771fd369f40295dfd622324` (1.0a2).
M evidence is in [the modeling audit](modeling-evidence.md). BPL remains on
public snapshot `4e505740`, with only M1a and M2 assessed here.

| Criterion | Culsma example source | LabOP example source | Evidence scope |
|---|---|---|---|
| L1 | `parser/ast_nodes.py`, `ProtocolDecl.params`; `pipeline/component_expander.py`; [WashCells definition](https://github.com/culsma/paper-patterns/blob/58a9031/supplementary/modeling_level_comparison/flow.culs). | `uml/activity.py`, `input_value`; `uml/behavior.py`, parameter definitions. | Parameter mechanisms inspected; no new paired reuse run. The abbreviated `sub.input_value("sample", SAMPLE)` uses an existing protocol and the SampleArray type URI. |
| L2 | Same compiler expansion path; `let washed_cells = WashCells(...)` and `return sample` in the flow example. | `test/test_subprotocols.py` invokes subprotocols; `test/test_protocol_outputs.py` designates protocol outputs. | Existing construction/call/output mechanisms; the complete cross-procedure output-to-input contrast remains unassessed. |
| L3 | [PCR source](https://github.com/culsma/paper-patterns/blob/58a9031/supplementary/pcr_alternative/normal.culs) and its retained 92-operation trace. | `test/test_decision_nodes.py`, including `protocol.make_decision_node(...)`; the code wires a measurement output to a decision input in its calibration case. | Culsma fixed repetition is run evidence. LabOP decision-node source was inspected, not rerun here; no general absence of branching is asserted. |
| L4 | No newly implemented capability/regression check. | [ClarifyLysate and FractionationUpdater](fractionation.py), with the retained GFP run. | An extension without core changes exists; complete extension/regression checks remain unassessed. |
| I1 | [Duration-dimension probe](check_duration_units.py). | Same matched parameter fault and [positive diagnostic probes](check_labop_diagnostics.py). | Existing run records; results are specific to each fault and entry point. |
| I2 | [GFP transfer results](results/comparison.json) and [magnetic component/aggregate results](results/magnetic-comparison.json). | GFP results with the supplied separation updater. | 160 uL minus a 20 uL transfer leaves 140 uL; the displayed subtraction summarizes the state transition, rather than quoting a program expression. The Culsma magnetic aggregate failure remains explicit. |
| I3 | [PCR overdraw source](https://github.com/culsma/paper-patterns/blob/58a9031/supplementary/pcr_alternative/overdraw.culs) and retained rejection record. | No matched overdraw task. | Culsma rejects before transfer/thermal effects; no LabOP comparative verdict is added. |
| I4 | `driver/human_driver/run_sheet.py`, `build_run_sheet(projections)`. | `test/test_protocol_outputs.py`, `labop_convert.MarkdownSpecialization(...)`; Markdown specialization implementation. | Generator entry points inspected. No new complete instruction-fidelity check. |
| I5 | `driver/robot_driver/backend_emitter.py`, `RobotBackendEmitter.emit`. | `labop_convert/opentrons/opentrons_specialization.py`, transfer emission around lines 423/493. | Device mapping/emission code exists. Neither a matched device-command audit nor hardware execution is claimed. |
| I6 | GFP program and [ancestry record](results/comparison.json). | Same GFP record, reconstructed from existing terminal sample/provenance records. | The retained three-well task only; the LabOP mapping assumes terminal observations. |
| I7 | GFP result fluorescence is null. | `results/labop/readings.json` has three null signal values. | Missingness, not a complete classification of declared/derived/measured origins. |
| I8 | Retained JSON output. | `gfp_labop.py`, `document.write(..., sbol3.TURTLE)`; [selected M-field roundtrips](results/modeling/report.json). | Export examples exist; full independent-reader recovery remains unassessed. Reading LabOP RDF with the same library is not called an independent-reader test. |
| D1 | GFP product reference, transfer and observation records. | GFP output pin, transfer and terminal readout records. | Partial runtime-chain evidence; not a completed source-to-model-to-plan-to-result preservation check. |

The Culsma M4 table cell uses `with constraint(high_precision, low_carryover)`
from the pinned PCR program. The frozen source's
`pipeline/validate/statement_contracts.py` defines those requirements and
`pipeline/plan/gates.py` carries scoped requirements into plan gates.
This keeps the displayed table on Culsma 1.0.7; the development-only dropwise
example remains a separate candidate rather than being silently assigned to
the frozen version. Representing these requirements does not establish their
physical enforcement or a numeric precision tolerance.

The full source snapshots are prepared under `benchmarks/local-results/comparison-runtime/` by
[reproduce.sh](reproduce.sh). Source-inspected upstream tests establish what
the implementation attempts and exposes; their mere presence is not a test
pass in this comparison.
