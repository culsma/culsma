# Evidence index for the lifecycle comparison

Source index, 11 November 2026. The active manuscript uses M1–M4, L1–L4
and I1–I8. See [the current task registry and decision records](checklist-evidence.md)
for operational predicates, scoped outcomes and E/V evidence conditions.
The F1–F10 derivation and earlier A/B/C probes below are retained as historical
source mappings, not current capability scores. They preserve inspected
mechanisms that may still be NE under the stricter operational checks.

## Evidence and versions

- **R**: a retained software run, not physical laboratory execution.
- **S**: inspection of a pinned source implementation; not an executed test.
- **L**: a published description; not independently reproduced behavior.
- **Not evaluated**: the corresponding capability has not been established
  from the reviewed evidence. This is not a negative capability judgment.

Culsma source: version 1.0.7, commit
`5364676bc2437b4981a00ce0133c730af243e469`.
LabOP source: version 1.0a2, commit
`2e2bd88150c71a440771fd369f40295dfd622324`.
Source paths below are relative to those repository roots. Local source
archives used for inspection are under `benchmarks/local-results/comparison-runtime/` and can be
reconstructed using the reproduction instructions; they are not new sources.

Retained run evidence:

- **GFP**: [program](gfp.culs), [LabOP program](gfp_labop.py),
  [extension](fractionation.py), [common results](results/comparison.json),
  and raw records under `results/culsma/` and `results/labop/`.
- **Magnetic**: [program](magnetic.culs),
  [source audit and checked results](results/magnetic-comparison.json),
  and raw records under `results/magnetic-culsma/`.
- **PCR**: [controlled-variant results](https://github.com/culsma/paper-patterns/blob/58a9031/supplementary/pcr_alternative/results/summary.json).
- **Pilot**: [earlier transfer results](https://github.com/culsma/paper-patterns/blob/58a9031/revision/2026-11-09/labop-comparison/results/comparison.json).
  This pilot uses a handoff-based representation of fractions and is not the
  later GFP extension. Its overdraw run records −20 µL remaining supernatant
  with no execution issue. It does not establish general LabOP error coverage.

Literature:

- **LabOP**: Bartley et al. (2023),
  [Building an Open Representation for Biological Protocols](https://jakebeal.github.io/Publications/JETC23-LabOP.pdf).
  §2: design requirements; §3.1: OWL/RDF representation; §3.2: UML token-flow
  semantics; §5.3: extension through libraries while retaining the UML core.
- **BPL**: Song et al. (2026),
  [Towards autonomous biology](https://www.biorxiv.org/content/10.64898/2026.05.05.720956v1).
  Only the abstract has been verified for this working table. It supports
  biology-native types, physical units/forms, compiler-tracked container state,
  compiler diagnostics in translation repair, and reported manual/liquid-handler
  execution. It does not establish the detailed mechanisms in the unfilled rows.
- **Culsma formal analysis**: the earlier preprint already cited by the
  manuscript, DOI [10.64898/2026.05.07.723509](https://doi.org/10.64898/2026.05.07.723509).
  A9 preserves the manuscript's bounded literature claim for covered constructs;
  it does not assert a new proof audit or coverage of every current extension.

## Historical F1–F10 derivation and source mapping

The objective is to compare experimental representation, its implemented
interpretation/execution, and the inspectable support for verification and
maintenance. The three perspectives are author-defined organizational views,
not a claim that a published standard consists of exactly three categories.
The stages locate primary use; F3 checks can run during execution and F8–F10
span every stage. There is no total score or claim of a uniquely minimal set.

The selection procedure follows [GQM](https://www.cs.umd.edu/~mvz/handouts/gqm.pdf):
state the comparison goal, derive questions, and identify evidence. The table
is a qualitative application of this logic, not a new numerical GQM metric.

| Historical criterion | Source concept and exact location | Operational question and boundary | Earlier evidence probes |
| --- | --- | --- | --- |
| F1 Experimental information representation | [Krogstie et al. 1995](https://folk.idi.ntnu.no/krogstie/publications/1995/ISCO3/fulltext.pdf), §3.11 domain appropriateness; [EXACT2](https://doi.org/10.1186/1471-2105-15-S14-S5), ontology-design discussion and Figure 1: material entities, action descriptors and conditions. | Which materials, dimensioned quantities, states, products, relationships, and procedural requirements can be represented? This list is our laboratory operationalization, not a verbatim checklist from either source. Representation alone does not establish automatic state updates. | A1–A4 representation; A8 describes the representation/interface rather than scoring it. |
| F2 Workflow composition and reuse | [Workflow Data Patterns](https://doi.org/10.1007/11568322_23); extended report at https://www.vdaalst.com/publications/p220.pdf, §2.1, Block Data pattern 2, data interaction/transfer and routing patterns; LabOP §3.2 and §5.3. | Can existing procedures be parameterized, composed, and connected by control/data flows? Record source-file organization and data-dependent control separately. This is reuse of existing definitions, not adding new semantics. | A5, B5. |
| F3 Validation and diagnostics | Krogstie §3.4–3.5: syntactic/semantic quality and checking; LabOP §2: verification of completeness/coherence. | Which rule violations are detected, at what stage, with what diagnostic and effect on execution? Requirement applicability, stock/capacity checks, and device-support rejection are subchecks. Detection in a case does not prove complete semantic validity. | A4 applicability, A6, B1 rejection, B2, B4 capability rejection. |
| F4 Computable interpretation | Krogstie §3.7 and §3.11: interpretation by technical actors, formality and executability. | What state does the implementation derive from the declared operation semantics? Check quantities and relationships against explicit expectations. This is our operationalization of technical interpretation; the source does not prescribe a material-accounting benchmark. Formal definitions and implementation results remain separate evidence. | A9, B1 accounting, C1–C2. |
| F5 Human and device execution | LabOP §2, §5.1–5.2: human/machine execution and mapping between laboratory environments. | What instruction-generation or device-mapping path is implemented? Source support is distinct from physical execution; hardware rejection belongs to F3 and is currently untested here. | B3, B4 mapping. |
| F6 Result records and provenance | [PROV-DM](https://www.w3.org/TR/2013/REC-prov-dm-20130430/), §2.1 and §5.1–5.2: entities, activities, usage, generation, derivation. | Can recorded observations and derived states be traced to inputs and activities? Source-of-value labels are a case-specific subcheck. PROV activity association is not a protein–bead relationship, and this is not a PROV-conformance test. | C3–C4; C2 association calculation remains F4. |
| F7 Representation interchange | LabOP §3.1: common linked-data representation and ontology interoperability. | Which representation and schema enable another tool to interpret records? Format availability is recorded; semantic round trips are not tested. JSON versus RDF is not itself a score. | C5; representation background from A8. |
| F8 Extension and modularity | LabOP §5.3: library extensions preserve the UML core; [Wilson et al. 2014](https://doi.org/10.1371/journal.pbio.1001745), Box 1 §4 and the corresponding modularization discussion. | What must change to introduce new experimental meaning or a backend: configuration, library, scientific model, adapter, or core? Report actual changes; neither primitive count nor unchanged core proves lower maintenance cost. | A7; model/driver interfaces. |
| F9 Verification and replay support | Wilson et al., Box 1 §§2, 3, 5: automation, version control, assertions and automated tests. | Are inputs, expected outcomes, checking procedures and environment information supplied for repeatable verification? Replay is our operational extension of these practices, not a certified reproducibility badge. | New engineering view of existing GFP/PCR checkers, expected.json, reproduce.sh, dependency locks, versions and raw records. |
| F10 Documentation and version evidence | Wilson et al., Box 1 §§3, 7, 8: version control, interface/design documentation, collaboration and issue tracking. | What documentation and revision/support evidence is available in the inspected snapshot? Presence does not establish documentation accuracy or responsiveness. | New source inspection described below; maintenance outcomes remain unassessed. |

### Additional engineering inspection

For F9, the study supplies both GFP programs, the LabOP fractionation extension,
`expected.json`, `check.py`, `reproduce.sh`, `labop-requirements.txt`, and
`results/versions.txt`, together with raw records. This is a common comparison
package created for the study, not an assertion that the upstream projects
have equivalent test coverage. The PCR case supplies an additional controlled
failure check for Culsma only. No independent replay was performed in this edit.

For F10, Culsma's README and CHANGELOG were read with `git show` at commit
`5364676bc2437b4981a00ce0133c730af243e469`; the runtime-only archive under
`benchmarks/local-results/comparison-runtime/culsma-source` does not contain those root documents.
The README includes installation, usage and reference pointers; the changelog
records versioned changes. Their completeness and accuracy were not audited.
For LabOP, the pinned `README.md` contains installation/API/validation/execution
instructions. `docs/index.md` and `docs/how-to-guides.md` were inspected; the
former is minimal and the latter empty in the snapshot. Thus the table records
presence of documentation sources, not comprehensive documentation quality.
No issue-response, release-frequency, compatibility-history, or long-term
maintenance comparison was performed for either project. BPL artifacts were
not inspected.

### Coverage and exclusions

Each criterion answers a different decision: describe an experiment (F1),
compose existing methods (F2), detect violations (F3), calculate consequences
(F4), perform instructions (F5), trace results (F6), exchange representations
(F7), add capabilities (F8), check/replay an implementation (F9), and inspect
its documentation/version support (F10). These distinctions justify retaining
the rows for this goal; they do not establish mathematical independence or
universal necessity. Failure to evaluate a row remains visible rather than
being used to remove a competitor's potentially useful capability.

Performance, security, usability studies, physical reliability, and long-term
maintenance outcomes are not covered. The framework therefore must not be
presented as an exhaustive software-product-quality evaluation. The old
19 questions all map above, but that mapping demonstrates continuity of this
study's requirements, not completeness for all laboratory applications.

## Earlier questions retained as evidence probes

| ID | Culsma | LabOP | BPL |
| --- | --- | --- | --- |
| A1 | GFP and magnetic input declarations/results; typed component quantities and attributes. | GFP uses `sbol3.Component`, `SampleArray`, and `sbol3.Measure`; physical-form checks not assessed. | Abstract: types, units, physical forms, compiler-tracked containers. |
| A2 | Both separation programs and resolved output references in retained records. | `fractionation.py` supplies two outputs and binding; magnetic audit lists bundled Spin/Filter parameters. This is a version-specific library gap. | Not evaluated. |
| A3 | Magnetic `transitions` declaration and returned `bead_bound` association targeting the bead component. | Paper §3.1 supports extensible relations; audited default handlers lack the association update. Absence of an update is not inability to declare a relationship. | Not evaluated. |
| A4 | `src/culsma/pipeline/validate/statement_contracts.py`: requirement registry, scope validation, operation-family checks; e.g. `SEM_CONSTRAINT_ACTION_FAMILY_MISMATCH`. | Not evaluated for equivalent scoped requirements. | Not evaluated. |
| A5 | `src/culsma/parser/culsma.lark`: protocol parameters, default values, source inclusion; this entry records source support, not a new cross-file run. | `uml/behavior.py:add_parameter`, `uml/activity.py:input_value`, `call_behavior`; cross-file composition not evaluated. | Not evaluated. |
| A6 | `src/culsma/pipeline/validate/`, `typecheck/`, and scope analysis; PCR records validation/type checking separately from runtime failure. | `gfp_labop.py` calls `document.validate()` before execution; clean validation is retained in `results/labop/run-status.json`. This does not measure material-error detection coverage. | Abstract: physical, dimensional, and state checks by the compiler. |
| A7 | GFP and magnetic use existing `sep` with differing method configuration/material rules; magnetic adds no runtime implementation. | `fractionation.py` adds primitive definition, output binding and provenance updater through existing APIs. The core is unchanged; this does not prove that every new technique needs a new primitive. | Not evaluated. |
| A8 | Dedicated grammar and `src/culsma/cli.py` processing pipeline. | Paper §3.1–3.2, `labop/protocol.py`, and retained protocol Turtle: representation and Python interface are distinct. | Abstract identifies a domain-specific language; other interface details not assessed. |
| A9 | Earlier formal-analysis citation, restricted to covered constructs. | Paper §3.2 for workflow semantics; primitive output/provenance handlers and the GFP extension for domain-specific computations. No claim of equivalent whole-language proofs. | Not evaluated. |
| B1 | `src/culsma/runtime/material/` checks; PCR overdraw records failure before the 92 thermal operations. | Earlier pilot overdraw only; capacity rejection not evaluated. This is not the matched GFP implementation or a matched error study. | Abstract reports pre-execution checks; runtime behavior not assessed. |
| B2 | PCR `MAT_INSUFFICIENT_VOLUME`, source line 14/column 3, and fail-fast/skipped-step records. | Source-location diagnostic quality not evaluated. | Abstract: compiler diagnostics drive repair; source locations not established. |
| B3 | Operator-instruction export not evaluated in these cases. | `labop_convert/markdown/markdown_specialization.py`: available specialization, not a newly generated or comprehension-tested protocol. | Abstract reports manual execution; its instruction-generation mechanism is not established. |
| B4 | `src/culsma/driver/base.py`, `framework/driver.py`, and `framework/capability.py`: configured policies return unsupported-requirement/option results. Hardware rejection not tested. | `labop_convert/opentrons/` and `labop_convert/autoprotocol/`: specialization source; device rejection not tested. | Abstract reports manual and liquid-handler-assisted contexts; rejection behavior not established. |
| B5 | `src/culsma/runtime/gates.py`, runtime condition handling in `steps.py`, and protocol-call grammar. No measurement-driven workflow run claimed. | `labop/protocol.py:make_decision_node`, `uml/decision_node.py` guarded token routing, and behavior calls. No measurement-driven workflow run claimed. | Not evaluated. |
| C1 | Magnetic dimensioned component ledger and GFP cellular propagation. Magnetic aggregate volume/mass projections are erroneous and explicitly excluded from verified quantities. | GFP graph tracks liquid volume and ancestry; cellular count is input metadata, not propagated count. This is a claim about this graph, not all possible LabOP implementations. | Not evaluated for post-execution quantities. |
| C2 | Magnetic output association resolves to the bead component. No downstream transfer in that case. | Source audit finds no bundled association updater; no extended magnetic implementation was run. | Not evaluated. |
| C3 | Common checker verifies all three GFP well/fraction/source ancestry paths. | Same checks pass with the extension, followed by standard transfer handlers. | Not evaluated. |
| C4 | Magnetic fields distinguish `author_transition` and `scientific_model_provider`; GFP observation signals remain empty. This is not a claim that every numeric field has a complete epistemic classification. | Retained execution/dataset records and missing signals; no classification of assumed versus calculated values assessed. | Not evaluated. |
| C5 | JSON run/output records; `src/culsma/runtime/report.py` schema. JSON syntax alone is not semantic interoperability. | Retained `protocol.ttl`, `execution.ttl`, and separate dataset JSON exports. No cross-tool round-trip benchmark claimed. | Not evaluated. |

## Interpretation boundaries

The earlier lifecycle arrangement, ten F criteria, and retained concrete questions are
the authors' synthesis and operationalization, informed by prior conceptual-model quality and protocol
requirements literature. They should not be described as a verbatim standard.
No totals or ranking are calculated. Equivalent final outcomes do not imply
identical support mechanisms, and a library extension is not a core-language
change. Cases illustrate reviewer-relevant differences after the comparison;
they do not establish exhaustive coverage of all laboratory protocols.
