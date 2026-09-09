# Translation Record

- Status: validated current case
- Coverage: cell culture, transfection, lysis, electrophoresis, membrane transfer, immunoblotting, and image acquisition
- Source class: publicly available protocol
- Runtime result: 176/176 generated active steps completed with no diagnostics
- Reviewed date: 2026-09-02

## Step Alignment

| Source step | Culsma representation | Coverage | Notes |
|---|---|---|---|
| S1 | well allocation, transfers, and environmental hold | current | Cell count is represented in the seeded material; confluency remains an observed biological state. |
| S2 | transfection-mixture construction, transfer, and timed hold | bridge | PEI-mediated transfection is represented through declared material exposure. |
| S3 | wash and lysis transfers, cold hold, and centrifugation | current | The declared material handling is represented directly. |
| S4 | sample-buffer transfers and heated hold | current | Reducing sample preparation is represented directly. |
| S5 | lane loading and field separation | bridge | SDS-PAGE is represented through the general field-separation model. |
| S6 | PVDF chamber preparation, component routing, field separation, and cold environment | bridge | The source's 200 mA is represented by `field_program(current = 200mA, duration = 4h)`. General field-separation operations record the transfer; biological transfer efficiency is not predicted. |
| S7 | blocking and antibody transfers, repeated washes, and structured imaging | bridge | Target identity, antibody specificity, and instrument-specific acquisition remain structured labels and readout fields. |

## Scope

The program records the declared material path from cultured cells through lysate, gel separation, membrane transfer, antibody treatment, and image acquisition. Biological transfection success, protein-target interpretation, and image analysis remain outside protocol execution.
