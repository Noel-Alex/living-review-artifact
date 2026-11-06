import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_c6 import safety_family,hybrid,strict_tracker
from wpc_core import digest,failed

def trial(old,new,path='a.py',start=1,end=2):
    return dict(anchor=dict(path=path,line_start=start,line_end=end,quotation='\n'.join(old.splitlines()[start-1:end]),content_hash=digest(old)),old_lines=old.splitlines(),version={path:(digest(new),new)})

class C6(unittest.TestCase):
    def test_ig_python_absolute_layout_and_fixed_location(self):
        old='    a()\n    b()\n';t=trial(old,'a()\nb()\n');o=dict(label='exact',placement=['a.py',1],range=['a.py',1,2],recheck=False)
        got=safety_family(t,{'a.py':old},o)
        self.assertFalse(got['quote']['recheck']);self.assertTrue(got['IG']['recheck']);self.assertEqual(got['IG']['label'],'changed')
        for v in got.values():self.assertEqual(v['placement'],o['placement']);self.assertEqual(v['range'],o['range'])
    def test_nonpython_absolute_indent_is_not_ig(self):
        old='    a();\n    b();\n';t=trial(old,'a();\nb();\n',path='a.java');o=dict(label='exact',placement=['a.java',1],range=['a.java',1,2],recheck=False)
        self.assertFalse(safety_family(t,{'a.java':old},o)['IG']['recheck'])
    def test_ag_preexisting_copy_and_no_fabricated_old(self):
        old='a()\nb()\n';t=trial(old,old);t['version']['b.py']=(digest(old),old)
        o=dict(label='moved',placement=['b.py',1],range=['b.py',1,2],recheck=False)
        self.assertTrue(safety_family(t,{'a.py':old,'b.py':old},o)['AG']['recheck'])
        self.assertFalse(safety_family(t,{'a.py':old},o)['AG']['recheck'])
    def test_failure_not_deletion_or_fallback(self):
        t=trial('a()\nb()\n','');err=failed('parse');cross=dict(label='moved',placement=['b.py',1],range=['b.py',1,2],recheck=False,tier='cross_exact')
        self.assertEqual(hybrid(err,cross),err)
        self.assertTrue(all(v['label']=='execution_error' for v in safety_family(t,{},err).values()))
    def test_hybrid_only_cross_exact(self):
        no=dict(label='removed',placement=None,range=None,recheck=True)
        other=dict(label='changed',placement=['a.py',3],range=['a.py',3,4],recheck=True,tier='local')
        self.assertIs(hybrid(no,other),no)
        other['tier']='cross_exact';self.assertEqual(hybrid(no,other)['placement'],other['placement'])
    def test_strict_samepath_absence(self):
        t=trial('a()\nb()\n','a()\nb()\n');t['version']={}
        renamed=dict(label='moved',placement=['b.py',1],range=None,recheck=False)
        self.assertEqual(strict_tracker(t,renamed)['label'],'removed')
    def test_guards_equal_frozen_postselection_when_location_agrees(self):
        from wpb_variants import prepare,choose
        examples=[('    a()\n    b()\n','a()\nb()\n'),('a()\nb()\n','x()\na()\nb()\n'),('a()\nb()\n','a()\nb()\nx()\na()\nb()\n')]
        for old,new in examples:
            t=trial(old,new);d=prepare(t,{'a.py':old});base=choose(d);family=safety_family(t,{'a.py':old},base)
            for layer,ig,ag in [('quote',False,False),('IG',True,False),('AG',False,True),('IG+AG',True,True)]:
                frozen=choose(d,ig=ig,ag=ag)
                if frozen['placement']==base['placement']:
                    for field in ('label','recheck','reasons'):self.assertEqual(family[layer][field],frozen[field],(old,new,layer,field))
    def test_paired_direction_denominator_and_zero_denominator(self):
        from analyze_wpc_c6 import paired,BASES,TRANSFER
        good=dict(label='changed',placement=['a.py',1],range=['a.py',1,1],recheck=True)
        bad=dict(label='exact',placement=['a.py',3],range=['a.py',3,3],recheck=False)
        rows=[dict(suite='indentation',source_file=p,cls='edited',truth_at=['a.py',1],anchor_at=['a.py',1],reference_range=['a.py',1,1],methods={**{m:dict(bad) for m in BASES},**{m:dict(good) for m in TRANSFER}}) for p in ('first.py','second.py')]
        result=paired(rows)['gumtree+IG+AG minus t0.85-deployed']
        self.assertEqual(result['clusters'],2)
        for name,expected in [('accuracy',1),('missed',-1),('wrong_silent',-1),('lost',0)]:
            got=result['metrics'][name];self.assertEqual(got['difference'],expected);self.assertEqual(got['cluster95'],[expected,expected])
        self.assertIsNone(result['metrics']['false_recheck']['cluster95'])
        self.assertEqual(result['metrics']['false_recheck']['undefined_resamples'],10000)
        self.assertEqual(result['metrics']['accuracy']['exact_paired']['p'],.5)

if __name__=='__main__':unittest.main()
