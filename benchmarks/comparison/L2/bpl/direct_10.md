# Main - Execution Protocol

## Overview

| Field | Value |
|---|---|
| Protocol | Main |
| Plan ID | `Main_plan` |
| Target | `human` |
| Total Steps | 2 |

## Primitive Distribution

| Primitive | Count | Percent |
|---|---:|---:|
| `ASPIRATE` | 1 | 50.0% |
| `DISPENSE` | 1 | 50.0% |

## Step Index

| # | Step ID | Primitive | Intent | Action | Source | Destination | Volume | Depends On |
|---:|---|---|---|---|---|---|---|---|
| 1 | `step_0001` | `ASPIRATE` | `transfer` | Aspirate 10 uL from plate_1:A1 | plate_1:A1 | - | 10 uL | - |
| 2 | `step_0002` | `DISPENSE` | `transfer` | Dispense 10 uL into plate_1:A2 | - | plate_1:A2 | 10 uL | step_0001 |

## Plate Map View

_Cell legend: `Nx/VuL` where `N` is transfer count and `V` is total volume in uL._

### Plate-to-Plate Summary

| Source Plate | Destination Plate | Transfer Count | Total Volume (uL) |
|---|---|---:|---:|
| `plate_1` | `plate_1` | 1 | 10 |

### Source Wells (Outgoing)

#### `plate_1`

| Row/Col | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 1x/10uL | . | . | . | . | . | . | . | . | . | . | . |
| B | . | . | . | . | . | . | . | . | . | . | . | . |
| C | . | . | . | . | . | . | . | . | . | . | . | . |
| D | . | . | . | . | . | . | . | . | . | . | . | . |
| E | . | . | . | . | . | . | . | . | . | . | . | . |
| F | . | . | . | . | . | . | . | . | . | . | . | . |
| G | . | . | . | . | . | . | . | . | . | . | . | . |
| H | . | . | . | . | . | . | . | . | . | . | . | . |

### Destination Wells (Incoming)

#### `plate_1`

| Row/Col | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | . | 1x/10uL | . | . | . | . | . | . | . | . | . | . |
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
| `step_0001` | `/Users/yangchen/VsCodeProjects/labword-theroy/Culsma/benchmarks/comparison/L2/bpl/direct_10.bpl:14` |
| `step_0002` | `/Users/yangchen/VsCodeProjects/labword-theroy/Culsma/benchmarks/comparison/L2/bpl/direct_10.bpl:14` |
