# Benchmark records and website presentation

## Ownership and record

`Culsma/benchmarks` is the sole maintained source. Each migrated case contains
`source.md`, `protocol.culs` and generated `coverage.json`. Context and Notes
preserve background and source information; only the numbered Steps section
is the correspondence denominator. In the program, each copied instruction is
identified by the dedicated `// Source step S<n>:` prefix so ordinary comments
remain outside the metric. Consecutive source-step markers may share the next
code region when one constrained operation implements more than one source
instruction. Do not hand-edit coverage results.

The compact record stores the checked version, input hashes, total/matched counts,
percentage, status and issues. Successful steps are implicit; only unmatched steps
and structural errors are listed. `pass` means the annotation correspondence check
passed. Missing comments can be detected; incorrect translation or incomplete
experimental meaning cannot be inferred from this score. Even an incorrect program
can retain all source comments. Numerical and semantic judgments remain separate.

## Website decision

Use a concise overview as the default presentation, with one optional worked
example (Case 00). Do not reproduce every workflow and its full diagnostic tables.
A name-only directory is too sparse for readers assessing the workflow range;
include a short task description and evidence links.

The overview should show:

- Case ID/name and a one-line experimental task description.
- Role: worked example or corpus case; exclude 00 from corpus totals.
- Matched/total source steps and percentage, labeled **Step correspondence**.
- Status, including pending, incomplete, error or stale evidence.
- Language version and implementation revision, at page level if shared.
- Links to the exact source, annotated program and generated record.

Case 00 may show a collapsed, automatically rendered source/code example so a
reader can understand what correspondence means without leaving the page. All
other full texts remain available through the benchmark links. An optional preview
must be generated from the same snapshot, never maintained as another source copy.

Build the overview from a specified benchmark revision. Verify coverage input
hashes before displaying scores. Use revision-pinned links and show the benchmark
revision/date separately from the language implementation version. A case without
a current-format record is pending, not 0% or implicitly 100%. An incomplete or
error status must remain visible even if matched/total happens to be 100%.

## Versioned display model

Publish three views from each immutable coverage snapshot:

1. **Current benchmark overview.** Show the benchmark snapshot, Culsma version,
   total step correspondence, open language-gap count, and one row per case.
   A case row uses matched/total plus a separate gap count; never combine them
   into one score.
2. **Case page.** Keep a stable case URL with its current result and a short
   version history. Each version links to revision-pinned source.md,
   protocol.culs, and coverage.json. Full source and code stay in the benchmark
   repository; the page does not maintain another copy.
3. **Snapshot page.** Preserve one immutable page per benchmark version. Show
   resolved, introduced, and still-open correspondence issues and language gaps
   relative to the previous comparable snapshot.

The paper should cite one snapshot and use one compact case overview table:
case, workflow, step correspondence, open language gaps, and status. It should
not carry the evolving history. The website presents the current snapshot and
history; Git remains the auditable evidence store.

A manually reviewed missing language capability is declared beside the affected
program region as `// Language gap S<n>: ...`. This declaration is not part of
the automatic correspondence percentage. Translation mistakes, ambiguous source
instructions, and added domain detail are not language gaps. Remove the marker
only when a later implementation expresses the instruction and the case has
been reviewed again.

`tools/build_coverage_snapshot.py` verifies the case hashes and writes the
versioned aggregate defined by
`schemas/benchmark-coverage-snapshot.schema.json`. Comparisons are made only
when a case's source hash is unchanged; otherwise the case is labeled
source-changed instead of reporting a misleading improvement.

## Basis in the inspected files

The current local website renderer reads website-owned `artifacts/cases/` copies.
Its index and tables still foreground descriptor totals, material-state continuity
and result traceability. Case pages reproduce full source, full code and detailed
artifact tables; Case 09 alone contains 54 expandable blocks. This is a second
publication copy of an older evaluation structure, not the current three-file view.

Paper Section 3.1 already explains modeling granularity with code examples. The
website should help readers inspect breadth and retrieve evidence, rather than
repeat that argument for every case. A single worked example preserves orientation;
the overview and original files supply navigation and auditability.

Section 3.2 and Methods now describe the case-local correspondence check and
Case 00's twelve numbered steps. The former partial numerical/semantic inventories
and seven-step grouping are not the current evaluation. Corpus migration remains
pending; the historical 208-step total must not be reused for a changed inventory.

## Publication transition

Keep the paper-linked benchmark snapshot identifiable and accessible while a later
version evolves. Preserve existing case URLs as compact landing pages or provide
redirects to their versioned evidence; avoid breaking readers' citations. Existing
source availability conditions still apply to linked full texts.

Next: finish current-format cases, update the manuscript overview, then replace the
website overview and case-page defaults with snapshot-generated summaries. Preserve
older published metric pages as a clearly dated snapshot instead of mixing their
numbers with the new correspondence results. This file records the presentation
decision; the website itself has not yet been changed.
