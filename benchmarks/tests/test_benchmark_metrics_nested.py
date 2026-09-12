"""Integration tests for nested statistics, using the installed frontend only."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import benchmark_metrics as metrics
from benchmark_metrics_nested import NestedExtractor, object_associations, content

SETUP = '''  // Source step S1: Declare materials.
  let a = tube(label = "A", capacity = 1mL, load = [content(kind = chemical, type = solvent, code = "A"):500uL]);
  let b = tube(label = "B", capacity = 1mL);
'''


def dereference(data, pointer):
    for part in pointer.split('/')[1:]:
        part = part.replace('~1', '/').replace('~0', '~')
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


class NestedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.python = os.environ.get('CULSMA_TEST_PYTHON')
        if not cls.python:
            raise unittest.SkipTest('Set CULSMA_TEST_PYTHON to installed Culsma 1.0.7rc1')
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.serial = 0

    def capture(self, source, steps=2, main='Main'):
        type(self).serial += 1
        root = self.root / str(self.serial)
        root.mkdir()
        (root/'protocol.culs').write_text(source)
        config = {'case_id':'nested-test', 'role':'test', 'protocol':main, 'step_protocol':main,
                  'profile':'nested-v1', 'expected_steps':[f'S{i}' for i in range(1,steps+1)],
                  'source':'protocol.culs', 'source_sha256':metrics.digest(root/'protocol.culs'),
                  'culsma_version':'1.0.7rc1', 'lark_version':'1.3.1'}
        metrics.write_json(root/'case.json',config)
        return metrics.capture(root/'case.json',self.python,root/'input')

    def run_case(self, source, steps=2):
        bundle = self.capture(source,steps)
        extractor = NestedExtractor(bundle)
        return extractor, extractor.derive()

    def rows(self, outputs, step='S2', category=None):
        row = next(r for r in outputs['action_descriptors.json']['rows'] if r['step']==step)
        return [d for d in row['descriptors'] if category is None or d['category']==category]

    def test_content_enums_preserve_material_results_and_metric_counts(self):
        source = 'protocol Main {\n' + SETUP + '''
  // Source step S2: transfer material.
  b << [a:100uL];
}
Main();
'''
        legacy, old = self.run_case(source)
        explicit, new = self.run_case(source.replace('kind = chemical, type = solvent',
                                  'kind = ContentKind.CHEMICAL, type = ContentType.SOLVENT'))
        self.assertEqual(legacy.data['run']['state']['artifacts']['material_state'],
                         explicit.data['run']['state']['artifacts']['material_state'])
        for filename, keys in {
            'action_descriptors.json': ['source_steps', 'descriptor_items'],
            'material_state_continuity.json': ['reused_objects', 'later_use_links', 'active_steps', 'completed_steps'],
            'result_traceability.json': ['reagent_records', 'touched_containers', 'final_material_states'],
        }.items():
            for key in keys:
                self.assertEqual(old[filename][key], new[filename][key], (filename, key))
        self.assertIn('ContentKind', json.dumps(new['action_descriptors.json']))
        self.assertIn('SOLVENT', json.dumps(new['action_descriptors.json']))

    def test_panel_parameter_aliases_keep_one_identity(self):
        x, out = self.run_case('''protocol Acquire(sample, panel_definition) {
  let events = stream(sample = sample, unit = single_cell, panel = panel_definition);
  return events;
}
protocol Pair(sample, panel_definition) {
  // Source step S2: declare two streams using the shared panel.
  let first = Acquire(sample = sample, panel_definition = panel_definition);
  let second = Acquire(sample = sample, panel_definition = panel_definition);
}
protocol Main {
  // Source step S1: prepare a sample and one panel.
  let a = tube(label = "A", capacity = 1mL);
  let selected_panel = markers([CD45, CD3]);
  Pair(sample = a, panel_definition = selected_panel);
}
Main();
''')
        continuity = out['material_state_continuity.json']
        panels = [o for o in continuity['actual_objects'] if o['kind'] == 'marker_panel']
        self.assertEqual(len(panels), 1)
        self.assertEqual(len(x.panel_aliases), 3)
        self.assertEqual(sum(e['classification'] == 'parameter_binding' for e in continuity['execution_coverage']), 3)
        self.assertEqual(len([d for d in self.rows(out) if d['label'] == 'selected_panel']), 1)
        # A stream declaration records parameter evidence without treating the
        # metadata assignment as an extra experimental operation/use.
        self.assertTrue(any(ref and ref.get('_alias_evidence')
                            for fact in x.facts for _, _, refs in x.candidates(fact)
                            for _, _, _, ref in refs))

    def test_distributed_markers_without_root_markers(self):
        x, out = self.run_case('''protocol Prepare {
  // Source step S1: prepare material.
  let a = tube(label = "A", capacity = 1mL);
  return a;
}
protocol Measure(sample) {
  // Source step S2: warm sample.
  with env(thermal = 25C, duration = 1min) { hold(sample = sample); }
}
protocol Main { let a = Prepare(); Measure(sample = a); }
Main();
''')
        self.assertEqual(out['action_descriptors.json']['source_steps'], 2)
        self.assertEqual(out['material_state_continuity.json']['later_use_links'], 1)
        self.assertTrue(all(r['source_range']['markers'] for r in out['action_descriptors.json']['rows']))
        self.assertTrue(any(e.get('step_origin', {}).get('kind') == 'local'
                            for d in self.rows(out) for e in d['evidence']))

    def test_repeated_marked_child_at_distinct_call_sites(self):
        _, out = self.run_case('''protocol Work(sample, destination) {
  // Source step S2: transfer each sample.
  destination << [sample:10uL];
}
protocol Main {
'''+SETUP+''' Work(sample = a, destination = b);
  Work(sample = b, destination = a);
}
Main();
''')
        self.assertEqual(len(self.rows(out, category='operation')), 2)
        self.assertEqual(out['action_descriptors.json']['source_steps'], 2)
        self.assertEqual(out['material_state_continuity.json']['later_use_links'], 2)

    def test_descending_number_keeps_all_actual_uses(self):
        source = '''protocol Prepare {
  // Source step S2: introduce sample.
  let a = tube(label = "A", capacity = 1mL);
  return a;
}
protocol Early(sample) {
  // Source step S1: use sample in an earlier paper step.
  with env(thermal = 25C, duration = 1min) { hold(sample = sample); }
}
protocol Late(sample) {
  // Source step S3: use sample in a later paper step.
  with env(thermal = 37C, duration = 1min) { hold(sample = sample); }
}
protocol Main { let a = Prepare(); Early(sample = a); Late(sample = a); }
Main();
'''
        _, out = self.run_case(source, 3)
        continuity = out['material_state_continuity.json']
        self.assertEqual(continuity['rows'][0]['introduced_at'], 'S2')
        self.assertEqual(continuity['rows'][0]['used_in'], ['S3'])
        self.assertEqual(set(continuity['actual_objects'][0]['uses']), {'S1', 'S3'})
        self.assertEqual(continuity['later_use_links'], 1)
        # The unreachable definition's S3 must not satisfy completeness or add a use.
        _, out = self.run_case(source.replace(' Late(sample = a);', ''), 2)
        continuity = out['material_state_continuity.json']
        self.assertEqual(continuity['rows'], [])
        self.assertEqual(set(continuity['actual_objects'][0]['uses']), {'S1'})

    def test_local_child_markers_do_not_change_parent_step(self):
        _, out = self.run_case('''protocol Work(sample) {
  // Source step S3: child operation.
  with env(thermal = 37C, duration = 1min) { hold(sample = sample); }
}
protocol Main {
'''+SETUP+''' Work(sample = a);
  // Source step S2: resume parent.
  b << [a:10uL];
}
Main();
''', 3)
        self.assertEqual([r['label'] for r in self.rows(out, 'S2', 'operation')], ['transfer'])
        self.assertEqual([r['label'] for r in self.rows(out, 'S3', 'operation')], ['hold'])

    def test_unmarked_child_prefix_has_no_automatic_s1(self):
        bundle = self.capture('''protocol Work {
  let a = tube(label = "A", capacity = 1mL);
  // Source step S1: warm.
  with env(thermal = 25C, duration = 1min) { hold(sample = a); }
}
protocol Main { Work(); }
Main();
''', 1)
        target = bundle.parent / 'results'
        with self.assertRaisesRegex(metrics.EvidenceError, 'STEP_MAPPING'):
            metrics.extract(bundle, target)
        self.assertFalse(target.exists())

    def test_same_object_repeated_named_return_calls_use_ir_parameter_links(self):
        _, out = self.run_case('''protocol Wash(sample) returns (retained) {
  let split = sep(sample = sample, program = centrifuge_program(drive = 300g));
  return retained = sample;
}
protocol Main {
'''+SETUP+'''  // Source step S2: first wash.
  let once = Wash(sample = a);
  // Source step S3: second wash of the same object.
  let twice = Wash(sample = once);
}
Main();
''', 3)
        rows = out['material_state_continuity.json']['rows']
        self.assertEqual(rows[0]['used_in'], ['S2', 'S3'])
        first = {e['step_id'] for u in rows[0]['uses']['S2'] for e in u['execution']}
        second = {e['step_id'] for u in rows[0]['uses']['S3'] for e in u['execution']}
        self.assertFalse(first & second)
        self.assertEqual(len(self.rows(out, 'S2', 'operation')), 1)

    def test_schema_validation_rejects_corrupted_counts_and_evidence(self):
        from copy import deepcopy
        x, out = self.run_case('protocol Main {\n'+SETUP+'''  // Source step S2: use.
  b << [a:10uL];
}
Main();
''')
        wrong = deepcopy(out)
        wrong['material_state_continuity.json']['later_use_links'] += 1
        with self.assertRaisesRegex(metrics.EvidenceError, 'OUTPUT_COUNTS'):
            x.validate_outputs(wrong)
        wrong = deepcopy(out)
        wrong['action_descriptors.json']['rows'][0]['descriptors'][0]['evidence'][0]['json_pointer'] = '/missing'
        with self.assertRaisesRegex(metrics.EvidenceError, 'OUTPUT_EVIDENCE_POINTER'):
            x.validate_outputs(wrong)

    def semantic_rows(self, x, outputs):
        # Compare actual object relationships, not source-path-derived identifiers.
        names={k:v['name'] for k,v in x.objects.items()}
        def norm(v):
            if isinstance(v,dict):return {k:(names[val] if k=='object_id' else norm(val)) for k,val in v.items()}
            if isinstance(v,list):return [norm(e) for e in v]
            return v
        return {r['step']:sorted(metrics.canonical([d['category'],d['label'],norm(d['details'])])
                                for d in r['descriptors']) for r in outputs['action_descriptors.json']['rows']}

    def test_inline_and_nested_details_equivalent(self):
        body='''  // Source step S2: Warm and transfer.
  with env(thermal = 25C, duration = 5min) { hold(sample = a); }
  b << [a:10uL];
'''
        direct='protocol Main {\n'+SETUP+body+'}\nMain();\n'
        nested='''protocol Work(sample, destination, temperature = 25C) {
  with env(thermal = temperature, duration = 5min) { hold(sample = sample); }
  destination << [sample:10uL];
}
protocol Main {
'''+SETUP+'''  // Source step S2: Warm and transfer.
  Work(sample = a, destination = b);
}
Main();
'''
        x,a=self.run_case(direct)
        y,b=self.run_case(nested)
        self.assertEqual(self.semantic_rows(x,a),self.semantic_rows(y,b))
        self.assertEqual(a['material_state_continuity.json']['reused_objects'],2)
        self.assertEqual(b['material_state_continuity.json']['later_use_links'],2)
        self.assertEqual(a['result_traceability.json']['reagent_records'],b['result_traceability.json']['reagent_records'])
        for out in b.values():
            for _,e in metrics.nodes(out):
                if 'file' in e and 'json_pointer' in e:
                    node=dereference(y.data[next(k for k,v in y.paths.items() if v==e['file'])],e['json_pointer'])
                    if 'source_span' in e:self.assertEqual(e['source_span'],node['span'])
        self.assertEqual(metrics.extract(y.root,y.root.parent/'results'),b)

    def test_defaults_merge_by_content_and_keep_sources(self):
        x,o=self.run_case('''protocol Warm(sample, temperature = 25C, unused = 99C) {
  with env(thermal = temperature, duration = 5min) { hold(sample = sample); }
}
protocol Main {
'''+SETUP+'''  // Source step S2: Repeated settings.
  Warm(sample = a);
  Warm(sample = a, temperature = 25C);
  Warm(sample = a, temperature = 37C);
  Warm(sample = b);
}
Main();
''')
        envs=self.rows(o,category='environment')
        self.assertEqual(len(envs),3)
        self.assertFalse(any(n.get('value') == 99 and n.get('unit') == 'C'
                             for _,n in metrics.nodes(self.rows(o))))
        merged=next(d for d in envs if len(d['evidence'])==2)
        origins={e['origin_kind'] for ev in merged['evidence'] for e in ev.get('parameter_sources',[]) if 'origin_kind' in e}
        self.assertEqual(origins,{'explicit','default'})
        self.assertEqual(o['material_state_continuity.json']['later_use_links'],2)

    def test_nested_steps_and_return_alias(self):
        _,o=self.run_case('''protocol Inner(sample, destination) { destination << [sample:10uL]; return destination; }
protocol Outer(sample, destination) { let result = Inner(sample = sample, destination = destination); return result; }
protocol Main {
'''+SETUP+'''  // Source step S2: First call.
  let same_b = Outer(sample = a, destination = b);
  // Source step S3: Use returned identity.
  a << [same_b:5uL];
}
Main();
''',3)
        reuse=o['material_state_continuity.json']
        self.assertEqual((reuse['reused_objects'],reuse['later_use_links']),(2,4))
        self.assertEqual(len(reuse['source_objects']),2)
        nested=self.rows(o,category='operation')[0]
        self.assertEqual(len(nested['evidence'][0]['call_path']),3)

    def test_roles_keep_reverse_transfers_distinct(self):
        _,o=self.run_case('protocol Main {\n'+SETUP+'''  // Source step S2: Transfers.
  b << [a:10uL];
  a << [b:10uL];
  b << [a:10uL];
}
Main();
''')
        operations=self.rows(o,category='operation')
        self.assertEqual(len(operations),2)
        self.assertEqual(sorted(len(d['evidence']) for d in operations),[1,2])

    def test_environment_dedup_ignores_child_transfer_volume(self):
        _,o=self.run_case('protocol Main {\n'+SETUP+'''  // Source step S2: Same conditions, different amounts.
  with env(thermal = 25C, duration = 5min) { b << [a:10uL]; }
  with env(thermal = 25C, duration = 5min) { b << [a:20uL]; }
}
Main();
''')
        envs=self.rows(o,category='environment')
        self.assertEqual(len(envs),1)
        self.assertEqual(len(envs[0]['evidence']),2)
        operations=self.rows(o,category='operation')
        self.assertEqual(len(operations),2)
        self.assertEqual({n['value'] for d in operations for _,n in metrics.nodes(d['details'])
                          if n.get('unit')=='uL'}, {10.0,20.0})
        self.assertFalse(any(n.get('unit')=='uL' for _,n in metrics.nodes(envs[0]['details'])))

    def test_environment_associations_preserve_transfer_roles(self):
        _,o=self.run_case('protocol Main {\n'+SETUP+'''  // Source step S2: Reversed roles.
  with env(thermal = 25C, duration = 5min) { b << [a:10uL]; }
  with env(thermal = 25C, duration = 5min) { a << [b:10uL]; }
}
Main();
''')
        self.assertEqual(len(self.rows(o,category='environment')),2)

    def test_different_calls_do_not_merge_local_objects(self):
        _,o=self.run_case('''protocol Portion(sample) {
  let local = tube(label = "Local", capacity = 1mL);
  local << [sample:10uL];
  return local;
}
protocol Main {
'''+SETUP+'''  // Source step S2: Two allocations from the same definition.
  let first = Portion(sample = a);
  let second = Portion(sample = a);
  // Source step S3: Both identities remain distinct.
  b << [first:5uL];
  b << [second:5uL];
}
Main();
''',3)
        reuse=o['material_state_continuity.json']
        locals=[r for r in reuse['rows'] if r['members'][0]['name']=='local']
        self.assertEqual(len(locals),2)
        self.assertNotEqual(locals[0]['entry_id'],locals[1]['entry_id'])
        self.assertTrue(all(r['used_in']==['S3'] for r in locals))

    def test_loop_call_is_static_once(self):
        _,o=self.run_case('''protocol Move(sample, destination) { destination << [sample:10uL]; }
protocol Main {
'''+SETUP+'''  // Source step S2: Repeated call.
  repeat i in schedule(start = 1, end = 3, step = 1) { Move(sample = a, destination = b); }
}
Main();
''')
        self.assertEqual(len(self.rows(o,category='operation')),1)
        self.assertEqual(len(self.rows(o,category='schedule')),1)
        reuse=o['material_state_continuity.json']
        a=next(r for r in reuse['rows'] if r['members'][0]['name']=='a')
        self.assertEqual(len({e['step_id'] for u in a['uses']['S2'] for e in u['execution']}),3)

    def test_unexecuted_branch_keeps_static_details(self):
        _,o=self.run_case('''protocol Work(sample, destination, enabled = false) {
  if enabled { destination << [sample:10uL]; }
}
protocol Main {
'''+SETUP+'''  // Source step S2: Branch is not taken.
  Work(sample = a, destination = b);
}
Main();
''')
        self.assertEqual(len(self.rows(o,category='operation')),1)
        self.assertEqual(o['material_state_continuity.json']['reused_objects'],0)

    def test_wrapper_batch_preserves_static_counts_and_runtime_instances(self):
        main = 'protocol Main {\n'+SETUP+'''  // Source step S2: Transfer.
  b << [a:10uL];
}
'''
        x,a = self.run_case(main+'Main();\n')
        y,b = self.run_case(main+'''protocol Batch(n = 2) {
  repeat j in schedule(start = 1, end = n, step = 1) { Main(); }
}
Batch();
''')
        self.assertEqual(self.semantic_rows(x,a), self.semantic_rows(y,b))
        self.assertEqual(b['material_state_continuity.json']['reused_objects'],4)
        self.assertEqual(b['material_state_continuity.json']['later_use_links'],4)
        self.assertEqual(b['material_state_continuity.json']['completed_steps'],
                         2*a['material_state_continuity.json']['completed_steps'])

    def test_local_allocations_in_loop_do_not_expand_static_objects(self):
        _,o=self.run_case('''protocol Portion(sample) {
  let local = tube(label = "Local", capacity = 1mL);
  local << [sample:10uL];
}
protocol Main {
'''+SETUP+'''  // Source step S2: Loop allocations.
  repeat i in schedule(start = 1, end = 3, step = 1) { Portion(sample = a); }
}
Main();
''')
        locals=[d for d in self.rows(o,category='object') if d['label']=='local']
        self.assertEqual(len(locals),1)
        self.assertEqual(o['result_traceability.json']['touched_containers'],5)  # A, B, three locals.
        self.assertEqual(o['material_state_continuity.json']['reused_objects'],1)

    def test_unused_protocol_has_no_descriptors(self):
        direct='protocol Main {\n'+SETUP+'  // Source step S2: Use.\n b << [a:10uL];\n}\nMain();\n'
        x,a=self.run_case(direct)
        y,b=self.run_case('''protocol Unused(sample) {
  with env(thermal = 99C, duration = 2min) { hold(sample = sample); }
}
'''+direct)
        self.assertEqual(self.semantic_rows(x,a),self.semantic_rows(y,b))
        self.assertFalse(any(n.get('value')==99 for _,n in metrics.nodes(b['action_descriptors.json'])))

    def test_nested_program_settings_are_preserved(self):
        _,o=self.run_case('''protocol Spin(sample, temperature = 25C, duration = 5min, drive = 300g) {
  with env(thermal = temperature, duration = duration) { sep(sample = sample, program = centrifuge_program(drive = drive)); }
}
protocol Main {
'''+SETUP+'''  // Source step S2: Settings in the called definition.
  Spin(sample = a);
}
Main();
''')
        settings={(n.get('value'),n.get('unit')) for _,n in metrics.nodes(self.rows(o)) if 'value' in n and 'unit' in n}
        self.assertTrue({(25.0,'C'),(5.0,'min'),(300.0,'g')}<=settings)
        self.assertEqual(len(self.rows(o,category='program')),1)
        self.assertEqual(len(self.rows(o,category='environment')),1)

    def test_ambiguous_local_instances_fail_without_output(self):
        bundle=self.capture('''protocol Allocate {
  let local = tube(label = "Same", capacity = 1mL);
  return local;
}
protocol Main {
'''+SETUP+'''  // Source step S2: No exported use to disambiguate two allocations.
  let first = Allocate();
  let second = Allocate();
}
Main();
''')
        out=bundle.parent/'results'
        with self.assertRaisesRegex(metrics.EvidenceError,'CALL_INSTANCE_AMBIGUOUS'):
            metrics.extract(bundle,out)
        self.assertFalse(out.exists())

    def test_inconsistent_argument_binding_fails(self):
        bundle=self.capture('protocol Main {\n'+SETUP+'  // Source step S2: Use.\n b << [a:10uL];\n}\nMain();\n')
        x=NestedExtractor(bundle)
        ps=next(s for s in x.plan_steps if s['op']=='Mutation')
        ps['args']['target']['name']='unknown_binding'
        with self.assertRaisesRegex(metrics.EvidenceError,'EXECUTION_MAPPING'):
            x.derive()

    def test_recursive_call_rejected_from_exported_ast(self):
        # The real compiler rejects recursion before capture. Mutate the loaded
        # AST only to exercise the extractor's separate guard, never the source.
        bundle=self.capture('protocol Main {\n'+SETUP+'  // Source step S2: Use.\n b << [a:10uL];\n}\nMain();\n')
        x=NestedExtractor(bundle)
        stmt=x.protocol['statements'][-1]
        stmt.clear();stmt.update(name='Main',args=[],span=x.protocol['span'])
        with self.assertRaisesRegex(metrics.EvidenceError,'RECURSIVE_CALL'):
            x.call({'name':'Main','args':[]},'/statements/0',{}, {'path':[], 'key':[], 'stack':['Main']},'S2')

    def group_source(self, selected='wells', aliases=False, batch=False):
        source = '''protocol Warm(sample) {
  with env(thermal = 25C, duration = 1min) { hold(sample = sample); }
}
protocol Main {
'''+SETUP+'''  let p = plate(label = "P", format = "96well", carrier_id = "P", capacity = 500uL);
  let wells = p[A1:A2];
  wells << [a:50uL];
'''+('  let same = p[A1:A2];\n' if aliases else '')+'''  // Source step S2: Select actual members in a subprotocol.
  Warm(sample = '''+selected+''');
  // Source step S3: Reuse the whole group.
  with env(thermal = 25C, duration = 1min) { hold(sample = wells); }
}
'''
        return source + ('''protocol Batch {
  repeat run in schedule(start = 1, end = 2, step = 1) { Main(); }
}
Batch();
''' if batch else 'Main();\n')

    def test_nested_whole_group_vs_selected_member_and_alias(self):
        _, whole = self.run_case(self.group_source(aliases=True), 3)
        c = whole['material_state_continuity.json']
        self.assertEqual((c['reused_objects'], c['later_use_links']), (1, 2))
        self.assertEqual({m['name'] for m in c['rows'][0]['members']}, {'A1', 'A2'})
        self.assertEqual(len(c['grouping_audit']), 1)
        self.assertEqual(len(c['grouping_audit'][0]['bases']), 2)
        self.assertEqual(c['grouping_audit'][0]['status'], 'retained')
        self.assertTrue(all(len(u['call_path']) == 2 for u in c['rows'][0]['uses']['S2']))
        _, selected = self.run_case(self.group_source('wells[0]'), 3)
        c = selected['material_state_continuity.json']
        self.assertEqual((c['reused_objects'], c['later_use_links']), (2, 3))
        uses = {r['members'][0]['name']:r['used_in'] for r in c['rows']}
        self.assertEqual(uses, {'A1':['S2','S3'], 'A2':['S3']})
        self.assertEqual(c['grouping_audit'][0]['status'], 'different_introduction_or_uses')

    def test_group_index_loop_counts_source_once_and_all_actual_members(self):
        source = self.group_source().replace('Warm(sample = wells);',
                 'repeat i in schedule(start = 0, end = 1, step = 1) { Warm(sample = wells[i]); }', 1)
        _, out = self.run_case(source, 3)
        self.assertEqual(len(self.rows(out, category='operation')), 1)
        c = out['material_state_continuity.json']
        self.assertEqual((c['reused_objects'], c['later_use_links']), (1, 2))
        self.assertEqual(len(c['rows'][0]['uses']['S2']), 2)
        # The environment keeps the selector, including the symbolic schedule.
        env = self.rows(out, category='environment')[0]['details']
        self.assertTrue(any('iterator' in n for _,n in metrics.nodes(env['associations'])))

    def test_named_single_well_alias_uses_only_its_selected_identity(self):
        source = self.group_source('chosen').replace('  // Source step S2:',
                    '  let chosen = wells[0];\n  // Source step S2:')
        _, out = self.run_case(source, 3)
        c = out['material_state_continuity.json']
        self.assertEqual({r['members'][0]['name']:r['used_in'] for r in c['rows']},
                         {'A1':['S2','S3'], 'A2':['S3']})

    def test_returned_group_from_nested_declaration_keeps_well_identity(self):
        source = '''protocol Make {
  let p = plate(label = "P", format = "96well", carrier_id = "P", capacity = 500uL);
  let wells = p[A1:A2];
  return wells;
}
protocol Main {
'''+SETUP+'''  let returned = Make();
  returned << [a:50uL];
  // Source step S2: Use returned group without introducing new wells.
  with env(thermal = 25C, duration = 1min) { hold(sample = returned); }
}
Main();
'''
        _, out = self.run_case(source)
        c = out['material_state_continuity.json']
        self.assertEqual((c['reused_objects'], c['later_use_links']), (1, 1))
        self.assertEqual({m['name'] for m in c['rows'][0]['members']}, {'A1', 'A2'})
        self.assertEqual(c['rows'][0]['introduced_at'], 'S1')

    def test_batch_group_identities_do_not_mix_iterations(self):
        _, out = self.run_case(self.group_source(batch=True), 3)
        c = out['material_state_continuity.json']
        self.assertEqual((c['reused_objects'], c['later_use_links']), (1, 2))
        ids = [m['runtime_identity']['container_id'] for r in c['rows'] for m in r['members']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 2)  # Exported plate carrier is reused across batches.

    def test_grouped_readout_and_schema_are_joined_without_well_duplication(self):
        source = self.group_source().replace('  // Source step S2:',
                  '  let schema = data_schema(label = "Signals", fields = [signal]);\n  // Source step S2:')
        source = source.replace('  Warm(sample = wells);',
                  '  let observed = img(sample = wells, quantity = customized, schema_ref = schema, save_raw = true);', 1)
        x, out = self.run_case(source, 3)
        readout = next(o for o in x.runtime_objects.values() if o['kind'] == 'readout')
        self.assertIn('data_group_id', readout['runtime_identity'])
        self.assertEqual(len(readout['runtime_identity']['item_ids']), 2)
        c = out['material_state_continuity.json']
        self.assertEqual((c['reused_objects'], c['later_use_links']), (2, 3))  # Group plus schema.
        self.assertEqual(sum(len(r['members']) for r in c['rows']), 3)
        for result in out.values():
            for _, node in metrics.nodes(result):
                if 'file' in node and 'json_pointer' in node:
                    dereference(x.data[next(k for k,v in x.paths.items() if v == node['file'])], node['json_pointer'])

    def test_data_declaration_counts_once_and_schema_keeps_setting(self):
        _, out = self.run_case('''protocol Main {
  // Source step S1: Declare data and schema.
  let labels = data_ref(kind = custom);
  let schema = data_schema(label = "Signals", fields = [signal]);
}
Main();
''', 1)
        self.assertCountEqual([d['category'] for d in self.rows(out, 'S1')],
                              ['object', 'object', 'schema'])
        self.assertEqual({d['label'] for d in self.rows(out, 'S1', 'object')}, {'labels', 'schema'})

    def stream_source(self, declarations, later=''):
        return '''protocol Main {
'''+SETUP+'''  let panel = markers([CD45]);
  // Source step S2: Declare streams.
'''+declarations+later+'''
}
Main();
'''

    def test_stream_declaration_includes_direct_sample_and_panel_references(self):
        _, out = self.run_case(self.stream_source(
            '  let events = stream(sample = a, unit = single_cell, panel = panel);'))
        self.assertCountEqual([d['label'] for d in self.rows(out, 'S2', 'object')],
                              ['a', 'panel', 'events'])
        self.assertEqual(len(self.rows(out)), 3)

    def test_stream_declarations_merge_shared_parameter_objects_in_same_step(self):
        _, out = self.run_case(self.stream_source('''
  let first = stream(sample = a, unit = single_cell, panel = panel);
  let second = stream(sample = a, unit = single_cell, panel = panel);
'''))
        self.assertCountEqual([d['label'] for d in self.rows(out, 'S2', 'object')],
                              ['a', 'panel', 'first', 'second'])

    def test_later_reference_does_not_expand_historical_declaration_parameters(self):
        source = self.stream_source(
            '  let events = stream(sample = a, unit = single_cell, panel = panel);', '''
  // Source step S3: Observe the stream.
  let observed = img(sample = events, quantity = customized, schema_ref = schema, save_raw = true);
''').replace('  // Source step S2:',
             '  let schema = data_schema(label = "Signals", fields = [signal]);\n  // Source step S2:')
        _, out = self.run_case(source, 3)
        self.assertCountEqual([d['label'] for d in self.rows(out, 'S2', 'object')],
                              ['a', 'panel', 'events'])
        self.assertCountEqual([d['label'] for d in self.rows(out, 'S3', 'object')],
                              ['events', 'observed', 'schema'])

    def test_external_result_members_and_readout_annotations_remain_structural(self):
        x, out = self.run_case('''protocol Inspect(sample, score) {
  let schema = data_schema(label = "Score", fields = [score]);
  let measured = img(sample = sample, quantity = customized, schema_ref = schema, save_raw = true);
  measured.result.score = score;
  if measured.result.score > 0 {
    with env(thermal = 25C, duration = 1min) { hold(sample = sample); }
  }
  return measured;
}
protocol Main(score) {
'''+SETUP+'''  // Source step S2: Read a member passed through the entry and helper.
  let alias = Inspect(sample = a, score = score);
}
let fixture = data_ref(kind = custom);
fixture.result.score = 1;
Main(score = fixture.result.score);
''')
        annotation = self.rows(out, category='annotation')[0]['details']
        self.assertEqual(annotation['value']['member'], 'score')
        self.assertEqual(annotation['value']['base']['member'], 'result')
        self.assertEqual(x.objects[annotation['value']['base']['base']['object_id']]['name'], 'fixture')
        self.assertEqual(len(self.rows(out, category='condition')), 1)
        self.assertEqual(out['material_state_continuity.json']['reused_objects'], 1)
        self.assertEqual(x.parameters['score']['value']['member'], 'score')

    def test_identical_group_calls_without_callsite_evidence_fail_atomically(self):
        source = self.group_source().replace(
            '  with env(thermal = 25C, duration = 1min) { hold(sample = wells); }',
            '  Warm(sample = wells);')
        bundle = self.capture(source, 3)
        out = bundle.parent/'results'
        with self.assertRaisesRegex(metrics.EvidenceError, 'CALL_INSTANCE_AMBIGUOUS'):
            metrics.extract(bundle, out)
        self.assertFalse(out.exists())

    def test_group_binding_corruption_and_incomplete_full_group_fail(self):
        bundle = self.capture(self.group_source(), 3)
        x = NestedExtractor(bundle)
        ir = next(n for _,n in x.ir_nodes if 'id' in n and isinstance(n.get('value'), dict) and n['value'].get('elements'))
        ir['value']['elements'][0]['name'] = 'unknown_member'
        with self.assertRaisesRegex(metrics.EvidenceError, 'GROUP_IR'):
            x.derive()
        x = NestedExtractor(bundle)
        hold = next(s for s in x.plan_steps if s['op'] == 'env_hold')
        hold['gate']['env_targets'].pop()
        with self.assertRaisesRegex(metrics.EvidenceError, 'EXECUTION_MAPPING'):
            x.derive()

    def test_nested_case04_full_plan_and_raw_records(self):
        source = (Path(__file__).resolve().parents[1]/'cases/04/protocol.culs').read_text()
        x = NestedExtractor(self.capture(source, 10, 'SandwichELISA'))
        out = x.derive()
        c = out['material_state_continuity.json']
        self.assertEqual((c['reused_objects'], c['later_use_links'], c['completed_steps']), (37,173,778))
        self.assertEqual(len(c['grouping_audit']), 6)
        self.assertTrue(all(g['status'] == 'overlap' for g in c['grouping_audit']))
        self.assertEqual(sum(m['kind'] == 'well' for r in c['rows'] for m in r['members']),16)
        self.assertEqual(out['action_descriptors.json']['descriptor_items'],157)
        trace = out['result_traceability.json']
        self.assertEqual((trace['reagent_records'], trace['touched_containers'], trace['final_material_states']), (20,37,17))
        for key in ('reagent_consumption', 'final_products'):
            self.assertEqual([r['record'] for r in trace[key]], x.data['result']['materials'][key])
        self.assertEqual([r['name'] for r in trace['touched_names']],
                         x.data['result']['resource_summary']['containers']['touched_names'])
        self.assertEqual(trace['formal_returns']['value'], x.data['output']['returns'])
        for result in out.values():
            for _, node in metrics.nodes(result):
                if 'file' in node and 'json_pointer' in node:
                    dereference(x.data[next(k for k,v in x.paths.items() if v == node['file'])], node['json_pointer'])

class AssociationProjectionTests(unittest.TestCase):
    def test_preserves_selection_index_without_operation_quantity(self):
        # Projection unit test only: this does not claim nested plate support.
        def association(index, volume):
            selection={'base':{'object_id':'plate'}, 'index':{'value':index}}
            return content(object_associations([{'slots':{
                '/args/target':selection,
                '/args/sources':[{'left':{'object_id':'a'}, 'right':{'value':volume,'unit':'uL'}}]
            }}]))
        self.assertEqual(association(0,10),association(0,20))
        self.assertNotEqual(association(0,10),association(1,10))

    def test_preserves_region_and_result_member_roles(self):
        def projection(ref):
            return content(object_associations([{'slots': {'/args/target': ref}}]))
        base = {'object_id':'group'}
        self.assertNotEqual(projection({'base':base,'regions':[{'start':'A1','end':'A2'}]}),
                            projection({'base':base,'regions':[{'start':'A1','end':'A3'}]}))
        self.assertNotEqual(projection({'base':{'base':base,'member':'result'},'member':'a'}),
                            projection({'base':{'base':base,'member':'result'},'member':'b'}))


if __name__=='__main__':unittest.main()
