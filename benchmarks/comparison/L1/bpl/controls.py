"""Run upstream examples/tests to distinguish working routes from L1/L2 failures.

No laboratory hardware or LLM calls. Upstream code is unmodified; LabOP output
directories and Graphviz rendering are the only redirected behavior.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

ENV = Path(os.environ["COMPARISON_RUNTIME_DIR"])
PACKAGE = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "controls"

LABOP = r'''
import importlib.util, io, json, runpy, sys, unittest
from pathlib import Path
from unittest.mock import patch
from collections import Counter
import labop
from labop.execution.harness import ProtocolHarness, ProtocolExecutionNTuples
from evaluate import save_dot

source, out, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
out.mkdir(parents=True,exist_ok=True)
harnesses=[]
def relocated_harness(*args, **kwargs):
    kwargs['base_dir']=str(out)
    h=ProtocolHarness(*args, **kwargs)
    harnesses.append(h)
    return h
report={'mode':mode}
with patch('labop.execution.harness.ProtocolHarness', relocated_harness), patch('graphviz.Digraph.render',save_dot):
    if mode=='protocol_outputs_test':
        spec=importlib.util.spec_from_file_location('upstream_protocol_outputs',source/'test/test_protocol_outputs.py')
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        stream=io.StringIO()
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.TestSuite([
            module.TestProtocolOutputs('test_protocol_outputs')]))
        (out/'unittest.txt').write_text(stream.getvalue())
        report['test']={'success':result.wasSuccessful(),'tests_run':result.testsRun,
                       'failures':len(result.failures),'errors':len(result.errors)}
    else:
        runpy.run_path(str(source/'examples/protocols/ludox/LUDOX_protocol.py'),run_name='__main__')
report['executions']=[]
for h in harnesses:
    for artifact in h.artifacts_of_type(ProtocolExecutionNTuples):
        ex=artifact.execution
        calls=[r for r in ex.executions if isinstance(r,labop.CallBehaviorExecution)]
        report['executions'].append({
            'completed_normally':ex.completed_normally,
            'calls_by_behavior':dict(Counter(str(r.get_behavior().identity) for r in calls)),
            'protocol_calls':[str(r.get_behavior().identity) for r in calls if isinstance(r.get_behavior(),labop.Protocol)],
            'outputs':[{'name':p.get_name(),'value_type':type(p.value.get_value()).__name__}
                       for p in ex.parameter_values if p.get_parameter().is_output()],
            'issues':{str(k):list(map(str,v)) for k,v in artifact.execution_engine.issues.items()}})
(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
print('RESULT_JSON='+json.dumps(report))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=["bpl", "labop", "all"], default="all")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(PACKAGE))
    report = {"labop_commit": "2e2bd88150c71a440771fd369f40295dfd622324",
              "bpl_commit": "4e505740f5025d59ba655c6c955f83876f753007", "runs": {}}
    def invoke(label, args):
        try:
            result = subprocess.run(list(map(str,args)), cwd=OUT, env=env,
                                    capture_output=True,text=True,timeout=120)
            (OUT/(label+'.stdout.txt')).write_text(result.stdout)
            (OUT/(label+'.stderr.txt')).write_text(result.stderr)
            row={'command':list(map(str,args)),'returncode':result.returncode}
            for line in result.stdout.splitlines():
                if line.startswith('RESULT_JSON='): row['summary']=json.loads(line[12:])
        except subprocess.TimeoutExpired as exc:
            row={'command':list(map(str,args)),'timeout_seconds':120}
            for suffix,value in [('stdout',exc.stdout),('stderr',exc.stderr)]:
                (OUT/(label+'.'+suffix+'.txt')).write_text(value.decode(errors='replace') if isinstance(value,bytes) else value or '')
        report['runs'][label]=row
        (OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n')
        print(label, {k:v for k,v in row.items() if k!='command'},flush=True)

    if args.system in ("bpl", "all"):
        path=ENV/'bpl-source/examples/minimal_protocol.bpl'
        report['bpl_input_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        (OUT/'upstream_minimal_protocol.bpl').write_bytes(path.read_bytes())
        cli=ENV/'bpl-env/bin/bplc'
        invoke('bpl-lower',[cli,'lower',path,'--target','simulation','--out',OUT/'bpl-plan.json','--json-errors'])
        invoke('bpl-simulate',[cli,'simulate',path,'--trace',OUT/'bpl-trace.json','--json-errors'])
    for mode in (['protocol_outputs_test','ludox'] if args.system in ('labop', 'all') else []):
        relative='test/test_protocol_outputs.py' if mode=='protocol_outputs_test' else 'examples/protocols/ludox/LUDOX_protocol.py'
        report[mode+'_source_sha256']=hashlib.sha256((ENV/'labop-source'/relative).read_bytes()).hexdigest()
        invoke(mode,[ENV/'labop-env/bin/python','-c',LABOP,ENV/'labop-source',OUT/mode,mode])
    # The upstream harness emits thousands of tiny specialization JSON files.
    # Retain them losslessly in ZIP files instead of thousands of Git entries.
    for directory in OUT.glob('*/**/artifacts/MarkdownSpecialization'):
        files = sorted(directory.glob('*.json'))
        if not files:
            continue
        archive = directory.parent / 'MarkdownSpecialization.json-artifacts.zip'
        with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as bundle:
            for path in files:
                bundle.write(path, arcname='MarkdownSpecialization/' + path.name)
        with ZipFile(archive) as bundle:
            for path in files:
                assert bundle.read('MarkdownSpecialization/' + path.name) == path.read_bytes()
        for path in files:
            path.unlink()
        if not any(directory.iterdir()):
            directory.rmdir()


if __name__=='__main__':
    main()
