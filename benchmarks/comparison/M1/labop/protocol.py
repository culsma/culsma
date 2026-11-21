"""GFP checks using released LabOP primitives and the default execution engine.

No custom primitive, compute_output replacement, or provenance handler.
Distinguishes authoring-time absent fraction outputs from runtime completion.
A location-based continuation is a control, not a declared fraction model.

"""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import traceback
from unittest.mock import patch

import labop
import sbol3
from labop.execution.execution_engine import ExecutionEngine

OM = 'http://www.ontology-of-units-of-measure.org/resource/om-2/'
DATASET = 'http://bioprotocols.org/labop#Dataset'


def measure(value, unit):
    return sbol3.Measure(value, OM + unit)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + '\n')


def write_dataset(path, value):
    payload = json.loads(json.dumps(value.to_dict()), parse_constant=lambda _: None)
    write_json(path, payload)


def save_dot(graph, filename, **kwargs):
    path = Path(filename).with_suffix('.dot')
    path.write_text(graph.source)
    return str(path)


def build_protocol(mode):
    protocol, document = labop.Protocol.initialize_protocol(
        'gfp_' + mode, 'GFP released-mechanism check',
        'https://example.org/gfp-native/' + mode + '/')
    labop.import_library('plate_handling')

    def container(identifier, label, kind, geometry):
        spec = labop.ContainerSpec(identifier, name=label, queryString=kind)
        samples = labop.SampleArray(name=label, container_type=spec)
        samples.empty(geometry=geometry)
        document.add(spec)
        return protocol.primitive_step('EmptyContainer', specification=spec,
            sample_array=samples).output_pin('samples')

    def supply(identifier, label, target, amount):
        resource = sbol3.Component(identifier, [sbol3.SBO_FUNCTIONAL_ENTITY], name=label)
        document.add(resource)
        protocol.primitive_step('Provision', resource=resource, destination=target,
                               amount=measure(amount, 'microlitre'))

    def select(plate, wells):
        return protocol.primitive_step('PlateCoordinates', source=plate,
                                       coordinates=wells).output_pin('samples')

    def transfer(source, target, amount):
        return protocol.primitive_step('Transfer', source=source, destination=target,
                                       amount=measure(amount, 'microlitre'))

    tube = 'cont:MicrofugeTube1.5mL'
    lysate = container('lysate_tube', 'GFP lysate', tube, 'A1')
    supply('lysate_liquid', 'GFP lysate with 100000 suspended cellular units', lysate, 160)
    # Only the supplied liquid amount is machine-interpreted; cellular units
    # in the resource label do not become an independent material count.
    protocol.primitive_step('Hold', location=lysate,
                            temperature=measure(22, 'degreeCelsius'))
    spin = protocol.primitive_step('Spin', location=lysate,
        duration=measure(10, 'minute-Time'),
        acceleration=measure(12000 * 9.80665, 'metrePerSecond-TimeSquared'))
    binding_attempts = {}
    for name in ['supernatant', 'pellet']:
        try:
            pin = spin.output_pin(name)
            binding_attempts[name] = {'found': True, 'identity': pin.identity}
        except ValueError as error:
            binding_attempts[name] = {'found': False, 'stage': 'authoring/output lookup',
                'type': type(error).__name__, 'message': str(error)}
    if mode == 'spin_prefix':
        protocol.order(spin, protocol.final())
    else:
        # No hypothetical fraction API. Retain the nominal pellet in its tube
        # and decant liquid to another tube with ordinary transfers. This is
        # an operator convention, not selective partition semantics.
        supernatant_tube = container('supernatant_tube', 'Collected liquid', tube, 'A1')
        buffer = container('buffer_tube', 'Assay buffer', tube, 'A1')
        assay = container('assay_plate', 'Assay plate', 'cont:Plate96Well', 'A1:H12')
        supply('assay_buffer', 'Assay buffer', buffer, 100)
        transfer(lysate, supernatant_tube, 160)
        transfer(supernatant_tube, select(assay, 'A1'), 20)
        transfer(buffer, lysate, 40)
        protocol.primitive_step('PipetteMix', samples=lysate,
            amount=measure(32, 'microlitre'), cycleCount=measure(1, 'one'))
        transfer(lysate, select(assay, 'A2'), 20)
        transfer(buffer, select(assay, 'A3'), 20)
        reading = protocol.primitive_step('MeasureFluorescence', samples=select(assay, 'A1:A3'),
            excitationWavelength=measure(488, 'nanometre'),
            emissionWavelength=measure(510, 'nanometre'),
            emissionBandpassWidth=measure(20, 'nanometre'))
        result = protocol.designate_output('fluorescence', DATASET,
                                           reading.output_pin('measurements'))
        protocol.order(result, protocol.final())
    return protocol, document, spin, binding_attempts


def run_case(mode, output):
    output.mkdir(parents=True, exist_ok=True)
    protocol, document, spin, bindings = build_protocol(mode)
    document.write(str(output / 'protocol.ttl'), sbol3.TURTLE)
    validation = document.validate()
    engine = ExecutionEngine(out_dir=str(output), use_ordinal_time=True, failsafe=False)
    row = {'mode': mode, 'fraction_output_names': [p.name for p in spin.outputs],
        'fraction_output_lookup': bindings,
        'spin_behavior': spin.behavior.lookup().identity,
        'spin_has_default_material_handler': spin.behavior.lookup().identity in engine.prov_observer.handlers,
        'validation_errors': list(map(str, validation.errors)),
        'validation_warnings': list(map(str, validation.warnings)),
        'completed_normally': False, 'execution_exception': None}
    logger = logging.getLogger('labop.execution.behavior_dynamics')
    handler = logging.FileHandler(output / 'observer.log', mode='w')
    logger.addHandler(handler)
    try:
        if validation.errors:
            raise ValueError('Native protocol validation failed')
        # Rendering only; no protocol, token, or material processing is patched.
        with patch('graphviz.Digraph.render', save_dot):
            execution = engine.execute(protocol, sbol3.Agent('software_runner'),
                                       id='gfp_native_execution', parameter_values=[])
        row['completed_normally'] = execution.completed_normally
        row['issues'] = list(map(str, engine.issues['gfp_native_execution']))
        row['executed_behaviors'] = [str(r.get_behavior().identity)
            for r in execution.executions if isinstance(r, labop.CallBehaviorExecution)]
        graph = engine.prov_observer.graph
        write_dataset(output / 'sample_graph.json', graph)
        row['provenance_edges'] = graph.edges.values.tolist() if 'edges' in graph else []
        if mode == 'location_continuation':
            reading = labop.ParameterValue.parameter_value_map(execution.parameter_values)['fluorescence']
            data = reading.to_dataset()
            write_dataset(output / 'readings.json', data)
            row['fluorescence_data'] = reading.data.identity
            row['observation_coordinates'] = list(data.location.values)
            plate = data.container.item()
            volumes, stocks = {}, {}
            for well in data.location.values.tolist():
                states = graph.sel(container=plate, location=well).sortby('tick')
                latest = states.sample_location.dropna('tick').tick[-1].item()
                values = states.sel(tick=latest)['contents']
                volumes[well] = float(values.sum().item())
                stocks[well] = {str(k): float(v) for k, v in
                    zip(values.reagent.values, values.values) if float(v) > 0}
            row['well_volumes_uL'] = volumes
            row['well_reagents'] = stocks
    except Exception as error:
        row['execution_exception'] = {'type': type(error).__name__, 'message': str(error)}
        (output / 'traceback.txt').write_text(traceback.format_exc())
    finally:
        logger.removeHandler(handler)
        handler.close()
        document.write(str(output / 'execution.ttl'), sbol3.TURTLE)
        write_json(output / 'results.json', row)
    return row


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    report = {'source_commit': '2e2bd88150c71a440771fd369f40295dfd622324',
              'extension_used': False,
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'cases': {mode: run_case(mode, output / mode) for mode in
                        ['spin_prefix', 'location_continuation']}}
    write_json(output / 'results.json', report)
    print(json.dumps(report, indent=2, default=str))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    run(parser.parse_args().output)
