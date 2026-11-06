"""A1--A7 analyses, refusing ungated matcher results. All numbers originate here."""
from collections import Counter, defaultdict
import csv
import itertools
import json

from wpa_core import *
import numpy as np


def strata(records):
    result = {'all': records}
    if records[0]['benchmark'] == 'real':
        for g in ('own','oss'):
            result[g] = [r for r in records if r['group']==g]
            for s in ('uniform','targeted'):
                result[g+'-'+s] = [r for r in records if r['group']==g and r['sample']==s]
        for s in ('uniform','targeted'):
            result[s] = [r for r in records if r['sample']==s]
    else:
        result['within-file'] = [r for r in records if r['cls']!='moved file']
        for op in sorted({r['op'] for r in records}):
            result['op-'+op] = [r for r in records if r['op']==op]
    for cls in CLASSES:
        result['class-'+cls] = [r for r in records if r['cls']==cls]
    return {k:v for k,v in result.items() if v}


def outputs(sub, method):
    if isinstance(method,int):
        return [decode_output(r['grid'][method],r) for r in sub]
    return [r['methods'][method] for r in sub]


FINAL = CELLS.index(('fuzzy_first','local','full',.85))
CAL = CELLS.index(('fuzzy_first','local','full',.5))
V1CAL = CELLS.index(('cross_first','whole','legacy',.5))
FINAL75 = CELLS.index(('fuzzy_first','local','full',.75))
ANALYSIS_METHODS = list(METHODS)+['tracker_adapter','calibrated']


def summarize_method(sub, method):
    return summarize(sub, outputs(sub,CAL if method=='calibrated' else method))


def safety(benchmarks):
    result = {}
    for name, records in benchmarks.items():
        result[name] = {stratum:{m:summarize_method(sub,m) for m in ANALYSIS_METHODS}
                        for stratum,sub in strata(records).items()}
    write('safety-metrics.json', result, [OUT/'gate-trials.json',OUT/'reproduction-gate.json'])
    return result


def errors(benchmarks):
    missed = [r['missed_case'] for r in benchmarks['real'] if r['missed_case']]
    failures = [r['controlled_failure'] for name in ('main','replication') for r in benchmarks[name] if r['controlled_failure']]
    fields = ['tier','label','cls','how','repo','horizon','span','same_file_copies','other_file_copies','total_copies']
    grouped = {f:dict(Counter(str(r[f]) for r in missed)) for f in fields}
    joint = Counter((r['tier'],r['cls'],r['how'],r['repo'],r['horizon'],r['span'],r['same_file_copies'],r['other_file_copies']) for r in missed)
    result = {'missed_n':len(missed),'missed_cases':missed,'marginal_groups':grouped,
              'joint_groups':[dict(zip(['tier','cls','how','repo','horizon','span','same_file_copies','other_file_copies'],k),n=v) for k,v in joint.items()],
              'controlled_failure_cases':failures,
              'controlled_failure_groups':{name:dict(Counter(r['cause'] for r in failures if r['benchmark']==name)) for name in ('main','replication')},
              'cause_definitions':{'tie-breaking among identical runs':'same-file exact branch; at least two raw-equal runs',
                  'whitespace normalisation':'same-file exact branch without two raw-equal runs; normalized/raw ambiguity',
                  'local-window similarity':'local fuzzy branch wins at wrong location or for gone target',
                  'cross-file ordering':'cross-file exact branch selects wrong file/start or resurrects gone target',
                  'other':'unmatched residual, including no-match after full cascade'}}
    write('error-analysis.json',result,[OUT/'gate-trials.json'])
    with (OUT/'missed-recheck-cases.csv').open('w',newline='',encoding='utf-8') as stream:
        names = ['row','repo','sample','pair','horizon','span','cls','how','label','tier','same_file_copies','other_file_copies','total_copies','anchor_at','truth_at','placement','copies']
        writer = csv.DictWriter(stream,fieldnames=names,extrasaction='ignore')
        writer.writeheader()
        writer.writerows({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in r.items()} for r in missed)
    return result


def cluster_summary(sub, cluster_key, seed=20261031):
    method_keys = list(METHODS)+['tracker_adapter',CAL,V1CAL,FINAL75]
    names = list(METHODS)+['tracker_adapter','calibrated','v1_calibrated','final_theta075']
    arrays = [[events(r,o)['accuracy'] for r,o in zip(sub, outputs(sub,m))] for m in method_keys]
    groups = sorted({str(r[cluster_key]) for r in sub})
    by = {key:i for i,key in enumerate(groups)}
    sums = np.zeros((len(groups),len(method_keys)+1),dtype=np.int64)
    for i,r in enumerate(sub):
        j = by[str(r[cluster_key])]
        sums[j,0] += 1
        sums[j,1:] += [a[i] for a in arrays]
    rng = np.random.default_rng(seed)
    bootstrap = np.empty((10000,len(method_keys)))
    for start in range(0,10000,250):
        counts = rng.multinomial(len(groups),np.full(len(groups),1/len(groups)),size=min(250,10000-start))
        totals = counts @ sums
        bootstrap[start:start+len(counts)] = totals[:,1:]/totals[:,:1]
    total = sums.sum(axis=0)
    result = {'n':len(sub),'clusters':len(groups),'unit':cluster_key,'resamples':10000,'seed':seed,
              'methods':{name:dict(rate(int(total[i+1]),int(total[0])),cluster95=np.quantile(bootstrap[:,i],[.025,.975]).tolist()) for i,name in enumerate(names)}}
    contrasts = [('cascade',m) for m in names if m!='cascade']
    contrasts += [('calibrated','cascade'),('calibrated','cascade_v1'),('calibrated','v1_calibrated'),('calibrated','tracker_adapter'),('final_theta075','cascade_v1')]
    result['contrasts'] = {}
    for a,b in contrasts:
        i,j = names.index(a),names.index(b)
        result['contrasts'][a+'-minus-'+b] = {'difference':float((total[i+1]-total[j+1])/total[0]),
            'cluster95':np.quantile(bootstrap[:,i]-bootstrap[:,j],[.025,.975]).tolist(),
            'only_first':sum(x and not y for x,y in zip(arrays[i],arrays[j])),
            'only_second':sum(y and not x for x,y in zip(arrays[i],arrays[j]))}
    return result


def uncertainty(benchmarks):
    result = {}
    for name, rows in benchmarks.items():
        sets = strata(rows)
        sets = {k:v for k,v in sets.items() if not k.startswith(('op-','class-'))}
        result[name] = {}
        for label,sub in sets.items():
            units = ['pair','repo'] if name=='real' else ['source_file']
            result[name][label] = {u:cluster_summary(sub,u) for u in units}
        print('Bootstrap complete:',name,flush=True)
    rows = benchmarks['real']
    project = {}
    for sample in ('all','targeted','uniform'):
        project[sample] = {}
        for repo in sorted({r['repo'] for r in rows}):
            sub = [r for r in rows if r['repo']==repo and (sample=='all' or r['sample']==sample)]
            summary = cluster_summary(sub,'pair')
            project[sample][repo] = summary
    signs = {}
    for sample,projects in project.items():
        keys = next(iter(projects.values()))['contrasts']
        signs[sample] = {key:dict(Counter('positive' if p['contrasts'][key]['difference']>0 else 'negative' if p['contrasts'][key]['difference']<0 else 'zero' for p in projects.values())) for key in keys}
    result.update(per_project=project, sign_agreement=signs)
    write('cluster-uncertainty.json',result,[OUT/'gate-trials.json'])
    return result


def factorial(benchmarks):
    result = {}
    metrics = ('accuracy','missed','gone_correct','wrong')
    for name, rows in benchmarks.items():
        sets = {'all':rows} if name!='real' else {k:v for k,v in strata(rows).items() if k in ('all','own','oss','own-targeted','oss-targeted')}
        result[name] = {}
        for stratum,sub in sets.items():
            summaries = [summarize(sub,outputs(sub,i)) for i in range(len(CELLS))]
            rates = np.array([[s[k]['rate'] if s[k]['rate'] is not None else np.nan for k in metrics] for s in summaries])
            cells = [dict(order=c[0],scope=c[1],height=c[2],theta=c[3], metrics={k:s[k] for k in metrics}) for c,s in zip(CELLS,summaries)]
            effects = {}
            # Scope/order effects use valid full-height windows to avoid aliasing the legacy factor.
            for theta in THETAS:
                ids = {(o,s):CELLS.index((o,s,'full',theta)) for o in ('fuzzy_first','cross_first') for s in ('local','whole')}
                a,b,c,d = (rates[ids[k]] for k in [('fuzzy_first','local'),('cross_first','local'),('fuzzy_first','whole'),('cross_first','whole')])
                order_effect = ((b-a)+(d-c))/2
                scope_effect = ((c-a)+(d-b))/2
                interaction = (d-c)-(b-a)
                effects[str(theta)] = {label:dict(zip(metrics,values.tolist())) for label,values in (
                    ('cross_first_minus_fuzzy_first',order_effect),('whole_minus_local',scope_effect),('order_by_scope_difference_in_differences',interaction))}
            theta_effects = {}
            for o,s in itertools.product(('fuzzy_first','cross_first'),('local','whole')):
                theta_effects[o+'/'+s] = {str(t):dict(zip(metrics,(rates[CELLS.index((o,s,'full',t))]-rates[CELLS.index((o,s,'full',.5))]).tolist())) for t in THETAS}
            legacy = []
            for o,s,t in itertools.product(('fuzzy_first','cross_first'),('local','whole'),THETAS):
                full,old = CELLS.index((o,s,'full',t)),CELLS.index((o,s,'legacy',t))
                legacy.append(dict(order=o,scope=s,theta=t,changed_observations=sum(r['grid'][full]!=r['grid'][old] for r in sub)))
            result[name][stratum] = {'n':len(sub),'cells':cells,'effects_by_theta':effects,'threshold_effects_relative_to_050':theta_effects,
                'averaged_main_effects':{label:{k:float(np.mean([e[label][k] for e in effects.values()])) for k in metrics}
                    for label in ('cross_first_minus_fuzzy_first','whole_minus_local','order_by_scope_difference_in_differences')},
                'legacy_partial_factor':legacy,'short_file_inputs':sum(r['short_file'] for r in sub)}
        print('Factorial summary complete:',name,flush=True)
    write('factorial-summary.json',result,[OUT/'gate-trials.json'])
    return result


def select_cell(sub, candidates, constrained=None):
    viable = []
    changed = [r for r in sub if r['cls'] in ('edited','gone')]
    gone = [r for r in sub if r['cls']=='gone']
    for i in candidates:
        if constrained:
            alpha,beta = constrained
            if not changed or not gone:
                continue
            missed = sum(r['grid'][i]//4 in (0,1) for r in changed)/len(changed)
            gone_present = sum(r['grid'][i]%4==1 for r in gone)/len(gone)
            if missed>alpha or gone_present>beta:
                continue
        o,w,h,t = CELLS[i]
        viable.append(((sum(r['grid'][i]%4==0 for r in sub),t,o=='fuzzy_first',h=='full',w=='local'),i))
    if not viable:
        return None,None
    i = max(viable,key=lambda x:x[0])[1]
    return i,summarize(sub,outputs(sub,i))


def calibration(rows):
    deployed = [i for i,c in enumerate(CELLS) if c[:3]==('fuzzy_first','local','full')]
    projects = sorted({r['repo'] for r in rows})
    lo = {}
    for objective in ('all','targeted'):
        lo[objective] = {}
        for repo in projects:
            train = [r for r in rows if r['repo']!=repo and (objective=='all' or r['sample']=='targeted')]
            test = [r for r in rows if r['repo']==repo]
            results = {}
            for design,candidates in [('threshold_only',deployed),('full_cell',range(len(CELLS)))]:
                i,s = select_cell(train,candidates)
                results[design] = {'selected_cell':CELLS[i], 'selected_index':i,'training':s,
                                  'held_out':{sample:summarize(sub,outputs(sub,i)) for sample,sub in strata(test).items() if sample in ('all','uniform','targeted')},
                                  'held_out_default':summarize(test,outputs(test,FINAL)), 'held_out_theta050':summarize(test,outputs(test,CAL))}
            lo[objective][repo] = results
            print('LOPO complete:',objective,repo,flush=True)
    internal = [r for r in rows if r['group']=='own' and r['sample']=='targeted']
    public = [r for r in rows if r['group']=='oss']
    constrained = []
    for design,candidates in [('threshold_only',deployed),('full_cell',range(len(CELLS)))]:
        for alpha,beta in itertools.product((.01,.02,.05),(.05,.1,.2)):
            i,s = select_cell(internal,candidates,(alpha,beta))
            record = {'design':design,'alpha':alpha,'beta':beta,'feasible':i is not None,'selected_cell':None if i is None else CELLS[i],
                      'training':s, 'public_evaluation':None if i is None else {sample:summarize(sub,outputs(sub,i)) for sample,sub in strata(public).items() if sample in ('all','uniform','targeted')}}
            constrained.append(record)
    result = {'lopo':lo,'selected_theta_counts':{objective:{design:dict(Counter(str(p[design]['selected_cell'][3]) for p in projects_.values())) for design in ('threshold_only','full_cell')} for objective,projects_ in lo.items()},
              'safety_constrained':constrained,
              'accuracy_only_existing_theta050':{'internal_all':summarize([r for r in rows if r['group']=='own'],outputs([r for r in rows if r['group']=='own'],CAL)),
                'internal_targeted':summarize(internal,outputs(internal,CAL)),
                'public':{sample:summarize(sub,outputs(sub,CAL)) for sample,sub in strata(public).items() if sample in ('all','uniform','targeted')}},
              'default':{'internal_targeted':summarize(internal,outputs(internal,FINAL)),
                'public':{sample:summarize(sub,outputs(sub,FINAL)) for sample,sub in strata(public).items() if sample in ('all','uniform','targeted')}}}
    write('calibration.json',result,[OUT/'gate-trials.json'])
    return result


def effort(benchmarks,safety_data):
    axes = {'wrong_with_recheck':np.logspace(-1,1,5).tolist(),'wrong_silent':np.logspace(0,2,5).tolist(),
            'missed':np.logspace(0,2,5).tolist(),'false_recheck':np.logspace(-2,0,5).tolist()}
    regions = {}
    for benchmark,strata_data in safety_data.items():
        regions[benchmark] = {}
        for label,stats in strata_data.items():
            if label.startswith(('op-','class-')):
                continue
            methods = [m for m,s in stats.items() if s['execution_errors']==0]
            rows = []
            for weights in itertools.product(*axes.values()):
                costs = {m:(stats[m]['event_counts']['lost']+sum(w*stats[m]['event_counts'][k] for k,w in zip(axes,weights)))/stats[m]['n'] for m in methods}
                best = min(costs.values())
                winners = [m for m,c in costs.items() if abs(c-best)<1e-12]
                rows.append(dict(zip(axes,weights), winners=winners,costs=costs,minimum_cost=best))
            regions[benchmark][label] = {'n':next(iter(stats.values()))['n'],'methods':methods,'regions':rows,
                'win_counts':dict(Counter(m for r in rows for m in r['winners'])),
                'tracker_failure_handling':'excluded from primary effort dominance if any failures; safety JSON retains all-target denominators'}
            # Exact linear-region description, in addition to the finite grid sweep.
            coefficients = {m:{k:stats[m]['event_counts'][k]/stats[m]['n'] for k in ('lost',*axes)} for m in methods}
            regions[benchmark][label]['linear_coefficients'] = coefficients
            regions[benchmark][label]['dominance_regions'] = {
                m:[{'versus':other,'coefficients':{k:coefficients[m][k]-coefficients[other][k] for k in ('lost',*axes)},
                    'relation':'lost_coefficient + sum(other_coefficient * weight) <= 0'} for other in methods if other!=m]
                for m in methods}
            if stats['tracker_adapter']['execution_errors']:
                sensitivities = {}
                for error_cost in (.1,1,10,100):
                    winners = Counter()
                    for r in rows:
                        tracker = stats['tracker_adapter']
                        cost = (tracker['event_counts']['lost']+error_cost*tracker['execution_errors']+
                            sum(r[k]*tracker['event_counts'][k] for k in axes))/tracker['n']
                        best = min(r['minimum_cost'],cost)
                        if abs(cost-best)<1e-12:
                            winners['tracker_adapter'] += 1
                        for m,c in r['costs'].items():
                            if abs(c-best)<1e-12:
                                winners[m] += 1
                    sensitivities[str(error_cost)] = dict(winners)
                regions[benchmark][label]['tracker_inspection_cost_sensitivity'] = sensitivities
    write('effort-dominance.json',{'axes':axes,'lost_weight':1,'regions':regions},[OUT/'safety-metrics.json'])
    path = OUT/'effort-dominance.csv'
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['benchmark','sample',*axes,'winners','minimum_cost'])
        for b,ss in regions.items():
            for s,item in ss.items():
                for r in item['regions']:
                    writer.writerow([b,s,*[r[k] for k in axes],';'.join(r['winners']),r['minimum_cost']])
    return {'axes':axes,'regions':regions}


def characterisation(rows):
    gate = read(OUT/'exclusion-gate.json')['data']
    assert gate['passed']
    attempts = read(OUT/'attempted-observations.json')['data']
    lookup = {(r['pair'],r['sample'],tuple(r['anchor_at'])):r for r in attempts if r['status']=='retained'}
    assert len(lookup)==len(rows)
    augmented = [dict(r,**{k:lookup[(r['pair'],r['sample'],tuple(r['anchor_at']))][k] for k in ('diff_bin','diff_size','hunks','max_hunk_size')}) for r in rows]
    distribution = {}
    for status in ('retained','excluded'):
        sub = [r for r in attempts if r['status']==status]
        distribution[status] = {'n':len(sub),'project':dict(Counter(r['repo'] for r in sub)),
            'horizon':dict(Counter(r['horizon'] for r in sub)), 'reason':dict(Counter(str(r['reason']) for r in sub)),
            'span':dict(Counter(r['span'] for r in sub)), 'diff_bin':dict(Counter(r['diff_bin'] for r in sub)),
            'continuous':{k:{'mean':float(np.mean([r[k] for r in sub])), 'quantiles':np.quantile([r[k] for r in sub],[0,.25,.5,.75,1]).tolist()} for k in ('diff_size','hunks','max_hunk_size','overlapping_hunk_size','span')}}
    project_horizon = []
    for repo in sorted({r['repo'] for r in attempts}):
        for horizon in (1,10):
            sub = [r for r in attempts if r['repo']==repo and r['horizon']==horizon]
            kept = [r for r in sub if r['status']=='retained']
            ex = [r for r in sub if r['status']=='excluded']
            project_horizon.append({'repo':repo,'horizon':horizon,'attempted_observations':len(sub),
                'attempted_pairs':len({r['pair'] for r in sub}),'retained_pairs':len({r['pair'] for r in kept}),
                'excluded_pairs':len({r['pair'] for r in ex}),'retained':len(kept),'excluded':len(ex),
                'exclusion_reasons':dict(Counter(r['reason'] for r in ex))})
    by = {}
    for key in ('horizon','diff_bin'):
        by[key] = {}
        for value in sorted({r[key] for r in augmented},key=str):
            sub = [r for r in augmented if r[key]==value]
            by[key][str(value)] = {'n':len(sub),'pairs':len({r['pair'] for r in sub}),
                'methods':{m:summarize_method(sub,m) for m in ANALYSIS_METHODS},
                'targeted_methods':{m:summarize_method([r for r in sub if r['sample']=='targeted'],m) for m in ANALYSIS_METHODS}}
    result = {'distribution':distribution,'project_horizon':project_horizon,'performance':by,
              'cross_tab':{key:[{'project':p,'horizon':h,'status':st,'value':v,'n':n} for (p,h,st,v),n in Counter((r['repo'],r['horizon'],r['status'],str(r[key])) for r in attempts).items()] for key in ('reason','diff_bin','span')},
              'pair_counts_note':'Pairs count sampled observations at each horizon. The same project/pair can have retained and excluded targets; pair columns are not additive.'}
    write('exclusion-horizon.json',result,[OUT/'attempted-observations.json',OUT/'gate-trials.json',OUT/'exclusion-gate.json'])
    return result


def numerical(benchmarks):
    partitions = []
    for benchmark,rows in benchmarks.items():
        for label,sub in strata(rows).items():
            for method in ANALYSIS_METHODS:
                counts = Counter(outcome(r['truth_at'],o['placement'],o['label']=='execution_error') for r,o in zip(sub,outputs(sub,CAL if method=='calibrated' else method)))
                rounded = {k:round(100*counts[k]/len(sub),1) for k in ('correct','wrong_place','lost','execution_error')}
                partitions.append(dict(benchmark=benchmark,stratum=label,method=method,n=len(sub),counts=dict(counts),rounded=rounded,total=round(sum(rounded.values()),1)))
    quoted = {'.5':(76.6,61.8),'.7':(70.9,81.9),'.85':(53.6,92.4),'.95':(26.5,94.4)}
    checks = []
    rows = benchmarks['real']
    for threshold,expected in quoted.items():
        i = CELLS.index(('fuzzy_first','local','full',float(threshold)))
        vals = {}
        for cls in ('edited','gone'):
            sub = [r for r in rows if r['cls']==cls]
            k = sum(events(r,decode_output(r['grid'][i],r))['accuracy'] for r in sub)
            vals[cls] = dict(rate(k,len(sub)),rounded_percent=round(100*k/len(sub),1))
        assert tuple(vals[k]['rounded_percent'] for k in ('edited','gone'))==expected
        checks.append(dict(theta=float(threshold),classes=vals,reviewer_values_verified=True))
    result = {'outcome_partitions':partitions,'non_100_partitions':[r for r in partitions if r['total']!=100],
              'v10_table_III':[r for r in partitions if r['benchmark']=='main' and r['stratum']=='all' and r['method'] in METHODS],
              'threshold_reviewer_checks':checks,
              'rounding_note':'Percentages are independently rounded to one decimal from raw integer counts; mutually exclusive categories may sum to 99.9% or 100.1%. Counts define the exact partition. Accuracy columns for different methods or overlapping subsets are not partitions.'}
    write('numerical-audit.json',result,[OUT/'gate-trials.json',ROOT/'v10-citation-methods/main.tex'])
    return result


def main():
    gate = read(OUT/'reproduction-gate.json')['data']
    assert gate['passed'], 'STOP: matcher gate did not pass'
    rows = read(OUT/'gate-trials.json')['data']
    benchmarks = {name:[r for r in rows if r['benchmark']==name] for name in ('main','replication','real')}
    tasks = sys.argv[1:] or ['safety','errors','uncertainty','factorial','calibration','effort','characterisation','numerical']
    for task in tasks:
        print('Analyzing:',task,flush=True)
        if task=='safety': safety(benchmarks)
        elif task=='errors': errors(benchmarks)
        elif task=='uncertainty': uncertainty(benchmarks)
        elif task=='factorial': factorial(benchmarks)
        elif task=='calibration': calibration(benchmarks['real'])
        elif task=='effort': effort(benchmarks,read(OUT/'safety-metrics.json')['data'])
        elif task=='characterisation': characterisation(benchmarks['real'])
        elif task=='numerical': numerical(benchmarks)
        else: raise ValueError(task)


if __name__=='__main__':
    main()
