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
| `constraints` | Add `low_carryover` and `high_precision` with a configured pipetting method | Verify tip handling and the selected method settings |
| `missing-method` | Same requirements without the precision method | Reject before device execution with `DRV_OT_CONSTRAINT_METHOD` |
| `no-cooling` | Configure a centrifuge without the requested cooling capability | Reject the request before device execution |
| `failure` | Inject loss of completion confirmation during a transfer | Report unknown execution state and stop subsequent execution |

The script generates variant inputs inside each run directory. Expected rejection
or injected failure counts as a passed check only when its recorded behavior
matches the verifier.
Each scenario saves the plan, runtime results and available driver evidence;
`results.json` in the output directory collects the verification reports.
`--check-only` checks retained file hashes and the five saved verification outcomes
without importing the driver or rerunning the simulation.

</details>

## Whole-blood workflow

The [whole-blood case](whole-blood-lps-rbc/) combines LPS stimulation,
supernatant collection, RBC lysis and washing. Its files are:

- `source.md`: numbered experimental procedure.
- `protocol.culs`: executable Culsma program.
- `deck.json`: Flex workstation configuration.
- `results.json`: retained verification results.
- `manifest.json`: implementation versions, dependencies and file hashes.

Experimental parameters, device settings and detailed outcomes are recorded in
these files. Pipetting and supported plate movements use the official Opentrons
simulator; centrifugation and environmental holds use reference device models
with virtual time. The results describe software execution.
