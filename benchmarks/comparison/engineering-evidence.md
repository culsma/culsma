# I1–I4: implementation quality and engineering practice

Assessed 12 November 2026. These are engineering checks, not a repeat of M/L
functional-conformance checks. No physical devices were used. No upstream
implementation or test assertions were changed.

## Scope and decision rules

I1–I3 inspect the same source snapshots as the working comparison table:
Culsma `5364676bc2437b4981a00ce0133c730af243e469` (1.0.7), LabOP
`2e2bd88150c71a440771fd369f40295dfd622324` (package version 1.0a2), and BPL
`4e505740f5025d59ba655c6c955f83876f753007` (package version 2.4.0).
LabOP's package version does not imply that its January 2024 commit is identical
to the October 2022 release tag. Archives are in [sources](sources/manifest.json).

- **I1 Testing:** tests contain concrete assertions or documented expected
  outcomes. Automation and CI are not required. A sample run checks executability;
  neither its size nor its success establishes comprehensive coverage.
- **I2 Implementation structure:** a structural explanation identifies component
  responsibilities, and sampled source paths and interfaces substantiate that
  organization. This is not a judgment that all components work correctly.
- **I3 Documentation:** installation/dependency guidance, usage examples, and
  core reference material are supplied for the inspected implementation. Yes
  means these categories are present with concrete content, not that every API,
  example, public website, or documentation claim has been validated.
- **I4 Ongoing maintenance:** inspect the same window for all projects,
  **2025-11-12 00:00 UTC to 2026-11-12 00:00 UTC (exclusive)**. Record dated
  maintenance changes and defect handling, releases, and issue/PR activity.
  Yes here means observed maintenance, including corrective work, during that
  window. No means no such activity in the inspected public channels, not proof
  of abandonment or absence of private work. No commit-count ranking is used.
  Empty issue lists do not by themselves cause No; corrective commits can
  establish defect handling. Support responsiveness is not inferred from fixes.

The I4 window and evidence rule are this study's operationalization, not an SSI
or JOSS threshold. I4 is project-level evidence as of the cutoff; newer releases
do not change the pinned versions used for M/L or I1–I3.

## I1 — tests and a bounded execution sample

| System | Verdict | Inspected test and actual result |
|---|---|---|
| Culsma | Yes | `tests/test_pipeline_scope.py` asserts local/repeat binding and assignment effects. Unchanged upstream module: **2 passed**. |
| LabOP | Yes | `test/test_validation.py` asserts precise validation warnings/errors for activity flows. Unchanged upstream module: **2 passed**, with 30 dependency deprecation warnings. |
| BPL | Yes | `tests/phase2_state/test_state_model.py` asserts values, units, uncertainty and state-history behavior. Unchanged upstream module: **69 passed**. |

The original archives contain 57, 18, and 46 `test_*.py` files respectively.
The same archives contain **1,178, 45, and 1,261 static test definitions** respectively. The count includes module/class-level functions or methods named `test_*` in these files. Parameterization is not expanded and skipped definitions are counted; neither count is an executed-case count or coverage measure. The files include parser/compiler/runtime/material checks (Culsma), model/validation/activity/sample/example checks (LabOP), and phase-organized parser/state/lowering/scheduler/backend/audit checks (BPL).

[Counting script](count_engineering_tests.py) and [per-file definitions with names and line numbers](results/engineering/test-inventory.json) make these totals reproducible. For example, Culsma has 119 definitions in `test_parser.py` and 148 in `test_kernel_runtime.py`; LabOP has 6 in `test_bottom_up_protocol_build.py`; BPL has 42 in `test_intent_lowering.py` and 94 in `test_audit.py`. These inventory numbers do not establish that those tests check every previously observed failure path. Actual inspected
files, hashes, and inventory are in [source-inspection.json](results/engineering/source-inspection.json).
The selected comparison environments initially lacked pytest; pytest 8.4.2 was
installed before the runs. This setup issue is not a software failure verdict.

[Runner](check_engineering_tests.py), [commands and output](results/engineering/test-runs.json),
[Culsma log](results/engineering/culsma-test.txt),
[LabOP log](results/engineering/labop-test.txt),
[BPL log](results/engineering/bpl-test.txt).

Replay after preparing the existing pinned source/environment directories:

```sh
python benchmarks/comparison/check_engineering_tests.py
```

## I2 — implementation structure

All three receive **Yes** for the inspected component organization. In plain terms, this asks whether the code is divided into components with explained jobs and identifiable source locations. It does not measure semantic correctness, coupling, complexity, or architecture quality by counting directories.

- **Culsma:** the pinned README maps parser, pipeline, runtime, driver, and
  standard library to source directories. `docs/README.md` indexes component
  diagrams; `docs/architecture/pipeline/scope_module_diagrams.md` explains scope
  analysis and downstream consumption. `src/culsma/pipeline/scope/__init__.py`
  exposes the separately organized analysis, model, and query modules. The
  [pinned documentation and sampled source](sources/engineering/culsma) are retained.
- **LabOP:** README's API and Protocol Execution sections describe OWL-generated
  model classes and `ExecutionEngine`/`BehaviorSpecialization`. Source separates
  `uml/`, `labop/`, `labop/execution/`, and `labop_convert/`; the execution engine
  imports model/execution-context components and uses the specialization boundary.
  [Pinned README](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/README.md),
  [engine](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop/execution/execution_engine.py).
- **BPL:** README's Architecture/Repository Layout and `docs/BPL_STRUCTURE.md`
  explain parser, AST, lowering, scheduling, and runtime responsibilities. Those
  directories and `bpl/orchestrator.py` exist in the snapshot. Some structural
  documentation also lists unpublished directories and semantic capabilities
  that the earlier M/L audits did not establish; this Yes concerns identifiable
  core component organization, not those broader claims.
  [Pinned README](https://gitlab.com/bota-biosciences-public/bpl-code/-/blob/4e505740f5025d59ba655c6c955f83876f753007/README.md).

## I3 — documentation

All three receive **Yes** for provision of the three documentation categories,
with the following limits recorded explicitly.

- **Culsma:** pinned README provides installation, a small protocol and CLI
  commands; `pyproject.toml` declares Python/runtime requirements. Companion
  reference commit `856d7fb7ca4e9b300f5af8e1a2ad3fb2cc10b838` is the 21 September
  2026 change aligning accepted 1.0.7 contracts; sampled chapters cover operation
  contracts and units. [Reference extracts](sources/engineering/culsma-reference)
  are retained from the local companion repository. Its README still labels an
  older published snapshot as aligned with 1.0.6, and the implementation README
  retains a v1.0.4 installation example. Public reference-site/repository access
  was not confirmed in this audit. Thus this is documentation-provision evidence,
  not a claim of fully synchronized release metadata or public-site availability.
- **LabOP:** README documents `pip3 install labop`, Graphviz prerequisites,
  document construction/validation, protocol execution, and example notebooks.
  `setup.py` supplies dependencies; `mkdocs.yml` and `docs/reference/` organize
  model/API reference material backed by source and ontology descriptions.
  The tutorial/how-to/explanation landing files are empty in this snapshot;
  the README and notebooks supply the actual usage guidance. Documentation-site
  generation and all notebook examples were not rerun.
- **BPL:** README gives Python/uv prerequisites, `uv sync --dev`, reproducible
  CLI examples and expected reproduction output. `pyproject.toml`/`uv.lock`
  describe dependencies; `docs/BPL_Syntax_Reference.md` provides a detailed
  language reference (in Chinese). This is a provision check, not an endorsement
  of every semantic capability claimed in the documentation or a fresh execution
  of the entire paper-reproduction workflow.

## I4 — observed maintenance

| System | Verdict within the window | Dated evidence and limits |
|---|---|---|
| Culsma | Yes | Public releases include 1.0.7 (2026-09-21), 1.0.8 (10-08), 1.0.9 (10-19), and 1.0.10 (11-09). Commit `98404d8` on 11-06 fixes solution-mass conservation; `c93e651` on 11-09 prepares the release. The queried code-repository issue list is empty; no support-response claim is made. |
| LabOP | No | No default-branch commits or issues updated in the window. Latest default-branch commit is 2024-01-02; latest published release is 2022-10-27. The most recently updated PR is #213, merged 2024-10-07 for the labop.io about page, also outside the window. Other repositories, private work, and future activity are outside this finding. |
| BPL | Yes | Public history records the initial release on 2026-04-28, determinism/audit fixes (`ba60dd8`) on 04-30, and an evaluation-header fix (`cb62b1d`) plus documentation changes on 06-26. Latest main commit is 06-26. No GitLab release objects or updated issues were returned. This establishes observed maintenance on multiple dates, not recent-month activity or guaranteed ongoing support. |

The observation period includes time before BPL's public project creation on
2026-04-28. That earlier time is not treated as inactivity. No relative age or
commit-frequency score is calculated.

API evidence: [GitHub records](results/engineering/github-maintenance.json),
[LabOP recent PRs](results/engineering/labop-recent-pull-requests.json), and
[BPL GitLab records](results/engineering/bpl-maintenance.json). BPL's full public
main history contains nine returned entries with no next page; GitHub latest
commit/release lists are bounded samples and are not presented as total counts.

## Method sources

- Jackson, Crouch and Baxter, [SSI criteria-based assessment](https://www.software.ac.uk/sites/default/files/SSI-SoftwareEvaluationCriteria.pdf): Testability (pp. 9–10), Analysability (pp. 11–12), Documentation/Buildability/Installability (pp. 3–6), and Supportability/Accessibility/Evolvability.
- [JOSS review criteria](https://joss.readthedocs.io/en/latest/review_criteria.html), accessed 12 November 2026: Tests accepts documented manual checks; Documentation includes installation, usage, and API material. Community guidelines supplies supplementary support-channel evidence, not a substitute for observed maintenance. We adopt selected criteria, not JOSS's complete publication checklist.

## Direct documentation index

The following files are exact extracts retained from the inspected snapshots, not newly written documentation for those systems.

| System | Installation and usage | Reference material | Implementation structure |
|---|---|---|---|
| Culsma | [README](sources/engineering/culsma/README.md), Install and Quick Run | [Operations](sources/engineering/culsma-reference/05_operation_vocabulary_and_call_contracts.md), [Units](sources/engineering/culsma-reference/09_type_and_units.md) | [Docs layout](sources/engineering/culsma/docs/README.md), [Scope diagrams](sources/engineering/culsma/docs/architecture/pipeline/scope_module_diagrams.md) |
| LabOP | [README](sources/engineering/labop/README.md), Installation, API and Protocol Execution | [Model reference source](sources/engineering/labop/docs/reference/labop/top.md), [Execution reference source](sources/engineering/labop/docs/reference/labop/execution.md) | README describes model generation and execution/specialization boundaries |
| BPL | [README](sources/engineering/bpl/README.md), Getting Started, CLI Reference and Reproducible Quick Start | [BPL Syntax Reference](sources/engineering/bpl/docs/BPL_Syntax_Reference.md) | README Architecture/Repository Layout and [BPL Structure](sources/engineering/bpl/docs/BPL_STRUCTURE.md) |

LabOP reference Markdown contains `mkdocstrings` directives that require the corresponding source/docstrings to render. It is not standalone prose documentation. The reference build was not verified. BPL's reference includes function declarations (§4.10); its presence does not establish that execution implements those declarations correctly, as the separate L1/L2 evidence demonstrates.
