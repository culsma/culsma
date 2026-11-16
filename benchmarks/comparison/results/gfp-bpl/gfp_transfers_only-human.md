# GFPTransfersOnly - Execution Protocol

## Overview

| Field | Value |
|---|---|
| Protocol | GFPTransfersOnly |
| Plan ID | `GFPTransfersOnly_plan` |
| Target | `human` |
| Total Steps | 10 |

## Primitive Distribution

| Primitive | Count | Percent |
|---|---:|---:|
| `ASPIRATE` | 5 | 50.0% |
| `DISPENSE` | 5 | 50.0% |

## Step Index

| # | Step ID | Primitive | Intent | Action | Source | Destination | Volume | Depends On |
|---:|---|---|---|---|---|---|---|---|
| 1 | `step_0001` | `ASPIRATE` | `transfer` | Aspirate 160 uL from sources:A1 | sources:A1 | - | 160 uL | - |
| 2 | `step_0002` | `DISPENSE` | `transfer` | Dispense 160 uL into sources:A3 | - | sources:A3 | 160 uL | step_0001 |
| 3 | `step_0003` | `ASPIRATE` | `transfer` | Aspirate 20 uL from sources:A3 | sources:A3 | - | 20 uL | step_0002 |
| 4 | `step_0004` | `DISPENSE` | `transfer` | Dispense 20 uL into assay:A1 | - | assay:A1 | 20 uL | step_0003 |
| 5 | `step_0005` | `ASPIRATE` | `transfer` | Aspirate 40 uL from sources:A2 | sources:A2 | - | 40 uL | step_0004 |
| 6 | `step_0006` | `DISPENSE` | `transfer` | Dispense 40 uL into sources:A1 | - | sources:A1 | 40 uL | step_0005 |
| 7 | `step_0007` | `ASPIRATE` | `transfer` | Aspirate 20 uL from sources:A1 | sources:A1 | - | 20 uL | step_0006 |
| 8 | `step_0008` | `DISPENSE` | `transfer` | Dispense 20 uL into assay:A2 | - | assay:A2 | 20 uL | step_0007 |
| 9 | `step_0009` | `ASPIRATE` | `transfer` | Aspirate 20 uL from sources:A2 | sources:A2 | - | 20 uL | step_0008 |
| 10 | `step_0010` | `DISPENSE` | `transfer` | Dispense 20 uL into assay:A3 | - | assay:A3 | 20 uL | step_0009 |

## Plate Map View

_Cell legend: `Nx/VuL` where `N` is transfer count and `V` is total volume in uL._

### Plate-to-Plate Summary

| Source Plate | Destination Plate | Transfer Count | Total Volume (uL) |
|---|---|---:|---:|
| `sources` | `assay` | 3 | 60 |
| `sources` | `sources` | 2 | 200 |

### Source Wells (Outgoing)

#### `sources`

| Row/Col | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 2x/180uL | 2x/60uL | 1x/20uL | . | . | . | . | . | . | . | . | . |
| B | . | . | . | . | . | . | . | . | . | . | . | . |
| C | . | . | . | . | . | . | . | . | . | . | . | . |
| D | . | . | . | . | . | . | . | . | . | . | . | . |
| E | . | . | . | . | . | . | . | . | . | . | . | . |
| F | . | . | . | . | . | . | . | . | . | . | . | . |
| G | . | . | . | . | . | . | . | . | . | . | . | . |
| H | . | . | . | . | . | . | . | . | . | . | . | . |

### Destination Wells (Incoming)

#### `assay`

| Row/Col | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 1x/20uL | 1x/20uL | 1x/20uL | . | . | . | . | . | . | . | . | . |
| B | . | . | . | . | . | . | . | . | . | . | . | . |
| C | . | . | . | . | . | . | . | . | . | . | . | . |
| D | . | . | . | . | . | . | . | . | . | . | . | . |
| E | . | . | . | . | . | . | . | . | . | . | . | . |
| F | . | . | . | . | . | . | . | . | . | . | . | . |
| G | . | . | . | . | . | . | . | . | . | . | . | . |
| H | . | . | . | . | . | . | . | . | . | . | . | . |

#### `sources`

| Row/Col | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 1x/40uL | . | 1x/160uL | . | . | . | . | . | . | . | . | . |
| B | . | . | . | . | . | . | . | . | . | . | . | . |
| C | . | . | . | . | . | . | . | . | . | . | . | . |
| D | . | . | . | . | . | . | . | . | . | . | . | . |
| E | . | . | . | . | . | . | . | . | . | . | . | . |
| F | . | . | . | . | . | . | . | . | . | . | . | . |
| G | . | . | . | . | . | . | . | . | . | . | . | . |
| H | . | . | . | . | . | . | . | . | . | . | . | . |

## Source Mapping

| Step ID | Source Location |
|---|---|
| `step_0001` | `/Users/yangchen/VsCodeProjects/labword-theroy/papers/patterns_v1/supplementary/comparison_examples/cases/gfp/gfp_transfers_only.bpl:3` |
| `step_0002` | `/Users/yangchen/VsCodeProjects/labword-theroy/papers/patterns_v1/supplementary/comparison_examples/cases/gfp/gfp_transfers_only.bpl:3` |
| `step_0003` | `/Users/yangchen/VsCodeProjects/labword-theroy/papers/patterns_v1/supplementary/comparison_examples/cases/gfp/gfp_transfers_only.bpl:4` |
| `step_0004` | `/Users/yangchen/VsCodeProjects/labword-theroy/papers/patterns_v1/supplementary/comparison_examples/cases/gfp/gfp_transfers_only.bpl:4` |
| `step_0005` | `/Users/yangchen/VsCodeProjects/labword-theroy/papers/patterns_v1/supplementary/comparison_examples/cases/gfp/gfp_transfers_only.bpl:5` |
| `step_0006` | `/Users/yangchen/VsCodeProjects/labword-theroy/papers/patterns_v1/supplementary/comparison_examples/cases/gfp/gfp_transfers_only.bpl:5` |
| `step_0007` | `/Users/yangchen/VsCodeProjects/labword-theroy/papers/patterns_v1/supplementary/comparison_examples/cases/gfp/gfp_transfers_only.bpl:6` |
| `step_0008` | `/Users/yangchen/VsCodeProjects/labword-theroy/papers/patterns_v1/supplementary/comparison_examples/cases/gfp/gfp_transfers_only.bpl:6` |
| `step_0009` | `/Users/yangchen/VsCodeProjects/labword-theroy/papers/patterns_v1/supplementary/comparison_examples/cases/gfp/gfp_transfers_only.bpl:7` |
| `step_0010` | `/Users/yangchen/VsCodeProjects/labword-theroy/papers/patterns_v1/supplementary/comparison_examples/cases/gfp/gfp_transfers_only.bpl:7` |
