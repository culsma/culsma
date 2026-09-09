# Translation Record

- Status: reviewed local case revision
- Coverage: single-sample magnetic-bead cDNA amplification plus batch execution wrapper
- Source class: anonymized vendor-manual excerpt
- Product/vendor names: intentionally omitted
- Reviewed date: 2026-09-03

## Revision Notes

- Made the natural-language source standalone for the public benchmark page: the first procedure step now refers to bead-bound template-switched cDNA input material rather than an external manual section.
- Uses `RunCDNAAmplificationBatch(selected_sample_count = 1, selected_amplification_cycles = 7)` as the outer execution wrapper that repeats the single-sample module and forwards the selected cycle count.
- Uses `CDNAAmplification(selected_amplification_cycles = 7)` as the single-sample wet-lab module and `PreAmplificationWash(...)` for the repeated bead-retention wash sequence.
- Represented source-table-derived PCR cycle count as a protocol formal parameter used in `schedule(end = selected_amplification_cycles)`.
- Used `with env(field = magnetic_rack)` for operations performed while still on the magnetic rack.
- Used `magnetic_program(duration = 2min/1min)` for magnetic separations.
- Converted settled-bead conditional text into required preventive resuspension using 80% volume x 10.
- Represented active on-ice handling with bounded `env(thermal = 0C, duration = ...)` windows.
- Represented the final thermocycler 4C wrap-up as `4C 15min`, while preserving the up-to-18h storage allowance as a note.

## Validation Note

The full stored program, including its batch wrapper and subprotocols, completed 99 of 99 generated active steps with zero diagnostics in the current local Culsma runtime.
