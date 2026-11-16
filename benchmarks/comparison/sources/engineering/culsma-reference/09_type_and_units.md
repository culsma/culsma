# 11. Type and Units

## 11.1 Scope

Type checking connects expression values to operation contracts. A quantity has
both a numeric value and a physical dimension; a unitless Number can scale a
quantity but does not satisfy a dimension-constrained argument by itself.
Operation catalogs define the required dimensions. Material execution checks
whether the requested amount is available and transferable.

The same quantity rules apply to direct expressions, local bindings, and
concrete protocol arguments. Author-declared unknown material mass is a separate
quantity state, defined below; it is not a numeric operand.

## 11.2 Quantity Requirement Model

A dimension-constrained argument must resolve to a quantity with a recognized
unit and a compatible dimension. Constructor loads and quantified transfers
accept volume, mass, or count. Capacity accepts volume, and duration accepts
time. These requirements apply to the result of an expression, not just to the
literal spelling at the use site.

### 11.2.1 Quantity Arithmetic (`QTY-ARITH-01`)

| Operands | Result |
| --- | --- |
| Quantity × Number, Number × Quantity | Quantity in the quantity operand's unit |
| Quantity ÷ Number | Quantity in the numerator's unit |
| Compatible Quantity +/− Quantity | Convert the right operand into the left unit; retain the left unit |
| Compatible Quantity ÷ Quantity | Unitless Number after conversion |
| Unary −Quantity | Negated value with the same unit |

For example, `10mL / 1000` yields `0.01mL`, equivalent to `10uL`;
`1mL - 100uL` yields `0.9mL`. These results can be used directly as load or
transfer amounts, bound with `let`, or calculated in a parameterized protocol
loaded from another source file. A unitless ratio cannot itself fill a
unit-bearing load or transfer slot.

Arithmetic retains numerical precision for subsequent operations; display
rounding MUST NOT determine a later aliquot or diluent subtraction. Material
projections may normalize volume to `uL` and mass to `mg` while preserving the
represented amount. This does not require arbitrary-precision arithmetic.

Quantity/scalar addition, incompatible dimensions, compound-unit multiplication,
and inverse-unit division are outside this model. A known zero denominator or
non-finite calculation is rejected. Conversion is limited to the unit families
and constraints in Section 11.3.

### 11.2.2 Unknown Material Quantity

The author-declared replacement statement in Section 6.3.5.1 accepts
`unknown(dimension = mass)` for a product whose identity is declared but whose
yield has not been quantified. It is a material quantity state, not a unitless
Number, zero, or a value usable in ordinary quantity arithmetic. Replacement
does not accept this form in an initial load or as a transfer amount.

An unknown mass retains its dimension, an absent numeric value, and provenance
that supports relative shares through movement and separation. Replacement
requires free product entries and explicit separation fates; changing their
relationship is unsupported. Known carrier volume remains independent. A mass-dependent request cannot be satisfied from
unknown mass; execution reports `MAT_QUANTITY_UNKNOWN`. The rules for scaling,
recombining, and exposing these quantities belong to Chapter 7.

## 11.3 Supported Dimensions and Unit Families

| Dimension | Canonical units |
| --- | --- |
| Time | `ms`, `s`, `min`, `h`, `day` |
| Temperature | `C`, `K` |
| Volume | `uL`, `mL`, `L` |
| Mass | `ug`, `mg`, `g`, `kg` |
| Count | `cells` |
| Electric potential | `mV`, `V` |
| Electric current | `uA`, `mA`, `A` |
| Rotation rate | `rpm` |
| Percent | `%` |

The unit definitions and scale factors are maintained in
[data/units.yaml](./data/units.yaml). Legacy aliases `sec`, `hr`, `ul`, `ml`, and
`pct` identify their canonical units and retain their compatibility warnings.
Parser recognition alone does not grant a suffix a supported dimension.

Scaled units within a compatible family use fixed conversion factors. Mixed
`C`/`K` arithmetic requires explicit affine conversion and is not implicit.
The ordinary mass unit `g` also has a context-specific meaning in a centrifugal
setting; conversion between that setting and `rpm` requires rotor information
and is not provided by this arithmetic contract. Percent quantities remain
unit-bearing; a dilution factor such as `1000` is a Number.

## 11.4 Type Failure Surface

Type checking rejects unknown or disallowed units, incompatible expression
operands or result dimensions, and unitless values in unit-bearing positions.
It also checks numeric validity when values are known, content descriptor types,
assignment compatibility, and program-field contracts.

The receiving operation owns the dimension or unit-required diagnostic. Known
zero division and non-finite quantity calculations use their specific
`TYPE_QUANTITY_*` diagnostics. Chapter 8 defines all codes and stage placement.

## 11.5 Binding and Deferred Values

Known bindings are resolved recursively through arithmetic. A numeric `let`
captures the value at its binding point; later assignment to an input does not
recalculate that binding. Assignment updates the current value and preserves a
known arithmetic failure for the consuming quantity position.

Generic protocol checking retains the numeric kind and dimension of defaults
without assuming their values at every call. Concrete expansion checks explicit
arguments or the defaults actually used. Unknown parameters and values affected
by nested-block assignments remain deferred when their values cannot be
established. Known dimensions still constrain their use; stale initializers
MUST NOT be substituted for current runtime bindings.

## 11.6 Boundary with Semantic Validation and Execution

Semantic validation owns statement existence, call shape, content vocabulary,
and the allowed positions for special forms such as replacement products.
Type checking owns quantity and dimension compatibility. Runtime owns
state-dependent feasibility, including source availability, capacity, and
whether a requested material quantity is known.

An undecidable value may be deferred to execution, but deferral does not invent
an amount or relax the operation's contract. A runtime expression that cannot be
evaluated must fail through the execution error path rather than become zero.

## 11.7 Conformance Boundary

Conforming implementations apply these rules consistently through source
loading, binding, protocol expansion, and material execution. Chapter 12 defines
the required evidence for `QTY-ARITH-01` and material replacement. Test and
module names are implementation mappings, not language rules.

## 11.8 Variable Type Catalog

Basic language-level type catalog:

Operation-specific result types are defined in Chapter 6.

Basic types:

1. `Boolean`: `true` / `false`
2. `String`: quoted text literal
3. `Quantity`: numeric with unit suffix (for example `10uL`, `37C`, `5%`)
4. `Number`: unitless numeric scalar (`Quantity` without unit in semantic usage)
5. `Identifier`: symbolic name resolved by binding/type/runtime stages
6. `List[T]`: list value
7. `Record`: structured payload value
8. `Void`: no value / no required return object

Signed quantity note:

1. A leading `-` is expression syntax, not part of the quantity token.
2. `-20C` therefore remains a quantity-like temperature expression for type and unit checking.

Domain reference type (used by operation contracts in Chapter 6):

1. `Container`: logical container identity reference; runtime may map it to physical labware (typically tube or plate well) through metadata.
2. `Content`: logical content identity reference independent of container position.

## 11.9 Content Descriptor Type Contracts

Chapter 6 defines which content descriptor fields are required or optional.
Value-level type constraints for those fields:

1. `content_kind: Text`
2. `content_type: Text`
3. `content_code: Text` (optional)
4. `content_name: Text` (optional)
5. `attrs: Record` (optional)

Type failures for these fields are commonly reported as
`TYPE_CONTENT_KIND_NOT_TEXT`, `TYPE_CONTENT_TYPE_NOT_TEXT`,
`TYPE_CONTENT_CODE_NOT_TEXT`, or `TYPE_CONTENT_ATTRS_NOT_RECORD`. The complete
diagnostic list and stage placement are specified in Chapter 8.

## 11.10 Quantity Axis Rules for Content Loading

For `LoadContent(container, content, amount, ...)` style operations:

1. `amount` must be `Q[Volume|Mass|Count]`.
2. Unit family determines load axis (volume, mass, or count).
3. Missing unit or wrong quantity dimension is rejected at type stage, commonly
   as `TYPE_LOAD_QUANTITY_UNIT_REQUIRED` or
   `TYPE_LOAD_QUANTITY_DIMENSION_MISMATCH`.
4. Incompatible existing runtime axis should surface as a material-stage error,
   commonly as `MAT_CONTENT_LOAD_AXIS_MISMATCH`, not a late semantic/type-stage
   error.
5. Diagnostic code definitions and stage placement are specified in Chapter 8.
6. `cells` requires cellular content when the content contract is statically known.
7. Direct authored and transferred `cells` quantities must be non-negative integers; runtime partition results may be fractional estimates.
8. Count is an authoritative component quantity axis, not a volume unit. A
   count-quantified transfer may nevertheless require runtime concentration to
   resolve the physical carrier volume moved with the cells.

## 11.11 Program, Stream, and Data Types

Program/value type families:

1. `thermal_program`: programmatic thermal-control descriptor/callable value used by `env(thermal=...)` and other thermal-control flows.
2. `sep program`: mechanism descriptor/callable value family for `sep`.
3. `frac program`: mechanism descriptor/callable value family for `frac`.
4. `data_schema_ref`: declared open result-structure contract used by `schema_ref`.
5. Program descriptor values may be bound with `let`; a let-bound program descriptor is not a container, content value, or executable statement.
6. Program descriptor values do not emit runtime steps by themselves. They become executable only when consumed by a compatible owner such as `sep`, `frac`, or `env(thermal=...)`.

Program parameter value types:

1. `CentrifugalSetting` is
   `Q[RelativeCentrifugalForce] | Q[RotationRate]`.
2. Relative centrifugal force is written with `g`, for example `8000g`;
   rotation rate is written with `rpm`, for example `12000rpm`.
3. The unit `g` denotes mass in an ordinary mass-quantity position and relative
   centrifugal force in a `CentrifugalSetting` position.
4. Conversion between relative centrifugal force and rotation rate requires
   rotor geometry and is not implicit.
5. `field_program` requires exactly one of `voltage: Q[ElectricPotential]`,
   `current: Q[ElectricCurrent]`, or `field: Q[ElectricPotential]`.
6. `field` is an alias for `voltage`; electric potential and electric current
   are not implicitly interchangeable.

Stream/reference types:

1. `unit_stream_ref`: stream handle returned by `stream(sample=..., unit=...)`.
2. `unit_ref`: temporary unit reference valid only inside `repeat x in unit_stream`.
3. `sep_container_group`: fixed-length tuple-like group with stable slots `group[0]` / `group[1]`.
4. `fraction_group`: ordered container sequence with stable index semantics.
5. These stream/group values are typed frontend/runtime references; they are not material-state scalar values.

Data/reference types:

1. `data_ref`: structured information result payload for `img/ecp/phy` and decomposed analytical readout paths.
2. `data_group_ref`: flat, ordered group of `data_ref`, aligned with grouped readout input order and supporting stable `group[index]` access.
3. `artifact_ref`: minimal raw-artifact handle containing artifact identity/profile metadata.
4. `export_ref`: minimal external/profile export handle containing export kind/profile/format identity metadata.

Result scalar/value types:

1. `BoolResult`: boolean predicate/result field.
2. `IntResult`: integer count-like field.
3. `NumberResult`: unitless numeric field.
4. `TextResult`: text/label field.
5. `QuantityResult`: quantity-valued field with unit.

## 11.12 Type Constraints for Atomic/Readout Contracts

1. `env(thermal=...)` accepts union type: `Q[Temperature] | thermal_program`.
2. Mechanism program records used by `sep` and `frac` must satisfy their
   declared field type and dimension constraints.
3. `frac` `bins` must be integer-like.
4. Readout returns use `data_ref` for single inputs and `data_group_ref` for
   grouped inputs; they are not container-typed values.
5. Complex or profile-specific readout result shapes use `schema_ref` to
   constrain accessible fields.

Operator-specific accepted program families, source forms, and return contracts
are defined in Chapter 6.
