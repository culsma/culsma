# Whole-blood LPS stimulation and RBC lysis: independent driver simulation

`source.md` describes the current whole-blood procedure. Its three
centrifugation steps (S5, S10 and S13) specify 4°C.
`whole_blood_lps_stimulation_rbc_lysis_sequential.culs` and `automation.culs`
contain the same executable program. `source-manifest.json` records the
upstream provenance and current file checksums.
This is the selected continuous automation example.

The verified implementation uses Culsma 1.0.11rc1 at source commit
`2d1fe05e4306947ac6b61ca961bf1bbb3190a5aa` and the Opentrons driver package
0.1.0 at commit `90ad174576eeb5798f9b80602bfefb14a0fe12b1`.
Use these source revisions; the package version labels alone do not identify
these changes. `reproduction-manifest.json` records the tested environment
and checksums of the runnable inputs and validation scripts.
No culsmaOS package, desktop application, database, service or special offline
bundle is needed. In a Python 3.11/3.12 virtual environment install these two
repositories (`pip install -e /path/to/Culsma -e /path/to/opentrons-simulator`).
From the Culsma repository:

```sh
culsma run benchmarks/automation/whole-blood-lps-rbc/automation.culs \
  --driver opentrons-simulator \
  --driver-config benchmarks/automation/whole-blood-lps-rbc/deck.json \
  --artifacts-dir run-artifacts/whole-blood-lps-rbc --json
python benchmarks/automation/whole-blood-lps-rbc/verify.py run-artifacts/whole-blood-lps-rbc
```

Use a fresh artifact directory for a fresh simulated run. The driver checks the
whole program in a private core state before issuing device actions. A failed
check produces the normal failed CLI report with `device_execution_started=false`.
After execution begins, the same directory cannot be replayed automatically.

## Device mapping and evidence

| Program behavior | Driver behavior | Evidence |
| --- | --- | --- |
| Add liquid and remove supernatant | Official SDK aspirate/dispense, fresh tips, balanced split above 1000 µL | Six transfers, seven transfer strokes; each supernatant transfer references its completed centrifuge cycle |
| Five self-transfers per mixing phase | Official SDK aspirate/dispense into the same well, without net material movement | Five 160 µL strokes and ten 800 µL strokes |
| 37°C, 5% CO₂, 6 h | Configured reference incubator at C1; virtual time | Environment request and model receipt; no measured CO₂ or temperature |
| Add/mix at 20°C; wait 15 min at 20°C | Configured reference working enclosure covering D1/D2 | Both transfer and mixing receipts retain the 20°C condition |
| 2000 × g for 10 min; twice 500 × g for 5 min, all at 4°C | Existing reference centrifuge model, 10 cm rotor; RCF converted to rpm | Requested values, rotor geometry and dispatched cycle settings |
| Move processing plate between deck, incubation and centrifuge | Seven official Flex gripper moves | Source/destination, returned move phase, associated source step |

`run.json` contains the normal runtime events and final material state.
`opentrons/evidence.json` contains the driver receipts. SDK virtual operations and
our reference centrifuge/environment models are identified separately. Initial
loads are declared preloaded materials. The second plate supplies reagents and
separate collection/waste wells. Only the processing sample occupies the moving
plate, so other samples are not inadvertently incubated or centrifuged.

The deck configuration uses 2 mL deep wells and a Flex 1000 µL pipette. A 1044 µL
supernatant removal becomes two 522 µL strokes. The 50 µL/s flow rates, reference
rotor geometry and matched 100 g loads are explicit simulation configuration,
not experimentally validated settings or measured masses. Reference device docks
are represented by deck slots; they do not establish a physical robot's access to
an external centrifuge or incubator.

The expected final volumes (1/155/1044/1000 µL in processing/supernatant/lysis
waste/wash waste) verify the program's declared partition and material accounting.
They do not predict cell recovery, reaction completion, viability or lysis kinetics.

The selected source revision specifies a fixed 15-minute hold at 20°C followed
by centrifugation. It does not request a clarity observation or conditional lysis
extension, and its culture step does not request plate-cover handling. Those are
not outstanding requirements of this revision. No observation or cover action is
claimed by the simulation. The update from `69e82bb` changes source wording and
code comments; the executable CULS statements are unchanged.

## Temperature requirement rejection (R2-13)

The same `automation.culs` is also checked with `deck-no-cooling.json`, whose
only difference from `deck.json` is a centrifuge minimum temperature of 20°C
instead of 4°C. No special driver branch or injected failure is used.

```sh
culsma run benchmarks/automation/whole-blood-lps-rbc/automation.culs \
  --driver opentrons-simulator \
  --driver-config benchmarks/automation/whole-blood-lps-rbc/deck-no-cooling.json \
  --artifacts-dir run-artifacts/whole-blood-lps-rbc-no-cooling --json
# The CLI command above is expected to return exit status 1.
python benchmarks/automation/whole-blood-lps-rbc/verify.py \
  run-artifacts/whole-blood-lps-rbc-no-cooling --expect-rejection
```

The preflight rejects the first centrifugation with
`DRV_OT_CENTRIFUGE_TEMPERATURE_RANGE`: `Requested 4 °C is outside 20–40 °C`.
The `STEP_FAILED` event retains the 4°C requirement and `processing_well`
reference; the diagnostic and saved plan connect it to the source statement.
`device_execution_started=false`, and there are no device receipts. The saved
state is a private preflight projection, not a physical sample observation or a
completed experiment. No successful separation is recorded for the rejected step.
This demonstrates refusal of a known unsupported setting, not detection of an
unexpected cooling failure after a physical cycle starts.

The successful 4°C run and the rejected profile are summarized in
`evidence/4c-interface-check.json`. Generate fresh CLI artifacts with the commands
above and run the verifier to reproduce these checks.


## Method requirements and execution-time failure

`check_interfaces.py` runs the same independent executor through a small validation
harness. It does not use OS or add special cases to production driver code.
The `constraints` variant adds LOW_CARRYOVER and HIGH_PRECISION only to the first
100 µL stimulation-medium transfer. All other workflow statements are retained.
Generated inputs are saved under the run's `inputs/` directory. The configured
Flex method uses a 20–1000 µL range and aspiration/dispensing rates of 25/40 µL/s;
these are simulation method settings, not a measured precision claim.

```sh
python benchmarks/automation/whole-blood-lps-rbc/check_interfaces.py constraints   run-artifacts/whole-blood-constraints
python benchmarks/automation/whole-blood-lps-rbc/verify.py   run-artifacts/whole-blood-constraints --interface constraints
python benchmarks/automation/whole-blood-lps-rbc/check_interfaces.py missing-method   run-artifacts/whole-blood-missing-method
# Expected exit status 1: no device execution; DRV_OT_CONSTRAINT_METHOD.
python benchmarks/automation/whole-blood-lps-rbc/verify.py   run-artifacts/whole-blood-missing-method --interface missing-method
python benchmarks/automation/whole-blood-lps-rbc/check_interfaces.py failure   run-artifacts/whole-blood-failure
# Expected exit status 1: execution stops at supernatant collection.
python benchmarks/automation/whole-blood-lps-rbc/verify.py   run-artifacts/whole-blood-failure --interface failure
```

The failure scenario uses the unchanged `automation.culs` and `deck.json`. After
preflight succeeds, the harness raises `RuntimeError` at the supernatant transfer
(`entry.s16`) before invoking that transfer's SDK execution. This deliberately
exercises the driver's completion-unconfirmed path; it is not a historical
Opentrons fault or an observation of liquid movement. The earlier return-to-deck
move can have completed and is retained in the receipt record.

The failed event records `DRV_OT_EXECUTION_UNKNOWN`, the native cause
`Injected loss of transfer completion confirmation`, `execution_state=unknown`
and `retry_safe=false`, with the source location. No successful material update
is committed for that transfer: the software record retains 200 µL in the
processing well and 0 µL in the collection well. All later steps are skipped;
this does not imply a physical rollback, verified sample state, or automatic
recovery. `evidence/constraint-and-failure-checks.json` contains extracted records
from these three runs. The verifier checks saved run records and detects missing
method application, lost rejection context, or continuation after the failure.
