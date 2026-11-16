# Positive LabOP diagnostic witnesses

11 November 2026. These checks supplement the [duration-dimension probe](m2-mechanism-evidence.md). They characterize actual diagnostics rather than infer diagnostic quality from an undetected fault. They are LabOP-only probes, not matched three-system results.

Prepared LabOP environment: commit `2e2bd88150c71a440771fd369f40295dfd622324`, standard Spin and released SBOL/UML validation. No extension and no protocol or hardware execution.

```bash
benchmarks/local-results/comparison-runtime/labop-env/bin/python \
  benchmarks/comparison/check_labop_diagnostics.py \
  --output benchmarks/comparison/results/labop-diagnostics.json
```

[Observer](check_labop_diagnostics.py); [raw results, versions and selected hashes](results/labop-diagnostics.json). Each negative case changes one feature of the valid Spin model. All three cases reach `document.validate()`; none fails during construction.

| Case | Actual result | Diagnostic target |
|---|---|---|
| Valid duration Measure and control flow | No errors or warnings | Not applicable: no diagnostic |
| Duration Measure without a unit | `Too few values for property unit. Expected 1, found 0` | URI ending in `CallBehaviorAction1/ValuePin1/LiteralIdentified1/Measure1` |
| Incoming control edge to InitialNode | `InitialNode must have no incoming edges, but has 1` | URI ending in `InitialNode1` |

The observed messages use model/property concepts, including the unit field and UML control-flow concepts. They are not Python syntax or exception messages. They are not necessarily phrased in laboratory terminology (e.g., centrifugation time). Record the vocabulary as **Domain/model**, with this narrower subtype and the actual text; do not describe them as human-friendly without usability evidence.

The returned issues have `object_id`, `rule_id`, and `message`; the two issue records identify model URIs and provide no Python statement location. This is a result for these two witnesses, not a claim that all LabOP diagnostic paths lack source mapping. A manually inferred link from the URI to the builder script is not a mapping supplied by the diagnostic.

Both checks occur **before protocol execution** and **during the host construction script's execution**, after the relevant model has been built. This illustrates why model-construction order and host-script execution stage cannot be treated as the same axis.

The rules are represented by the released Measure unit cardinality (`URIProperty(..., 1, 1)`) and the UML Activity validator's InitialNode inflow check. These are machine-readable schema/code definitions. For each tested rule, the proposed paired record is `R_rule=1 (schema/code); E_check=1 (document validation)`. For these two faults, Culsma/BPL remain NE because they were not probed. The earlier duration-dimension check remains a distinct fault family: a present unit can still have the wrong dimensional meaning for its parameter.
