# 01 Conversion Record

## Scope

01 is a canonical textbook-style restriction-cloning workflow covering insert
PCR, agarose-gel quality control, conditional PCR cleanup or gel extraction,
EcoRI/HindIII digestion, ligation and controls, DH5alpha transformation,
blue-white screening, colony PCR, miniprep, diagnostic digest, and bidirectional
Sanger confirmation.

## Stored Files

- `source.md`: complete natural-language source protocol
- `source.steps.json`: exported reviewed workflow steps for page navigation; the upstream source remains `source.md` in the local protocol case
- `protocol.culs`: validated benchmark entrypoint
- `Case01_colony_pcr.culs`: reusable one-colony-to-one-PCR-well helper module
- `Case01_sanger_sequencing.culs`: reusable bidirectional Sanger submission module
- `run.md`: validation and runtime summary
- `record.md`: semantic coverage and declared boundaries

## Declared Semantic Boundaries

- Gel images produce structured readouts; the runtime does not infer band
  identity, successful excision, or biological quality.
- Image-selected colony positions cannot currently become material handles
  automatically. Candidate cultures are declared after manual selection.
- Positive colony-PCR candidates are instantiated after manual readout review.
- Sanger alignment and final clone acceptance remain downstream interpretation.
- The source's indefinite 4 C PCR hold is instantiated as a finite 10 minute
  execution window.
- Generic kit buffers and conservative material partitions are used where the
  source does not define vendor formulations or recovery efficiencies.

## Validation

The entrypoint passed the Culsma pipeline and runtime with all 611 active
scheduled steps completed, zero failed steps, 46 inactive branch steps, and
zero diagnostics.
