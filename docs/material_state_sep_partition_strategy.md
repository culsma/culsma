# Material State Separation Partition Strategy

Status: implemented default runtime behavior
Date: 2026-05-08
Scope: runtime material-state tracking for `sep(...)`

## Goal

Runtime material state is an execution ledger. It should make final products,
important retained materials, and important reagent consumption understandable.
It is not a precise physical simulation.

The current generic `sep(...)` behavior splits every component by the same
fixed ratio. That makes wash buffers, extraction reagents, and other carried
liquids appear as major final product components even when the protocol has
selected the correct output slot.

This design replaces the generic 50/50 behavior with program-specific
approximate partition rules:

1. each separation program defines the two output slots;
2. each component class gets an approximate percentage into each slot;
3. small residuals can be marked as trace or ignored by final-product display;
4. unknown or user-defined material uses a conservative fallback until explicit
   author overrides are added.

## Core Idea

For each component in the input container, runtime computes:

```text
amount in group[0] = input amount * group0_ratio
amount in group[1] = input amount * group1_ratio
```

The ratios are not intended to be exact. They are semantic defaults that keep
material tracking plausible.

These ratios are for component fate only. They must not be treated as physical
volume or mass estimators. Until Culsma has explicit volume partition or
carryover-volume syntax, `volume_uL` and `mass_mg` should continue to use the
runtime's conservative bulk material accounting. Component partitioning only
affects `components`, component identity, trace reporting, and final-product
summary behavior.

Example for centrifuging a cell culture and keeping the pellet:

```text
liquid medium -> 99% supernatant, 1% pellet carryover
cells         -> 1% supernatant, 99% pellet
cell-bound target -> follows cells
```

If the reporting threshold is 10%, the 1% liquid carryover does not compete as
a major final product component.

## Runtime Rules

1. Runtime does not infer special behavior from literal names like `DNA`,
   `ETOH70`, or `PCI`.
2. Runtime uses component metadata or explicit protocol annotations to choose a
   component class.
3. Non-standard runtime state uses a conservative 50/50 fallback as a guard;
   user-authored protocols should be rejected before runtime.
4. Defaults are approximate. User-authored ratio overrides remain a follow-up
   syntax/API item rather than current runtime behavior.
5. Trace filtering should affect reports first. Conservation-sensitive raw
   material state should either keep trace values or record explicit loss/prune
   events.

## Fixed Content-Type Mapping

Current Culsma content descriptors already have:

```text
kind = biosample | reagent | buffer | control | fraction | waste | other
type = standard lower_snake_case token from the supported content vocabulary,
       or a custom_* token
```

This section closes the first-version mapping for all current standard content
types. User-defined `custom_*` values are allowed, but they are not added to the
fixed standard mapping table.

Mapping rules:

1. `kind` gives a coarse class.
2. `type` refines or overrides the coarse class.
3. Standard types listed below have fixed partition classes.
4. `custom_*` types are accepted but are not fixed standard types. Runtime uses
   a kind-level default (`buffer` as process liquid, `reagent` as liquid
   reagent, other kinds as `custom`) unless material state provides
   `component_partition_ratios`.
5. `control`, `waste`, and `other` currently have no standard type set for
   separation partitioning.

| Kind | Standard `type` values | Partition class | Notes |
| --- | --- | --- | --- |
| `biosample` | `plasma`, `serum`, `solution` | `liquid_matrix` | Liquid-like biosample matrix. |
| `biosample` | `cell_suspension`, `mixed_cells`, `adherent_cells` | `pelletable_cells` | Cells or cell-like material; centrifuge-biased to pellet. |
| `biosample` | `cell_pellet` | `pelletable_material` | Already pellet-like. |
| `biosample` | `cell_lysate`, `extract`, `molecular_extract` | `soluble_biosample_matrix` | Treated as liquid/soluble unless a separation override marks a retained target. |
| `biosample` | `dna_sample`, `sample_dna`, `dna_solution`, `dna_lysate`, `dna_stock`, `purified_dna`, `template_dna`, `amplicon`, `plasmid_vector`, `dna_insert` | `molecular_target` | Soluble target by default; precipitable/field target only when the program or override uses that target behavior. |
| `biosample` | `reaction_mix` | `liquid_reaction_matrix` | Mixed liquid reaction material. |
| `biosample` | `tissue_piece` | `solid_sample` | Solid or particulate sample; centrifuge/filtration behavior should usually retain it. |
| `biosample` | `whole_blood`, `cell_or_tissue_sample` | `composite_sample` | Composite material; default should warn or require override for precise fraction fate. |
| `buffer` | `buffer`, `water`, `diluent`, `te_buffer`, `elution_buffer`, `resuspension_buffer`, `phosphate_buffer`, `reaction_buffer`, `culture_media`, `culture_medium`, `reaction_media`, `media`, `drug_stock`, `sequencing_read_buffer`, `test_buffer` | `liquid_matrix` | Liquid matrix; usually follows supernatant/filtrate/liquid phase. |
| `buffer` | `lysis_buffer`, `binding_buffer`, `nucleic_acid_extraction_buffer`, `molecular_extraction_buffer` | `process_liquid_matrix` | Liquid processing buffer; default is liquid-like, but program-specific overrides may be common. |
| `buffer` | `wash_buffer`, `ethanol_wash_buffer`, `column_wash_buffer`, `column_wash_buffer_1`, `column_wash_buffer_2` | `wash_liquid` | Wash liquid; usually should not dominate retained product reports. |
| `reagent` | `precipitation_reagent` | `precipitation_liquid` | Liquid reagent used to drive precipitation; usually follows supernatant/liquid phase with carryover. |
| `reagent` | `magnetic_bead` | `capture_particle` | Retained/captured support, not a liquid reagent. |
| `reagent` | `agarose_powder`, `powder` | `solid_particle` | Solid material, not a liquid reagent. |
| `reagent` | `taq_polymerase`, `enzyme`, `fluor_antibody` | `soluble_reagent` | Soluble reagent/protein-like material. |
| `reagent` | `feed`, `nutrient_feed`, `vehicle_control`, `positive_control_compound`, `compound_x_low`, `compound_x_mid`, `compound_x_high`, `compound_x_max`, `drug_x`, `compound_x_stock` | `soluble_compound` | Soluble compound/feed/control material. |
| `reagent` | `qpcr_master_mix`, `standard_mix`, `fluor_quant_mix`, `fragmentation_reagent`, `adapter_mix`, `ligation_reagent`, `cleanup_reagent`, `amplification_reagent`, `ionization_reagent`, `anticoagulant` | `liquid_reagent` | Generic soluble/liquid reagent. |
| `reagent` | `dna_stain`, `plate_stain` | `stain_reagent` | Soluble stain; should not become final product identity unless explicitly retained. |
| `fraction` | `supernatant`, `filtrate`, `target_phase` | `liquid_fraction` | Fraction already named as a liquid/output phase. |
| `fraction` | `pellet`, `precipitate`, `washed_dna_pellet` | `retained_fraction` | Fraction already named as retained/pellet-like material. |
| `fraction` | `retentate` | `retained_fraction` | Material retained by a filter or column. |
| `buffer` | `custom_*` | `process_liquid_matrix` | User-defined buffer; default follows liquid/process-buffer behavior unless an explicit ratio is provided. |
| `reagent` | `custom_*` | `liquid_reagent` | User-defined reagent; default follows soluble/liquid reagent behavior unless an explicit ratio is provided. |
| other supported kinds | `custom_*` | `custom` | User-defined content with no safe kind-level behavior; default split is 50/50 unless an explicit ratio is provided. |

Program strategies then map these partition classes to ratios. For example,
`liquid_matrix` uses the liquid rule in `centrifuge_program`, while
`pelletable_cells` uses the pelletable rule.

Known first-version limitation:

- `composite_sample` is intentionally not decomposed. For example,
  `whole_blood` contains both liquid and cellular material, but the current
  component ledger treats it as one component. The default uses conservative
  split behavior unless the protocol initializes separate plasma and cell
  components or provides explicit partition overrides.
- Custom content types are accepted by the validator, but the runtime does not
  infer scientific behavior from the custom name. It uses only the declared
  `kind` for a default and can be controlled through
  `component_partition_ratios`.

## Default Strategy Table

These ratios are default runtime behavior, not scientific constants. They provide a
plausible material-state ledger when the author does not provide explicit
partition values.

Interpretation:

- `0.99 / 0.01`: very strong bias with small carryover;
- `0.95 / 0.05`: biased but with more loss or residue;
- `0.50 / 0.50`: unknown, conservative fallback, should warn.

| Program | Slot contract | Component class | `group[0]` ratio | `group[1]` ratio | Notes |
| --- | --- | --- | ---: | ---: | --- |
| `centrifuge_program` | `group[0] = supernatant`, `group[1] = pellet` | liquid / matrix | 0.99 | 0.01 | Most liquid remains in the supernatant; pellet has small carryover. |
| `centrifuge_program` | `group[0] = supernatant`, `group[1] = pellet` | particles / cells / pelletable material | 0.01 | 0.99 | Pelletable material mostly sediments. |
| `centrifuge_program` | `group[0] = supernatant`, `group[1] = pellet` | material bound to particles | 0.01 | 0.99 | Bound material follows the particles. |
| `phase_partition_program` | `group[0] = target_phase`, `group[1] = other_phase` | target-phase material | 0.99 | 0.01 | Target material mostly follows the selected phase. |
| `phase_partition_program` | `group[0] = target_phase`, `group[1] = other_phase` | other-phase solvent / extraction reagent | 0.01 | 0.99 | Extraction solvent mostly follows the non-target phase. |
| `phase_partition_program` | `group[0] = target_phase`, `group[1] = other_phase` | interface / contaminant | 0.50 | 0.50 | Unknown behavior uses the conservative fallback. |
| `precipitation_program` | `group[0] = precipitate`, `group[1] = supernatant` | precipitable target | 0.95 | 0.05 | Product mostly enters the precipitate, with some loss. |
| `precipitation_program` | `group[0] = precipitate`, `group[1] = supernatant` | liquid / matrix / precipitation reagent | 0.01 | 0.99 | Most liquid remains in the supernatant; precipitate has carryover. |
| `filtration_program` / `centrifugal_filtration_program` | `group[0] = filtrate`, `group[1] = retentate` | pass-through material | 0.99 | 0.01 | Material that can pass the filter mostly enters filtrate. |
| `filtration_program` / `centrifugal_filtration_program` | `group[0] = filtrate`, `group[1] = retentate` | retained material | 0.01 | 0.99 | Material retained by the membrane/column mostly stays in retentate. |
| `filtration_program` / `centrifugal_filtration_program` | `group[0] = filtrate`, `group[1] = retentate` | wash liquid / matrix | 0.99 | 0.01 | Wash liquid mostly leaves through filtrate. |
| `magnetic_program` | `group[0] = bound`, `group[1] = flowthrough` | captured / bead-bound material | 0.99 | 0.01 | Captured material mostly remains bound. |
| `magnetic_program` | `group[0] = bound`, `group[1] = flowthrough` | unbound material / wash liquid | 0.01 | 0.99 | Unbound material mostly leaves in flowthrough. |
| `disrupt_program` | `group[0] = lysate`, `group[1] = debris_or_residue` | released material | 0.95 | 0.05 | Released contents mostly enter lysate. |
| `disrupt_program` | `group[0] = lysate`, `group[1] = debris_or_residue` | debris / residue | 0.05 | 0.95 | Debris mostly remains residue. |
| `field_program` | `group[0] = target_band_fraction`, `group[1] = non_target_fraction` | target-band material | 0.95 | 0.05 | Target material mostly enters the selected band. |
| `field_program` | `group[0] = target_band_fraction`, `group[1] = non_target_fraction` | non-target material | 0.05 | 0.95 | Non-target material mostly remains outside the target band. |
| any `sep` program | program-specific slots | unknown component class | 0.50 | 0.50 | Conservative fallback. |

User override need remains high for most programs. Defaults should be good
enough for plausible reports, but explicit ratios should be available when the
author knows the expected recovery or carryover.

## Current Implementation

`src/culsma/runtime/material_compute.py` implements the default behavior through
`SepPartitionStrategy` subclasses selected by program kind:

| Program | Strategy class |
| --- | --- |
| `centrifuge_program` | `CentrifugePartitionStrategy` |
| `phase_partition_program` | `PhasePartitionStrategy` |
| `precipitation_program` | `PrecipitationPartitionStrategy` |
| `filtration_program` | `FiltrationPartitionStrategy` |
| `centrifugal_filtration_program` | `CentrifugalFiltrationPartitionStrategy` |
| `magnetic_program` | `MagneticPartitionStrategy` |
| `disrupt_program` | `DisruptPartitionStrategy` |
| `field_program` | `FieldPartitionStrategy` |
| unknown `sep` program | base `SepPartitionStrategy` fallback |

The strategy affects component fate only. `volume_uL` and `mass_mg` use
conservative bulk accounting and are not derived from these component ratios.

The runtime also keeps internal `component_partition_classes` metadata on
intermediate containers when a program turns a component into a retained
fraction. That metadata is part of the internal material ledger and is stripped
from public protocol returns.

## Conformance Hooks

| Requirement | Test |
| --- | --- |
| `centrifuge_program` sends liquid to `group[0]` and pelletable material to `group[1]`. | `test_sep_centrifuge_partitions_liquid_to_supernatant_and_cells_to_pellet` |
| `phase_partition_program` keeps target-phase material separate from extraction reagent. | `test_sep_phase_partition_sends_target_phase_material_away_from_extraction_reagent` |
| `precipitation_program` keeps target in precipitate and liquid in supernatant. | `test_sep_precipitation_sends_target_to_precipitate_and_liquid_to_supernatant` |
| `filtration_program` keeps pass-through liquid in filtrate and retained target in retentate. | `test_sep_filtration_sends_liquid_to_filtrate_and_target_to_retentate` |
| `centrifugal_filtration_program` preserves the filtration slot contract while carrying centrifugal run parameters. | `test_sep_centrifugal_filtration_uses_filtrate_and_retentate_slots` |
| `magnetic_program` keeps target and beads in bound fraction and wash in flowthrough. | `test_sep_magnetic_sends_target_and_beads_to_bound_fraction` |
| `disrupt_program` sends released material to lysate and cells/debris to residue. | `test_sep_disrupt_sends_released_material_to_lysate_and_cells_to_residue` |
| `field_program` sends target to selected band/fraction and non-target material away. | `test_sep_field_sends_target_to_band_fraction_and_stain_to_non_target_fraction` |
| custom components use the conservative fallback by default. | `test_sep_custom_components_use_conservative_equal_split_by_default` |
| custom components can use explicit per-component partition ratios. | `test_sep_custom_component_uses_configured_partition_ratio` |
| DNA cleanup issue path keeps wash/extraction reagents out of public product return and preserves raw ledger internally. | `test_runtime_sep_partition_keeps_dna_cleanup_product_from_wash_reagents` |

## Future Override Shape

The exact syntax is not frozen. A later language/API addition should support an
authoring shape equivalent to:

```text
partition_rules = [
  class liquid_matrix -> group[0]: 0.99, group[1]: 0.01,
  class pelletable -> group[0]: 0.01, group[1]: 0.99
]
```

or a per-component equivalent:

```text
partition_rules = [
  component culture_medium -> group[0]: 0.99, group[1]: 0.01,
  component cells -> group[0]: 0.01, group[1]: 0.99
]
```

The current runtime API supports the per-component equivalent through source
container metadata:

```text
metadata.component_partition_ratios = {
  CUSTOM: {0: 0.2, 1: 0.8}
}
```

The public authoring syntax for this metadata is still a future language/API
design item.

## Trace And Reporting

Material tracking needs two views:

1. raw ledger: the best available approximate component amounts;
2. report view: final product and major components.

Trace policy should prevent tiny carryover from becoming a misleading final
product identity. A possible future default:

```text
major_component_threshold = 0.10 of returned container component total
trace_component_threshold = 0.01 of returned container component total
```

Components below the major threshold should not win `primary_component`.
Components below the trace threshold may be hidden from compact reports, while
remaining available in detailed material-state output.

## Remaining Design Items

1. Whether overrides live on `sep(...)`, inside `program(...)`, or in a separate
   material policy block.
2. Whether unknown components warn only, fall back to proportional split, or
   require explicit rules in strict mode.
3. Whether trace pruning changes only reports or also mutates stored
   `components`.
4. How conservation checks account for trace pruning if raw state is mutated.
