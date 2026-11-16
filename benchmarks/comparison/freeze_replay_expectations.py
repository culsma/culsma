"""Maintainer-only: build frozen predicates from previously reviewed evidence.

Never called by the replay command. Changes require review against the audits.
"""
import json
from pathlib import Path
p=Path(__file__).resolve().parent
r=p/'results'; result={s:[] for s in ['culsma','labop','bpl']}

def row(s,c,v,scope,audit):
 x={'criterion':c,'expected_result':v,'scope':scope,'mechanism_audit':audit,'checks':[]};result[s].append(x);return x

def add(x,file,path,frozen=None,oldpath=None):
 d=json.loads((r/(frozen or file)).read_text())
 for k in (oldpath if oldpath is not None else path): d=d[k]
 x['checks'].append({'file':file,'path':path,'equals':d})

for s in result:
 if s=='culsma':
  x=row(s,'M1','Yes','GFP lysate contents slots 0 and 1 are separately referenced and transferred to distinct destinations.','m1-mechanism-evidence.md')
  gfp=json.loads((r/'culsma/run.json').read_text())
  bindings=gfp['state']['artifacts']['material_state']['bindings']
  for event,slot,destination in [(25,'0','__lw_plate_assay_A1'),(27,'1','resuspended')]:
   base=['events',event,'payload','material_delta','sources',0]
   for field,expected in [('source',bindings['lysate']),('selected_slot',slot),('dest',bindings[destination])]:
    add(x,'gfp/run.json',base+[field],'culsma/run.json')
    assert x['checks'][-1]['equals']==expected
  assert bindings['__lw_plate_assay_A1']!=bindings['resuspended']
  x=row(s,'M2','Yes','Reject a volume in a duration field before execution.','m2-mechanism-evidence.md')
  for i in [0,1]:add(x,'duration.json',['cases',i,'accepted'],'duration-unit-check.json',[s,'cases',i,'accepted'])
  x=row(s,'M3','Yes','GFP cellular quantity is retained (100000 to two portions of 50000); suspension changes to pellet at separation, under stipulated partition rules.','material-evolution-evidence.md')
  initial=['events',11,'payload','material_state_snapshot','containers',bindings['lysate']]
  separated=['events',21,'payload','material_state_snapshot','contents_states',bindings['lysate']]
  requirements=[
   (initial+['component_quantities','GFP_CELL_DEBRIS'],{'dimension':'count','unit':'cells','value':100000.0}),
   (initial+['material_relationships',0,'material_state'],'suspension'),
   (separated+['kind'],'partitioned'),
   (separated+['parts','1','component_quantities','GFP_CELL_DEBRIS'],{'dimension':'count','unit':'cells','value':100000.0}),
   (separated+['parts','1','material_relationships',0,'material_state'],'pellet')]
  for name in ('resuspended','__lw_plate_assay_A2'):
   requirements.append((['state','artifacts','material_state','containers',bindings[name],'component_quantities','GFP_CELL_DEBRIS'],{'dimension':'count','unit':'cells','value':50000.0}))
  for path,expected in requirements:
   add(x,'gfp/run.json',path,'culsma/run.json')
   assert x['checks'][-1]['equals']==expected, (path,expected)
  # Retain the magnetic witness as an additional check.
  add(x,'material-audit.json',['typed_quantities_and_association_passed'],'magnetic-comparison.json',['culsma','typed_quantities_and_association_passed'])
  x=row(s,'M4','Yes','Returned local references remain usable; unbound local use outside a procedure is rejected.','scope-mechanism-evidence.md')
  for i in [0,1]:add(x,'scope.json',['cases',i,'diagnostics'],'scope-mechanisms.json',[s,'cases',i,'diagnostics'])
  x=row(s,'L1','Yes','One procedure called with 10/20-uL arguments produces 10/20-uL destinations.','l1-mechanism-evidence.md')
  for i in [0,1]:
   for k in ['name','volume_uL']:add(x,'l1/culsma/output.json',['report','materials','final_products',i,k])
  add(x,'l1/culsma/summary.json',['runtime_ok'])
  x=row(s,'L2','Yes','Single returned container is bound to the next procedure; target receives 10 uL.','l2-mechanism-evidence.md')
  for k in ['name','volume_uL']:add(x,'l2/culsma/output.json',['report','materials','final_products',0,k])
  add(x,'l2/culsma/summary.json',['runtime_ok'])
  x=row(s,'L3','Yes','Counted repetition and exclusive branching on injected runtime observations; no physical measurement.','l3-mechanism-evidence.md')
  for group,keys in [('loops',['2','3']),('branches',['1250','800'])]:
   for key in keys:
    for field in ['ok','volumes_ul']:add(x,'l3/culsma/results.json',[group,key,field])
  add(x,'l3/culsma/results.json',['same_plan_used_for_both_values'])
 elif s=='labop':
  x=row(s,'M1','Yes','Native GFP EmptyContainer and PlateCoordinates samples outputs feed downstream transfers.','m1-mechanism-evidence.md')
  for name in ('EmptyContainer','PlateCoordinates'):
   x['checks'].append({'file':'gfp-references.json','path':['samples_outputs_used_by_transfer',name],'equals':True})
  for field in ('completed_normally','validation_errors','well_volumes_uL'):
   add(x,'gfp-references.json',[field],'gfp-labop-native/location_continuation/results.json')
  x=row(s,'M2','No','Standard Spin document validation accepts a volume-valued duration.','m2-mechanism-evidence.md')
  for i in [0,1]:add(x,'duration.json',['cases',i,'accepted'],'duration-unit-check.json',[s,'cases',i,'accepted'])
  x=row(s,'M3','No','Published handler inventory lacks the tested material-separation propagation; GFP extension assessed separately.','material-evolution-evidence.md')
  add(x,'material-audit.json',['default_handlers'],'magnetic-comparison.json',['labop','default_handlers'])
  x=row(s,'M4','Yes','Activity ownership enforces model-reference scope; Python helper scope is distinct.','scope-mechanism-evidence.md')
  for field in ['owner','python_helper_name_in_rdf','cross_activity_rejection']:add(x,'scope.json',[field],'scope-mechanisms.json',[s,field])
  x=row(s,'L1','No','Parameterized nested activity loses the quantity input; direct Transfer and official upstream test are controls.','l1-mechanism-evidence.md')
  for mode in ['direct','subprotocol']:
   for field in ['validation_errors','executed_transfers','latest_recorded_buffer_ul']:add(x,'l1/labop-reproduction/comparison.json',['results',mode,field])
  add(x,'l1/public-api-audit/results.json',['upstream_subprotocol_test','success'])
  add(x,'l1/public-api-audit/results.json',['counterexample_official_harness','executed_transfer_amounts_ul'])
  x=row(s,'L2','No','Nested output-to-input execution receives two sample values; direct operations work.','l2-mechanism-evidence.md')
  add(x,'l2/labop/results.json',['results','direct','latest_recorded_buffer_ul'])
  for mode in ['composition','composition_explicit_final']:
   add(x,'l2/labop/results.json',['results',mode,'validation_errors'])
   for k in ['type','message']:add(x,'l2/labop/results.json',['results',mode,'execution_error',k])
  x=row(s,'L3','No','Both guarded Transfer branches execute for either Boolean input; native cycle raises the retained MergeNode error.','l3-mechanism-evidence.md')
  for i in [4,5]:
   for k in ['runtime_values','consumed_values','volumes_ul','completed_normally']:add(x,'l3/labop/results.json',['cases',i,k])
  for i in [2,3]:add(x,'l3/labop/results.json',['cases',i,'execution_error','message'])
 else:
  x=row(s,'M1','Yes','Named labware declarations and distinct resolved endpoints; not a claim of complete local binding.','bpl-modeling-evidence.md')
  add(x,'bpl-modeling/results.json',['cases','named_entities','declaration_types'])
  add(x,'bpl-modeling/results.json',['cases','named_entities','primitives'])
  x=row(s,'M2','No','Duration and transfer lowering accept incompatible dimensions.','bpl-modeling-evidence.md')
  for case in ['duration_valid','duration_wrong_dimension','volume_wrong_dimension']:
   for field in ['diagnostics','primitives']:add(x,'bpl-modeling/results.json',['cases',case,field])
  x=row(s,'M3','No','Transfer moves liquid volume but does not propagate the seeded component into the destination.','bpl-modeling-evidence.md')
  add(x,'bpl-modeling/results.json',['transfer_simulation'])
  x=row(s,'M4','No','Documented let-bound 10/20-uL transfer arguments are rejected with SEMANTIC_MISSING_VOLUME by the public CLI.','scope-mechanism-evidence.md')
  retained={row['case']:row for row in json.loads((r/'bpl-m4/result.json').read_text())}
  for case in ('m4_let_10','m4_let_20'):
   assert (p/'cases/m4/bpl'/f'{case}.bpl').read_bytes()==(r/'bpl-m4'/f'{case}.bpl').read_bytes()
   for action in ('check','validate','lower'):
    assert retained[case][action]==11
    assert 'SEMANTIC_MISSING_VOLUME' in retained[case][action+'_msg']
    for field,expected in [('returncode',11),('diagnostic_codes',['SEMANTIC_MISSING_VOLUME'])]:
     x['checks'].append({'file':'bpl-m4/results.json','path':[case,action,field],'equals':expected})
  x=row(s,'L1','No','Procedure bodies and argument binding are absent on the checked CLI route; direct and no-argument controls retained.','bpl-l1-evidence.md')
  for case in ['direct','function_calls','undefined_calls']:
   for target in ['human','simulation']:
    for field in ['returncode','steps']:add(x,'l1/bpl-cli/results.json',['cases',case,'lower',target,field])
  for case in ['no_parameters','no_parameters_direct']:
   add(x,'l1/bpl-endpoint-binding/results.json',['cases',case,'lower','simulation','steps'])
  x=row(s,'L2','No','Changing the callee body or return leaves plans unchanged; simulation ignores the call while direct control works.','l2-mechanism-evidence.md')
  for field in ['body_change_leaves_operations_identical','return_change_leaves_operations_identical','direct_volume_change_changes_operations']:add(x,'l2/bpl-consumption/results.json',[field])
  for case in ['base-simulate','base-strict','direct_10-simulate']:add(x,'l2/bpl-consumption/results.json',['simulations',case,'returncode'])
  x=row(s,'L3','No','Loop/conditional blocks are omitted from executable plans; direct three-transfer control remains.','l3-mechanism-evidence.md')
  for case in ['loop_2','loop_3','branch_true','branch_false','direct_3']:
   for field in ['returncode','steps']:add(x,'l3/bpl-cli/results.json',['cases',case,'lower','simulation',field])
for s in ['bpl','labop']:
 x=next(x for x in result[s] if x['criterion']=='L1')
 paths=[['runs','bpl-lower','returncode'],['runs','bpl-simulate','returncode']] if s=='bpl' else [['runs','protocol_outputs_test','summary','test','success']]
 for path in paths:add(x,'upstream-examples/results.json',path)
x=next(x for x in result['culsma'] if x['criterion']=='L2')
state=json.loads((r/'l2/culsma/run.json').read_text())['state']['artifacts']['material_state']
for identity in state['containers']:
 add(x,'l2/culsma/run.json',['state','artifacts','material_state','containers',identity,'volume_uL'])

# Additional GFP observations already retained and reviewed.
x=row('labop','M3 / GFP released route','No','Released material semantics: execution completes, but no Spin fraction outputs or material updater; this is not an execution-failure verdict.','material-evolution-evidence.md')
add(x,'gfp-labop-native/results.json',['extension_used'])
add(x,'gfp-labop-native/results.json',['cases', 'spin_prefix', 'fraction_output_names'])
add(x,'gfp-labop-native/results.json',['cases', 'spin_prefix', 'spin_has_default_material_handler'])
add(x,'gfp-labop-native/results.json',['cases', 'spin_prefix', 'validation_errors'])
add(x,'gfp-labop-native/results.json',['cases', 'spin_prefix', 'completed_normally'])
add(x,'gfp-labop-native/results.json',['cases', 'spin_prefix', 'execution_exception'])
add(x,'gfp-labop-native/results.json',['cases', 'location_continuation', 'fraction_output_names'])
add(x,'gfp-labop-native/results.json',['cases', 'location_continuation', 'spin_has_default_material_handler'])
add(x,'gfp-labop-native/results.json',['cases', 'location_continuation', 'validation_errors'])
add(x,'gfp-labop-native/results.json',['cases', 'location_continuation', 'completed_normally'])
add(x,'gfp-labop-native/results.json',['cases', 'location_continuation', 'execution_exception'])
add(x,'gfp-labop-native/results.json',['cases', 'location_continuation', 'well_volumes_uL'])
add(x,'gfp-labop-native/results.json',['cases', 'location_continuation', 'well_reagents'])
x=row('bpl','GFP task','No','Documented optical syntax fails; reduced projection has correct liquid totals but skips centrifugation, mixing and measurement, and does not carry components.','gfp-three-system-evidence.md')
add(x,'gfp-bpl/results.json',['cases', 'gfp_documented', 'check_returncode'])
add(x,'gfp-bpl/results.json',['cases', 'gfp', 'cli_api_operations_match'])
add(x,'gfp-bpl/results.json',['cases', 'gfp', 'default', 'volume_expectations_met'])
add(x,'gfp-bpl/results.json',['cases', 'gfp', 'default', 'unsupported_step_count'])
add(x,'gfp-bpl/results.json',['cases', 'gfp', 'default', 'well_components'])
add(x,'gfp-bpl/results.json',['cases', 'gfp', 'strict', 'success'])
add(x,'gfp-bpl/results.json',['cases', 'gfp_transfers_only', 'default', 'volume_expectations_met'])
add(x,'gfp-bpl/results.json',['cases', 'gfp_transfers_only', 'default', 'unsupported_step_count'])

(p/'replay_expectations.json').write_text(json.dumps(result,indent=2)+'\n')
