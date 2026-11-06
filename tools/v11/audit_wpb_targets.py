"""Target composition and pre-freeze/frozen internal consistency, from saved rows."""
from collections import Counter,defaultdict
from pathlib import Path
import re
from wpa_core import read,sha
from run_wpb import ROOT,OUT,write,verify_freeze
from wpb_stress import corpus


def rows(stage):
    for path in sorted((OUT/stage).glob('trials-*.json')):
        yield from read(path)['data']


def main():
    verify_freeze()
    _,files,_=corpus()
    categories=Counter();bystratum=defaultdict(Counter);examples=defaultdict(Counter)
    templates={'return':r'^return\b','import':r'^(?:import\s|from\s.*\simport\s)',
               'self-assignment':r'^self\.\w+\s*=', 'raise':r'^raise\b', 'condition':r'^(?:if|elif)\s.*:\s*$'}
    internal={}
    for r in rows('development'):
        if r['suite']=='real':internal[r['row']]=r
    comparisons=Counter();label_only=[];n=0
    for r in rows('evaluation'):
        if r['suite']=='short':
            quote=r['quotation'].strip()
            count=sum(s.strip()==quote for s in files[r['source_file']])
            f='1' if count==1 else '2-3' if count<=3 else '4+'
            nt=len(re.findall(r'\w+|[^\s\w]',quote))
            token='1-3' if nt<=3 else '4-6' if nt<=6 else '7+'
            assert f==r['frequency'] and token==r['tokens']
            kind=next((name for name,pattern in templates.items() if re.search(pattern,quote)),'other')
            categories[kind]+=1;bystratum[f+'/'+token][kind]+=1;examples[kind][quote]+=1;n+=1
        if r['suite']=='real' and r['group']=='own':
            before=internal[r['row']]
            for method,o in r['methods'].items():
                prior=before['methods'][method]
                for field in ('placement','range','recheck'):
                    assert o[field]==prior[field],(r['row'],method,field)
                if o['label']!=prior['label']:
                    assert 'pre-existing-copy' in o['reasons'] and o['label']=='moved' and prior['label']=='exact'
                    label_only.append(dict(row=r['row'],method=method,before=prior['label'],after=o['label']))
                comparisons[method]+=1
    assert n==16200
    assert all(v==len(internal)==3805 for v in comparisons.values())
    write('short-target-audit.json',dict(n=n,categories=dict(categories),strata={k:dict(v) for k,v in bystratum.items()},
          examples={k:[dict(quotation=q,n=c) for q,c in v.most_common(5)] for k,v in examples.items()},
          definition='Regex target categories; lexical bins and recurrence verified against original source. Categories are descriptive, not human labels.',script_sha256=sha(Path(__file__))))
    write('development-consistency.json',dict(internal_n=len(internal),per_method=dict(comparisons),
          placement_range_request_identical=True,pre_freeze_label_clarifications=label_only,script_sha256=sha(Path(__file__))))
    print('Short composition',dict(categories),'internal consistency',len(internal),'label clarifications',len(label_only),flush=True)


if __name__=='__main__':main()
