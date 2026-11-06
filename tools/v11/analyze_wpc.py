"""WP C aggregation, explicit reproduction gate, paired statistics and TeX."""
import sys,json,math,csv,re,itertools
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
from wpa_core import events
from analyze_wpb import event,denominators,DENOMS,exact_binomial
PRIMARY=('t0.85-deployed','t0.85-IG+AG+VW','t0.55-IG+AG+VW')
def fix_upstream_file_absence(rows):
    for r in rows:
        if 'input_error' in r or r.get('truth_region') is not None:continue
        for name,o in r['methods'].items():
            score=r.get('character_scores',{}).get(name,{}).get('upstream')
            if score and score.get('exact') and not upstream_file_agrees(r['annotation']['target_file'],None,o):
                r.setdefault('reporting_corrections',{})[name]=dict(original_upstream=score,reason='upstream also checks explicit native file on deleted-region predictions')
                r['character_scores'][name]['upstream']=character_score('',None,None,False,upstream=True)
    return rows
def load(stage):
    assert read(OUT/stage/'completion.json')['data']['complete'],stage+' incomplete'
    rows=[r for p in sorted((OUT/stage).glob('trials-*.json')) for r in read(p)['data']]
    assert len(rows)==read(OUT/stage/'completion.json')['data']['n']
    assert len({r['id'] for r in rows})==len(rows)
    return fix_upstream_file_absence(rows) if stage.startswith('external-') else rows
def char_summary(rows,name,view='upstream'):
    values=[r.get('character_scores',{}).get(name,{}).get(view,{}) for r in rows]
    k=sum(v.get('exact',0) for v in values);partial=[v['distance'] for v in values if v.get('partial') and v.get('distance') is not None]
    return dict(n=len(rows),exact=rate(k,len(rows)),overlap=rate(sum(v.get('overlap',0) for v in values),len(rows)),partial_n=len(partial),distance_mean=sum(partial)/len(partial) if partial else None,**{key:sum(v.get(key,0.) for v in values)/len(rows) if rows else None for key in ('precision','recall','f1')})
def repaired_native_rows(final=False):
    initial=load('external-codemapper-native');byid={r['id']:r for r in initial}
    stages=['external-codemapper-native-repair']+(['external-codemapper-native-repair2'] if final else [])
    for stage in stages:
      for r in load(stage):
        old=byid[r['id']]
        assert 'lazy fetching disabled' in old['methods']['codemapper'].get('error','') or 'promisor remote' in old['methods']['codemapper'].get('error','')
        for key in ('source_sha256','target_sha256','old_commit','new_commit','annotation'):assert old[key]==r[key],(r['id'],key)
        r['prior_io_failure']=old['methods']['codemapper'];byid[r['id']]=r
    return [byid[r['id']] for r in initial]
def reproduction(native=False,repaired=False,final=False):
    stage='external-codemapper-native' if native else 'external-codemapper'
    rows=repaired_native_rows(final) if repaired else load(stage);tables=read(OUT/'published-tables.json')['data'];result={}
    for index,dataset in enumerate(('annotation_a','annotation_b','suppression','variable_test','block_test','method_test')):
        subset=[r for r in rows if r['dataset']==dataset];observed=char_summary(subset,'codemapper')
        table=tables[0 if index<3 else 1];column=3*(index%3)+3;published={}
        for row in table[2:]:
            key={'Exact matches':'exact','Overlapping':'overlap','Char. dist.':'distance_mean','Recall':'recall','Precision':'precision','F1-score':'f1'}[row[0]]
            published[key]=float(re.match(r'[\d.]+',row[column]).group())
        differences={}
        for key,value in published.items():
            got=observed[key]['k'] if key in ('exact','overlap') else observed[key]
            digits=0 if key in ('exact','overlap') else 1 if key=='distance_mean' else 3
            if got is None or round(got,digits)!=value:differences[key]=dict(published=value,observed=got)
        result[dataset]=dict(observed=observed,published=published,differences=differences,exact_reproduction=not differences,input_failures=sum('input_error' in r for r in subset),execution_failures=sum(r['methods']['codemapper']['label']=='execution_error' for r in subset))
    inputs=[OUT/'published-tables.json',OUT/'external-input-index.json',OUT/'dataset-acquisition.json']+sorted((OUT/stage).glob('trials-*.json'))
    if repaired:inputs+=sorted((OUT/'external-codemapper-native-repair').glob('trials-*.json'))
    if final:inputs+=sorted((OUT/'external-codemapper-native-repair2').glob('trials-*.json'))
    suffix='-native-final' if final else ('-native' if native else '')+('-repaired' if repaired else '')
    write('codemapper-reproduction'+suffix+'.json',dict(passed=all(v['exact_reproduction'] for v in result.values()),datasets=result,scope='actual execution of unchanged native matching; '+('source-compatible native resolver' if native else 'frozen direct-rename adapter')+('; acquisition-only missing-object corrections overlaid, initial failures separately retained' if repaired else '')+'; not fast reaggregation'),inputs)
    print(json.dumps({k:v['differences'] for k,v in result.items()},indent=1),flush=True)
def ev(row,o):
    result=event(row,o)
    if o['label']=='execution_error':result['range_correct']=result['same_subset_start_correct']=0
    return result
def groups(rows):
    result=defaultdict(list)
    for r in rows:
        if r['suite']=='original':names=['controlled:'+r['benchmark'],'controlled:'+r['benchmark']+':'+r['op']]
        elif r['suite']=='real':names=['real','real:'+r['group'],'real:'+r['sample'],'real:'+r['group']+':'+r['sample'],'real:project:'+r['repo'],'real:class:'+r['cls']]
        else:
            names=['external','external:'+r['dataset'],'external:language:'+r.get('language','Unavailable'),'external:'+r['dataset']+':'+r.get('language','Unavailable')]
            if r.get('language') not in ('Python',None) and not r.get('language','Other').startswith('Other'):names+=['external:non-Python-code']
            if r['dataset'] in ('annotation_a','annotation_b'):
                names+=['external:human-AB','external:human-AB:language:'+r.get('language','Unavailable')]
                if r.get('language') not in ('Python',None) and not r.get('language','Other').startswith('Other'):names+=['external:human-AB:non-Python-code']
        for name in names:result[name].append(r)
    return result
METRICS=('accuracy','placement_accuracy','classification_accuracy','missed','false_recheck','wrong','wrong_silent','lost','gone_correct','adapter_missed','adapter_false_recheck','range_correct','same_subset_start_correct')
def metrics(rows,name):
    known=[r for r in rows if 'input_error' not in r]
    c=Counter();d=Counter();conf=Counter()
    for r in known:
        o=r['methods'][name];c.update(ev(r,o));d.update(denominators(r));conf[o['label']+' / '+r['cls']]+=1
    unavailable=len(rows)-len(known);c['failure']+=unavailable;d['n']+=unavailable
    result=dict(n=len(rows),reference_unavailable=unavailable,execution_errors=c['failure'],counts=dict(c),denominators=dict(d),label_by_class=dict(conf),**{k:rate(c[k],d[DENOMS.get(k,'n')]) for k in METRICS})
    if all(r['methods'][name].get('range') is None for r in known) and name in ('cascade_v1','quote_exact','diff_drift','line_number','tracker_adapter'):
        result['range_correct']=dict(k=None,n=d['range_eligible'],rate=None,reason='line-only comparator has no native end')
    times=[r['methods'][name].get('wall_ms',r['methods'][name].get('elapsed_ms')) for r in known]
    times=[t for t in times if t is not None]
    result['runtime_ms']=dict(n=len(times),median=float(np.median(times)) if times else None,p95=float(np.quantile(times,.95)) if times else None,total=sum(times),note='Warm persistent processes; GT includes cache-hit lookup. Matching-only file-pair times retained per raw output. Not cold interpreter startup latency.')
    if rows[0]['suite']=='external':result['characters']={view:char_summary(rows,name,view) for view in ('upstream','positional')}
    return result
def paired(rows):
    known=[r for r in rows if 'input_error' not in r]
    if not known:return {}
    comparisons=[(tool,base) for tool in ('gumtree','codemapper') if tool in known[0]['methods'] for base in PRIMARY if base in known[0]['methods']]
    measures=('accuracy','range_correct','missed','wrong_silent')
    result={}
    for tool,base in comparisons:
        cluster=defaultdict(lambda:np.zeros((len(measures),3),dtype=np.int64));discord={m:[0,0] for m in measures}
        for r in known:
            key=r['source_file'] if r['suite']=='original' else r['pair'];a,b=ev(r,r['methods'][tool]),ev(r,r['methods'][base]);ds=denominators(r)
            for j,m in enumerate(measures):
                den=ds[DENOMS.get(m,'n')];cluster[key][j]+=[den,a[m],b[m]]
                if den:discord[m][0]+=int(a[m] and not b[m]);discord[m][1]+=int(b[m] and not a[m])
        matrix=np.stack(list(cluster.values()));total=matrix.sum(axis=0);rng=np.random.default_rng(20261031);boot=[]
        for at in range(0,10000,250):
            weights=rng.multinomial(len(matrix),np.full(len(matrix),1/len(matrix)),size=min(250,10000-at));sums=np.einsum('bc,cmn->bmn',weights,matrix,optimize=True)
            with np.errstate(divide='ignore',invalid='ignore'):boot.append((sums[:,:,1]-sums[:,:,2])/sums[:,:,0])
        boot=np.concatenate(boot);contrast={}
        for j,m in enumerate(measures):
            vals=boot[:,j];finite=vals[np.isfinite(vals)]
            contrast[m]=dict(n=int(total[j,0]),difference=float((total[j,1]-total[j,2])/total[j,0]) if total[j,0] else None,cluster95=np.quantile(finite,[.025,.975]).tolist() if len(finite) else None,undefined_resamples=10000-len(finite),exact_paired=exact_binomial(*discord[m]))
        result[tool+' minus '+base]=dict(clusters=len(matrix),resamples=10000,seed=20261031,metrics=contrast)
    return result
def merged():
    gt=load('gumtree-living')
    for r in gt:r['methods']=dict(r['methods'],gumtree=r.pop('output'))
    native_cm={r['id']:r for r in load('codemapper-living-native')}
    for r in gt:
        r['methods']['codemapper']=native_cm[r['id']]['output']
    native={r['id']:r for r in load('external-codemapper')};ext=load('external-frozen')
    canonical={r['id']:r for r in repaired_native_rows(True)}
    for r in ext:
        n=native[r['id']];r['methods']['codemapper_direct_adapter']=n['methods']['codemapper'];r.setdefault('character_scores',{})['codemapper_direct_adapter']=n.get('character_scores',{}).get('codemapper',{})
        n=canonical[r['id']];r['methods']['codemapper']=n['methods']['codemapper'];r['character_scores']['codemapper']=n.get('character_scores',{}).get('codemapper',{})
    return gt+ext
def analyze():
    import time
    deadline=time.monotonic()+7200
    while not (OUT/'codemapper-reproduction-native-final.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('native missing-object corrections incomplete')
        time.sleep(10)
    verify_freeze();rows=merged();strata=groups(rows);summaries={};pairs={}
    for name,subset in strata.items():
        names=list(subset[0]['methods']);summaries[name]=dict(n=len(subset),methods={m:metrics(subset,m) for m in names})
        if name in ('controlled:main','controlled:replication','real','real:own','real:oss','real:own:targeted','real:oss:targeted','external:human-AB','external:human-AB:non-Python-code','external:non-Python-code','external:annotation_a','external:annotation_b','external:suppression','external:variable_test','external:block_test','external:method_test'):
            print('paired',name,len(subset),flush=True);pairs[name]=paired(subset)
    # A separately declared same-file-reference subset retains gone cases and all parse failures.
    for suite in ('original','real'):
        subset=[r for r in rows if r['suite']==suite and (r['truth_at'] is None or r['truth_at'][0]==r['anchor_at'][0])]
        summaries[suite+':same-file']=dict(n=len(subset),methods={m:metrics(subset,m) for m in subset[0]['methods']})
    for name,predicate in [('external:same-file',lambda r:True),('external:human-AB:same-file',lambda r:r['dataset'] in ('annotation_a','annotation_b'))]:
        subset=[r for r in rows if r['suite']=='external' and 'input_error' not in r and predicate(r) and (r['truth_at'] is None or r['truth_at'][0]==r['anchor_at'][0])]
        summaries[name]=dict(n=len(subset),methods={m:metrics(subset,m) for m in subset[0]['methods']})
    disagreements=[dict(id=r['id'],row=r['row'],repo=r['repo'],group=r['group'],cls=r['cls'],pair=r['pair'],truth_at=r['truth_at'],gumtree=r['methods']['gumtree'],oracle_range=r['reference_range']) for r in rows if r['suite']=='real' and ev(r,r['methods']['gumtree'])['accuracy']==0]
    reporting_repairs=[dict(id=r['id'],corrections=r['reporting_corrections']) for r in rows if r.get('reporting_corrections')]
    inputs=[OUT/'external-input-index.json',OUT/'dataset-acquisition.json',OUT/'native-resolver-freeze.json']+[p for stage in ('gumtree-living','codemapper-living-native','external-frozen','external-codemapper-native','external-codemapper-native-repair','external-codemapper-native-repair2','external-codemapper') for p in sorted((OUT/stage).glob('trials-*.json'))]
    write('evaluation-summary.json',dict(strata=summaries,n=len(rows),disagreement_count=len(disagreements),disagreement_groups=dict(Counter(r['cls'] for r in disagreements)),code_mapper_path_adaptation=True,external_scope='paired-file restricted inputs for Living Review; native CodeMapper resolver has Git-history scope'),inputs)
    write('paired-comparisons.json',pairs,inputs);write('oracle-disagreements.json',disagreements,inputs)
    write('upstream-file-reporting-repairs.json',reporting_repairs,inputs)
    print('summary',len(rows),'disagreements',len(disagreements),flush=True)
def gumtree_analysis():
    rows=load('gumtree-living')
    for r in rows:r['methods']=dict(r['methods'],gumtree=r['output'])
    result={}
    for name,subset in groups(rows).items():
        result[name]=dict(n=len(subset),methods={m:metrics(subset,m) for m in ('gumtree',*PRIMARY)})
    write('gumtree-checkpoint-summary.json',result,sorted((OUT/'gumtree-living').glob('trials-*.json')))
    for name in ('controlled:main','controlled:replication','real','real:oss:targeted'):
        print(name,{m:v['accuracy'] for m,v in result[name]['methods'].items()},flush=True)
if __name__=='__main__':
    if sys.argv[1]=='reproduction':reproduction()
    elif sys.argv[1]=='reproduction-native':reproduction(True)
    elif sys.argv[1]=='reproduction-native-repaired':reproduction(True,True)
    elif sys.argv[1]=='reproduction-native-final':reproduction(True,True,True)
    elif sys.argv[1]=='all':analyze()
    elif sys.argv[1]=='gumtree-checkpoint':gumtree_analysis()
