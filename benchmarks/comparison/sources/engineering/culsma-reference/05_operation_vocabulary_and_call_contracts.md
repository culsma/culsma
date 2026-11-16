# 6. Core Atomic Operators and Call Contracts

Operator and call contracts specify:

1. operation name
2. input parameter names and parameter types
3. return type policy

## 6.1 Layer Boundary (Surface Sugar vs Domain Built-ins)

1. Surface sugar is defined in Chapter 4 and exists for source ergonomics.
2. Source authoring truth is the combination of Chapter 4 source forms and the statement/operator contract set in `6.3.7`-`6.3.19`.
3. The contracts in `6.3.7`-`6.3.19` govern source-level operator behavior; historical frontend spellings are accepted only when listed as compatibility inputs.

## 6.2 Contract Type Notation

### 6.2.1 Argument Type Aliases

1. `Container`: abstract logical container handle type (`STRING` or resolvable identifier); runtime maps it to container state (`volume_uL`, `mass_mg`, `components`, `component_quantities`, `metadata`)
2. `TubeContainer`: concrete `Container` kind for tube-like vessels
3. `WellContainer`: concrete `Container` kind for plate-well vessels
4. `Content`: logical content identity handle (independent of container position)
5. `ContentKind`: enum of canonical material families (§6.2.5 and §6.2.7)
6. `Text`: free-form text (`STRING`)
7. `Bool`: boolean value
8. `Scalar`: unitless numeric scalar
9. `Q[Volume]`: quantity with volume unit
10. `Q[Mass]`: quantity with mass unit
11. `Q[Temperature]`: quantity with temperature unit
12. `Q[Time]`: quantity with time unit
13. `Q[Count]`: discrete-count quantity; the initial supported domain unit is `cells`
14. `Q[Volume|Mass|Count]`: quantity constrained to a material amount axis
15. `List[Container]`: list of logical containers
16. `List[Text]`: list of text values
17. `Quantity`: quantity value with supported unit family (general form)
18. `Record`: key-value map for structured metadata fields
19. `ContainerContents`: target view selecting the material contents carried by a container
20. `ContainerStructureFacet`: target view selecting one physical container-structure facet
21. `ContainerTargetView`: `ContainerContents | ContainerStructureFacet`
22. `HoldTarget`: environment-hold target; `Container`, `ContainerTargetView`, or a group composed of those targets
23. `ContainerGroup`: flat, ordered group of resolvable `Container` values
24. `ContentType`: enum of canonical material types (§6.2.6 and §6.2.7)
25. `ContainerKind`: enum of concrete container kinds (§6.2.4 and §6.2.7)
26. `LegacyText`: a bare token or text value admitted by the classification compatibility rules (§6.2.7–8)

`ContainerGroup` static indexing contract:

1. `group_ref[i]` requires a compile-time decidable non-negative integer `i`.
2. The result is the existing container at ordered position `i`; indexing does
   not allocate, copy, or reconstruct a container.
3. A statically known index outside the group cardinality is rejected before
   execution.
4. Plate selector-derived groups use selector expansion order and therefore
   preserve the selected well's original carrier identity.

### 6.2.2 Return Type Aliases

1. `Void`: no required return object
2. `Container`: resulting logical container
3. `sep_container_group`: fixed two-slot separation result handle
4. `fraction_group`: ordered multi-slot fractionation result handle
5. `data_ref`: single readout result handle
6. `data_group_ref`: grouped readout result handle

### 6.2.3 Container Content Contract

Container content state (runtime record) is modeled as:

1. `volume_uL`: current volume
2. `mass_mg`: current mass
3. `components`: backward-compatible numeric composition summary
4. `component_quantities`: component identity to `{dimension, unit, value}` quantity record
5. `metadata`: container metadata (for example carrier mapping, density)

Container target-accessor surface:

1. `container.contents` denotes the material contents carried by the container.
2. `container.structure.top` denotes the top structural facet of the container.
3. `container.structure.bottom` denotes the bottom structural facet of the container.
4. `container.structure.sidewall` denotes the sidewall structural facet of the container.
5. `container.structure` by itself is a target-view namespace, not a complete target view.
6. `container.structure.top` is closure-agnostic. For closed vessels it may correspond to the cap/seal-facing top structure; for open vessels it denotes the upper rim/top structural facet, not headspace air and not liquid surface.
7. A bare `container` used as a `HoldTarget` defaults to the content-facing target view, equivalent to `container.contents` for env-hold semantics.
8. Container target views are not material container aliases; they do not carry volume, mass, or components and must not be used as mutation targets or as `sep/frac/img/ecp/phy/stream/agit` sample inputs unless a future operator explicitly accepts target-view types.
9. `container.contents[i]` is the defined exception for mutation source position: it selects an indexed, container-backed source portion from the container's current contents state.
10. These accessors are direct target views, not `partition(...)`-style methods and not materialized child containers.
11. No deeper structure path is defined. `container.structure.top.inner` and device-like aliases such as `container.lid` are not container target-view accessors.

Recommended metadata keys:

1. `carrier_kind`: `tube` / `plate` / other
2. `carrier_id`: physical carrier ID
3. `carrier_position`: position label (for example plate well `A1`)
4. `capacity_uL`: container upper volume bound (optional, for capacity enforcement)

### 6.2.4 Container/Carrier and Content Taxonomy

Container taxonomy rules:

1. `Container` is an abstract handle type, not a user-mutable object/class.
2. Concrete container kinds are `tube`, `well`, `chamber`, and `surface`.
3. `plate` is modeled as carrier context; content-bearing runtime state is on well containers.
4. Built-ins must accept abstract `Container` handles and remain independent of frontend sugar spellings.

Content taxonomy rules:

1. Content identity/classification is represented as `Content` records and container-linked content state.
2. Recommended content fields: `content_kind`, `content_type`, `content_code`, `content_name`, and `attrs`.
3. `content_kind` is a closed mid-level material family and answers "what family of material is this?".
4. `content_type` is a closed canonical material category within `content_kind` and answers "what material category is this?".
5. `content_code` and `content_name` identify/display the concrete instance; they are not taxonomy fields.
6. `attrs` is the open metadata record for state, source, preparation, concentration, composition detail, and `attrs.role`.
7. `attrs.role` is the role field. It is not promoted to a top-level `role` argument in this baseline.
8. Source-level family constructors (`blood/reagent/buffer`) are compatibility/ergonomic sugar and do not define canonical `content_kind` names by themselves.

### 6.2.5 Canonical Content Kind Set

`content_kind` set used by strict-mode validation:

1. `bio_entity`
2. `bio_fluid`
3. `bio_cellular`
4. `bio_subcellular`
5. `bio_molecule_or_virus`
6. `chemical`
7. `particulate`
8. `formulation`

Mode note:

1. Strict-mode conformance uses this exact whitelist.
2. Authoring examples and conformance claims must stay within this whitelist.
3. Legacy inputs such as `biosample`, `reagent`, `buffer`, `control`, `waste`, or `fraction` are compatibility inputs only when legacy normalization mode is explicitly enabled.

### 6.2.6 Canonical `content_type` and `attrs.role` Table

This table defines the canonical material taxonomy. `attrs.role`
contains recommended role values for that `kind/type`. It is optional, remains
within the open `attrs` record, and is not a top-level constructor parameter.
The recommendation table does not restrict a material to the listed roles.

| content_kind | canonical content_type | recommended `attrs.role` values |
|---|---|---|
| `bio_entity` | `organism`, `organ`, `tissue`, `other_bio_entity` | `material` |
| `bio_fluid` | `whole_blood`, `plasma`, `serum`, `buffy_coat`, `urine`, `saliva`, `lymph`, `cerebrospinal_fluid`, `tears`, `semen`, `ascites`, `synovial_fluid`, `bronchoalveolar_lavage_fluid`, `other_body_fluid` | `material` |
| `bio_cellular` | `cell_line`, `primary_cells`, `cell_population`, `microbial_cells`, `other_cellular_material` | `material` |
| `bio_subcellular` | `organelle`, `membrane`, `vesicle`, `cytoskeletal_structure`, `other_subcellular_structure` | `sample` |
| `bio_molecule_or_virus` | `dna` | `sample`, `template`, `primer`, `probe`, `marker`, `standard`, `vector` |
| `bio_molecule_or_virus` | `rna` | `sample`, `template`, `guide`, `probe`, `marker`, `standard` |
| `bio_molecule_or_virus` | `protein` | `sample`, `antibody`, `enzyme`, `cytokine`, `marker`, `standard`, `antigen` |
| `bio_molecule_or_virus` | `virus` | `sample`, `vector` |
| `bio_molecule_or_virus` | `other_biomolecule_or_virus` | `sample` |
| `chemical` | `organic_compound` | `substrate`, `inhibitor`, `activator`, `fixative`, `selection`, `precipitation`, `crowding_agent`, `matrix_component` |
| `chemical` | `inorganic_compound` | `salt`, `pH_adjuster`, `ion_source`, `cofactor` |
| `chemical` | `solvent` | `solvent`, `carrier`, `extraction`, `fixative` |
| `chemical` | `detergent` | `lysis`, `permeabilization`, `washing`, `solubilization` |
| `chemical` | `dye` | `stain`, `detection`, `tracking` |
| `chemical` | `other_chemical` | `material` |
| `particulate` | `beads` | `capture`, `cleanup`, `purification`, `enrichment` |
| `particulate` | `resin` | `affinity_purification`, `chromatography`, `capture` |
| `particulate` | `particle` | `labeling`, `calibration` |
| `particulate` | `other_particulate` | `material` |
| `formulation` | `medium` | `culture`, `maintenance` |
| `formulation` | `buffer` | `wash`, `elution`, `binding`, `lysis`, `storage`, `reaction_environment` |
| `formulation` | `supplement` | `supplement`, `selection`, `growth_factor` |
| `formulation` | `master_mix` | `reaction_mix` |
| `formulation` | `gradient_medium` | `density_gradient_separation` |
| `formulation` | `other_formulation` | `material` |

Normalization rules:

1. `content_type` values SHOULD use lowercase snake_case for stable matching.
2. Display labels (human-readable) MAY be stored separately in metadata.
3. `content_type` is closed by the canonical table. Unknown or lab-local material categories should use the appropriate canonical `other_*` type plus `attrs`, `code`, and `name`.
4. Non-standard `attrs.role` values MAY be recorded as ordinary attr metadata; unknown attr keys remain allowed because `attrs` is open metadata.
5. Specific identities such as mitochondrion, exosome, plasmid, amplicon, peptide, polymer class, bead material, unusual body-fluid identity, or virus form belong in `attrs` when they are more specific than the canonical `kind/type` table.
6. Preparation or state labels such as pellet, suspension, lysate, stock, diluted, purified, or amplified belong in `attrs.state` or a more specific attr key, not in `content_type`.
7. Workflow labels such as control, waste, fraction, wash, elution, binding, lysis, detection, or capture belong in `attrs.role`, `attrs.disposition`, or operation-return metadata, not in `content_kind`.
8. Legacy aliases or previously accepted unknown/custom type strings are compatibility inputs; legacy normalization mode should emit a warning and normalize to canonical `content_kind`, canonical `content_type` including an `other_*` fallback when needed, and `attrs`.

Examples:

```culsma
content(kind = bio_fluid, type = whole_blood, code = "WB-001")
content(kind = bio_fluid, type = synovial_fluid, code = "SF-001")
content(kind = formulation, type = buffer, code = "PBS-001", attrs = { role: wash })
content(kind = bio_molecule_or_virus, type = protein, code = "AB-001", attrs = { role: antibody })
content(kind = bio_molecule_or_virus, type = dna, code = "PRIMER-001", attrs = { role: primer })
content(kind = bio_fluid, type = other_body_fluid, code = "AF-001", attrs = { fluid_identity: amniotic_fluid })
```

### 6.2.7 Explicit Content Enum Contract

`ContentKind`, `ContentType`, and `ContainerKind` are distinct enum families.
Their members are named by uppercasing the canonical tokens in §6.2.4–6. For
example, `ContentKind.FORMULATION`, `ContentType.MEDIUM`, and
`ContainerKind.TUBE` denote the corresponding classification values. Member
names are case-sensitive. A member of one family MUST NOT be accepted in a
position requiring another family, even if their textual representations match.

A content classification consists of a kind and a type from that kind's
canonical set. Invalid members and invalid kind/type pairs MUST be rejected.
If either argument is an explicit enum, compatibility normalization MUST NOT
repair an invalid pair.

Bindings follow the language's lexical scope rules. Local bindings shadow enum
namespaces; aliases and parameter defaults preserve enum family and value.
Assignments MUST preserve the binding's enum family. An alias captures the value
at its declaration, so subsequent assignment to the original binding does not
change the alias. Where a branch or loop can change a value, validation MUST
consider the value that reaches the use rather than assume an earlier value
still applies.

Bare canonical tokens and quoted canonical strings are accepted in both strict
and compatibility taxonomy modes. Noncanonical legacy inputs are admitted only
in compatibility mode and are subject to §6.2.8. These compatibility forms do not add enum members.

A classification MUST be valid before it is recorded as material state. Static
errors are rejected when decidable; values determined only during execution are
checked before the affected material write. Serialization and restoration MUST
preserve enum family and value wherever subsequent classification checks depend
on them. Material-record classification fields use canonical text values;
unknown historical values MUST NOT be treated as valid canonical classifications.
Diagnostic placement is specified in Chapter 8.

Example:

```culsma
protocol EnumMedium {
  let medium = container(kind = ContainerKind.TUBE, capacity = 5mL, load = [
    content(kind = ContentKind.FORMULATION, type = ContentType.MEDIUM,
            code = "DMEM_F12_COMPLETE", attrs = { role: culture }):4mL
  ]);
}
EnumMedium();
```

### 6.2.8 Selected Legacy Normalization Conformance Cases

The following cases specify representative legacy conversions. They are not
additional canonical members or an exhaustive alias list. The fallback for each
canonical kind is its unique `other_*` type in §6.2.6. Conversion preserves the
original kind/type and inferred attributes; explicitly supplied attributes take
precedence when material is defined.

| legacy kind | legacy type | canonical kind | canonical type | inferred attrs |
|---|---|---|---|---|
| `biosample` | `dna_stock` | `bio_molecule_or_virus` | `dna` | `{"state":"stock"}` |
| `biosample` | `cell_pellet` | `bio_cellular` | `other_cellular_material` | `{"state":"pellet"}` |
| `buffer` | `wash_buffer` | `formulation` | `buffer` | `{"role":"wash"}` |
| `reagent` | `enzyme` | `bio_molecule_or_virus` | `protein` | `{"role":"enzyme"}` |
| `blood` | `lab_local` | `bio_fluid` | `whole_blood` | `{}` |
| `formulation` | `lab_local` | `formulation` | `other_formulation` | `{"original_type":"lab_local"}` |
| `chemical` | `medium` | `chemical` | `other_chemical` | `{"original_type":"medium"}` |
| `waste` | `lab_local` | `formulation` | `other_formulation` | `{"disposition":"waste","original_type":"lab_local"}` |

Historical material plans may retain the generic `container` kind. It is not an
additional source-level `ContainerKind` member. Compatibility of source forms
and compatibility of historical records are independent contracts.

## 6.3 Global Call Rules

These rules apply to every call, including constructor expressions nested in
`load` items and expressions reached through aliases.

1. All required args `MUST` be provided.
2. Provided args `MUST` be in the allowed arg set. Open records such as `attrs` do not make the call's top-level parameter set open.
3. Duplicate arg names `MUST` be rejected; an implementation MUST NOT silently choose one occurrence.
4. Quantity args `MUST` satisfy declared dimension constraints.
5. `Container` args resolve to runtime container identity and operate on container content state.
6. For volume-increasing writes, if target container has `metadata.capacity_uL`, post-step volume `MUST` satisfy `volume_uL <= capacity_uL`.
7. Invalid non-positive `capacity_uL` is a contract failure.
8. Execution stages operate on canonical IR and plan/runtime structures, not raw source text; some source forms lower into kernel built-ins, while others remain first-class statement/operator IR nodes.

Capacity enforcement:

1. Capacity rules above are enforced through explicit capacity normalization and overflow diagnostics.

### 6.3.1 Operator Layering (Type Strategy)

Domain built-ins are classified by type-dependency level, following the `Quantity` + `Container` strategy.

| Layer | Type dependency focus | Typical return shape | Operations |
|---|---|---|---|
| L1 material/env/readout primitives | IR / plan executable units | material delta, env hold, indexed group, or `data_ref`/`data_group_ref` | `Mutation` (from `mutation_stmt (<<)`), `sep`, `frac`, `img`, `ecp`, `phy`, `env_hold`, `stream`, `constraint` |
| L2 Internal constructor/init ops | container/content initialization and metadata | container/content identity updates | `AllocContainer`, `DefineContent`, `LoadContent`, `AnnotateContent` |

Layering intent:

1. L1 defines executable truth used by runtime.
2. Constructor/init ops are internal canonical targets for frontend sugar and init boundaries, not preferred protocol-body authoring forms.

### 6.3.2 Semantic Domain Layering

Operations are classified by execution semantic domain.

Domain definitions:

1. `material`: operation primarily updates container material state (`volume_uL`, `mass_mg`, `components`, `component_quantities`, metadata).
2. `bridge`: operation consumes container state and also produces structured analytical/process payload.
3. `data`: operation consumes only data payloads/records and does not read/write container material state.

Built-in mapping:

| Operation | Semantic Domain | Primary state effect |
|---|---|---|
| `Mutation` (`mutation_stmt (<<)` plan/runtime op) | `material` | move/merge material across containers |
| `sep` | `material` | split material into a fixed two-slot indexed group |
| `frac` | `material` | split material into an ordered indexed group |
| `stream` | `material` | convert a macro sample into a unit stream |
| `img` / `ecp` / `phy` | `bridge` | consume container state and emit `data_ref` / `data_group_ref` |
| `constraint` | `semantic policy` | attach device-independent execution requirements to a scope or single step |

Domain boundary note:

1. `bridge` operators are container-addressed; they are not pure data operators.
2. Pure `data` operators are reserved for future vocabulary extension and are not part of built-ins.

### 6.3.3 Surface Sugar Lowering Boundary

1. Sugar forms from Chapter 4 are compile-time/frontend forms only.
2. Validation/type/runtime stages operate on canonical IR and plan nodes after frontend compilation.
3. Conformance checks for the source-level contracts in `6.3.7`-`6.3.19` define the authoring surface.
4. Constructor sugar (`tube(...)`, `well(...)`, and inline content specs such as `buffer(...)`, `reagent(...)`, `blood(...)`, or `content(...)` inside `load=[...]`) lowers to `AllocContainer` / `DefineContent` / `LoadContent`.
5. `mutation_stmt (<<)` compiles to first-class mutation IR/plan nodes; it is not authored through `Transfer(...)` / `Mix(...)` in the frontend.
6. Historical operation calls such as `Transfer(...)`, `Mix(...)`, and `Dilute(...)` are not part of the source contract and are rejected by the frontend.

### 6.3.4 Constructor Built-ins (Lowering Targets)

These built-ins are the canonical targets for container/content sugar lowering.
`LegacyText` denotes the retained bare-token/quoted-string compatibility input
from §6.2.7; it is not a new source type declaration:

1. `AllocContainer(kind: ContainerKind | LegacyText, [spec: Text], [carrier_kind: Text], [carrier_id: Text], [carrier_position: Text], [capacity: Q[Volume]], [open: Bool], [label: Text], [barcode: Text], [load: List[content_spec:Q]]) -> Container`
2. `DefineContent(kind: ContentKind | LegacyText, type: ContentType | LegacyText, [code: Text], [name: Text], [attrs: Record]) -> Content`
3. `LoadContent(container: Container, content: Content, amount: Q[Volume|Mass|Count]) -> Container`
4. `AnnotateContent(content: Content, [type: Text], [code: Text], [attrs: Record]) -> Content`

Rules:

1. `AllocContainer` creates a new logical container identity and initializes runtime container state.
2. `DefineContent` creates logical content identity/classification independent of container location.
3. `LoadContent` materializes content into container state using explicit amount axis.
4. `AnnotateContent` updates content classification metadata without implicit quantity mutation.
5. All constructor built-ins above are domain-layer APIs; they are not user-defined functions or object methods.
6. `open` and `load` belong to the constructor/init lowering contract, even though they are authored through frontend sugar rather than direct user calls to `AllocContainer(...)`.
7. `cells` is valid only for content normalized to `bio_cellular`; direct authored load counts MUST be non-negative integers.
8. Applying a count load does not itself add volume. After all constructor load
   items, container finalization may materialize an implicit carrier for a free
   count-only cellular population; that inferred volume participates in
   `capacity_uL` checks and records its assumption policy.

### 6.3.5 Mutation Statement Sugar Contract (`<<`)

Container mutation sugar contract:

Surface forms:

1. `target << [s1, s2, ...]`
2. `target << [s1:q1, s2:q2, ...]`
3. `group_target << [series(src_ref, [q1, q2, ...])]`
4. `target << [source.partition(program_expr)[i]: q]`
5. `target << [container.contents[i]]`
6. `target << [container.contents[i]: q]`

Contract rules:

1. `[]` denotes the mutation source list. It is a statement-specific source-list form, not an ordinary list literal.
2. Full-transfer and quantified source items must not be mixed in one statement.
3. Quantified mode requires unit-bearing quantities, including expression results governed by Section 11.2.1.
4. `series(...)` is the sole ordered-mapping surface form.
5. `series(...)` is valid only when the target is a `container_group_ref`.
6. `series(src_ref, [v1, ...])` requires cardinality equality between target-group size and value-list length.
7. Ordinary `[...]` source-list semantics remain unchanged and do not imply ordered mapping.
8. If an ordinary source item resolves to the same container as `target`, that source item is valid and evaluates as a no-op rather than a validation/runtime error.
9. `source.partition(program_expr)[i]` is a source-local selector form;
   its accepted program set and selector semantics are defined in Section 6.3.11.
10. `container.contents[i]` is a container-backed contents-portion selector valid only as a mutation source item. It does not create a child container and does not make bare `container.contents` a material container alias.
11. If `container.contents[i]` resolves to the same container as `target`, the material transfer is a no-op but the current indexed contents state is disturbed and must not be reused for later `container.contents[j]` reads without a new explicit organization-producing operation.
12. The current public contract is conservative: ordinary mutation of a container with current indexed contents state invalidates that indexed state unless the mutation effect can be applied to the current contents state.
13. A mutation effect is preservable only when it is covered by an explicit selected-part operation such as `container.contents[i]`, or by a preservation contract recorded on the current indexed contents state.
14. Preservation contracts are declared by the operation or program that produced the indexed contents state. A preserving mutation must satisfy the contract through the current execution gate and must map the mutation effect to a declared indexed part, such as a default incoming slot.
15. If the contract is satisfied and the effect is mappable, runtime updates the affected indexed part and keeps the contents state valid. Otherwise the indexed state is marked stale.

Currently defined preservation contracts:

1. `field_retention`: produced by magnetic separation. It requires a matching active field context and declares a retained slot plus a default incoming slot for compatible additions.

Compilation/runtime mapping:

1. Source form compiles to first-class `MutationStmt -> IRMutation -> PlanStep(op="Mutation")`.
2. Full-transfer form uses merge/full-move material semantics at runtime.
3. Quantified form uses ordered quantity transfer semantics at runtime. Volume/mass transfers reuse density bridge rules and proportionally carry component quantities. A count transfer from a homogeneous cell suspension resolves the requested count to carrier volume from the recorded concentration, then uses the ordinary volume-transfer path.
4. Same-container ordinary source items are preserved through lowering and become no-op mutation entries at material execution.
5. Same-container `container.contents[i]` source items preserve material totals but invalidate the current indexed contents state.
6. `series(...)` is compiler-lowered into ordered per-target quantified mutations; it does not introduce a new runtime primitive.

Note:

1. Statement-first mutation is the preferred frontend source style.

### 6.3.5.1 Author-Declared Component Replacement

`MAT-REPLACE-01` defines an author-declared change of tracked composition. It is
distinct from `<<`, which moves existing
material, and from `sep.transitions`, which changes an existing entry's
relationship while preserving its identity and quantity.

```text
lysate.materials.replace({
    lysate.materials.get("CELLS"):
        content(kind = ContentKind.BIO_MOLECULE_OR_VIRUS, type = ContentType.PROTEIN, code = "PROTEIN"):unknown(dimension = mass)
});
```

| Element | Contract |
| --- | --- |
| Receiver | An established container binding followed by `.materials`. |
| Map key | One live entry selected by `materials[index]` or `materials.get(entry_id)` using the same container binding as the receiver. All keys resolve against the pre-change snapshot and must identify distinct entries. |
| Source quantity | Any live entry with a tracked mass, volume, or count quantity. |
| Map value | One `content(...):quantity` material or a nonempty list of such materials. The single form is shorthand for a one-item list. Known mass, volume, and whole-number count and `unknown(dimension = mass)` are accepted. |
| Result | Each selected entry is retired and its replacement list is spliced at the same position. Unselected entries retain identity and order; the statement returns no new container. |

A container with active indexed contents must first have the relevant material
collected into a container. Empty replacement lists are invalid and do not
double as deletion. Coupled multi-source transformations remain outside this
contract.

Product identities and their unquantified yield are author declarations. A
preceding disruption does not calculate this list, and undeclared constituents
are not inferred. Chapter 7 defines retirement, provenance, atomic commit, and
subsequent movement; Section 11.2.2 defines unknown quantity.

### 6.3.6 Core Intrinsic Decomposition

1. Scope is limited to surface sugar and domain built-in contracts.
2. Deeper kernel intrinsic decomposition is intentionally deferred.
3. Future intrinsic API standardization must not break the domain built-in contracts defined here.

### 6.3.7 Atomic Statement Contract Matrix

Alignment rule:

1. Source-level shapes in this subsection MUST follow Chapter 4 when older draft wording conflicts.
2. Operator call contracts are listed in one place.

| Atomic unit | Source shape | Required core args | Run spec / options | Return contract |
|---|---|---|---|---|
| `MutationStmt (<<)` | `target << [sources...];` | `target`, `sources` | no `program`; quantified and full-transfer source styles must not mix; quantified item must be unit-bearing (`src:20uL`) | mutates target/source container material state |
| `agit` | `agit(sample=..., mode=..., [duration=...], [rate=...], [cycles=...]);` | `sample: Container | ContainerGroup`, `mode` | `mode` is `vortex`, `invert`, `flick`, `shake`, or `stir`; `invert` and `flick` use `cycles` and forbid `duration/rate`; other modes forbid `cycles` and use `duration/rate` where required | `Void`; applies agitation independently to each resolved sample |
| `WithEnvStmt` | `with env(...) { [hold(target_expr);] ... }` | `env`, `body`, optional hold target declarations | scalar thermal may use `duration` inside `env(...)` when a finite environment window is required; `thermal_program` forbids outer duration duplication; env targets are declared by positional `hold(target_expr)` or inferred from body; legacy `hold(sample = ...)` is compatibility-only | scoped environment context over statement block |
| `WithConstraintStmt` | `with constraint(...) { ... }` or `stmt with constraint(...);` | `constraint` set, scoped stmt/block | device-independent execution requirements; detailed conflict rules live in semantic validator | applies execution requirement scope to enclosed statement(s) |
| `stream` | `let s = stream(sample = x, unit = single_cell, [panel = p]);` | `sample`, `unit` | `panel` optional; result is unit-stream only, not material split group | `unit_stream_ref` |
| `sep` | `let g = sep(sample=..., program=centrifuge_program(...));` | `sample`, `program` | optional `component_fates` and `transitions`; program is mechanism group; `keep_source` only inside `centrifuge_program(...)` | `sep_container_group` fixed `group[0]` / `group[1]` |
| `frac` | `let fg = frac(sample=..., program=density_gradient_program(...));` | `sample`, `program` | program carries `axis/order/bins` | `fraction_group` ordered containers (`fg[0..n-1]`) |
| `img` | `let obs = img(sample=..., quantity=..., [schema_ref=...], [save_raw=...]);` | `sample`, `quantity` | standard simple quantities use fixed result fields; complex results use `schema_ref` | single `data_ref`; grouped input returns `data_group_ref` |
| `ecp` | `let obs = ecp(sample=..., quantity=..., [schema_ref=...], [save_raw=...]);` | `sample`, `quantity` | standard simple quantities use fixed result fields; complex results use `schema_ref` | single `data_ref`; grouped input returns `data_group_ref` |
| `phy` | `let obs = phy(sample=..., quantity=..., [schema_ref=...], [save_raw=...]);` | `sample`, `quantity` | standard simple quantities use fixed result fields; complex/raw results use `schema_ref` | single `data_ref`; grouped input returns `data_group_ref` |

### 6.3.8 Program / Quantity / Schema Contracts

| Contract kind | Typical statement/operator | Role |
|---|---|---|
| `thermal_program` | `env(thermal=thermal_program(...))`, `pcr(...)` | retained as single-segment thermal trajectory object |
| `centrifuge_program` / `centrifugal_filtration_program` / `magnetic_program` / `field_program` / `filtration_program` / `phase_partition_program` / `precipitation_program` / `disrupt_program` | `sep(..., program=...)` | separation mechanism parameter groups |
| `density_gradient_program` / `chromatography_program` | `frac(..., program=...)` | fractionation mechanism parameter groups |
| `quantity = ...` | `img/ecp/phy` | standard measurement/readout target selector |
| `data_schema(...)` / `schema_ref` | `img/ecp/phy/data_ref` | open result-structure declaration and injection surface |

Program constructors are descriptor/callable values, not executable actions by
themselves. They may be bound with `let` for readability and reuse, but no
runtime step is emitted until a compatible owner consumes the descriptor, for
example `sep(..., program=p)`, `frac(..., program=p)`, or
`with env(thermal=tp)`. The consuming owner is responsible for resolving the
descriptor and enforcing the program family match.

### 6.3.9 Core Contract Boundary

Core source contract:

1. atomic statements and statement-scoped forms from Chapter 4
2. constructor/init lowering targets required to explain those forms
3. readout/result contracts needed by `img/ecp/phy` authoring

Workflow libraries and higher-level standard-library compositions are outside this chapter's scope.

### 6.3.10 Source-Level Contract Summary

Cross-cutting source-level contracts used by the operator-specific sections:

| Topic | Contract |
|---|---|
| Container/content mutation | Source-level mutation is unified as statement-first `<<`; no separate `mix/dilute/transfer` source keywords. |
| Mutation source style | One `<<` source list must be style-consistent: all full-transfer (`src`) or all quantified (`src:Q`). |
| Quantified source item | Must carry physical units (for example `20uL`); unitless ratio form (for example `src:1`) is forbidden. |
| Source-local partition selector | `source.partition(program)[i]` is a mutation-source-only selector for drawing from one ordered portion of a source container without first materializing a `sep` group. |
| Container contents selector | `container.contents[i]` is a mutation-source-only selector for drawing from the current indexed contents state produced by standalone `sep(...)` or `frac(...)`; it is not a child container or bindable value. |
| Environment control | Environment is block-scoped via `with env(...) { ... }`; scalar thermal uses optional `duration` inside `env(...)` when the block needs a finite environment window; `thermal_program.cycles` does not imply block repetition; canonical explicit target declaration is `hold(target_expr)`. |
| Constraint layer | Execution requirements are represented by `constraint(...)`, not by device/program fields; block form is formal semantics and trailing form is sugar. |
| Macro-to-micro transition | `stream(sample=..., unit=...)` is the source-level entry for converting macro samples into unit streams. |
| Binary separation | `sep` is fixed two-output split with ordered return `group[0] / group[1]`, with mechanism `program` and mode-specific slot semantics. |
| Multi-fraction separation | `frac` is ordered multi-output split and is not collapsed into `sep`. |
| Measurement/readout | `img/ecp/phy` use `quantity = ...`; outputs are `data_ref` / `data_group_ref`. |

#### 6.3.10.1 Transfer Delivery Requirements

Execution requirements constrain how an existing operation is performed.
They do not introduce a new material operation or override its quantity and
conservation rules. Requirements must be compatible with the enclosed action
family; incompatibility is `SEM_CONSTRAINT_ACTION_FAMILY_MISMATCH`.

`dropwise` is a standard requirement in the delivery-mode category, valid on
`<<` transfers in either block or trailing form:

```culs
target << [source:150uL] with constraint(dropwise);
```

The liquid is delivered drop by drop. `150uL` remains the total transfer
quantity; a full-transfer source likewise retains full-transfer semantics.
No drop count, per-drop volume, rate, duration, mixing, or material conversion
is inferred. The requirement applies to each source delivery in the statement
and can coexist with compatible requirements such as `gentle`. As with other
standard requirements, additional options are rejected with
`SEM_CONSTRAINT_UNKNOWN_OPTION`.

The requirement is retained in the plan's execution constraints and passed to
the driver. Human instructions must make dropwise delivery explicit; a device
adapter must honor it when executing the command. A driver's declared lack of
support produces `RT_DRIVER_REQUIREMENT_UNSUPPORTED` before material movement.
An instruction or command projection alone does not establish physical execution.

`spread` is a standard delivery-mode requirement for distributing transferred
material evenly across a receiving surface. It accepts the same block and
trailing forms as `dropwise`:

```culs
plate_surface << [suspension:100uL] with constraint(spread, aseptic);
```

The target must resolve to a `surface`, including through protocol parameters;
a different target kind is `SEM_SPREAD_TARGET_NOT_SURFACE`. The requirement
preserves the transferred amount, source and destination identities, and
material accounting. It does not specify a spreading tool or add a second
transfer. `aseptic` is independent and may be combined with it; `spread` and
`dropwise` are not intrinsically exclusive. The requirement must reach the
execution provider, and declared lack of support fails before material movement.

#### 6.3.10.2 Sealed Environment-Hold Requirement

`sealed` is a standard requirement in the environmental-protection category.
It is valid on a pure environment hold and states that the hold target remains
sealed for the duration of that hold:

```culs
with constraint(sealed) {
  with env(thermal = 25C, duration = 2h) {
    hold(elisa_plate);
  }
}
```

For a plate-level closure requirement, the hold target is the plate binding,
not a selected well group. `sealed` does not create a material operation,
container-state transition, implicit seal/unseal step, or persistent closure
state after the constraint scope ends. Applying it to an unrelated action
family is `SEM_CONSTRAINT_ACTION_FAMILY_MISMATCH`.

The requirement is retained on the `env_hold` plan step. Human instructions
must explicitly say that the target remains sealed throughout the hold, and a
device adapter receives `sealed` as a requirement flag. A driver's declared
lack of support produces `RT_DRIVER_REQUIREMENT_UNSUPPORTED` before the hold.

### 6.3.11 Source-Local Partition Selector Contract

Canonical source-level shapes:

1. `target << [source.partition(program_expr)[0]: amount];`
2. `target << [source.partition(program_expr)[1]];`

The selector `source.partition(program_expr)[i]` is a source-local portion
reference. It selects one ordered portion of `source` under the supplied
partition program and is valid only as a mutation source item. It is not a
container, not a materialized group, and not a value that authors may bind with
`let` for later standalone use.

`program_expr` must resolve to a concrete let-bound or inline partition-capable
program descriptor. The accepted program descriptors are the same binary
separation program descriptors used by `sep`; no new program type is introduced
for this selector.

| `partition(program_expr)` accepted program | Required fields | Optional fields | `[0]` | `[1]` |
|---|---|---|---|---|
| `centrifuge_program` | `drive: CentrifugalSetting` | `keep_source` | `supernatant` | `pellet` |
| `magnetic_program` | - | - | `bound` / `retained` | `flowthrough` / `removable` |
| `disrupt_program` | - | `method`, `duration` | `lysate` | `debris_or_residue` |
| `field_program` | exactly one of `voltage: Q[ElectricPotential]`, `current: Q[ElectricCurrent]`, or `field: Q[ElectricPotential]` | `duration` | `target_band_fraction` | `non_target_fraction` |
| `filtration_program` | `membrane`, `drive` | - | `filtrate` | `retentate` |
| `centrifugal_filtration_program` | `membrane`, `drive: CentrifugalSetting` | `duration` | `filtrate` | `retentate` |
| `phase_partition_program` | `solvent` | - | `target_phase` | `other_phase` |
| `precipitation_program` | `reagent` | - | `precipitate` | `supernatant` |

`centrifugal_filtration_program(...)` models membrane/column filtration driven
by centrifugal force. It does not inherit the sedimentation result semantics of
`centrifuge_program(...)`: its stable outputs remain filtrate and retentate.
Its `drive` field has type `CentrifugalSetting`.

Rules:

1. The index must be a compile-time decidable non-negative integer.
2. Current partition selectors are binary; only `[0]` and `[1]` are valid.
3. `density_gradient_program(...)` and `chromatography_program(...)` are not
   accepted by `partition(...)`; they remain `frac` programs.
4. `thermal_program(...)` and readout-oriented descriptors are not partition
   programs.
5. `partition(...)` does not accept free-form named fields such as
   `partition(mode = ..., drive = ...)`; program fields stay inside the concrete
   `*_program(...)` descriptor.
6. A full-transfer selector item moves the whole selected portion. A quantified
   selector item moves the requested amount from the selected portion.
7. Unselected portions, and any residual material left in the selected portion
   after quantified transfer, remain associated with the original source
   container according to the program's partition semantics.
8. `partition(...)` does not replace `sep(...)`. Use `partition(...)` when the
   source container remains the operative container and the partition is only
   consumed by the current transfer. Use `sep(...)` when the protocol needs
   materialized, independently addressable output containers or groups.

Magnetic-bead liquid removal example:

```culs
let mag_sep = magnetic_program(duration = 5min);

with env(field = magnetic_rack) {
  waste << [bead_tube.partition(mag_sep)[1]: 180uL];
}
```

Here `[0]` is the bound/retained bead-associated portion and `[1]` is the
flowthrough/removable liquid portion. The transfer removes liquid from the
source-local portion without first creating a `sep_group`.

### 6.3.12 `sep` Detailed Contract

Canonical source-level shapes:

1. `let sep_group = sep(sample=..., program=centrifuge_program(...));`
2. `sep(sample=..., program=centrifuge_program(...));`
3. `let sep_group = sep(sample=..., program=filtration_program(...), component_fates={RPE1:{filtrate:0%, retentate:100%}});`
4. `let sep_group = sep(sample=..., program=magnetic_program(...), transitions=[transition(subject=sample.materials[1], output=MagneticProgramOutput.FLOWTHROUGH, to=MaterialRelation.FREE)]);`
5. `let sep_group = sep(sample=..., program=magnetic_program(...), transitions=[transition(subject=sample.materials.get("TARGET_PROTEIN"), output=MagneticProgramOutput.FLOWTHROUGH, to=MaterialRelation.FREE)]);`

Effect contract:

1. Let-bound `sep(...)` materializes a two-slot container group and preserves
   existing `sep_group[0]` / `sep_group[1]` return behavior.
2. Standalone `sep(...)` acts on the source container and records an indexed
   contents organization for later `container.contents[0]` /
   `container.contents[1]` mutation-source reads.
3. Standalone `sep(...)` does not create a bindable group unless authored in a
   `let` binding.

Per-content fate contract:

1. `component_fates` is optional and maps content identity to a two-output
   ratio record.
2. Output keys may use the selected program's semantic output names or the
   string slot keys `"0"` and `"1"`.
3. Both outputs are required. Each value is a unitless ratio from 0 to 1 or a
   percentage from 0% to 100%, and the pair must sum to 1 (100%).
4. An authored fate has precedence over association-derived retention and the
   reference partition strategy. It remains subject to quantity-axis and
   conservation validation.
5. The referenced content must exist in the source container at runtime.

Per-material relationship-transition contract:

A live quantity may be a positive known amount or a retained positive share of
an unknown mass. Selection does not grant transition eligibility: unknown-mass
replacement does not support relationship changes on its products
(Sections 7.2.2 and 11.2.2).

1. `transitions` is optional and contains `transition(...)` values scoped to a
   concrete positive-quantity separation output.
2. `subject` is either `sample.materials[index]` or
   `sample.materials.get(entry_id)`, where `materials` is the normalized,
   ordered list of live material entries immediately before the operation.
   The index is a non-negative static integer. The `entry_id` key is a
   statically resolvable non-empty string and is matched exactly within the
   same container. `get(...)` never matches `content_ref`, content codes,
   labels, or prefixes and never falls back to another same-content entry.
3. `output` is one namespaced member of the selected separation program's
   concrete output enum. The enum type must match the concrete program; for
   example, `filtration_program(...)` accepts
   `FiltrationProgramOutput.FILTRATE` or
   `FiltrationProgramOutput.RETENTATE` and rejects members of
   `MagneticProgramOutput`.
4. `to` is a namespaced `MaterialRelation.MEMBER` expression. The
   author-settable
   domain is `free`, `container_surface`, `pellet`, `precipitate`, `disrupted`,
   `bead_bound`, `membrane_bound`, `cell_bound`, and `field_retained`.
   `UNRESOLVED` is an internal sentinel and MUST NOT be authored. String values,
   bare identifiers such as `free`, and members outside this enum are invalid.
5. The directed transition graph has no source/target-pair whitelist. Runtime
   derives the current `MaterialRelation` from the selected entry and accepts
   any target in the author-settable enum domain, subject to target-state
   structural invariants.
6. `free` has no association target and clears the source association. The
   container-associated target relations use the concrete output container as
   their typed association target.
7. `bead_bound`, `membrane_bound`, and `cell_bound` require
   `associated_with` to use either same-sample material selector form. The
   selected association target must have positive quantity in the same output
   and is represented as an
   `AssociationTarget(kind=component_entry, id=...)`.
8. `associated_with` is forbidden for target relations that are not
   component-bound.
9. An authored relationship transition overrides only Table 3 state resolution
   for the selected source entry and output. It does not replace Table 2
   `component_fates`, create material, infer chemistry, or add a separation
   program.
10. Runtime preserves identity and quantity, validates the complete candidate,
    and commits atomically. Any selector, enum, association, output, or
    conservation failure preserves the previously committed source state.

Surface-release authoring pattern:

`filtration_program(membrane = "adherent_cell_surface", drive = "cell_lifter")`
uses the existing surface-boundary partition vocabulary: `FILTRATE` is the
released liquid fraction and `RETENTATE` is the surface-retained fraction. It
does not declare an additional filter material. An author routes cells and
carrier with `component_fates` and declares the selected cellular entry
`MaterialRelation.FREE` in `FILTRATE`. A bound `let lifted = sep(...)` produces
the output group; subsequent transfer collects `lifted[0]`. Detachment therefore
precedes collection and any chemical-lysis material replacement.

Complete recovery is an author-declared fate, not a predicted efficiency. This
pattern preserves count and carrier volume and supplies no rupture, yield,
duration, force, or stroke-count inference. Human execution presents cell-lifter
handling; a robot projection identifies surface release separately from a
filter-device action. Actual device execution requires an adapter for that
handling operation. Existing selector, output, quantity, and association
validation rules apply without additional syntax or diagnostic codes.

`MaterialRelation` has the following closed association contract. In this
table, “required” means that the author must supply
`associated_with = sample.materials[index]` or
`associated_with = sample.materials.get(entry_id)`; “not applicable” means
that the argument MUST NOT appear because the relationship either has no target
or its target is the concrete output container.

| `to` member | Relationship target category | Explicit same-sample material selector | Runtime association target |
|---|---|---|---|
| `MaterialRelation.FREE` | no association | not applicable | association is cleared |
| `MaterialRelation.CONTAINER_SURFACE` | output-container association | not applicable | concrete output container |
| `MaterialRelation.PELLET` | output-container association | not applicable | concrete output container |
| `MaterialRelation.PRECIPITATE` | output-container association | not applicable | concrete output container |
| `MaterialRelation.DISRUPTED` | output-container-scoped state | not applicable | concrete output container |
| `MaterialRelation.FIELD_RETAINED` | output-container-scoped retention | not applicable | concrete output container |
| `MaterialRelation.BEAD_BOUND` | component-entry association | required | selected bead material entry projected into the same output |
| `MaterialRelation.MEMBRANE_BOUND` | component-entry association | required | selected membrane material entry projected into the same output |
| `MaterialRelation.CELL_BOUND` | component-entry association | required | selected cell material entry projected into the same output |
| `MaterialRelation.UNRESOLVED` | internal sentinel | invalid author target | none; the transition is rejected |

Therefore, only `BEAD_BOUND`, `MEMBRANE_BOUND`, and `CELL_BOUND` explicitly
bind one material entry to another material entry. For those three members,
the selected association target must belong to the operation's source
`materials` list and must have positive quantity in the same output. All other
author-settable relations reject the `associated_with` argument.

Program-owned output enums are closed and ordered by `part_id`:

| Program | Output enum | part `0` | part `1` |
|---|---|---|---|
| `sep_program` compatibility surface | `SepProgramOutput` | `FRACTION_A` | `FRACTION_B` |
| `centrifuge_program` | `CentrifugeProgramOutput` | `SUPERNATANT` | `PELLET` |
| `magnetic_program` | `MagneticProgramOutput` | `BOUND` | `FLOWTHROUGH` |
| `disrupt_program` | `DisruptProgramOutput` | `LYSATE` | `DEBRIS_OR_RESIDUE` |
| `field_program` | `FieldProgramOutput` | `TARGET_BAND_FRACTION` | `NON_TARGET_FRACTION` |
| `filtration_program` | `FiltrationProgramOutput` | `FILTRATE` | `RETENTATE` |
| `centrifugal_filtration_program` | `CentrifugalFiltrationProgramOutput` | `FILTRATE` | `RETENTATE` |
| `phase_partition_program` | `PhasePartitionProgramOutput` | `TARGET_PHASE` | `OTHER_PHASE` |
| `precipitation_program` | `PrecipitationProgramOutput` | `PRECIPITATE` | `SUPERNATANT` |

The same enum members define the ordered `sep` result and the `transition`
selector. `sep_group[0]` / `sep_group[1]` remain the stable structural access
surface. `component_fates` record keys remain the program's semantic-role keys
because record-key grammar does not use member expressions; those keys are a
compatibility projection of the enum, not a second output vocabulary.

Return contract:

1. `sep_group[0]` / `sep_group[1]` are the stable user-facing access forms for
   let-bound `sep(...)` output groups.
2. Return arity is fixed at 2 for all included modes.
3. `container.contents[0]` / `container.contents[1]` are valid only when a
   current standalone contents state exists for that container.

`keep_source` contract:

1. Allowed only inside `centrifuge_program(...)`.
2. Values: `supernatant | pellet`.
3. Omitted `keep_source` means both outputs are newly materialized container identities.

Mode contract:

| program | Required fields | Optional fields | `group[0]` | `group[1]` |
|---|---|---|---|---|
| `centrifuge_program` | `drive: CentrifugalSetting` | `keep_source` | `supernatant` | `pellet` |
| `magnetic_program` | - | - | `bound` | `flowthrough` |
| `disrupt_program` | - | `method`, `duration` | `lysate` | `debris_or_residue` |
| `field_program` | exactly one of `voltage: Q[ElectricPotential]`, `current: Q[ElectricCurrent]`, or `field: Q[ElectricPotential]` | `duration` | `target_band_fraction` | `non_target_fraction` |
| `filtration_program` | `membrane`, `drive` | - | `filtrate` | `retentate` |
| `centrifugal_filtration_program` | `membrane`, `drive: CentrifugalSetting` | `duration` | `filtrate` | `retentate` |
| `phase_partition_program` | `solvent` | - | `target_phase` | `other_phase` |
| `precipitation_program` | `reagent` | - | `precipitate` | `supernatant` |

Separation program fields describe the separation mechanism and its direct
mechanism parameters. They do not duplicate block-scoped physical environment
control. Run temperature remains an enclosing `with env(thermal=...)`
condition. `centrifugal_filtration_program(...)` owns an optional action-local
`duration` because it describes the membrane run time. In contrast,
`centrifuge_program(...)` intentionally does not accept `duration`; an authoring
phrase such as "centrifuge 5 min at 4C" is represented as a `sep(...)` statement
inside `with env(thermal=4C, duration=5min)`.

`field_program(...)` describes electric-field-driven separation. It requires
exactly one control setting: `voltage: Q[ElectricPotential]`,
`current: Q[ElectricCurrent]`, or `field: Q[ElectricPotential]`, where `field`
is an alias for `voltage`. Voltage and current are not implicitly converted.

`disrupt_program.method` is a device-independent controlled value:
`mechanical | sonication | shear_homogenization | high_pressure_disruption |
bead_impact`. It records the authored disruption method or physical mechanism;
it does not select a device. Concrete equipment binding remains a planner or
driver concern. Omit `method` when the source does not state one; implementations
must not infer it from the resulting material state.

### 6.3.13 `frac` Detailed Contract

Canonical source-level shapes:

1. `let frac_group = frac(sample=..., program=density_gradient_program(...));`
2. `frac(sample=..., program=density_gradient_program(...));`

Core argument contract:

1. Required source-level args: `sample`, `program`.
2. `program` is `density_gradient_program(...)` or `chromatography_program(...)`.
3. `bins` is integer-like and must satisfy semantic lower bound for ordered fractionation.

Return contract:

1. Return value is `fraction_group` with stable ordered indexing.
2. `frac_group[i]` resolves to container output at index `i`; only compile-time non-negative integer indexing is part of the contract.
3. Order semantics are controlled by `order` (for example `top_to_bottom`).
4. Standalone `frac(...)` records an ordered indexed contents state for later
   `container.contents[i]` mutation-source reads; it does not create a bindable
   group unless authored in a `let` binding.

### 6.3.14 `with env` Contract

Canonical shape:

1. `with env(thermal=..., [co2=...], [rh=...], [duration=...]) { ... }`
2. `with env(thermal=thermal_program(...)) { ... }`
3. `with env(field=...) { ... }`

Explicit target declaration shape:

1. `hold(container_ref);`
2. `hold(container_ref.contents);`
3. `hold(container_ref.structure.top);`
4. `hold(container_ref.structure.bottom);`
5. `hold(container_ref.structure.sidewall);`
6. `hold(group([target_ref_1, target_ref_2, ...]));`

Parameter contract:

1. At least one supported environment dimension is required; dimensions are `thermal` and `field`.
2. `thermal` accepts union type: `Q[Temperature] | thermal_program`.
3. `field` is used for non-thermal field domains such as `mz_separation`.
4. `co2/rh` are optional thermal modifiers; they are not primary dimensions.

Behavior constraints:

1. `thermal = Q[Temperature]`: constant-temperature environment scope. `duration` is required when the block is a pure environment hold/incubation, when the block body needs an enclosing time boundary, or when the author intentionally supplies a finite environment window.
2. `thermal = Q[Temperature]` may omit `duration` for active-operation blocks whose environment lifecycle is exactly the lexical execution of the enclosed statements. This form represents instructions such as assembling or mixing a reaction under a stated temperature condition without inventing a finite hold time.
3. `thermal = thermal_program`: program-driven thermal scope; `duration` is forbidden because total time is derived by program.
4. `field = ...`: field-domain environment scope; outer `duration` is forbidden.
5. `co2/rh` require `thermal`; they are forbidden when `thermal` is program-typed.
6. `duration` and `thermal_program.cycles` describe the environment program itself and MUST NOT imply block-body repetition.
7. Block-body statements execute once in lexical order; per-cycle/stage hooks are not part of the contract.
8. When a single enclosed action has no action-local duration field and the source supplies an execution time boundary, the enclosing scalar thermal `duration` supplies the time boundary for executing that action under the stated environment; for example centrifugation time may be expressed by wrapping `sep(..., program=centrifuge_program(drive=...))` in `with env(thermal=..., duration=...)`.
9. Action-local duration remains distinct from environment duration. Operations such as `agit(...)` do not inherit `env.duration`; if the action itself requires a duration, the action must declare it.

Target declaration constraints:

1. `hold(...)` is only valid directly inside a `with env(...)` block.
2. Canonical `hold(...)` accepts exactly one positional `HoldTarget` expression and no named arguments.
3. `hold(...)` records environment-hold/reporting targets for the nearest enclosing `with env(...)`; it does not define the environment scope and does not introduce temperature, time, program, device, or execution-requirement parameters.
4. Direct-child `hold(...)` declarations are not standalone executable actions. If a `with env(...)` block contains only `hold(...)` declarations, the block lowers to a pure env hold over those targets.
5. If a `with env(...)` block contains direct-child `hold(...)` declarations plus executable body statements, those declarations record environment-hold targets for that layer and the remaining statements execute under that same layer. They do not narrow the lexical environment scope, impose ordering, or exclude other body statements from the environment context.
6. Direct-child `hold(...)` declarations may appear anywhere in the immediate `with env(...)` body and are collected as environment targets rather than executable steps.
7. If a `with env(...)` block contains no explicit `hold(...)` declarations, env targets are inferred from enclosed executable statements as in the body-inference model.
8. Bare container targets in `hold(container_ref)` are content-facing by default. Authors should use a structure facet such as `container_ref.structure.top` when the controlled object is the physical container structure rather than the contained material.
9. Legacy `hold(sample = container_ref)` may be accepted by implementations as compatibility input, but it is not the canonical source form for new examples.
10. `hold(...)` inside nested `if`, `repeat`, `with constraint`, or other non-env sub-blocks is not a valid target declaration for the enclosing env block.

Target semantics:

1. Chapter 6 defines the `HoldTarget` type and `with env` target-declaration
   contract; Chapter 4 defines the corresponding source spelling.
2. `with env(...)` owns environmental conditions, `thermal_program(...)` owns
   thermal trajectory fields, and `hold(...)` owns only target declaration.
3. A container structure-facet target is not a sample/material state and must
   not be interpreted as sample thermal state.
4. A bare container remains ergonomic for ordinary thermal holds by defaulting
   to its contents in `HoldTarget` position.
5. `container.contents` and `container.structure.<facet>` are direct target
   views, not partitioning methods and not new container allocation.
6. `container.structure.top` is closure-agnostic and must not be lowered to a
   device-specific lid/cap concept.
7. A PCR anti-condensation or top-structure heating requirement is represented
   as a structure-facet hold such as `hold(pcr_tube.structure.top)` under a
   thermal env, not as sample temperature.

### 6.3.15 Agitation Contract (`agit`)

1. Shape: `agit(sample=..., mode=..., [duration=...], [rate=...], [cycles=...]);`.
2. `sample` accepts one `Container` or a flat, ordered `ContainerGroup`.
3. An explicit `group([...])` and a let-bound group have the same agitation semantics.
4. A grouped sample is a batch target: the same agitation action applies independently to each member. Grouping does not merge members or transfer material between them.
5. `mode` is one of `vortex`, `invert`, `flick`, `shake`, or `stir`.
6. `invert` and `flick` use `cycles` and forbid `duration` and `rate`; other modes forbid `cycles` and use `duration` and `rate` where required by the action.
7. `flick` denotes gentle tube flicking, distinct from inversion, shaking,
   vortexing, or plate tapping. Its cycle count may be omitted when the source
   procedure gives no count; omission does not imply an inferred count.
8. `agit` does not return a material or data value.
8. Chapter 7 defines the per-container material-state effect.

### 6.3.16 Readout Family Contract (`img/ecp/phy`)

`img`:

1. Shape: `let obs = img(sample=..., quantity=..., [schema_ref=...], [save_raw=...]);`
2. Core args: `sample`, `quantity`.
3. Quantity set: `uv_absorbance | fluorescence | colorimetric | customized`.
4. Return: single-sample input yields `data_ref`; grouped sample input yields `data_group_ref`.

`ecp`:

1. Shape: `let obs = ecp(sample=..., quantity=..., [schema_ref=...], [save_raw=...]);`
2. Quantity set: `ph | conductivity | dissolved_oxygen | orp | customized`.
3. Return: single-sample input yields `data_ref`; grouped sample input yields `data_group_ref`.

`phy`:

1. Shape: `let obs = phy(sample=..., quantity=..., [schema_ref=...], [save_raw=...]);`
2. Quantity set: `temperature | pressure | flow_rate | mass | volume | humidity | current | customized`.
3. Return: single-sample input yields `data_ref`; grouped sample input yields `data_group_ref`.

Cross-family rule:

1. Readout operators are data-producing operators and are not container-mutation operators.
2. `data_ref` uses a shared envelope plus family- and quantity-specific `result` payload.
3. `result` field sets are determined by `family + quantity`, not by free-form runtime text.
4. `raw_artifact` (when present) is auxiliary evidence and does not replace structured `result`.
5. Optional `export_refs` may attach richer external/profile-specific result exports; they do not replace `result` as the source-level control surface.
6. Grouped sample input yields `data_group_ref`, whose order matches the input container group.

### 6.3.17 Core Contract Boundary

1. Sections `6.3.7` to `6.3.19` define source-level contracts for
   the core atomic operator surface.
2. The core source path covers constructor/init, `<<`, `agit`, `with env`,
   `sep`, `frac`, source-local partition selectors, `img`, `ecp`, `phy`, and
   indexed group references.
3. Higher-level workflow libraries are outside the core contract defined in
   this chapter.
4. Compatibility behavior must not change the source-level contracts defined in
   this chapter.

### 6.3.18 Separation vs Fractionation Boundary

Principle distinction:

1. `sep` is binary semantic split (`target` vs `non-target`) and returns fixed two-slot outputs.
2. `frac` is ordered distribution split across multiple bins and returns ordered multi-slot outputs.
3. If domain intent is to preserve distribution/layer profile, use `frac` instead of collapsing to `sep`.

Classification note:

1. `sep` and `frac` are parallel atomic operators under the same broad separation family.
2. They are not aliases of each other.

### 6.3.19 Readout Category Map

| Category | Typical scenarios | Preferred atomic path | Typical output form |
|---|---|---|---|
| Optical quantification | UV/optical fluor/colorimetric quant | `img(sample=..., quantity=...)` | scalar/data readout reference |
| Electric-field-separated readout | gel/capillary style readout | `sep(sample=..., program=field_program(...))` + `img(sample=..., quantity=customized, schema_ref=...)` | band/peak data reference |
| Microscopy imaging | fixed/live-cell imaging | `img(sample=..., quantity=customized, schema_ref=...)` | image data reference |
| Physiological state readout | viability / pH / conductivity | `img(...)` (indicator route) or `ecp(sample=..., quantity=...)` | data reference |
| Separation-coupled readout | post-separation flow/seq/ms readout | decomposition path (`stream/repeat/env/img/phy/data_ref`) | data reference |

## 6.4 Authoring Boundary

Core source-level authoring boundary:

1. `target << [sources...]` for material transfer/merge/collection
2. `agit(...)` for agitation/mixing behavior
3. `source.partition(program)[i]` inside mutation source items for
   source-local portion selection
4. `sep(..., program=...)` and `frac(..., program=...)` for separation/fractionation
5. `img(...)`, `ecp(...)`, `phy(...)` for readout
6. constructor sugar and `with env` / `with constraint` forms as defined by Chapters 4 and 5
7. `container.materials.replace(...)` for selector-keyed author-declared replacement in Section 6.3.5.1

## 6.5 Contract Failures and Diagnostics

Call-contract validation covers:

1. unknown operation names, commonly reported as `SEM_UNKNOWN_STEP`
2. missing required arguments, commonly reported as `SEM_MISSING_REQUIRED_ARG`
3. unknown argument names, commonly reported as `SEM_UNKNOWN_ARG`
4. duplicate argument names, commonly reported as `SEM_DUPLICATE_ARG`
5. dimension/unit mismatches, reported with `TYPE_*` diagnostics
6. state-dependent material feasibility, such as capacity bounds, reported with
   `MAT_*` diagnostics

The complete diagnostic list and earliest-stage placement are specified in
Chapter 8.

## 6.6 Check Placement

1. Membership and arg-shape checks: semantic validation.
2. Unit/dimension checks: typecheck stage.
3. State-dependent feasibility: runtime/material stage.

## 6.7 Conformance Boundary

Validators, typecheckers, planners, runtime material handlers, and examples
must conform to these operation vocabulary and call contracts; they do not
define separate operation behavior.
