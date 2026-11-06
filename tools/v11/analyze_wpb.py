"""B1 metrics reuse WPA events/rates, with explicit proposed AG request semantics."""
from collections import Counter, defaultdict
import csv
import math
import sys
import numpy as np
from wpa_core import ROOT, read, sha, events, rate, outcome
from wpb_variants import THETAS, SWITCHES, variant_key
from run_wpb import OUT, write, verify_freeze

SEED=20261031
METRICS=('accuracy','placement_accuracy','classification_accuracy','classification_five_accuracy',
         'missed','false_recheck','wrong','wrong_silent','wrong_with_recheck','lost','gone_correct',
         'gone_misreported','adapter_missed','adapter_false_recheck','range_correct','same_subset_start_correct','false_unchanged')


def event(r,o):
    e=events(r,o)
    changed=r['cls'] in ('edited','gone')
    wrong=e['wrong']
    request=o['recheck']
    e.update(missed=int(changed and not request),false_recheck=int(not changed and request),
             wrong_silent=int(wrong and not request),wrong_with_recheck=int(wrong and request),
             false_unchanged=int(r.get('ast_changed',False) and not request),recheck=int(request))
    ref=r['reference_range']
    e['range_correct']=int(ref is not None and o.get('range')==ref)
    e['same_subset_start_correct']=int(ref is not None and o['placement']==ref[:2])
    return e


def denominators(r):
    changed=r['cls'] in ('edited','gone')
    survives=r['truth_at'] is not None
    return dict(n=1,changed=int(changed),preserved=int(not changed),survivors=int(survives),gone=int(not survives),
                range_eligible=int(r['reference_range'] is not None),AST_changed=int(r.get('ast_changed',False)))


DENOMS=dict(placement_accuracy='survivors',missed='changed',adapter_missed='changed',false_recheck='preserved',
            adapter_false_recheck='preserved',lost='survivors',gone_correct='gone',gone_misreported='gone',
            range_correct='range_eligible',same_subset_start_correct='range_eligible',false_unchanged='AST_changed')


def strata(r):
    suite=r['suite']
    result=[suite,suite+':'+r.get('op','all')]
    if suite=='short':
        result += ['short:'+r['frequency']+':'+r['tokens'],
                   'short:'+r['frequency']+':'+r['tokens']+':'+r['op']]
    if suite=='real':
        result += ['real:'+r['group'],'real:'+r['group']+':'+r['sample'],
                   'real:'+r['sample'],'real:project:'+r['repo'], 'real:horizon:'+str(r['horizon'])]
    return list(dict.fromkeys(result))


def exact_binomial(b,c):
    n=b+c
    if not n:return dict(b=b,c=c,p=1.,log10_p=0.)
    k=min(b,c)
    terms=[math.lgamma(n+1)-math.lgamma(j+1)-math.lgamma(n-j+1)-n*math.log(2) for j in range(k+1)]
    mx=max(terms)
    logp=min(0.,math.log(2)+mx+math.log(sum(math.exp(v-mx) for v in terms)))
    return dict(b=b,c=c,p=math.exp(logp),log10_p=logp/math.log(10))


def paired(records):
    """Same resampled clusters for both outputs; denominators fixed by reference."""
    if not records:return {}
    names=list(records[0]['methods'])
    comparisons=[]
    for method in names:
        baseline='t0.55-deployed' if method.startswith('t0.55') else 't0.85-deployed'
        if method!=baseline:comparisons.append((method,baseline))
        if baseline!='t0.85-deployed':comparisons.append((method,'t0.85-deployed'))
    comparisons=list(dict.fromkeys(comparisons))
    results={}
    measure=('accuracy','missed','false_recheck','wrong_silent','range_correct')
    clusters=defaultdict(lambda:np.zeros((len(measure),len(names)+1),dtype=np.int64))
    discord=defaultdict(lambda:[0,0])
    for r in records:
        cluster=r['pair'] if r['suite']=='real' else r['source_file']
        es={m:event(r,r['methods'][m]) for m in names}
        ds=denominators(r)
        for j,metric in enumerate(measure):
            d=ds[DENOMS.get(metric,'n')]
            clusters[cluster][j,0]+=d
            clusters[cluster][j,1:]+=[es[m][metric] for m in names]
            if not d:continue
            for m,b in comparisons:
                x,y=es[m][metric],es[b][metric]
                discord[m,b,metric][0]+=int(x==1 and y==0)
                discord[m,b,metric][1]+=int(x==0 and y==1)
    matrix=np.stack(list(clusters.values()))
    total=matrix.sum(axis=0)
    rng=np.random.default_rng(SEED)
    bootstrap=np.empty((10000,len(measure),len(names)))
    for at in range(0,10000,250):
        weights=rng.multinomial(len(matrix),np.full(len(matrix),1/len(matrix)),size=min(250,10000-at))
        sums=np.einsum('bc,cmn->bmn',weights,matrix,optimize=True)
        with np.errstate(divide='ignore',invalid='ignore'):
            bootstrap[at:at+len(weights)]=sums[:,:,1:]/sums[:,:,:1]
    for m,b in comparisons:
        mi,bi=names.index(m),names.index(b)
        result={}
        for j,metric in enumerate(measure):
            if metric=='range_correct' and (not m.startswith('t0.') or not b.startswith('t0.')):
                result[metric]=dict(n=0,difference=None,cluster95=None,reason='line-only comparator has no end-line contract')
                continue
            if not total[j,0]:
                result[metric]=dict(n=0,difference=None,cluster95=None)
                continue
            values=bootstrap[:,j,mi]-bootstrap[:,j,bi]
            finite=values[np.isfinite(values)]
            result[metric]=dict(n=int(total[j,0]),difference=float((total[j,mi+1]-total[j,bi+1])/total[j,0]),
                cluster95=np.quantile(finite,[.025,.975]).tolist() if len(finite) else None,
                undefined_resamples=int(10000-len(finite)),exact_paired=exact_binomial(*discord[m,b,metric]))
        results[m+' minus '+b]=result
    return dict(n=len(records),clusters=len(matrix),cluster_unit='commit pair' if records[0]['suite']=='real' else 'source file',
                resamples=10000,seed=SEED,contrasts=results,
                multiplicity='Nominal exploratory paired tests/intervals, no familywise-error claim; lower missed/false/wrong rates are better.')


def analyze(stage):
    completion=read(OUT/stage/'completion.json')['data']
    assert completion['complete']
    counts=defaultdict(Counter)
    totals=defaultdict(Counter)
    confusion=defaultdict(Counter)
    costs=defaultdict(Counter)
    cluster_records=defaultdict(list)
    indent_cases=[]
    special=[]
    reindent=defaultdict(Counter)
    n=0
    archived=read(ROOT/'evidence/v11-wpa/gate-trials.json')['data']
    real_archived={r['row']:r for r in archived if r['benchmark']=='real'}
    special_ids={i for i,r in real_archived.items() if r['missed_case'] or events(r,r['methods']['cascade'])['wrong_silent']}
    source_hashes={}
    paths=sorted((OUT/stage).glob('trials-*.json'))
    correction_paths=sorted((OUT/'development-correction').glob('trials-*.json')) if stage=='development' else []
    if correction_paths:assert read(OUT/'development-correction/completion.json')['data']['complete']
    for path in paths+correction_paths:
        source_hashes[str(path.relative_to(ROOT)).replace('\\','/')]=sha(path)
        document=read(path)
        for r in document['data']:
            if correction_paths and path.parent.name=='development' and r['suite']=='duplicates':continue
            n+=1
            es={m:event(r,o) for m,o in r['methods'].items()}
            ds=denominators(r)
            for s in strata(r):
                totals[s].update(ds)
                for method,o in r['methods'].items():
                    counts[s,method].update(es[method])
                    confusion[s,method][o['label']+' / '+r['cls']]+=1
                    if not ds['preserved']:continue
                    for theta in THETAS:
                        base='t'+format(theta,'.2f')+'-deployed'
                        if not method.startswith('t'+format(theta,'.2f')):continue
                        costs[s,method].update(dict(preserved=1,extra=int(o['recheck'] and not r['methods'][base]['recheck']),
                                                  spared=int(not o['recheck'] and r['methods'][base]['recheck'])))
            suite=r['suite']
            cluster_records[suite].append(r)
            if suite=='real':
                for s in ('real:'+r['group'],'real:'+r['group']+':'+r['sample']):cluster_records[s].append(r)
            if 'indentation_match' in r:indent_cases.append(r)
            if suite=='real' and r['row'] in special_ids:
                special.append(dict(row=r['row'],repo=r['repo'],pair=r['pair'],oracle_class=r['cls'],
                    original_missed=bool(real_archived[r['row']]['missed_case']),
                    original_wrong_silent=bool(events(real_archived[r['row']],real_archived[r['row']]['methods']['cascade'])['wrong_silent']),
                    truth_at=r['truth_at'],methods=r['methods']))
            if 'original_reindent_audit' in r:
                a=r['original_reindent_audit'];bucket=reindent[str(r['seed'])]
                bucket['n']+=1
                for k,v in a.items():
                    if isinstance(v,bool):bucket[k]+=v
                bucket['new_parse_failed']+=not a['new_parseable']
                bucket['parseable_AST_unchanged']+=a.get('old_parseable',False) and a.get('new_parseable',False) and not a.get('module_AST_changed',False)
                bucket['no_recheck']+=not r['methods']['t0.85-deployed']['recheck']
    assert n==completion['n']
    summaries={}
    for s,d in totals.items():
        methods={}
        for (ss,m),c in counts.items():
            if ss!=s:continue
            methods[m]=dict(event_counts=dict(c),execution_errors=c['failure'],label_by_class=dict(confusion[s,m]),
                           **{metric:rate(c[metric],d[DENOMS.get(metric,'n')]) for metric in METRICS})
            if not m.startswith('t'):
                methods[m]['range_correct']=dict(k=None,n=d['range_eligible'],rate=None,reason='line-only comparator; no end line inferred')
            if (s,m) in costs:
                k=costs[s,m]
                methods[m]['extra_rechecks_per_100_preserved']=100*k['extra']/k['preserved']
                methods[m]['spared_rechecks_per_100_preserved']=100*k['spared']/k['preserved']
                methods[m]['net_extra_rechecks_per_100_preserved']=100*(k['extra']-k['spared'])/k['preserved']
                methods[m]['extra_recheck_counts']=dict(k)
        summaries[s]=dict(denominators=dict(d),methods=methods)
    result=dict(stage=stage,n=n,strata=summaries,original_reindent_audit={s:dict(c) for s,c in reindent.items()},
                real_indentation_matches=dict(n=len(indent_cases),labels=dict(Counter(r['indentation_match']['label'] for r in indent_cases)),
                                             oracle_classes=dict(Counter(r['cls'] for r in indent_cases)),
                                             oracle_how=dict(Counter(r['how'] for r in indent_cases))),
                raw_input_sha256=source_hashes,
                held_out_status='All real histories are retrospective. Only post-freeze seed-2 stress construction is newly held out here. WP C human annotations and WP H student stand-in remain later evaluations.')
    write(stage+'-summary.json',result)
    write(stage+'-indentation-cases.json',indent_cases)
    write(stage+'-archived-safety-cases.json',special)
    print(stage,'summary',n,'indentation-matches',len(indent_cases),flush=True)
    # The many operator/stratum tables retain Wilson intervals; cluster comparisons are primary suite/real-group analyses.
    paired_results={}
    for s,records in cluster_records.items():
        print('paired',stage,s,len(records),flush=True)
        paired_results[s]=paired(records)
    write(stage+'-paired.json',paired_results)


if __name__=='__main__':
    stage=sys.argv[1]
    if stage=='evaluation':verify_freeze()
    analyze(stage)
