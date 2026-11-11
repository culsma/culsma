# Environment execution contract

Status: current implementation contract, ENV-PARAMETERS-151 (local, unreleased).
Language semantics: Culsma Reference §6.3.14 and §11.12.

This document specifies the Culsma implementation's Python API, serialized
environment fields, and compatibility behavior. They implement the
representation-independent requirements in Reference §9.3; those requirements
do not prescribe these field names or adapters.

Temperature control and incubation share one environment abstraction:

```culsma
let sample = tube(label = "Sample");
with env(thermal = 22C, duration = 30min, co2 = 5%, o2 = 20%, rh = 80%) {
  hold(sample);
}
```

The source keys are `thermal`, `field`, `medium`, `duration`, `co2`, `o2`, `rh`.
`humidity` is an execution key; it is not a source alias. `hold(sample = sample)`
remains accepted for compatibility; positional `hold(sample)` is preferred.

| Source | Public gate key | Quantity contract |
| --- | --- | --- |
| thermal | thermal | C or K, finite, >= -273.15C / 0K; or thermal_program |
| duration | duration | finite positive time: ms, s, min, h, day; legacy sec/hr accepted |
| co2 | co2 | CO2 concentration, percent in [0,100] |
| o2 | o2 | O2 concentration, percent in [0,100] |
| rh | humidity | relative humidity, percent in [0,100] |
| field | field | existing field-domain descriptor, unchanged |
| medium | medium | gas or liquid descriptor with composition requirements and optional source |

CO2 and O2 describe the same atmosphere; their explicit sum cannot exceed 100%.
No remaining gas composition is inferred. Percent quantities use `%`; legacy
`pct` remains accepted and becomes `%` at runtime preparation. Time and
temperature units remain explicit in the payload; consumers must convert
compatible units, including C/K, rather than assuming every temperature is C
or every duration is seconds. No device limits or integer rounding are applied.

Gas and humidity conditions require scalar thermal; they are forbidden with a
thermal program. Duration is permitted for ordinary-atmosphere holds without an
explicit medium. A field-only scope forbids outer duration, as does a thermal
program. A pure scalar or medium hold requires duration. An active-operation block may
omit duration and lasts for the lexical execution of its enclosed statements.
`thermal` and `field` may coexist under the existing contract; an executor must
satisfy both or reject the scope.

An omitted medium retains the enclosing medium for the same target, or defaults
to ordinary atmosphere. Other omitted conditions impose no numeric requirement.
Temperature-only `22C` and `22C`
plus gas/humidity are different requests. Explicit `0%` is still a requirement.
Neither a device name, an ambient-temperature fallback, a typical atmospheric percentage,
nor a default humidity may be inferred.

## Typed media

`culsma.domains.medium` owns the typed gas and liquid medium values. An inline
liquid descriptor uses `contents` with content-reference keys, an optional
fraction `basis`, and a final `volume`. It reuses existing content identities
and quantity units. A source descriptor instead uses a resolved container
identity. Source resolution accepts actual container references.

In a liquid contents map, all values are absolute volumes or all are fractions
on one common basis. Fractions must total 100%. The final volume is explicit
for fractions and derived from absolute entries. A fraction descriptor may
omit the volume as data, but a final volume is required before execution.
Resolving content descriptors and normalizing these quantities does not add
container inventory.

`pipeline.medium_boundary` decodes constructors and validates the canonical
JSON representation. An inline liquid descriptor has `kind: liquid_medium`
and a `contents` map from resolved material codes to quantity objects. It
includes `basis` for fractions and `volume` when known. Volumes use microliters
and fractions use percent. The `source` form uses a `container_ref` with `id`.
The runtime revalidates source references against live allocations.

Gas descriptors retain their composition coverage, components and optional
source. The canonical wire representation uses enum text. At source, basis
and coverage require members of their exact enum families.

`resolve_medium(environment, inherited=...)`, exported through
`pipeline.external_boundary`, resolves an explicit descriptor, the caller-supplied
enclosing medium for the same target, or `DEFAULT_MEDIUM` in that order. The
default is `GasMedium()` with no fixed numeric composition. This lookup does not
insert a `medium` key into stored gates; legacy payloads retain their shape.
An omitted inner medium therefore does not reset an enclosing liquid bath to air.

Static failures use `TYPE_ENV_MEDIUM_INVALID`; deferred descriptor, source and
nested-target conflicts use `RT_ENV_ARGUMENT_INVALID`. Runtime checks preserve
all environment layers and compare overlapping targets by allocation identity.
Different sequential baths remain separate holds, even with equal labels or
compositions. Neither entering a medium nor leaving its lexical scope creates
a material delta, predicts uptake or restores a previous material state.

The executor boundary preserves requirements; it does not establish physical
contact or certify source composition from a declared type. A device adapter
must check the actual source, fill, geometry and target access and implement
exposure establishment, maintained conditions, timing and removal. Current OS
processing/transfer profiles reject the new condition; physical immersion and
gas-supply adapters are not provided by this change. Runtime suspension must
not be interpreted as exposure termination or evidence of physical removal.

`CapabilityPolicy` requires explicit `supported_medium_phases` containing
`MediumPhase` members for explicit medium descriptors and defaults to none.
Omitted ordinary atmosphere follows the existing environment capability path.
`StubDriver` opts into
`MediumPhase.GAS` and `MediumPhase.LIQUID` for software simulation
only. Declaring phase support does not replace a driver's condition-specific
checks. Custom drivers must check every environment layer or reject it.

## Public normalization boundary

Import `EnvironmentParameterNormalizer` or the shared
`DEFAULT_ENVIRONMENT_PARAMETER_NORMALIZER` from
`culsma.pipeline.external_boundary`.

- `normalize_plan_environment(mapping)` copies the mapping, checks names and
  maps source/legacy `rh` to `humidity`. Symbolic quantity expressions remain
  symbolic; other declared conditions are preserved without defaults.
- `normalize_runtime_environment(mapping, require_duration=False)` validates
  final quantities and combinations. Pass `require_duration=True` for a pure
  environment hold. Symbolic or invalid scalar requirements are rejected.
- `normalize_runtime_gate(gate, resolve_environment=..., require_duration=False)`
  resolves and validates the innermost compatibility env and every `env_layers`
  entry. Its resolver accepts an environment mapping and returns a mapping of
  bound quantities. It preserves target references and other gate metadata.

All methods return independent copies. `rh` and `humidity` together are rejected,
even when equal. Old serialized plans containing only `rh` remain accepted.
Unknown conditions fail instead of being dropped. Normalization validates
language requirements, not hardware support.

AST/IR retain source names. Newly lowered plan `gate.env` and every
`gate.env_layers[i].env` use `humidity`. Pure holds lower to the internal
`env_hold` operation with empty action args and explicit `env_targets`; active
steps carry the same environment gate. The innermost compatibility `gate.env`
must agree with the final layer. Outer layers retain their own requirements;
executors must preserve these layers or reject scopes they cannot implement.

Runtime prepares bound environment values before material preflight and driver
`check`/`execute`. Bound environment failures produce `RT_ENV_ARGUMENT_INVALID`.
Driver capability rejection produces `RT_DRIVER_REQUIREMENT_UNSUPPORTED` and
does not execute the action. Events keep the authored plan gate, which can
contain expressions; prepared steps contain the bound execution gate.

## OS and driver integration

OS owns capability matching against every explicit condition and target
container. Drivers own vendor mappings. Neither may silently remove a condition
or reinterpret numeric `22C` as ambient waiting.

Consumers should call the public gate normalizer after resolving expressions to
support legacy `rh`, percent aliases and final language checks. They must also
convert supported units or reject unsupported units explicitly. OS capability
and device-profile limits are maintained in the OS environment-hold contract;
language acceptance does not imply that a selected profile can execute a scope.

The 22C tube-holder/device mapping remains OS/driver work. No hardware or
official simulation is exercised by the language conformance suite.
