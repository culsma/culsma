# Automation benchmarks

Each case keeps its source procedure, Culsma program, workstation configuration,
retained results and manifest together. `reproduce.py` runs the software scenarios
and checks their program results and device records. Culsma OS is not required.

## One-command reproduction

Use the [paper reproduction entry point](../README.md#reproduce-the-paper):

```sh
python3 benchmarks/replay.py --only automation
```

It installs the recorded core and public driver automatically in an isolated
environment and runs all five software scenarios into a fresh results directory.
Without `--only automation`, the same entry point also reproduces the workflow
benchmark versions and the language comparison. Versions are selected from the
manifest; users do not need to locate or install them manually.

<details>
<summary>Manual environment setup and individual checks</summary>

## Install

Use Python 3.11. Install Culsma and the public
[Opentrons driver](https://github.com/culsma/culsma-driver-opentrons);
installation packages are not duplicated in this benchmark.
The automation evaluation uses **Culsma 1.0.11** and the public Opentrons driver
**0.1.0**. Install the published versions:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install 'culsma==1.0.11' 'lark==1.3.1' \
  'culsma-opentrons-simulator @ git+https://github.com/culsma/culsma-driver-opentrons.git@v0.1.0'
```

The manifest records the exact public implementation commits and dependency
versions used to regenerate the retained results. The unified entry point
selects them automatically.

The driver's distribution and CLI registration remain
`culsma-opentrons-simulator` and `opentrons-simulator`, respectively.

## Reproduce

Run from the Culsma repository root. The output directory must not exist yet.

```sh
python benchmarks/automation/reproduce.py --check-only
python benchmarks/automation/reproduce.py \
  --output benchmarks/local-results/automation-run
```

Use `--scenario NAME` to run a single scenario. All five use the same whole-blood
LPS stimulation and RBC lysis workflow:

| Scenario | Input change | Expected check |
| --- | --- | --- |
| `normal` | None | Complete the workflow and verify operations, settings and material accounting |
| `constraints` | Add `low_carryover` and `high_precision` to the first medium transfer; configure its pipetting method | Fresh tips and the selected 25/40 µL/s aspiration/dispensing rates |
| `missing-method` | Same requirements without the precision method | Reject before device execution with `DRV_OT_CONSTRAINT_METHOD` |
| `no-cooling` | Change the centrifuge profile's minimum temperature from 4°C to 20°C | Reject the 4°C request before device execution |
| `failure` | Inject loss of completion confirmation at the supernatant transfer (`entry.s16`) | Report unknown execution state, prohibit automatic retry and skip subsequent steps |

The script generates variant inputs inside each run directory. Expected rejection
or injected failure counts as a passed check only when its recorded behavior
matches the verifier. Fault injection belongs to this script, not the driver.
Each scenario saves the plan, runtime results and available driver evidence;
`results.json` in the output directory collects the verification reports.
`--check-only` checks retained file hashes and the five saved verification outcomes
without importing the driver or rerunning the simulation.

</details>

## Whole-blood workflow

`whole-blood-lps-rbc/` contains:

- `source.md`: numbered procedure.
- `protocol.culs`: the single maintained executable program.
- `deck.json`: normal Flex workstation configuration.
- `results.json`: retained temperature, method and failure evidence, merged without
  dropping fields. Historical input names are mapped in the manifest.
- `manifest.json`: provenance, evaluated runtime revisions, dependencies and hashes.

The three centrifugations request 2000 × g for 10 min, 500 × g for 5 min after
lysis, and 300 × g for 5 min after washing, all at 4°C. The normal run checks six
transfers, fifteen mixing strokes, three centrifuge cycles, two environmental
holds and seven plate movements. The 1044 µL transfer is split into two 522 µL
strokes by the configured 1000 µL pipette. Final declared volumes are 1/155/1044/1000 µL
in the processing, collected-supernatant, lysis-waste and wash-waste wells.

Pipetting and supported Flex gripper moves use the official Opentrons simulator.
Centrifugation and incubation use reference device models and virtual time;
recorded temperatures and material quantities are software values, not measured
sample conditions or recovery. Reference device docks use deck slots. The
configuration does not establish physical access to an external instrument.
The injected failure leaves the transfer unconfirmed and its material update
uncommitted; it does not represent a physical rollback.
