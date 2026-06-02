# Release Decision: Direct CLI Return Display

Status: current

## Decision

The public CLI default run path prints a human-readable terminal result. Machine-readable run output remains available through an explicit `--json` flag or `--output` file.

Protocol return projection rules are tracked separately in
`docs/protocol_return_projection_decision.md`.

## Invariants

- Protocol return semantics stay explicit: the formal returned value is the value named by `return`.
- Container/tube display is a runtime projection of the returned container state, not a new binding model.
- `lab_report_v1` is a generated execution report. It is not the protocol return value.
- Machine-readable run output keeps `returns` separate from `report`.
- If a protocol has no explicit return, the CLI may summarize inferred final products, but it must not label them as protocol returns.
- Debug artifacts remain opt-in through `--artifacts-dir`.

## Diagnostics Ownership

- Parse, validation, typecheck, plan, and runtime diagnostics remain owned by their existing pipeline stages.
- CLI formatting does not create or suppress diagnostics; it only renders the returned run bundle.

## Conformance Hooks

- Req CLI-RETURN-001: default `culsma run file.culs` prints terminal text, not JSON. Test: `test_cli_run_prints_human_summary_to_stdout_by_default`.
- Req CLI-RETURN-002: `--json` prints machine-readable run output with separate `returns` and `report`. Test: `test_cli_run_prints_machine_output_json_when_requested`.
- Req CLI-RETURN-003: `culsma file.culs` is accepted as script-like shorthand. Test: `test_cli_accepts_top_level_input_path_shorthand`.
- Req CLI-RETURN-004: returned containers display their live tube/container state. Test: `test_cli_human_summary_includes_returned_container_state`.
