#!/usr/bin/env python3
"""Report numbered source-step correspondence with verbatim comments and AST code regions.

This metric is not numerical fidelity, semantic completeness or language capability.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

RULES = 'steps-section-correspondence-v1'
PARSER = '''import dataclasses,hashlib,importlib.metadata,json,pathlib,sys
from culsma.parser import parse
import culsma.parser.parser as parser_module
def encode(x):
    if dataclasses.is_dataclass(x):
        return dict(_type=type(x).__name__, **{f.name:encode(getattr(x,f.name)) for f in dataclasses.fields(x)})
    if isinstance(x,(list,tuple)): return [encode(v) for v in x]
    if isinstance(x,dict): return {str(k):encode(v) for k,v in x.items()}
    return x
ast=parse(sys.stdin.read())
print(json.dumps({'ast':encode(ast),'environment':{'culsma':importlib.metadata.version('culsma'),'lark':importlib.metadata.version('lark'),'parser_file_sha256':hashlib.sha256(pathlib.Path(parser_module.__file__).read_bytes()).hexdigest()}},default=str))
'''
MARKER = re.compile(r'^[ \t]*//[ \t]+([1-9]\d*)\.[ \t]+(.+)$')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def normalize(text):
    return ' '.join(text.split())


def source_steps(source):
    lines = source.splitlines()
    starts = [i for i, text in enumerate(lines) if text == '## Steps']
    if len(starts) != 1:
        raise ValueError('Source must contain exactly one ## Steps section')
    start = starts[0] + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith('## ')), len(lines))
    rows = []
    current = None
    for line, text in enumerate(lines[start:end], start + 1):
        if not text.strip(): continue
        m = re.fullmatch(r'([1-9]\d*)\.\s+(.+)', text)
        if m:
            current = {'step':int(m[1]),'source_line':line,'text':m[2]}; rows.append(current)
        elif current and not text.lstrip().startswith(('#', '|', '- ', '* ')):
            current['text'] += ' ' + text.strip()
        else:
            raise ValueError(f'Source line {line}: expected numbered experimental instructions only')
    if not rows or [r['step'] for r in rows] != list(range(1,len(rows)+1)):
        raise ValueError('Source steps must be nonempty and consecutively numbered from 1')
    for r in rows: r['text'] = normalize(r['text'])
    return rows


def parse_program(program, python):
    result = subprocess.run([str(python), '-I', '-c', PARSER], input=program,
                            text=True, capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError('Culsma parser failed: ' + result.stderr[-2000:])
    return json.loads(result.stdout)


def meaningful(node):
    if isinstance(node,dict):
        if node.get('_type') in ('MutationStmt','StepCall','CallExpr'): return True
        return any(meaningful(v) for k,v in node.items() if k!='span')
    return isinstance(node,list) and any(meaningful(v) for v in node)


def statements(ast):
    result=[]
    def walk(node, path=''):
        if isinstance(node,dict):
            for k,v in node.items():
                if k=='statements':
                    for i,s in enumerate(v):
                        if s.get('span') and meaningful(s): result.append((path+f'/statements/{i}',s))
                if k!='span': walk(v,path+'/'+k)
        elif isinstance(node,list):
            for i,v in enumerate(node): walk(v,path+'/'+str(i))
    walk(ast)
    return result


def assess(source, program, ast):
    expected=source_steps(source)
    lines=program.splitlines(keepends=True); offsets=[];offset=0
    for line in lines: offsets.append(offset);offset+=len(line)
    markers=[]
    for i,line in enumerate(lines):
        m=MARKER.fullmatch(line.rstrip('\r\n'))
        if not m:continue
        parts=[m[2]];end=i+1
        while end<len(lines) and re.match(r'^[ \t]*//',lines[end]):
            if MARKER.fullmatch(lines[end].rstrip('\r\n')):break
            parts.append(re.sub(r'^[ \t]*//[ \t]?', '', lines[end]).strip());end+=1
        markers.append({'step':int(m[1]),'text':normalize(' '.join(parts)), 'comment_line':i+1,
                        'offset':offsets[i],'end':offsets[end] if end<len(lines) else len(program)})
    candidates=statements(ast); rows=[]
    for src in expected:
        found=[m for m in markers if m['step']==src['step']]
        row=dict(src,occurrences=len(found),status='missing_comment',comment_line=None,
                 comment_lines=[m['comment_line'] for m in found],code_regions=[])
        if len(found)>1: row['status']='duplicate_comment'
        elif found:
            m=found[0]; row.update(comment_line=m['comment_line'],comment_text=m['text'])
            if m['text']!=src['text']:row['status']='text_mismatch'
            else:
                owners=[p['span'] for p in ast.get('protocols',[]) if p.get('span') and p['span']['start'] <= m['offset'] < p['span']['end']]
                scope_end=min((p['end'] for p in owners),default=len(program))
                end=min([scope_end]+[n['offset'] for n in markers if n['offset']>m['offset']])
                eligible=[(p,s) for p,s in candidates if m['end']<=s['span']['start'] and s['span']['end']<=end]
                eligible.sort(key=lambda x:(x[1]['span']['start'],-x[1]['span']['end']))
                # Exclude nested duplicates; include all statements belonging to this instruction region.
                regions=[]
                for p,s in eligible:
                    span=s['span']
                    if any(r['start']<=span['start']<r['end'] for r in regions):continue
                    regions.append(dict(pointer=p,node_type=s['_type'],line=span['line'],start=span['start'],end=span['end']))
                # The first statement must follow the comment directly, not an intervening brace/placeholder.
                between=program[m['end']:regions[0]['start']] if regions else ''
                if regions and not between.strip():
                    row.update(status='matched',code_regions=regions)
                else:row['status']='no_code_region'
        rows.append(row)
    unknown=[{'step':m['step'],'comment_line':m['comment_line']} for m in markers if m['step'] not in {r['step'] for r in expected}]
    ids=[m['step'] for m in markers if m['step'] in {r['step'] for r in expected}]
    order_ok=ids==sorted(ids)
    counts=dict(Counter(r['status'] for r in rows));matched=counts.get('matched',0)
    return {'metric':'source_step_correspondence','source_steps':len(rows),'matched_steps':matched,
            'coverage_percent':round(100*matched/len(rows),6),'counts':counts,'order_preserved':order_ok,
            'unknown_annotations':unknown,'passed':matched==len(rows) and order_ok and not unknown,
            'steps':rows,'errors':[]}


def compact(result):
    issues = [{'step': r['step'], 'reason': r['status']}
              for r in result.get('steps', []) if r['status'] != 'matched']
    issues += [{'step': r['step'], 'reason': 'unexpected_comment'}
               for r in result.get('unknown_annotations', [])]
    if result.get('order_preserved') is False:
        issues.append({'step': None, 'reason': 'order_changed'})
    issues += [{'step': None, 'reason': 'check_error', 'message': message}
               for message in result.get('errors', [])]
    return {
        'total_steps': result.get('source_steps'),
        'matched_steps': result.get('matched_steps'),
        'coverage_percent': result.get('coverage_percent'),
        'status': 'error' if result.get('errors') else ('pass' if result.get('passed') else 'incomplete'),
        'issues': issues,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True,type=Path);p.add_argument('--program',required=True,type=Path)
    p.add_argument('--python',default=sys.executable,help='Python environment containing Culsma')
    p.add_argument('--implementation',help='Recorded implementation revision supplied by caller')
    a=p.parse_args(); a.out=a.source.parent/'coverage.json'
    if a.source.parent.resolve() != a.program.parent.resolve(): p.error('Source and program must belong to the same case directory')
    if a.out.resolve() in (a.source.resolve(), a.program.resolve()): p.error('Output must not overwrite source or program')
    source_bytes=a.source.read_bytes();program_bytes=a.program.read_bytes()
    report={'schema':'source-coverage-v2','rules':RULES,
            'metric':'source_step_correspondence','case_id':a.source.parent.name,
            'implementation':a.implementation,'language_version':None,
            'source_sha256':digest(source_bytes),'program_sha256':digest(program_bytes)}
    try:
        source=source_bytes.decode();program=program_bytes.decode();source_steps(source)
        parsed=parse_program(program,a.python);report['language_version']=parsed['environment']['culsma']
        report.update(compact(assess(source,program,parsed['ast'])))
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        report.update(compact({'errors':[str(exc)]}))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,ensure_ascii=True)+'\n')
    print(str(a.out));print(f"{report.get('matched_steps')}/{report.get('total_steps')}; coverage={report['coverage_percent']}")
    return 0 if report['status'] == 'pass' else 1


if __name__=='__main__':raise SystemExit(main())
