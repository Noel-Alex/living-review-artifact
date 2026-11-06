"""Supplement the default/full-range gate with every archived threshold corner."""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime,timezone
import itertools
from wpa_core import loaders,runs,fuzzy,cell_output,outcome
from wpb_variants import prepare,choose
from run_wpa_gate import controlled_payloads,real_payloads
from run_wpb import ROOT,OUT,write,verify_freeze
from wpa_core import sha
from pathlib import Path


def initialize():
    global M,B
    M,B=loaders()


def work(payload):
    version,items=payload
    counts=Counter()
    for meta,t,archived,_,_ in items:
        if version is not None:t['version']=version
        a=t['anchor'];path=a['path'];origin=a['line_start']-1
        old='\n'.join(t['old_lines'])+'\n'
        data=prepare(t,{path:old})
        # Complete candidates for archived thresholds above this protocol's fixed 0.85/0.55.
        # The frozen protocol's actual candidate builder and variants are not changed.
        if not data['hash'] and data['wanted'] and not data['same'] and data['cross'] is None:
            for p in sorted(p for p in t['version'] if p!=path):
                found=runs(t['version'][p][1],data['wanted'])
                if found:data['cross']=(p,*found[0]);break
        M.FUZZY_CODE=.55
        native=M.relocate_code(a,t['version'],old)
        candidate=choose(data,.55)
        native_range=None if native['match']=='removed' else [native['path'],native['line_start'],native['line_end']]
        assert candidate['label']==native['match'] and candidate['range']==native_range,(meta,'native055')
        counts[meta['benchmark']]+=1
        if 'theta' not in archived:continue
        for key,value in archived['theta'].items():
            expected=value[0] if isinstance(value,list) else value
            o=choose(data,float(key))
            assert outcome(meta['truth_at'],o['placement'])==expected,(meta,'final',key)
            counts['final_threshold_checks']+=1
        same=None if not data['same'] else [path,min(data['same'],key=lambda r:abs(r[0]-origin))[0]+1]
        cross=None if data['cross'] is None else [data['cross'][0],data['cross'][1]+1]
        legacy=[0,None]
        if not data['hash'] and same is None and cross is None and path in t['version']:
            text=t['version'][path][1]
            score,at=fuzzy(text,data['wanted'],data['span'],tuple(range(max(1,len(text.splitlines())-data['span']+1))))
            legacy=[score,None if at is None else [path,at+1]]
        f=dict(hash=[path,origin+1] if data['hash'] else None,same=same,cross=cross,whole_legacy=legacy)
        for key,value in archived.get('theta_v1',{}).items():
            o=cell_output(f,'cross_first','whole','legacy',float(key),[path,origin+1])
            p=None if o['placement'] is None else (o['placement'][0],o['placement'][1]-1)
            actual,silent=B.score(t,p,o['label']!='exact')
            assert actual==value[0] and silent==value[1],(meta,'v1',key,actual,silent,value)
            counts['v1_threshold_checks']+=1
    return dict(counts)


def main():
    verify_freeze()
    _,b=loaders();pins={};counts=Counter()
    with ProcessPoolExecutor(max_workers=6,initializer=initialize) as pool:
        pending=[]
        def consume():
            counts.update(pending.pop(0).result())
            if sum(counts[k] for k in ('main','replication','real'))%500<25:print(dict(counts),flush=True)
        for payload in itertools.chain(controlled_payloads(b),real_payloads(pins)):
            pending.append(pool.submit(work,payload))
            if len(pending)>=12:consume()
        while pending:consume()
    assert {k:counts[k] for k in ('main','replication','real')}==dict(main=3600,replication=3600,real=15064)
    assert counts['final_threshold_checks']==counts['v1_threshold_checks']==15064*8
    write('threshold-reproduction-gate.json',dict(passed=True,counts=dict(counts),completed_utc=datetime.now(timezone.utc).isoformat(),
          script_sha256=sha(Path(__file__)),checks='All archived final/v1 threshold outcomes and v1 silent flags, plus native theta-0.55 labels/full ranges on both controlled seeds and every real observation. Protocol candidate generation remains unchanged.'))
    print('PASS',dict(counts),flush=True)


if __name__=='__main__':main()
