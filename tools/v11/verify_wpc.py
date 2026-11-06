"""Independent count/identity/packet audit of retained WP C artifacts."""
import sys,json,csv,hashlib,re,gzip
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
from analyze_wpc import merged,groups,load
def main():
    verify_freeze();gate=read(OUT/'reproduction-gate.json')['data']
    assert gate['passed'] and gate['counts']==dict(main=3600,replication=3600,real=15064,tracker_execution_errors=143)
    rows=merged();assert len(rows)==7200+15064+2392,len(rows)
    assert Counter(r['suite'] for r in rows)==dict(original=7200,real=15064,external=2392)
    assert len({r['id'] for r in rows})==len(rows)
    summary=read(OUT/'evaluation-summary.json')['data'];strata=groups(rows)
    checks=Counter();failure_reasons=Counter()
    for name,result in summary['strata'].items():
        subset=strata.get(name)
        if subset is None:
            suite=name.split(':')[0];subset=[r for r in rows if r['suite']==suite and 'input_error' not in r and (r['truth_at'] is None or r['truth_at'][0]==r['anchor_at'][0]) and ('human-AB' not in name or r['dataset'] in ('annotation_a','annotation_b'))]
        assert len(subset)==result['n'],name
        for method,m in result['methods'].items():
            correct=errors=wrong=lost=0
            for r in subset:
                o=r['methods'][method]
                if 'input_error' in r or o['label']=='execution_error':errors+=1;continue
                truth=r['truth_at'];at=o['placement']
                if at==truth:correct+=1
                elif at is None:lost+=1
                else:wrong+=1
                if o.get('range') is not None:
                    assert len(o['range'])==3 and o['range'][0]==at[0] and o['range'][1]==at[1] and 1<=o['range'][1]<=o['range'][2],(r['id'],method,o)
                if r['suite']=='external':
                    c=r.get('character_scores',{}).get(method,{}).get('upstream',{})
                    expected=r['truth_region'];pred=o.get('scored_character_range')
                    native=o.get('native')
                    predicted_file=native[0].get('target_file') if native else (at[0] if at else None)
                    file_ok=predicted_file==r['annotation']['target_file'] or (predicted_file is None and expected is None)
                    exact=expected==pred and file_ok
                    assert c.get('exact',0)==int(exact),(r['id'],method,'character exact')
            assert correct+errors+wrong+lost==len(subset),(name,method)
            assert m['accuracy']['k']==correct and m['accuracy']['n']==len(subset),(name,method,'counts')
            assert m['execution_errors']==errors,(name,method,'errors')
            if m['accuracy']['rate'] is not None:assert abs(m['accuracy']['rate']-correct/len(subset))<1e-14
            checks['stratum_methods']+=1
    for r in rows:
        for method,o in r['methods'].items():
            if o['label']=='execution_error':failure_reasons[method+' / '+str(o.get('error',''))[:160]]+=1
            if method in ('gumtree','codemapper') and o['label']=='execution_error':assert o['placement'] is None and o['range'] is None
            if o.get('raw_pair_output'):assert (ROOT/o['raw_pair_output']).is_file()
    v7=sum(r['reference_range'] is not None for r in rows if r['suite']=='real');assert v7==14917,v7
    packet=OUT/'disagreement-packet';manifest=read(OUT/'packet-manifest.json')['data'];key=read(OUT/'disagreement-key.json')['data'];assert manifest['n']==len(key['cases'])==60
    assert not (packet/'disagreement-key.json').exists()
    for p,h in manifest['files'].items():assert sha(OUT/p)==h,p
    for p in packet.glob('C*/case.json'):
        d=read(p);assert not set(d)&{'truth_at','oracle_class','oracle_target','gumtree','methods','stratum'}
    with (packet/'reviewer-responses.csv').open(newline='',encoding='utf-8') as f:
        entries=list(csv.reader(f));assert len(entries)==61 and all(not any(r[1:]) for r in entries[1:])
    for record in read(OUT/'report-data.json')['data']['tex_files'].items():assert sha(OUT/'tex'/record[0])==record[1]
    frozen=read(ROOT/'evidence/v11-wpb1/protocol-freeze.json')['data']
    assert read(OUT/'tests-verification-final.json')['data']['passed']
    output=dict(passed=True,n=len(rows),suites=dict(Counter(r['suite'] for r in rows)),checks=dict(checks),v7_common_surviving_subset=v7,blinded_packet_cases=60,human_responses=0,b1_frozen_hashes=frozen['code_sha256'],failure_reasons=dict(failure_reasons),research_tests_log_sha256=sha(OUT/'tests-verification-final.json'),limitations=['CodeMapper fresh published-number gate qualified/failed as recorded','external Living Review input scope is paired files','timings use warm persistent workers, not cold-start comparison','no manuscript PDF or human adjudication produced'])
    write('verification.json',output,[OUT/'evaluation-summary.json',OUT/'paired-comparisons.json',OUT/'packet-manifest.json',OUT/'report-data.json'])
    print('verification passed',len(rows),'observations',checks['stratum_methods'],'stratum/method count checks',flush=True)
if __name__=='__main__':main()
