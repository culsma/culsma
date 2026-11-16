# Main - Execution Protocol

## Overview

| Field | Value |
|---|---|
| Protocol | Main |
| Plan ID | `Main_plan` |
| Target | `human` |
| Total Steps | 1 |

## Primitive Distribution

| Primitive | Count | Percent |
|---|---:|---:|
| `HUMAN_STEP` | 1 | 100.0% |

## Step Index

| # | Step ID | Primitive | Intent | Action | Source | Destination | Volume | Depends On |
|---:|---|---|---|---|---|---|---|---|
| 1 | `step_0001` | `HUMAN_STEP` | `take_aliquot` | take_aliquot(sample: prepared, destination: TargetTube) | - | - | - | - |

## Source Mapping

| Step ID | Source Location |
|---|---|
| `step_0001` | `/Users/yangchen/VsCodeProjects/labword-theroy/papers/patterns_v1/supplementary/comparison_examples/results/l2/bpl-consumption/inputs/base.bpl:15` |
