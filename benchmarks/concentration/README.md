# Concentration accounting benchmark

Synthetic executable acceptance case for optional mass/volume concentration.
It checks declared starting quantities, not physical compatibility or experimental
success. Requires the local concentration implementation (not released).

`protocol.culs` initializes protein, RNA and small-molecule stocks, mixes aliquots,
splits the mixture and dilutes both portions. Each content code identifies a
solute. Volumes are homogeneous and additive by declaration.

The final aliquot is 10 uL with 10 ug antibody, 1 ug RNA and 4 ug compound:
respectively 1, 0.1 and 0.4 mg/mL. `expected.json` independently records final
volumes and solute masses in every container. Current concentration is mass
divided by that container's volume. Total initial solute quantities are conserved.

Run from the Culsma repository:

```sh
.venv/bin/python -m pytest -q tests/test_solution_concentration.py
.venv/bin/culsma run benchmarks/concentration/protocol.culs
```

Tests check actual state, global solute conservation and JSON event replay.
This case is separate from historical workflow coverage and does not change
versioned benchmark inputs or recorded results. It does not use inventory checks.
Separation, chemical reactions, cell association, unknown quantities and mixing
bare solids into these stocks remain outside the supported solution model.

## Calculated dose

`calculated-dose.culs` reads current concentration through an exact material-entry
selection, saves the original value, dilutes the stock, reads again and computes
the volume carrying 10ug. The final target is 4uL with 10ug antibody at 2.5mg/mL.

```sh
.venv/bin/culsma run benchmarks/concentration/calculated-dose.culs
.venv/bin/python -m pytest -q tests/test_concentration_expressions.py
```

The test checks displayed values, actual transfer quantities and event replay.
