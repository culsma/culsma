# Operational comparison: task registry and decision records

Updated 12 November 2026. Retained task and mechanism evidence accompanies the [current working table](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/comparison_table_working.md). Current definitions are in the [indicator specification](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/comparison_indicator_spec.md). Superseded execution-oriented I criteria and their decision rows have been removed. Current I1–I4 engineering judgments are recorded in the [engineering audit](engineering-evidence.md), with source evidence, sampled tests, and maintenance records. Original experiment code and output files are retained.

## Scope and decision rules

The three perspectives are modeling (M), language mechanisms (L), and
implementation quality and engineering practice (I). Before/during/after execution locate their use;
L4 spans stages. Replay and version/documentation conditions (E) and validity
checks on the evaluation instrument (V) are not system capabilities.

A record consists of system/version, task/check/input/expectation, conclusion,
representation level (M only), support route, event stage, and evidence links.
Use 1 for a met check, 0 for an established scoped failure, NE for insufficient
evidence, and NA only for predefined logical inapplicability. A missing feature
is not NA. Whole-study exclusions apply to all systems. There is no total score.
A family-level result is not inferred from its successful base instance. No
family denominator or coverage percentage is reported in this revision.

For M, defined meaning is the minimum threshold; mere storage is insufficient.
Actual semantic consumption is additional evidence. This is our
operationalization of Krogstie's domain appropriateness (§3.11) and technical
interpretation (§3.7), not a scale quoted from that source. Defined RDF
vocabularies are eligible on the same terms as textual constructs. A model
need not have an implementation to meet a modeling check.

Released mechanisms, added extensions, core modifications, and external
assistance are recorded separately. Implementations through defined protocol
interfaces, including compilers, scientific models and backends, remain within
the system boundary. Bypassing the protocol in a host script does not satisfy
the corresponding system check. An observer/checker belongs to E1, not to
these support routes, unless it actually supplies missing experimental meaning.

## Task registry and selection

Selected by the manuscript authors in response to the research questions and
review requirements; no independent selector is claimed. Registry consolidated
on 11 November 2026 after the cases had been implemented and inspected.

| Task | Source and extracted requirement | Shared input/expectation | Checks and exclusions |
|---|---|---|---|
| T1 Separation, transfer, observation | [Reviewer 2](https://github.com/culsma/paper-patterns/blob/58a9031/revision/2026-11-09/reports/reviewer-2.md), numbered request 4: separate fractions in distinct wells and trace observations to fractions. The source setting is the [introductory clarification procedure](https://github.com/culsma/paper-patterns/blob/58a9031/sections/01_introduction.tex), adapted in [gfp.culs](gfp.culs) and [gfp_labop_extended.py](gfp_labop_extended.py). | 160 µL lysate; stipulated fractionation; 20 µL per well. [expected.json](expected.json) defines volumes and ancestry. A1: supernatant/lysate; A2: pellet/lysate and buffer; A3: buffer only. Signals remain missing. | M1, M2, M3 and continuity; procedure composition requires separate checks. No lysis comparison, actual fluorescence, biological yield, or hardware performance. This task keeps both products; the introductory program discards the pellet. |
| T2 Material relationships | Reviewer 2's opening discussion of protein quantity versus bead association; manuscript [magnetic capture procedure](magnetic.culs). | Post-binding 10 mg beads, 1 µg protein, 100 µL buffer; declared allocations and protein-to-bead association. [retained output and audit](results/magnetic-comparison.json). | M3 and possible future continuity. Existing Culsma program ends at returned fractions; no matched LabOP magnetic run, downstream transfer, binding-efficiency prediction, or paired free/bound contrast. |
| T3 Accounting and preconditions | T1's quantities and Reviewer 2's numbered request 2; [PCR cases](https://github.com/culsma/paper-patterns/blob/58a9031/supplementary/pcr_alternative/README.md) extracted from the manuscript PCR program. | GFP volume expectations above. PCR: valid 1 µL template request versus 2 µL from 1 µL stock; invalid request must leave the reaction empty and stock unchanged and start no thermal operations. | Quantity and material-accounting evidence; no engineering verdict follows. PCR has Culsma-only evidence. Earlier LabOP overdraw is a different workflow and is not the comparator for this test. |
| T4 Repetition and conditional control | Reviewer 2 request 2 and [PCR original](https://github.com/culsma/paper-patterns/blob/58a9031/supplementary/pcr_alternative/original.culs); data-dependent routing concept from Workflow Data Patterns. | PCR initial hold, 30 ordered three-stage cycles, final extension: [expected sequence](https://github.com/culsma/paper-patterns/blob/58a9031/supplementary/pcr_alternative/expected.json). Dynamic-value and measurement-driven cases remain to be specified jointly. | L3a fixed-instance evidence; other loop bounds and L3b/c are NE. Repetition is not evidence of runtime branching. |

These are task families for the present study, not an exhaustive taxonomy.
The literature supplies concepts, not proof that these cases are a representative
sample of laboratory practice. New cases must record source steps, selector,
date, input domain, expected behavior, excluded requirements and check mapping
before new implementation/run work. Amendments must retain the earlier rule,
reason and affected results; a failure must not cause silent removal of a case.
A second task used for V5 must differ in experimental meaning, not just names.
Human/device-output tracks and parameterized reuse/extension tasks still need
explicit shared contracts; the existing GFP run cannot fill them by implication.

## Check definitions and provenance

Use the [current indicator specification](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/comparison_indicator_spec.md) for definitions and sources. The I group consists of Testing, Implementation structure, Documentation, and Ongoing maintenance. Retained protocol runs are not judgments of these engineering criteria.

## Fixed scope for retained-instance decisions

All records below inherit the following version and evidence conditions:

- Culsma 1.0.7, commit `5364676bc2437b4981a00ce0133c730af243e469`.
- LabOP 1.0a2, commit `2e2bd88150c71a440771fd369f40295dfd622324`.
- BPL M1a/M2 source audit: public repository commit `4e505740f5025d59ba655c6c955f83876f753007` (26 June 2026); no numbered release or new run is implied.
- Software reference runs only; no physical instruments. Artifact review date:
  11 November 2026. Retained execution records are unchanged. The separately
  recorded duration-dimension probe newly runs pre-execution checks only.
- G: [common GFP result](results/comparison.json), [raw Culsma run](results/culsma/run.json),
  [Culsma output](results/culsma/output.json), [LabOP status](results/labop/run-status.json),
  [sample graph](results/labop/sample_graph.json), [readings](results/labop/readings.json).
- M: [magnetic result/audit](results/magnetic-comparison.json),
  [raw run](results/magnetic-culsma/run.json), [output](results/magnetic-culsma/output.json).
- P: [PCR summary](https://github.com/culsma/paper-patterns/blob/58a9031/supplementary/pcr_alternative/results/summary.json),
  [normal thermal trace](https://github.com/culsma/paper-patterns/blob/58a9031/supplementary/pcr_alternative/results/normal.thermal-trace.json),
  [expected sequence](https://github.com/culsma/paper-patterns/blob/58a9031/supplementary/pcr_alternative/expected.json), and [checker](https://github.com/culsma/paper-patterns/blob/58a9031/supplementary/pcr_alternative/reproduce.py).
- All rows inherit E1/E2 below. `released` means the pinned mechanisms with
  task declarations/configuration; `extension` means released LabOP plus the
  supplied [fractionation implementation](fractionation.py). It is not a core
  change. R = retained run, S = source/artifact inspection, L = literature.

| Decision unit | System and conclusion | Input/expectation and actual evidence | Representation level (M only) | Support and event stage | Evidence |
|---|---|---|---|---|---|
| M1a.containers | Culsma 1; LabOP 1; BPL 1 | Distinct declared containers/sample locations have defined references. Existing protocol witnesses and declaration-to-reference mechanisms inspected; acceptance evidence differs by system and is documented. | Defined semantics; inspected consumption paths | Released/public snapshot; source/construction review; no new runtime validation | S: [pinned mechanism audit](m1-mechanism-evidence.md); retained Culsma/LabOP witnesses, BPL upstream test-source witness |
| M1b.product-reference-mechanism | Culsma 1; LabOP 1; BPL NE | Culsma separation slots and LabOP named output parameters/pins with ObjectFlow provide distinct product-reference mechanisms. The retained custom LabOP separation uses, rather than adds, the general reference mechanism. | Defined semantics with retained witnesses | Released reference mechanisms; custom domain operation in the LabOP witness | S/R: [corrected mechanism audit](m1-mechanism-evidence.md#corrected-m1b-mechanism-judgment) |
| Library inventory: Spin signature (not M1b verdict) | Fraction outputs absent | Standard Spin declares no output parameters for supernatant/pellet. This does not negate LabOP's general product-reference mechanism. | Task-specific outputs absent from this signature | Released; primitive-definition review | S: plate_handling.py, [audit](m1-mechanism-evidence.md) |
| M1b.G.base | Culsma 1; LabOP 1 with extension; released-only LabOP NE | In G, supernatant and pellet are distinct operation products used in downstream transfers. Culsma slot references and LabOP output pins resolve to the respective collections. Original-instance identity check only; swaps/renames NE. | Defined semantics and consumed by implementation | Culsma released; LabOP extension; bindings constructed and consumed at runtime | S/R: G programs, fractionation.py, G raw events/output bindings |
| M2.G.volume | Culsma 1; LabOP 1 | G declarations encode 160 µL lysate, 100 µL buffer and 20/40 µL operations as numeric values with volume units. This does not test all dimensions or unit arithmetic. | Defined semantics; unit-bearing input structures inspected | Released declaration mechanisms in both; construction/representation | S: gfp.culs, gfp_labop_extended.py and retained protocol.ttl |
| M2.mechanism.volume | Culsma 1; LabOP 1; BPL 1 | Numeric values and units have separately recoverable representations and defined volume dimensions. Source-mechanism decision; no new BPL run or exhaustive unit coverage. | Defined semantics | Released/public snapshot; source review, retained witnesses where available | S: [M2 audit](m2-mechanism-evidence.md) |
| M3.SBOL.complex-description | LabOP 1 for the named positive representation; Culsma/BPL not tested on this example | A standard non-covalent complex contains separately referenced protein and ligand constituents and is a standard Provision resource. All references survive roundtrip. A generic functional-entity control is association-unspecified, not explicitly unbound; the original bound/free magnetic contrast remains NE. | Defined SBOL/SBO semantics | Released material-description vocabulary; model construction and roundtrip, no execution | [Modeling audit](modeling-evidence.md), [report](results/modeling/report.json) |
| L3a.P.fixed | Culsma 1; LabOP NE; BPL NE | Initial hold, 30 ordered three-stage cycles and final extension match the 92-operation expected sequence. Changed loop bounds NE. | Not applicable | Released; runtime trace | R: P summary, normal.thermal-trace.json, expected.json; checker compares the complete ordered sequence |

The X in the manuscript denotes the extended workflow supporting the observation;
it does not assert that the extension newly implements every component of that
workflow (in particular, the standard LabOP measurement primitive already exists).

Additional identity-preservation variants remain NE, including equal-attribute runtime isolation and M1b swaps/renames. Other unassessed units are NE:
M3's paired bound/free magnetic relationship contrast; M4 requirement kinds other than the recorded LabOP temporal scope; L1/L2; L3b/c and changed loop bounds;
additional task variants. Current engineering criteria are assessed separately in the engineering audit.
The magnetic association is an inspected semantic/runtime witness, not a passed
M3 contrast. The no-core-change LabOP extension is an L4 witness, not a complete
L4 evaluation. BPL M1a and M2 now have pinned source evidence; its other detailed checks remain NE.
No runtime replay, general identity-preservation guarantee or absent-feature claim follows from the M1a audit.
The default Spin/Filter inventory is scoped to those definitions; it does not
establish that every released-only LabOP representation of T1 is impossible.

## Continuity records

The primary chain is the retained G instance: distinct separation products →
separate transfers → returned observation records with recoverable origins.
For each system, every link is traced within the same run using its native
identifiers, not assembled from different programs. Culsma uses the recorded
separation source/slot contract, transfer events and observation subjects;
LabOP uses the added fraction edges, standard transfer edges and dataset
coordinates joined to terminal well states. See the concrete identifiers and
paths in [comparison.json](results/comparison.json).

| Link | Culsma | LabOP | Limit |
|---|---|---|---|
| Distinct product declaration → bound runtime products | 1, released | 1, extension | M1b.G.base; distinct output identities, no swap variant |
| Products → downstream well contents | 1, released | 1, extension plus standard transfers | Same-run G volume/ancestry evidence |
| Well contents → observations and original sources | 1, released | 1, extended workflow | All signals missing; LabOP terminal-observation mapping only |

This supports the specified software identity chain for G, not measured
fluorescence or a general continuity result across all task variants. The
released-only LabOP chain remains NE. The magnetic downstream chain is NE
because the existing program stops at fraction outputs. Correct loss or change
of a relation under declared rules may preserve semantic continuity; blindly
copying a relation that should no longer hold would not.

## E: evidence conditions and evaluation tools

**E1.** Programs, expected outcomes, checkers, raw results, reproduction scripts
and version/dependency records are supplied for G and P; M supplies Culsma
execution and a LabOP source audit. The retained author-run evidence is not
independent third-party replay. Rechecking serialized results is also not
re-executing the protocol or reproducing physical experiments.

[check.py](check.py) is an evaluation tool. It joins only recorded identifiers,
slots, events, sample-graph edges and observation coordinates. It is specific
to G: original names and the terminal-observation ordering are assumed. For
LabOP it selects the final state at each observed coordinate because no later
material change follows measurement. Renaming, repeated/interleaved readings,
and subsequent transfers need new checking rules and evidence. These limits
remain visible as NE; no generic provenance reader is claimed. The fraction
updater in fractionation.py, in contrast, creates the missing protocol-level
lineage and is correctly counted as an added system extension.

**E2.** The exact commits are above and [versions.txt](results/versions.txt)
records the environment. Culsma README/CHANGELOG and LabOP README/docs were
inspected at the pinned versions; see the [source index](framework-evidence.md).
Documentation completeness, accuracy across the entire project, maintenance
responsiveness and compatibility history were not audited. BPL declaration/reference mechanisms and an upstream protocol/test witness were
inspected for M1a; no BPL replay was performed. Missing evidence limits the specific
claim; it does not by itself turn a capability into 0.

## V: validity of the checks, not a system score

V1/V6 language and architecture neutrality have been reviewed at the rule level:
no required keyword, class, file format or internal storage shape; the same
protocol-contract boundary applies to every system. This is a design review,
not proof of neutrality. V2 renaming, V3 parameter variation, V4 minimal
contrasts and V5 cross-task instantiation are not comprehensively executed.
The GFP blank and PCR single-fault contrast provide local evidence only.
Two genuinely different tasks per predicate are a proposed stress check, not
a literature-prescribed threshold or proof of generality. No emphasis ranking
or exhaustive capability distribution should be inferred from the sparse
retained-instance decisions.
