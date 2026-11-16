"""LabOP primitive and sample-graph update for the stipulated fractionation."""

from types import MethodType

import labop
import sbol3
import xarray as xr
from labop.execution.behavior_dynamics import BaseUpdater

SAMPLE_ARRAY = "http://bioprotocols.org/labop#SampleArray"


def fraction_output(self, inputs, parameter, sample_format, invocation_hash, engine):
    # Return the actual collection tokens for subsequent standard transfers.
    return inputs[{"supernatant": "lysate", "pellet": "pellet_tube"}[parameter.name]]


def define_fractionation(document):
    operation = labop.Primitive("ClarifyLysate")
    operation.description = (
        "Centrifuge GFP lysate. Retain all liquid as supernatant in the source "
        "tube and collect all cellular material in the pellet tube. The pellet "
        "has no liquid volume in this software model."
    )
    operation.add_input("lysate", SAMPLE_ARRAY)
    operation.add_input("pellet_tube", SAMPLE_ARRAY)
    for name in ("duration", "acceleration", "temperature"):
        operation.add_input(name, sbol3.OM_MEASURE)
    operation.add_output("supernatant", SAMPLE_ARRAY)
    operation.add_output("pellet", SAMPLE_ARRAY)
    document.add(operation)
    operation.compute_output = MethodType(fraction_output, operation)
    return operation


class FractionationUpdater(BaseUpdater):
    """Version both collection states and record their common material parent."""

    def update(self, record):
        inputs = record.call.lookup().parameter_value_map()
        observer = self.observer
        source = observer.select_samples_from_graph(inputs["lysate"].to_data_array())
        parent = source.sample_location.item()
        states, edges = [], []
        for role, collection in (
            ("supernatant", inputs["lysate"]),
            ("pellet", inputs["pellet_tube"]),
        ):
            state = observer.select_samples_from_graph(collection.to_data_array()).reset_coords(drop=True)
            sample_id = collection.new_sample_id()
            states.append(
                state.drop_vars("sample").assign(
                    sample_location=xr.full_like(state.sample_location, sample_id)
                ).assign_coords(sample=[sample_id])
            )
            edges.append([parent, sample_id, f"ClarifyLysate:{role}@{observer.exec_tick}"])

        # The source keeps its full liquid volume. The empty liquid ledger of
        # the pellet tube is unchanged until buffer is added. Its new sample ID
        # represents the solid fraction, whose provenance is independent of volume.
        lineage = xr.DataArray(
            edges,
            dims=("edge", "node"),
            coords={"node": ["sample_location", "next_sample_location", "label"]},
            name="edges",
        )
        return xr.merge([observer.time_stamp(xr.merge(states)), lineage])
