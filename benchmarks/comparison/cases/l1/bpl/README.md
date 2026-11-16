# BPL L1 inputs

These are comparison inputs, not additions to the BPL implementation.

| File | Purpose |
|---|---|
| [direct.bpl](direct.bpl) | Positive control: literal transfers of 10 and 20 uL. |
| [default_10.bpl](default_10.bpl), [default_20.bpl](default_20.bpl) | Minimal protocol-default pattern shown in the upstream README. The body uses `amount`. |
| [function_calls.bpl](function_calls.bpl) | One user-defined function, called twice with different arguments. |
| [protocol_calls.bpl](protocol_calls.bpl) | Retained initial hypothesis that a protocol declaration is callable. Not treated as documented invocation support. |
| [undefined_calls.bpl](undefined_calls.bpl) | Remove the declaration while keeping both calls; compare emitted operations. |

The runner also extracts and retains the complete upstream README code block
as `results/l1/bpl-cli/upstream_readme.bpl`. That unchanged block encounters an
unrelated syntax error before reaching the protocol, so it is excluded from
the L1 verdict. Its failure is not attributed to parameter binding.

Run from the manuscript root using the isolated BPL environment:

```sh
output/labop-comparison/bpl-env/bin/python supplementary/comparison_examples/check_bpl_l1.py
```

Every case is sent through the installed `bplc parse`, `bplc check`, and
`bplc lower` commands. Lowering is checked for both `human` and `simulation`
targets. This is plan generation, not simulation or instrument execution.
See the [audit](../../../bpl-l1-evidence.md) for setup, source evidence and limits.
