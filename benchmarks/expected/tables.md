# Recomputed benchmark tables

Case 00 is reported separately and excluded from every total.

## Structured experimental detail

| Case | source_steps | descriptor_items |
| --- | ---: | ---: |
| 01 | 18 | 511 |
| 02 | 12 | 208 |
| 03 | 14 | 261 |
| 04 | 10 | 157 |
| 05 | 11 | 1359 |
| 06 | 9 | 507 |
| 07 | 10 | 172 |
| 08 | 8 | 94 |
| 09 | 7 | 139 |
| 10 | 42 | 100 |
| 11 | 18 | 72 |
| 12 | 11 | 58 |
| 13 | 27 | 77 |
| 14 | 11 | 214 |
| Total | 208 | 3929 |

Worked example 00: source_steps=7, descriptor_items=25.

## Material-state continuity

| Case | reused_objects | later_use_links | active_steps | completed_steps |
| --- | ---: | ---: | ---: | ---: |
| 01 | 42 | 59 | 611 | 611 |
| 02 | 43 | 99 | 344 | 344 |
| 03 | 28 | 48 | 275 | 275 |
| 04 | 37 | 173 | 778 | 778 |
| 05 | 33 | 88 | 871 | 871 |
| 06 | 28 | 33 | 739 | 739 |
| 07 | 20 | 28 | 135 | 135 |
| 08 | 3 | 16 | 133 | 133 |
| 09 | 18 | 20 | 176 | 176 |
| 10 | 8 | 33 | 127 | 127 |
| 11 | 4 | 14 | 64 | 64 |
| 12 | 4 | 11 | 99 | 99 |
| 13 | 7 | 25 | 55 | 55 |
| 14 | 24 | 33 | 265 | 265 |
| Total | 299 | 680 | 4672 | 4672 |

Worked example 00: reused_objects=3, later_use_links=8, active_steps=27, completed_steps=27.

## Result traceability

| Case | reagent_records | touched_containers | final_material_states |
| --- | ---: | ---: | ---: |
| 01 | 39 | 115 | 29 |
| 02 | 15 | 52 | 24 |
| 03 | 25 | 56 | 24 |
| 04 | 20 | 37 | 17 |
| 05 | 16 | 33 | 9 |
| 06 | 29 | 180 | 124 |
| 07 | 11 | 39 | 20 |
| 08 | 15 | 17 | 2 |
| 09 | 21 | 33 | 7 |
| 10 | 7 | 8 | 4 |
| 11 | 5 | 8 | 5 |
| 12 | 4 | 6 | 4 |
| 13 | 4 | 7 | 4 |
| 14 | 18 | 42 | 14 |
| Total | 229 | 633 | 287 |

Worked example 00: reagent_records=2, touched_containers=5, final_material_states=3.
