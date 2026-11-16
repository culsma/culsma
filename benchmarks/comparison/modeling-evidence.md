# LabOP modeling examples: M1–M4

Checked on 12 November 2026 using the retained LabOP 1.0a2 environment, prepared from commit `2e2bd88150c71a440771fd369f40295dfd622324`, with SBOL 3 and the bundled LabOP time module. These checks construct protocol models, call `document.validate()`, serialize them as RDF, read them into a fresh document, and recover the relevant references and values. They do not execute laboratory protocols or instruments.

Run:

```bash
benchmarks/local-results/comparison-runtime/labop-env/bin/python \
  benchmarks/comparison/check_modeling.py \
  --output benchmarks/comparison/results/modeling
```

The [report](results/modeling/report.json) records package versions, selected source hashes, validation messages, and recovered model fields. The [observer](check_modeling.py) only reads the constructed representations; it supplies no execution semantics. Generated RDF documents are stored alongside the report.

All six field/reference checks passed, with no validation errors before or after roundtrip and isomorphic serialized graphs. On rereading, each document's validator reported one warning that `FinalNode1` had no incoming edges. This warning is retained in the report; the successful representation checks do not establish that these reread protocols are executable. The initial construction validations had no warnings.

| Check | Actual observation | Supported conclusion |
|---|---|---|
| M1a: declared containers | Two containers of the same kind and description have distinct output references. Two transfers retain their respective source references after validation and RDF roundtrip. The observer follows the existing ObjectFlow/ForkNode paths. | The declared-container reference mechanism is supported for this witness. No general runtime identity guarantee is inferred. |
| M1b: operation products | A newly declared `TwoProducts` primitive uses the existing `add_output` mechanism for `supernatant` and `pellet`. Each output feeds a different transfer. Both paths survive roundtrip. | Released multi-output/reference machinery works. The operation declaration is new, and no separation computation or execution handler is supplied by this probe. |
| M2: volume | `sbol3.Measure(20, OM + "microlitre")` retains both fields. The installed OM ontology links microlitre to litre and litre to the volume dimension. | Structured volume representation with defined dimensional meaning. This is separate from checking whether a volume is valid as a duration. |
| M3: non-covalent complex description | A standard SBOL `Component` typed as `SBO_NON_COVALENT_COMPLEX` contains `SubComponent` references to a protein and ligand. LabOP's standard `Provision.resource` references this component. Type, constituents, and protocol reference survive validation and roundtrip. | A defined association can be represented in the material description carried by a protocol, using the existing SBOL vocabulary. No new ontology property or LabOP handler is added. |
| M3: association-unspecified control | A second document has the same constituent references, amount, destination and resource identifier, but the material has the generic functional-entity type. | The explicit complex description is distinguishable from an association-unspecified description. Under open-world semantics the latter does **not** assert that the materials are unbound. The original paired bound/free magnetic-state check remains unestablished. |
| M4: scoped duration requirement | `labopt.duration(first, [10, 20], units=OM + "second-Time")`, stored in a `TimeConstraints` object linked to the protocol, identifies the first transfer only. The interval, units and target survive roundtrip; the second transfer is not included. | The bundled time module represents a temporal requirement and its operation scope. Enforcement and general handling requirements such as dropwise delivery are not established by this example. |

## Source and semantic basis

- M1: the existing [mechanism audit](m1-mechanism-evidence.md), especially `Behavior.add_output`, `Activity` object flows, and `Action.output_pin`. The generated primitive in the new probe witnesses the same mechanism, without invoking the GFP execution extension.
- M2: the existing [quantity audit](m2-mechanism-evidence.md); [SBOL 3.0.1 Appendix A.2](https://sbolstandard.org/docs/SBOL3.0.1.pdf); and the installed OM ontology whose hash and unit-to-dimension path are in the report.
- M3: [SBOL 3.0.1 §6.4, Table 2, and §6.4.1.1](https://sbolstandard.org/docs/SBOL3.0.1.pdf) define the non-covalent-complex type and constituent references. LabOP's [standard Provision declaration](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop/lib/liquid_handling.py) accepts an SBOL Component as its resource. This is a typed material description, not a demonstrated update of an individual protein–bead association in a running sample ledger.
- M4: [bundled time helpers](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop_time/__init__.py), [time vocabulary](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/labop_time/labop_time.ttl), and [upstream time tests](https://github.com/Bioprotocols/labop/blob/2e2bd88150c71a440771fd369f40295dfd622324/test/test_time.py). The module is distributed with the pinned source; it is not an extension invented for this comparison. `DurationConstraint.specification` defines its interval and `constrained_elements` identifies its scope.

## Supersession note: revised M2 and M3

The latest [working table](https://github.com/culsma/paper-patterns/blob/58a9031/notes/comparison/comparison_table_working.md) evaluates dimensional rejection under M2 and material evolution/accounting under M3. The successful volume and static-complex representation probes below do not establish those revised capabilities. See [M2 evidence](m2-mechanism-evidence.md) and [material evolution audit](material-evolution-evidence.md). The earlier interpretation below is retained as history and is superseded for the active M2/M3 judgments.

## Earlier interpretation in the compact table

Updated 12 November 2026: the M rows now identify semantic scope alongside
short code examples. M1 combines a description of domain kinds/structure
with the retained identity/reference checks; see the added source review in
[the M1 audit](m1-mechanism-evidence.md). M2 identifies where dimensional
meaning is defined, without changing the agreed volume outcomes.

For M3, the complex-description result is retained, but is not presented as
an equivalent pass for Culsma's declaration of a particular sample transition.
The LabOP sample-specific bound/free transition remains unassessed. For M4,
Culsma's pinned precision/carryover declaration and LabOP's scoped duration
interval are explicitly different requirement kinds; a temporal constraint
does not establish support for the corresponding handling requirement.

These changes correct interpretation of the existing evidence. They introduce
no new protocol runs, no whole-family Yes/No scores, and no claim that a Python
library cannot define experimental semantics. Calculating a declared relation
change and enforcing a procedural requirement remain implementation questions.
