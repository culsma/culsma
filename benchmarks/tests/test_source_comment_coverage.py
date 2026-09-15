import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from source_comment_coverage import assess, source_steps, compact

SOURCE='# Example\n\n## Steps\n\n1. Prepare a sample.\n\n2. Hold at 37 C.\n'
PROGRAM='protocol Test() {\n// 1. Prepare a sample.\nlet sample = tube();\n// 2. Hold at 37 C.\nhold(sample = sample);\n}\nTest();\n'

def ast(program):
    nodes=[]
    for text,kind,extra in [('let sample = tube();','LetStatement',{'value':{'_type':'CallExpr','name':'tube'}}),('hold(sample = sample);','StepCall',{}),('let placeholder = 1;','LetStatement',{'value':{'_type':'NumberLiteral','value':1}})]:
        if text not in program:continue
        start=program.index(text);nodes.append(dict(_type=kind,span={'start':start,'end':start+len(text),'line':program.count('\n',0,start)+1},**extra))
    end=program.index('}')+1;root=program.index('Test();')
    return {'protocols':[{'span':{'start':0,'end':end},'statements':nodes}], 'statements':[{'_type':'StepCall','span':{'start':root,'end':root+7,'line':program.count('\n',0,root)+1}}]}

class CoverageTests(unittest.TestCase):
    def test_complete_and_scope_boundary(self):
        r=assess(SOURCE,PROGRAM,ast(PROGRAM));self.assertEqual(r['coverage_percent'],100)
        self.assertEqual(len(r['steps'][1]['code_regions']),1)
    def test_missing_keeps_denominator(self):
        p=PROGRAM.replace('// 2. Hold at 37 C.\n','');r=assess(SOURCE,p,ast(p))
        self.assertEqual((r['source_steps'],r['matched_steps'],r['coverage_percent']),(2,1,50))
    def test_altered_quote(self):
        p=PROGRAM.replace('// 2. Hold at 37 C.','// 2. Hold at 38 C.');r=assess(SOURCE,p,ast(p))
        self.assertEqual(r['steps'][1]['status'],'text_mismatch')
    def test_duplicate_does_not_inflate_score(self):
        p=PROGRAM.replace('// 2. Hold at 37 C.','// 2. Hold at 37 C.\n// 2. Hold at 37 C.');r=assess(SOURCE,p,ast(p))
        self.assertEqual(r['matched_steps'],1);self.assertEqual(r['steps'][1]['status'],'duplicate_comment')
    def test_only_comment_or_placeholder_fails(self):
        for replacement in ('','let placeholder = 1;'):
            p=PROGRAM.replace('hold(sample = sample);',replacement);r=assess(SOURCE,p,ast(p))
            self.assertEqual(r['steps'][1]['status'],'no_code_region')
    def test_unknown_annotation_not_in_denominator(self):
        p=PROGRAM.replace('}\nTest();','// 3. Unexpected instruction.\n}\nTest();');r=assess(SOURCE,p,ast(p))
        self.assertEqual(r['source_steps'],2);self.assertFalse(r['passed']);self.assertEqual(len(r['unknown_annotations']),1)
    def test_source_format_and_whitespace(self):
        for s in ('','2. Missing one.','# Title\n1. Prepare sample.'):
            with self.assertRaises(ValueError):source_steps(s)
        p=PROGRAM.replace('// 2. Hold at 37 C.','// 2. Hold at\n// 37 C.');self.assertTrue(assess(SOURCE,p,ast(p))['passed'])
    def test_reordering_flagged(self):
        p=PROGRAM.replace('// 1. Prepare a sample.','// 2. Hold at 37 C.').replace('// 2. Hold at 37 C.\nhold','// 1. Prepare a sample.\nhold');r=assess(SOURCE,p,ast(p))
        self.assertFalse(r['order_preserved']);self.assertFalse(r['passed'])

class CompactRecordTests(unittest.TestCase):
    def test_success_records_counts_without_repeating_matched_steps(self):
        r=compact(assess(SOURCE,PROGRAM,ast(PROGRAM)))
        self.assertEqual(r, {'total_steps':2,'matched_steps':2,'coverage_percent':100.0,'status':'pass','issues':[]})
    def test_only_unmatched_steps_are_recorded(self):
        p=PROGRAM.replace('// 2. Hold at 37 C.','// 2. Hold at 38 C.')
        r=compact(assess(SOURCE,p,ast(p)))
        self.assertEqual(r['issues'],[{'step':2,'reason':'text_mismatch'}])
        self.assertEqual(r['status'],'incomplete')
    def test_errors_and_order_are_not_hidden_by_counts(self):
        r=compact({'errors':['Parser failed']})
        self.assertEqual(r['status'],'error');self.assertIsNone(r['coverage_percent'])
        r=compact({'source_steps':2,'matched_steps':2,'coverage_percent':100,'order_preserved':False,'passed':False})
        self.assertEqual(r['status'],'incomplete');self.assertEqual(r['issues'],[{'step':None,'reason':'order_changed'}])

class SourceFormatTests(unittest.TestCase):
    def test_context_and_notes_do_not_change_denominator(self):
        source = '# Example\n## Context\n1. Not a workflow step.\n\n## Steps\n1. Prepare a sample.\n2. Hold at 37 C.\n\n## Notes\n1. Background only.\n'
        self.assertEqual([r['step'] for r in source_steps(source)], [1,2])
        self.assertTrue(assess(source,PROGRAM,ast(PROGRAM))['passed'])
    def test_duplicate_or_empty_steps_section_rejected(self):
        for source in ('## Steps\n## Notes\nBackground.', '## Steps\n1. Prepare.\n## Steps\n1. Repeat.'):
            with self.assertRaises(ValueError):source_steps(source)

if __name__=='__main__':unittest.main()
