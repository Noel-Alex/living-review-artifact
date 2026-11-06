"""Independent count conservation, location invariance and segment identity."""
import sys
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_c6 import *
from analyze_wpc_c6 import load_all,strata,BASES,TRANSFER
from analyze_wpc import merged

def main():
    gate();rows,inputs=load_all();summary=read(OUT/'c6/summary.json')['data'];populations=strata(rows);counts=Counter(r['suite'] for r in rows)
    prior=Counter();frozen_baselines={}
    for p in (ROOT/'evidence/v11-wpb1/evaluation').glob('trials-*.json'):
        for r in read(p)['data']:
            if r['suite'] in ('indentation','duplicates','short'):
                prior[r['suite']]+=1
                key=tuple(r.get(k) for k in ('suite','op','index','seed','frequency','tokens'))
                frozen_baselines[key]={m:r['methods']['t0.85-deployed' if m=='deployed_native' else m] for m in BASES}
    assert {s:counts[s] for s in prior}==dict(prior)
    assert counts['real']==15064 and counts['original']==3600 and counts['external']==2392
    assert len(rows)==summary['n']==sum(counts.values())
    invariants=Counter()
    c15={r['id']:{m:r['methods']['cascade' if r['suite']=='external' else 't0.85-deployed'] if m=='deployed_native' else r['methods'][m] for m in (*BASES,'gumtree','codemapper')} for r in merged()}
    for r in rows:
        if r['suite'] in ('indentation','duplicates','short'):
            key=tuple(r.get(k) for k in ('suite','op','index','seed','frequency','tokens'))
            for m in BASES:assert r['methods'][m]==frozen_baselines[key][m],(r['id'],m,'B1 outcome drift')
        else:
            for m in BASES:assert r['methods'][m]==c15[r['id']][m],(r['id'],m,'C1-C5 baseline drift')
            for m in ('gumtree','codemapper'):assert r['c6_bases'][m]==c15[r['id']][m],(r['id'],m,'native mapping drift')
        invariants['unchanged_baseline_rows']+=1
        for matcher,base in r['c6_bases'].items():
            for layer in LAYERS:
                o=r['methods'][matcher+'+'+layer]
                assert o['placement']==base['placement'] and o.get('range')==base.get('range'),(r['id'],matcher,layer)
                assert o.get('character_range')==base.get('character_range')
                if base['label']=='execution_error':assert o['label']=='execution_error' and o['recheck']
                if o['label'] in ('changed','removed','execution_error'):assert o['recheck']
                invariants['fixed_location_range_character']+=1
        track=r['c6_bases']['tracker'];hy=r['c6_bases']['hybrid']
        if track['placement'] is not None:assert track['placement'][0]==r['anchor_at'][0]
        if track['placement'] is not None or track['label']=='execution_error':assert hy==track
        elif hy['placement'] is not None:assert hy.get('hybrid_fallback') and hy.get('tier')=='cross_exact'
    for name,x in summary['strata'].items():
        subset=populations[name];assert x['n']==len(subset)
        for method,m in x['methods'].items():
            good=errors=wrong=lost=0
            for r in subset:
                o=r['methods'][method]
                if o['label']=='execution_error':errors+=1
                elif o['placement']==r['truth_at']:good+=1
                elif o['placement'] is None:lost+=1
                else:wrong+=1
            assert good+errors+wrong+lost==len(subset)
            assert m['accuracy']['k']==good and m['execution_errors']==errors,(name,method)
            invariants['stratum_method_counts']+=1
    report=read(OUT/'c6/report-data.json')['data']
    for p,h in report['tex_files'].items():assert sha(OUT/'c6/tex'/p)==h
    assert sha(ROOT/'review/V11-WPC-C6-RESULTS.md')==report['report_sha256']
    c15=read(OUT/'c15-completion.json')['data'];assert sha(ROOT/'review/V11-WPC-RESULTS.md')==c15['report_sha256']
    assert read(OUT/'c6/tests-verification.json')['data']['passed']
    assert read(OUT/'c6/environment-verification.json')['data']['passed']
    write('c6/verification.json',dict(passed=True,n=len(rows),suites=dict(counts),checks=dict(invariants),c15_unchanged=True,b1_hashes_verified=True),inputs+[OUT/'c6/summary.json',OUT/'c6-protocol-freeze.json',OUT/'c6/tests-verification.json'])
    print('C6 independent verification passed',len(rows),dict(invariants),flush=True)
if __name__=='__main__':main()
