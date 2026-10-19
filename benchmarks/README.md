# Culsma workflow benchmark

Source procedures, Culsma programs and recorded source-step coverage across versions.

| Workflow | Source-step coverage (1.0.7) | Source-step coverage (1.0.9) |
| --- | ---: | ---: |
| [Module 01: Cell transfection](modules/01-cell-transfection/source.md) | 13/13 (100%) | 13/13 (100%) |
| [Module 02: Selective plating and colony isolation](modules/02-selective-plating-candidate-colony-isolation/source.md) | 12/12 (100%) | 12/12 (100%) |
| [Module 03: Cell lysate preparation](modules/03-cell-lysate-preparation/source.md) | 10/10 (100%) | 10/10 (100%) |
| [Module 04: Suspension-cell staining](modules/04-suspension-cell-staining/source.md) | 29/29 (100%) | 29/29 (100%) |
| [Module 05: Magnetic-bead immunoprecipitation](modules/05-magnetic-bead-immunoprecipitation/source.md) | 23/23 (100%) | 23/23 (100%) |
| [Module 06: Western blot](modules/06-western-blot/source.md) | 32/32 (100%) | 32/32 (100%) |
| [Module 07: Sandwich ELISA](modules/07-sandwich-elisa/source.md) | 41/42 (97.6%) | 42/42 (100%) |
| [Module 08: Qubit 1X dsDNA HS quantification](modules/08-qubit-dsdna-hs/source.md) | — | 13/13 (100%) |
| [Module 09: Double-sided SPRI selection](modules/09-double-sided-spri/source.md) | — | 21/21 (100%) |
| [Composite 01: Flow-cytometry immunophenotyping](composites/01-flow-cytometry-immunophenotyping/source.md) | 5/5 (100%) | 5/5 (100%) |
| [Composite 02: Magnetic-bead IP with Western blot](composites/02-magnetic-bead-ip-western-blot/source.md) | 7/7 (100%) | 7/7 (100%) |
| [Composite 03: Qubit quantification and double-sided SPRI selection](composites/03-qubit-double-sided-spri/source.md) | — | 3/3 (100%) |

Coverage is matched / total numbered source steps. **—** means not evaluated in that
version. Composite rows count their own steps, not the steps of reused modules.
Coverage measures source–program correspondence, not experimental success.

The original seven modules and two composites cover **172/173** steps in 1.0.7
and **173/173** in 1.0.9. The three added entries cover **37/37** in 1.0.9 and
are recorded separately.

## Run

Requires Git and Python 3.12 (recorded runs used 3.12.8). From a fresh directory:

```sh
git clone https://github.com/culsma/culsma.git culsma-benchmark
git clone --branch v1.0.9 https://github.com/culsma/culsma.git culsma-runtime
python3.12 -m venv .venv
.venv/bin/python -m pip install lark==1.3.1
.venv/bin/python culsma-benchmark/benchmarks/reproduce.py \
  --manifest culsma-benchmark/benchmarks/versions/1.0.9-d1216a1/manifest.json \
  --runtime-repo culsma-runtime --output results/benchmark-1.0.9
```

For Modules 08–09 and Composite 03, use the same environment:

```sh
.venv/bin/python culsma-benchmark/benchmarks/reproduce.py \
  --manifest culsma-benchmark/benchmarks/qubit-spri-manifest.json \
  --runtime-repo culsma-runtime --output results/qubit-spri-1.0.9
```

The runner checks runtime code, dependencies, input hashes and expected results.
Use a fresh output directory each time; results include `summary.json`, `table.md`
and per-workflow records. On Windows, use `.venv/Scripts/python.exe`.

## Historical runs and examples

To reproduce 1.0.7, switch the runtime and select its manifest:

```sh
git -C culsma-runtime checkout v1.0.7
.venv/bin/python culsma-benchmark/benchmarks/reproduce.py \
  --manifest culsma-benchmark/benchmarks/manifest.json \
  --runtime-repo culsma-runtime --output results/benchmark-1.0.7
```

The worked examples have separate material-state checks and do not enter the
coverage totals. With the 1.0.7 runtime selected above:

```sh
.venv/bin/python -m pip install -e culsma-runtime
.venv/bin/python culsma-benchmark/benchmarks/check_manuscript_examples.py \
  --culsma-repo culsma-runtime --culsma-cli .venv/bin/culsma \
  --output results/examples-1.0.7 --tex-output-dir results/examples-1.0.7/listings
.venv/bin/python culsma-benchmark/benchmarks/check_introduction_example.py \
  --culsma-cli .venv/bin/culsma \
  --output results/examples-1.0.7/modules/example-00/results \
  --tex-output-dir results/examples-1.0.7/listings
```

## Records

- **1.0.7:** [manifest](manifest.json), [results](summary.json).
- **1.0.9:** [manifest](versions/1.0.9-d1216a1/manifest.json), [results](versions/1.0.9-d1216a1/summary.json).
- **Added workflows (1.0.9):** [manifest](qubit-spri-manifest.json), [results](qubit-spri-summary.json).

Manifests retain exact runtime commits and input hashes. Release tags are accepted
only when their runtime source and package metadata match the pinned commit.
Module 07's missing plate-tapping step in 1.0.7 is covered in 1.0.9. Coverage
matches numbered source text to annotated statements; it does not verify every
experimental detail. Colony selection still requires an operator-supplied mapping;
Qubit/SPRI software runs do not measure DNA concentration or recovery.
