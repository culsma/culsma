# Translation Record

- Status: validated reviewed local case
- Coverage: cDNA template-switch reaction with mutually exclusive continuation/storage selection
- Review date: 2026-05-25

## Branch Semantics

The source step `Proceed immediately ... or proceed to the storage steps below` is authored with `if ... else ...`, not as a mainline hold followed by an optional independent branch. `proceed_immediately = true` executes only a transient `4C` hold for `10min`; `false` executes magnetic cleanup, Wash Buffer 2 resuspension, and source-defined storage at `4C` for `18h`.

## Standalone Case Wording

The vendor section originally follows a preceding capture section. For the public benchmark page, 11 is worded as a standalone case whose starting material is explicit bead-bound captured cDNA input material, and whose continuation target is the cDNA amplification module. This preserves the upstream/downstream relationship without requiring the page reader to resolve Section 2.1, Section 2.3, 10, or 12 first.

## Declared Boundaries

Brief centrifuge is not represented; `until clear` uses nominal magnetic durations; high magnet position is execution-layer mapping.
