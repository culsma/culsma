# Release Decision: Direct CLI Return Display

Status: current

## Decision

The public CLI default run path prints material use, resources, and explicit
protocol returns. `--results FILE.json` saves the same three sections as a
compact JSON object. The legacy complete run output remains available through
`--json` or `--output FILE.json`; its schema and fields are unchanged.

| Compact field | Shape | Source |
| --- | --- | --- |
| `materials` | `[{name, amount, unit}]` | Declared sample input and runtime reagent withdrawals; units are `uL`, `mg`, or `cells` |
| `resources` | `[{kind, capacity_uL, count}]` for containers; `[{kind, name, count}]` for devices | Physical container state and explicit device bindings |
| `returns` | Protocol-name map with existing `value` or `bindings` payloads | Complete public protocol return projection |

Capacity is the effective runtime capacity in `uL`, including constructor
defaults; it is `null` when unknown or not applicable. Container rows group
physical instances by kind and capacity, including supplied initial containers
that are used or explicitly returned.
Positions allocated within the same physical carrier are reported as one
carrier resource; for example, six used wells on one plate report one plate.
Skipped/failed allocations and virtual separation fractions are excluded.
Each explicitly named device contributes one resource row, even when the same
reference is reused by multiple completed steps. Devices are never inferred
from conditions or operation names. Material dimensions are separate rows;
unknown dimensions are omitted, and volume is not duplicated as both uL and mL.
For a container used as the processed sample, the material row reports the
declared input amount rather than the fraction subsequently routed out of that
container. Stock reagents continue to report the amount withdrawn at runtime.
This selection is made for each input lot using its stable `lot_id` and
`container_id`; display-name aggregation happens only after selection. Neither
names nor already aggregated report rows are identity joins.

A single input produces one compact object. Multiple inputs produce an array
of compact objects in input order, without merging independent runs. Console
output labels each input separately. `--results` requires a path and cannot
be combined with `--json` or `--output`; the legacy combination of `--json`
and `--output` still saves the complete output to the requested file.

On failure, the compact file contains partial results, stderr explains that
the run failed, and the exit status is 1. Execution status, alerts, and an
explicitly requested inventory check remain visible in the console; they are
not extra fields in the compact file. Full execution details remain available
through the legacy output and opt-in debug artifacts.

Protocol return projection rules are tracked separately in
`docs/protocol_return_projection_decision.md`.

## Invariants

- Protocol return semantics stay explicit: the formal returned value is the value named by `return`.
- Container/tube display is a runtime projection of the returned container state, not a new binding model.
- `lab_report_v1` is a generated execution report. It is not the protocol return value.
- Legacy machine-readable run output keeps `returns` separate from `report`.
- Compact output has exactly `materials`, `resources`, and `returns`; it does
  not change `culsma_run_output_v1` or `lab_report_v1` or introduce a DSL change.
- Compact output is projected from runtime state, accounting, completed plan
  steps, and protocol returns; it does not read the legacy report as an input.
- Compact material projection consumes per-lot accounting and per-container
  roles directly. It does not reconstruct lot relationships from the legacy
  report's name-aggregated tables.
- Only roles from completed steps contribute compact material and resource
  evidence; references in skipped or failed branches do not count as use.
- `report.materials.reagent_consumption` is the complete runtime-derived table
  of consumed input samples and reagents. It excludes runtime-generated
  intermediate fractions such as `entry...::0` unless the container was
  explicitly loaded as an input.
- For a consumption row, an unmeasured unit axis is `null`; it is not reported
  as a measured zero. Volume-only and mass-only input consumption are both
  represented.
- Display truncation belongs in terminal/UI rendering, not in report data.
- If a protocol has no explicit return, the console says so. Inferred final
  products remain available only in the legacy report, not as compact returns.
- Console data/group previews omit null measurement fields and bound the number
  of displayed members. JSON always preserves the full return objects.
- Console container previews show volume when available, otherwise mass, so a
  density-derived compatibility axis does not duplicate the primary quantity.
- Debug artifacts remain opt-in through `--artifacts-dir`.

## Diagnostics Ownership

- Parse, validation, typecheck, plan, and runtime diagnostics remain owned by their existing pipeline stages.
- CLI formatting does not create or suppress diagnostics; it only renders the returned run bundle.

## Conformance Hooks

- Req CLI-RETURN-001: default `culsma run file.culs` prints terminal text, not JSON. Test: `test_cli_run_prints_human_summary_to_stdout_by_default`.
- Req CLI-RETURN-002: `--json` prints machine-readable run output with separate `returns` and `report`. Test: `test_cli_run_prints_machine_output_json_when_requested`.
- Req CLI-RETURN-003: `culsma file.culs` is accepted as script-like shorthand. Test: `test_cli_accepts_top_level_input_path_shorthand`.
- Req CLI-RETURN-004: returned containers display their live tube/container state. Test: `test_cli_human_summary_includes_returned_container_state`.
- Req CLI-RESULTS-001: `--results FILE.json` writes exactly three result fields and preserves legacy outputs. Test: `test_results_file_has_three_fields_and_keeps_legacy_output`.
- Req CLI-RESULTS-002: default output displays material use, resource capacities, and explicit returns. Test: `test_default_console_shows_the_three_results`.
- Req CLI-RESULTS-003: observation previews omit null fields while JSON retains them. Test: `test_observation_results_keep_null_fields_but_console_is_compact`.
- Req CLI-RESULTS-004: compact resources exclude unexecuted allocations. Test: `test_results_skip_unexecuted_containers_and_keep_default_and_no_capacity`.
- Req CLI-RESULTS-005: failed compact exports cannot appear to be successful runs. Test: `test_failed_results_file_is_partial_and_failure_is_visible`.
- Req CLI-RESULTS-006: a processed sample reports its declared input amount rather than the fraction routed out during processing. Test: `test_results_report_declared_sample_input_instead_of_routed_fraction`.
- Req CLI-RESULTS-007: lots that share a display name retain independent sample/reagent quantity rules until final aggregation. Test: `test_results_select_quantity_per_lot_before_same_name_aggregation`.
- Req CLI-RESULTS-008: untouched containers supplied in an external state snapshot are excluded from compact resources. Test: `test_results_include_only_used_imported_containers`.
- Req CLI-RESULTS-009: sample references in unexecuted branches do not contribute compact usage, and repeated completed uses of one explicit device produce one resource row. Tests: `test_results_ignore_sample_role_in_unexecuted_branch`, `test_results_list_explicit_device_once_from_completed_steps`.
- Req CLI-RESULTS-010: positional allocations sharing one physical carrier report one carrier resource, and data-group console output reports the runtime observation count. Test: `test_results_count_plate_as_one_carrier_and_summarize_observations`.
