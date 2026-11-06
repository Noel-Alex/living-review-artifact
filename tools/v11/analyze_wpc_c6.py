"""Separate registered C6 metrics, paired uncertainty and generated fragments."""
import sys,json,math
from pathlib import Path
from collections import Counter,defaultdict
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_c6 import *
from analyze_wpc import ev,groups,load
from analyze_wpb import denominators,DENOMS,exact_binomial
import numpy as np

BASES=('deployed_native','t0.85-deployed','t0.85-IG+AG+VW','t0.55-IG+AG+VW')
TRANSFER=tuple(m+'+'+l for m in MATCHERS for l in LAYERS)
MEASURES=('accuracy','placement_accuracy','classification_accuracy','classification_five_accuracy','missed','false_recheck','wrong','wrong_silent','wrong_with_recheck','lost','gone_correct','range_correct','same_subset_start_correct')
PAIR=('accuracy','missed','wrong_silent','lost','false_recheck')

def load_all():
    result=[];inputs=[]
    for stage in ('stress','reuse'):
        folder=OUT/'c6'/stage;completion=read(folder/'completion.json')['data'];assert completion['complete']
        paths=sorted(folder.glob('trials-*.json'));rows=[r for p in paths for r in read(p)['data']];assert len(rows)==completion['n'];result+=rows;inputs+=paths
    assert len({r['id'] for r in result})==len(result)
    native_alias(result)
    inputs+=sorted((OUT/'external-frozen').glob('trials-*.json'))+[OUT/'c6/baseline-identity-clarification.json']
    return result,inputs

def native_alias(rows):
    correction=read(OUT/'c6/baseline-identity-clarification.json')['data']
    assert not correction['hidden_cross_file_acceptances'],'Hybrid equivalence requires separate review'
    native={r['id']:r['methods']['cascade'] for r in load('external-frozen')}
    for r in rows:r['methods']['deployed_native']=native[r['id']] if r['suite']=='external' else r['methods']['t0.85-deployed']

def strata(rows):
    result=defaultdict(list)
    for r in rows:
        if r['suite'] in ('indentation','duplicates','short'):
            names=['stress','stress:'+r['suite'],'stress:'+r['suite']+':'+r['op']]
            if r['suite']=='short':names+=['stress:short:'+r['frequency']+':'+r['tokens']]
        elif r['suite']=='original':names=['controlled:replication','controlled:replication:'+r['op']]
        elif r['suite']=='real':names=['real','real:'+r['group'],'real:'+r['sample'],'real:'+r['group']+':'+r['sample'],'real:project:'+r['repo']]
        else:
            names=['external','external:'+r['dataset'],'external:language:'+r['language']]
            if r['dataset'] in ('annotation_a','annotation_b'):
                names+=['external:human-AB','external:human-AB:language:'+r['language']]
                if r['language']!='Python' and not r['language'].startswith('Other'):names+=['external:human-AB:non-Python-code']
        for name in names:result[name].append(r)
    return result

def metric(rows,name):
    c=Counter();d=Counter();conf=Counter()
    for r in rows:
        o=r['methods'][name];c.update(ev(r,o));d.update(denominators(r));conf[o['label']+' / '+r['cls']]+=1
    return dict(n=len(rows),execution_errors=c['failure'],label_by_class=dict(conf),counts=dict(c),denominators=dict(d),**{m:rate(c[m],d[DENOMS.get(m,'n')]) for m in MEASURES})

def paired(rows):
    names=BASES+TRANSFER;cluster=defaultdict(lambda:np.zeros((len(PAIR),len(names)+1),dtype=np.int64));disc=defaultdict(lambda:[0,0])
    for r in rows:
        key=r['pair'] if r['suite'] in ('real','external') else r['source_file'];ds=denominators(r);es={m:ev(r,r['methods'][m]) for m in names}
        for j,m in enumerate(PAIR):
            den=ds[DENOMS.get(m,'n')];cluster[key][j]+=[den]+[es[n][m] for n in names]
            if den:
                for tool in TRANSFER:
                    for base in BASES:
                        a,b=es[tool][m],es[base][m];disc[tool,base,m][0]+=int(a and not b);disc[tool,base,m][1]+=int(b and not a)
    matrix=np.stack(list(cluster.values()));tot=matrix.sum(axis=0);rng=np.random.default_rng(20261031);boot=[]
    for start in range(0,10000,100):
        weights=rng.multinomial(len(matrix),np.full(len(matrix),1/len(matrix)),size=min(100,10000-start));sums=np.einsum('bc,cmn->bmn',weights,matrix,optimize=True)
        with np.errstate(divide='ignore',invalid='ignore'):boot.append(sums[:,:,1:]/sums[:,:,:1])
    boots=np.concatenate(boot);result={}
    for tool in TRANSFER:
      for base in BASES:
        contrast={};a,b=names.index(tool),names.index(base)
        for j,m in enumerate(PAIR):
            vals=boots[:,j,a]-boots[:,j,b];finite=vals[np.isfinite(vals)]
            contrast[m]=dict(n=int(tot[j,0]),difference=float((tot[j,a+1]-tot[j,b+1])/tot[j,0]) if tot[j,0] else None,cluster95=np.quantile(finite,[.025,.975]).tolist() if len(finite) else None,undefined_resamples=int(10000-len(finite)),exact_paired=exact_binomial(*disc[tool,base,m]))
        result[tool+' minus '+base]=dict(clusters=len(matrix),resamples=10000,seed=20261031,metrics=contrast)
    return result

def main():
    gate();rows,inputs=load_all();populations=strata(rows);summaries={};pairs={};dominance=[]
    headlines={'stress:indentation','stress:duplicates','stress:short','controlled:replication','real','real:oss:targeted','external','external:human-AB','external:human-AB:non-Python-code','external:suppression','external:variable_test','external:block_test','external:method_test'}
    for name,subset in populations.items():
        summaries[name]=dict(n=len(subset),methods={m:metric(subset,m) for m in BASES+TRANSFER})
        if name in headlines:
            print('C6 paired',name,len(subset),flush=True);pairs[name]=paired(subset)
            base=summaries[name]['methods'][BASES[0]]
            for m in TRANSFER:
                other=summaries[name]['methods'][m]
                deltas={k:(other[k]['rate']-base[k]['rate']) if other[k]['rate'] is not None and base[k]['rate'] is not None else None for k in ('missed','wrong_silent','lost','false_recheck','accuracy')}
                descriptive=all(deltas[k] is not None and deltas[k]<=0 for k in ('missed','wrong_silent')) and any(deltas[k]<0 for k in ('missed','wrong_silent')) and deltas['lost'] is not None and deltas['lost']<=.01
                p=pairs[name][m+' minus '+BASES[0]]['metrics'];supported=descriptive and all(p[k]['cluster95'] is not None and p[k]['cluster95'][1]<=0 for k in ('missed','wrong_silent'))
                dominance.append(dict(population=name,method=m,descriptive_safety_dominance=descriptive,both_safety_upper_limits_nonpositive=supported,differences=deltas))
    write('c6/summary.json',dict(n=len(rows),strata=summaries,dominance=dominance,scope='retrospective registered C6 extension; C1-C5 unchanged'),inputs+[OUT/'c6-protocol-freeze.json'])
    write('c6/paired-comparisons.json',pairs,inputs+[OUT/'c6-protocol-freeze.json'])
    print('C6 summary complete',len(rows),flush=True)
if __name__=='__main__':main()
