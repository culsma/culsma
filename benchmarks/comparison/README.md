# Reproduce the language comparison

Each of `M1`–`M4` and `L1`–`L4` contains `case.json` and three directories: `culsma`, `labop`, and `bpl`. Programs, their required helpers, execution records and evaluation results are kept together in each language directory. Criterion definitions and interpretation are in the manuscript supplement.

## One-command reproduction

Use the [paper reproduction entry point](../README.md#reproduce-the-paper):

```sh
python3 benchmarks/replay.py --only comparison
```

It obtains the recorded Python versions and dependencies, prepares all three
systems, and runs all eight criteria. New results are written to a separate copy
of this evidence package under `benchmarks/local-results/paper-replay-.../`.
Without `--only comparison`, it also runs the workflow benchmark and automation.

<details>
<summary>Manual environment setup and individual checks</summary>

## Prepare the environment

Use the pinned interpreters to install each system once:

```sh
python3 benchmarks/comparison/evaluate.py --setup culsma --python /path/to/python3.12.8
python3 benchmarks/comparison/evaluate.py --setup labop --python /path/to/python3.11.11
python3 benchmarks/comparison/evaluate.py --setup bpl --python /path/to/python3.13.1
```

Setup downloads the commit-pinned sources and installs the dependencies recorded in each language's `requirements.txt`. Network access is needed for setup. Sources and environments are installed under `benchmarks/local-results/comparison-runtime/`, outside this directory. Existing environments are not overwritten. To reuse an existing installation, pass `--runtime /absolute/path` or set `COMPARISON_RUNTIME_DIR`.

The pinned versions are Culsma `5364676bc2437b4981a00ce0133c730af243e469` (1.0.7), LabOP `2e2bd88150c71a440771fd369f40295dfd622324`, and BPL `4e505740f5025d59ba655c6c955f83876f753007`. Each case records the Python version and selected implementation-file hashes checked before execution.

## Run

From the Culsma repository root:

```sh
python3 benchmarks/comparison/evaluate.py
python3 benchmarks/comparison/evaluate.py --case M3
python3 benchmarks/comparison/evaluate.py --case M3 --system culsma
```

Runs use software only. They refresh generated results beside the programs. Control variants may have their own subdirectories within a language directory. The exact commands, exit status and input hashes are saved in `commands.json`; `evaluation.json` records each expected and observed value. The aggregate summary path is printed at completion; execution scratch files stay under `benchmarks/local-results/`.

To check retained results without rerunning the programs:

```sh
python3 benchmarks/comparison/evaluate.py --check-only
```

A reproduced negative capability witness is reported as `No`. Missing or changed evidence, failed commands or mismatched inputs are reported as `NE` and cause a nonzero exit status. `L4/culsma` and `L4/bpl` reproduce source-interface inspections; `L4/labop` runs the existing extension witness. Their evaluation method is recorded explicitly. No new Culsma-provider or BPL-callback execution is implied by a source inspection.

</details>
