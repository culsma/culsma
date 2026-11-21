# Archived 1.0.9 programs evaluated with 1.0.11rc1

All 12 entry programs complete: 2,877/2,877 execution steps. Original source inventory: 173/173; Qubit/SPRI additions: 37/37. Event replay reproduces final material state for every program. Compile-time compatibility warnings are preserved in diagnostics.json. This is a software-execution check, not equality of all outputs across versions or laboratory validation.

Modules 01–07 and Composites 01–02 are copied unchanged from ../1.0.9-d1216a1. The other three programs match the source/program hashes in ../../qubit-spri-summary.json. Use these frozen inputs, not the top-level historical modules: the latter still contain the 1.0.7 plate-tapping gap.

For reproduction, use a clean Culsma checkout at runtime commit `b27f9f8` with Python 3.12.8 and Lark 1.3.1. Copy this snapshot directory and `benchmarks/reproduce_revision.py` from the evidence branch into the corresponding paths in that checkout. Keep the coverage checker `benchmarks/reproduce.py` from the pinned runtime commit. From that checkout run:

```sh
python benchmarks/reproduce_revision.py --manifest benchmarks/versions/1.0.11rc1-b27f9f8/manifest.json --output output/revision-reproduction
```

The output directory must be new. The manifest pins input and checker hashes and compiler/runtime source revision b27f9f8. Unused CLI modifications are recorded separately. PBMC has its own manifest and checks and is excluded from these totals.
