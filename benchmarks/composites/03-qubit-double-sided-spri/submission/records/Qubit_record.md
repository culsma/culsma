# E02 Record

## Purpose

Test whether Culsma can represent a ready-to-use 1X assay solution, two-point calibration, instrument acquisition, and a measured concentration result that is consumed by another protocol.

## Status

- Source protocol: drafted from the official Qubit 1X dsDNA HS Assay Kits user guide.
- Culsma translation: a batch wrapper accepts grouped standards and a DNA-sample list, calibrates once, and collects the single-sample readouts. The executable example contains one sample.
- Validation: Culsma 1.0.8, 35/35 steps completed with zero diagnostics; the return contains one readout. A separate temporary two-sample input completed 50/50 steps with zero diagnostics and returned two distinct sample readouts; only two standard readings were performed.
- Readout limitation: the stub driver does not provide a measured numerical concentration or a real instrument calibration. Numeric concentration fields remain null until supplied by an instrument adapter.
- Coverage review: not run.
