"""WP K1 descriptive re-aggregation; run from paper-drafts with pinned Python."""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib, json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/v11'))
import analyze_wpi as AI
import wpb2_chains as WC
from wpi_core import identity_hop, OUT as WPI_OUT

OUT = ROOT / 'evidence/v12-wpk1'
PROTOCOL = ROOT / 'review/V12-PROTOCOL-K1.md'
FREEZE = OUT / 'protocol-freeze.json'
WPJ_SUM = ROOT / 'evidence/v11-wpj/summary-20261104T092825.json'
WEIGHTS = (1, 3, 10, 30)
MISDIR_WEIGHTS = (1, 3)
_EVENTS = {}
_DENOMS = {}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(path, data):
    with Path(path).open('x', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

def rate(k,n): return AI.rate(int(k),int(n))
def metric(rows, method):
    from collections import Counter
    c, d = Counter(), Counter()
    for r in rows:
        key=(id(r),method)
        if key not in _EVENTS:
            _EVENTS[key]=AI.ev(r,r['methods'][method])
            _DENOMS[id(r)]=AI.denominators(r)
        c.update(_EVENTS[key]); d.update(_DENOMS[id(r)])
    denoms=AI.DENOMS
    measures=('accuracy','placement_accuracy','missed','false_recheck','wrong','wrong_silent','wrong_with_recheck','lost','gone_correct','range_correct')
    return dict(n=len(rows),execution_errors=c['failure'],counts=dict(c),denominators=dict(d),
                **{m:rate(c[m],d[denoms.get(m,'n')]) for m in measures})
def cost(rows, method, w, m):
    met=metric(rows,method); c=met['counts']; n=met['n']
    return (w*(c.get('missed',0)+c.get('wrong_silent',0))+m*c.get('wrong_with_recheck',0)+c.get('false_recheck',0)+c.get('lost',0))/n if n else None

def outcomes(rows, method):
    x=metric(rows,method)
    names={'placement':'placement_accuracy','missed':'missed','silent':'wrong_silent','misdirected':'wrong_with_recheck','lost':'lost','unnecessary':'false_recheck','gone_kept':'gone_correct','correct':'accuracy'}
    return {k:x[v] for k,v in names.items()} | {'n':x['n'],'execution_errors':x['execution_errors'],'counts':x['counts'],'denominators':x['denominators']}

def candidate_methods(rows):
    return sorted(set.intersection(*(set(r['methods']) for r in rows))) if rows else []

def frontier(rows, methods):
    vec={}
    for a in methods:
        x=metric(rows,a); c=x['counts']; n=x['n']
        vec[a]=[(c.get('missed',0)+c.get('wrong_silent',0))/n,c.get('wrong_with_recheck',0)/n,c.get('lost',0)/n,c.get('false_recheck',0)/n]
    keep=[]
    for a,v in vec.items():
        if not any(all(x<=y for x,y in zip(vec[b],v)) and any(x<y for x,y in zip(vec[b],v)) for b in vec if b!=a): keep.append(a)
    return {'dimensions':['missed_plus_silent','misdirected','lost','unnecessary'],'vectors':vec,'pareto':sorted(keep)}

def choose(train, methods, w,m):
    scores=[]
    for a in methods:
        c=cost(train,a,w,m)
        if c is None: continue
        x=metric(train,a)
        missed_silent=(x['counts'].get('missed',0)+x['counts'].get('wrong_silent',0))/x['n']
        scores.append((c,missed_silent,x['execution_errors'],a))
    return min(scores)[-1] if scores else None

def lopo(rows, methods, groupkey, fixed):
    groups=defaultdict(list)
    for r in rows: groups[r[groupkey]].append(r)
    # Aggregate once per method and held-out group. This is exactly additive for the
    # registered count-per-target cost and avoids rescanning every target per fold.
    grouped={}
    for method in methods:
        grouped[method]={}
        for g,rs in groups.items():
            x=metric(rs,method)
            grouped[method][g]=(x['counts'],x['n'],x['execution_errors'])
    def gcost(method, selected_groups, w, m):
        vals=[grouped[method][g] for g in selected_groups]
        c=Counter(); n=err=0
        for counts,nn,ee in vals: c.update(counts); n+=nn; err+=ee
        return ((w*(c.get('missed',0)+c.get('wrong_silent',0))+m*c.get('wrong_with_recheck',0)+c.get('false_recheck',0)+c.get('lost',0))/n if n else None, c,n,err)
    folds=[]
    for g in sorted(groups):
        train_groups=[h for h in groups if h!=g]; test=groups[g]
        entry={'held_out':g,'train_n':sum(len(groups[h]) for h in train_groups),'test_n':len(test),'weights':{}}
        for w in WEIGHTS:
            for m in MISDIR_WEIGHTS:
                scores=[]
                for a in methods:
                    c,counts,n,err=gcost(a,train_groups,w,m)
                    scores.append((c,(counts.get('missed',0)+counts.get('wrong_silent',0))/n if n else 1,err,a))
                sel=min(scores)[-1] if scores else None
                if sel is None: continue
                sc=cost(test,sel,w,m); oracle=min((cost(test,a,w,m),a) for a in methods)
                comp={a:cost(test,a,w,m) for a in fixed if a in methods}
                entry['weights'][f'w{w}_m{m}']={'selected':sel,'held_cost':sc,'outcomes':outcomes(test,sel),'oracle_policy':oracle[1],'oracle_cost':oracle[0], 'regret_oracle':sc-oracle[0], 'fixed_costs':comp, 'regret_fixed':{a:sc-v for a,v in comp.items()}}
        folds.append(entry)
    stability={}
    for key in [f'w{w}_m{m}' for w in WEIGHTS for m in MISDIR_WEIGHTS]:
        selected=[f['weights'][key]['selected'] for f in folds]
        cnt=Counter(selected); mode,n=cnt.most_common(1)[0] if cnt else (None,0)
        stability[key]={'mode':mode,'mode_share':n/len(selected) if selected else None,'selected_counts':dict(cnt)}
    oos={}
    for key in [f'w{w}_m{m}' for w in WEIGHTS for m in MISDIR_WEIGHTS]:
        vals=[f['weights'][key] for f in folds]
        oos[key]={'selected_mean_cost':float(np.mean([x['held_cost'] for x in vals])) if vals else None,
                  'oracle_mean_cost':float(np.mean([x['oracle_cost'] for x in vals])) if vals else None,
                  'beats_fixed_count':{a:sum(x['regret_fixed'].get(a,0)<0 for x in vals) for a in fixed},
                  'fixed_mean_cost':{a:float(np.mean([x['fixed_costs'][a] for x in vals if a in x['fixed_costs']])) if any(a in x['fixed_costs'] for x in vals) else None for a in fixed}}
    return {'folds':folds,'stability':stability,'out_of_sample':oos}

def load_all():
    inputs=[]; pops={}
    for stage,pattern,origin in [('transfer','rows-*.json','transfer'),('compound','rows.json','compound'),('students2','rows.json','students'),('fresh','rows-*.json','fresh')]:
        rows,paths=AI.load(stage,pattern); inputs.extend(paths)
        print('loaded',stage,len(rows),flush=True)
        agi={r['id']:r['methods'] for p in sorted((WPI_OUT/'agi').glob(stage+'-*.json')) for r in AI.read(p)['data']}; inputs += sorted((WPI_OUT/'agi').glob(stage+'-*.json'))
        assert len(agi)==len(rows),(stage,len(agi),len(rows))
        for r in rows:
            r['methods'].update(agi[r['id']])
            if origin in ('students','compound','fresh'): r['methods']['deployed_native']=r['methods']['t0.85-deployed']
            AI.add_cmhybrid(r)
            r['_origin']=origin
        pops[origin]=rows
    # WP J populations: combine saved layer rows with their exact WP I targets.
    base={}
    tr=pops['transfer']; st=pops['students']
    for r in tr:
        if r['suite']=='external' and r['dataset'] in ('annotation_a','annotation_b'): base[r['id']]=('human-AB',r)
        elif r['suite']=='real' and r['group']=='oss' and r['sample']=='targeted': base[r['id']]=('real-oss-targeted',r)
    for r in st:
        if r['sample']=='targeted': base[r['id']]=('students-targeted',r)
    jsummary=read(WPJ_SUM)['data']
    for model_key,folder in [('beam','beam'),('nemotron','nemotron')]:
        jm={}
        for pop in ('human-AB','real-oss-targeted','students-targeted'):
            p=ROOT/f'evidence/v11-wpj/{folder}/layers/{pop}-pass1.json'
            if not p.exists(): continue
            inputs.append(p)
            recs=read(p)['data']
            for rr in recs: jm.setdefault(pop,[]).append(rr)
        for pop,recs in jm.items():
            rs=[]
            for item in recs:
                target=base[item['id']][1].copy(); target['methods']=dict(target['methods']); target['methods'].update(item['methods']); target['_origin']='external' if pop=='human-AB' else ('transfer' if pop=='real-oss-targeted' else 'students')
                target['methods']['llm-self']=item['methods'].get('llm-self')
                target['methods']['llm+quote']=item['methods'].get('llm+quote')
                target['methods']['llm+IG+AGi']=item['methods'].get('llm+IG+AGi')
                target['methods']['llm+AGi']=item['methods'].get('llm+AGi')
                # Base configuration names requested in the brief.
                model='llm' if model_key=='beam' else 'nemotron'
                for suffix,src in [('verdict','llm-self'),('quote','llm+quote'),('IG+AGi','llm+IG+AGi')]:
                    if src in item['methods']: target['methods'][f'{model}+{suffix}']=item['methods'][src]
                rs.append(target)
            pops[f'wpj:{model_key}:{pop}']=rs
    inputs.append(WPJ_SUM)
    return pops,inputs

def main():
    freeze=read(FREEZE)
    assert sha(PROTOCOL)==freeze['protocol_sha256']
    pops,inputs=load_all()
    # Requested populations, with aliases preserving row-level scope.
    aliases={'fresh':pops['fresh'],'fresh:duplicates':[r for r in pops['fresh'] if r['suite']=='duplicates'],'fresh:indentation':[r for r in pops['fresh'] if r['suite']=='indentation'],'fresh:short':[r for r in pops['fresh'] if r['suite']=='short'],'controlled:replication':[r for r in pops['transfer'] if r['suite']=='original'],'real':[r for r in pops['transfer'] if r['suite']=='real'],'students':pops['students'],'external:human-AB':[r for r in pops['transfer'] if r['suite']=='external' and r['dataset'] in ('annotation_a','annotation_b')],'fresh:compound:k=4':[r for r in pops['fresh'] if r['suite']=='compound' and r['k']==4]}
    # WP J's three populations are retained as separate target-limited cells.
    for model in ('beam','nemotron'):
        for pop in ('human-AB','real-oss-targeted','students-targeted'):
            key=f'wpj:{model}:{pop}'
            if pops.get(key): aliases[key]=pops[key]
    summary={'status':'post hoc descriptive','protocol_sha256':sha(PROTOCOL),'populations':{},'policy':{},'selection':{},'chains':{},'identity_floor':{},'strata':{},'limits':[]}
    for name,rows in aliases.items():
        methods=candidate_methods(rows)
        summary['populations'][name]={'n':len(rows),'methods':{m:outcomes(rows,m) for m in methods}}
        fr=frontier(rows,methods) if rows else {'pareto':[]}; summary['policy'][name]={'frontier':fr,'minimizers':{}}
        for w in WEIGHTS:
            for m in MISDIR_WEIGHTS:
                sel=choose(rows,methods,w,m)
                summary['policy'][name]['minimizers'][f'w{w}_m{m}']={'policy':sel,'cost':cost(rows,sel,w,m),'outcomes':outcomes(rows,sel) if sel else None}
        print('aggregated',name,flush=True)
    # LOPO: complete policy set common to every row, fixing defaults by exact method name.
    fixed=('t0.85-deployed','codemapper+IG+AGi')
    for name,rows,key in [('real',aliases['real'],'repo'),('students',aliases['students'],'repo')]:
        methods=candidate_methods(rows)
        summary['selection'][name]=lopo(rows,methods,key,fixed)
    # Cross-population train/evaluate for applicable saved row populations.
    cross={}
    sources=['real','students','external:human-AB','fresh']
    for src in sources:
        train=aliases[src]; cand=candidate_methods(train); cross[src]={}
        for w in WEIGHTS:
            for m in MISDIR_WEIGHTS:
                sel=choose(train,cand,w,m); cross[src][f'w{w}_m{m}']={'selected':sel,'destinations':{}}
                for dst,rr in aliases.items():
                    if dst not in sources: continue
                    if sel not in candidate_methods(rr): cross[src][f'w{w}_m{m}']['destinations'][dst]={'status':'unavailable'}
                    else: cross[src][f'w{w}_m{m}']['destinations'][dst]={'cost':cost(rr,sel,w,m),'outcomes':outcomes(rr,sel)}
    summary['selection']['cross_population']=cross
    # Chain outcomes and identity-floor trace replay.
    chain_summary=read(WPI_OUT/'summary-20261102T183407.json')
    chain_data=chain_summary['data']; inputs.append(WPI_OUT/'summary-20261102T183407.json')
    summary['chains']={'wp_i':chain_data['chains'],'wp_i_agi':chain_data['chains_agi']}
    summary['paired_cluster_bootstrap']={k:chain_data['paired'].get(k) for k in ('real','students','external:human-AB','fresh','controlled:replication')}
    summary['paired_cluster_bootstrap_note']='Saved WP I paired cluster-bootstrap contrasts use seed 20261031 and 10000 resamples. K1 policy-selected comparisons remain descriptive.'
    chains=json.loads((WPI_OUT/'chains/rows.json').read_text(encoding='utf-8'))['data']; inputs.append(WPI_OUT/'chains/rows.json')
    chains_agi=json.loads((WPI_OUT/'chains-agi/rows.json').read_text(encoding='utf-8'))['data']; inputs.append(WPI_OUT/'chains-agi/rows.json')
    summary['chains']['wp_i_agi']['gate_mismatches']=read(WPI_OUT/'chains-agi/gate.json')['data']['mismatches']
    # A transparent score replay over stored per-hop ratios; endpoint reference/decision semantics mirror WC.score.
    bases=[('v0.85-off','v0.85-off-id','v0.85-off-id0.3'),('v0.85-all','v0.85-all-id','v0.85-all-id0.3'),('v0.85-all2','v0.85-all2-id','v0.85-all2-id0.3'),('v0.55-all2','v0.55-all2-id','v0.55-all2-id0.3'),('v0.85-alli','v0.85-alli-id','v0.85-alli-id0.3'),('v0.55-alli','v0.55-alli-id','v0.55-alli-id0.3')]
    floor_result={}
    for rows,source in [(chains,'chains'),(chains_agi,'chains-agi')]:
      for base,idbase,id03 in bases:
        if base not in rows[0]: continue
        if id03 in rows[0]:
          sweep=[(round(x,2),idbase) for x in np.arange(.55,1.001,.05)]
          sweep += [(round(x,2),id03) for x in np.arange(.3,.501,.05)]
        else: sweep=[(round(x,2),idbase) for x in np.arange(.5,1.001,.05)]
        per_floor={}; gate={'0.7_from_0.5':{'mismatches':0,'examples':[]},'0.5_from_0.3':{'mismatches':0,'examples':[]}}
        ratio_groups={'true_target':[],'wrong_window':[]}; low_ids=[]; high_ids=[]; low_ratios=[]; high_ratios=[]
        for r in rows:
          if r.get(idbase):
            for h,hop in enumerate(r[idbase]):
              if hop.get('label')=='changed' and hop.get('ratio') is not None and str(h+1) in r['prefixes'] and r['prefixes'][str(h+1)]['reference']['status']=='ok':
                ref=r['prefixes'][str(h+1)]['reference']; at=hop.get('interval')
                key='true_target' if at and ref.get('truth_at') and at[:2]==ref['truth_at'] else 'wrong_window'
                ratio_groups[key].append(hop['ratio'])
          for f,srcname in sweep:
            trace=r.get(srcname)
            if not trace: continue
            hops=[]
            for j,hop in enumerate(trace):
              ratio=hop.get('ratio'); drop=hop.get('label')=='changed' and ratio is not None and ratio<f
              out=dict(hop)
              if drop: out.update(label='removed',interval=None,requested_recheck=True)
              else: out['requested_recheck']=bool(hop.get('requested_recheck') or (ratio is not None and ratio<1.0 and hop.get('label')!='removed'))
              hops.append(out)
            if f==.7 and srcname==idbase:
              expected=r.get(base+'-id0.7')
              if expected is not None:
                bad=[j for j,(a,b) in enumerate(zip(hops,expected)) if (a.get('label'),a.get('interval'),a.get('requested_recheck'))!=(b.get('label'),b.get('interval'),b.get('requested_recheck'))]
                if bad: gate['0.7_from_0.5']['mismatches']+=1; gate['0.7_from_0.5']['examples'].append({'row':r['row'],'hops':bad})
            if f==.5 and srcname==id03:
              expected=r.get(idbase)
              if expected is not None:
                bad=[j for j,(a,b) in enumerate(zip(hops,expected)) if (a.get('label'),a.get('interval'),a.get('requested_recheck'))!=(b.get('label'),b.get('interval'),b.get('requested_recheck'))]
                if bad: gate['0.5_from_0.3']['mismatches']+=1; gate['0.5_from_0.3']['examples'].append({'row':r['row'],'hops':bad})
            ref=r['prefixes']['10']['reference']
            if ref['status']!='ok': continue
            at=None if not hops or not hops[-1].get('interval') else hops[-1]['interval'][:2]
            truth=ref['truth_at']; changed=ref['cls'] in ('edited','gone'); wrong=truth is not None and at is not None and at!=truth
            counts=Counter(correct=int((truth is None and at is None) or (truth is not None and at is not None and at==truth)),wrong=int(wrong),lost=int(truth is not None and at is None),missed_last=int(changed and not hops[-1]['requested_recheck']),silent_wrong=int(wrong and not hops[-1]['requested_recheck']),changed=int(changed))
            slot=per_floor.setdefault(str(f),{'counts':Counter(),'n':0,'rows':[]}); slot['counts'].update(counts); slot['n']+=1
            if f==.3 and wrong:
              low_ids.append(r['row']); low_ratios.append(next((z.get('ratio') for z in reversed(hops) if z.get('ratio') is not None),None))
            if f==1.0 and truth is not None and at is None:
              high_ids.append(r['row']); high_ratios.append(next((z.get('ratio') for z in reversed(trace) if z.get('ratio') is not None),None))
        for f,x in per_floor.items(): x['counts']=dict(x['counts']); x['rows']=x['n']
        for g,v in ratio_groups.items(): ratio_groups[g]={'n':len(v),'median':float(np.median(v)) if v else None,'q1':float(np.quantile(v,.25)) if v else None,'q3':float(np.quantile(v,.75)) if v else None}
        floor_result[f'{source}:{base}']={'floors':per_floor,'gate':gate,'changed_hop_ratio_by_reference':ratio_groups,'extremes':{'too_low':'changed hops below the identity bound remain carried, allowing a wrong endpoint','floor_0.3_wrong_n':len(low_ids),'floor_0.3_wrong_row_ids':low_ids[:4],'floor_0.3_wrong_endpoint_ratio_median':float(np.nanmedian([x for x in low_ratios if x is not None])) if any(x is not None for x in low_ratios) else None,'too_high':'changed hops below the floor are dropped even when later history could support the original target','floor_1.0_lost_n':len(high_ids),'floor_1.0_lost_row_ids':high_ids[:4],'floor_1.0_lost_ratio_median':float(np.nanmedian([x for x in high_ratios if x is not None])) if any(x is not None for x in high_ratios) else None}}
      # CodeMapper has no 0.3 trace; replay 0.5 upward from its stored identity trace only.
      for idmethod in ('cm-seq-id','cm-seq-gi-id'):
        if idmethod not in rows[0]: continue
        base_method=idmethod.removesuffix('-id'); per={}
        for r in rows:
          for f in [round(x,2) for x in np.arange(.5,1.001,.05)]:
            src=r[idmethod]; hops=[]
            for hop in src:
              ratio=hop.get('ratio'); drop=hop.get('label')=='changed' and ratio is not None and ratio<f
              z=dict(hop)
              if drop:z.update(label='removed',interval=None,requested_recheck=True)
              else:z['requested_recheck']=bool(hop.get('requested_recheck') or (ratio is not None and ratio<1 and hop.get('label')!='removed'))
              hops.append(z)
            ref=r['prefixes']['10']['reference']
            if ref['status']!='ok':continue
            at=hops[-1].get('interval');at=at[:2] if at else None;truth=ref['truth_at'];wrong=truth is not None and at is not None and at!=truth;changed=ref['cls'] in ('edited','gone')
            c=per.setdefault(str(f),Counter());c.update(correct=int((truth is None and at is None) or (truth is not None and at is not None and at==truth)),wrong=int(wrong),lost=int(truth is not None and at is None),missed_last=int(changed and not hops[-1]['requested_recheck']),silent_wrong=int(wrong and not hops[-1]['requested_recheck']),changed=int(changed))
        floor_result[f'{source}:{idmethod}']={'floors':{k:dict(v) for k,v in per.items()},'scope':'replay from stored 0.5 identity trace only'}
    summary['identity_floor']['replay']=floor_result
    summary['identity_floor']['gate']='Per-base replay gates are recorded alongside each floor sweep.'
    # Basic span strata supported by per-row metadata.
    for pname,rows in [('real',aliases['real']),('students',aliases['students']),('fresh',aliases['fresh'])]:
      bins={'1':lambda r:r.get('span')==1,'2-3':lambda r:2<=r.get('span',0)<=3,'4-9':lambda r:4<=r.get('span',0)<=9,'>=10':lambda r:r.get('span',0)>=10}
      ms=('t0.85-deployed','t0.85-IG+AGi+VW','codemapper+quote','codemapper+IG+AG','codemapper+IG+AGi')
      summary['strata'][pname]={'anchor_span':{b:{'n':len(rs:=[r for r in rows if fn(r)]),'methods':{m:outcomes(rs,m) for m in ms if m in candidate_methods(rs)}} for b,fn in bins.items()}}
    # Confidence/guard cross-tabs use only recorded fields.
    for pname,rows in aliases.items():
      if not rows: continue
      cross=defaultdict(Counter)
      for r in rows:
        o=r['methods'].get('t0.85-IG+AGi+VW',r['methods'].get('t0.85-deployed',{}))
        tier=o.get('tier','unavailable'); guard=bool(o.get('reasons'))
        ev=AI.ev(r,o)
        cross[(tier,guard)]['n'] += 1
        cross[(tier,guard)]['changed'] += int(r['cls'] in ('edited','gone'))
        cross[(tier,guard)]['preserved'] += int(r['cls'] not in ('edited','gone'))
        cross[(tier,guard)]['survivors'] += int(r.get('truth_at') is not None)
        cross[(tier,guard)].update({k:ev[k] for k in ('accuracy','missed','wrong_silent','wrong_with_recheck','false_recheck','lost')})
      summary['strata'].setdefault(pname,{})['cascade_tier_guard_method']='t0.85-IG+AGi+VW when present; otherwise deployed cascade'
      summary['strata'].setdefault(pname,{})['cascade_tier_guard_outcomes']={f'{t}|guard={g}':dict(c) for (t,g),c in cross.items()}
    # Coordinate-based supervisor costs are supported by the saved rows; copy membership is not.
    summary['misdirection_cost']={}
    for pname in ('real','students','external:human-AB','fresh'):
      rows=aliases[pname]; methods=('t0.85-deployed','t0.85-IG+AGi+VW','codemapper+IG+AG','codemapper+IG+AGi')
      summary['misdirection_cost'][pname]={}
      for method in methods:
        if method not in candidate_methods(rows): continue
        report={}
        for kind,event_name in (('misdirected','wrong_with_recheck'),('silent','wrong_silent')):
          vals=[]
          for r in rows:
            o=r['methods'][method]; ev=AI.ev(r,o); at=o.get('placement'); truth=r.get('truth_at')
            if ev[event_name] and at and truth: vals.append({'same_file':at[0]==truth[0],'distance':abs(at[1]-truth[1]),'truth_at_shown':at==truth})
          ds=[x['distance'] for x in vals]
          report[kind]={'n':len(vals),'same_file_n':sum(x['same_file'] for x in vals),'same_file_share':sum(x['same_file'] for x in vals)/len(vals) if vals else None,'distance_median':float(np.median(ds)) if ds else None,'distance_q1':float(np.quantile(ds,.25)) if ds else None,'distance_q3':float(np.quantile(ds,.75)) if ds else None,'truth_at_shown_n':sum(x['truth_at_shown'] for x in vals),'candidate_membership':'requires source text'}
        tri=Counter(); shown=Counter();
        for r in rows:
          o=r['methods'][method]; at=o.get('placement'); truth=r.get('truth_at'); ev=AI.ev(r,o)
          request=bool(o.get('recheck',o.get('label') in ('changed','removed','execution_error')))
          reasons=' '.join(str(z) for z in o.get('reasons',[])).lower()
          if at is None: cls='missing'
          elif request and any(s in reasons for s in ('copy','duplicate','pre-existing')): cls='ambiguous'
          elif at is not None and not request: cls='verified'
          else: cls='other_requested'
          tri[cls]+=1; shown[cls]+=int(bool(at and truth and at==truth))
        report['three_way']={c:{'n':tri[c],'truth_at_shown_location_n':shown[c],'truth_in_candidate_set':'not available; new tree text required','candidate_set_size':'not available; new tree text required'} for c in ('verified','ambiguous','missing','other_requested')}
        summary['misdirection_cost'][pname][method]=report
    summary['limits'] += ['Old-tree copy-count/distance strata and new-version identical-copy candidate-set audits require reconstructed pinned tree text. Saved row coordinates support same-file and line-distance misdirection summaries, but not copy membership or candidate-set size.','Three-way verified/ambiguous/missing truth-in-candidate-set rates require the unavailable candidate sets; only placement, request and no-placement counts are available.','Issue-level multi-anchor grouping keys are not present in the saved WP I row schema; no issue-level rate is reported.','Cascade confidence is available as tier and guard-fire reasons; no saved similarity score was found. CodeMapper records have no confidence field.']
    # Provenance: hash every loaded evidence file, code and protocol.
    input_hashes={str(Path(p).resolve().relative_to(ROOT)).replace('\\','/'):sha(p) for p in sorted(set(Path(x) for x in inputs)) if Path(p).is_file()}
    code_files=[Path(__file__),ROOT/'tools/v11/analyze_wpi.py',ROOT/'tools/v11/wpi_core.py',ROOT/'tools/v11/wpb2_chains.py',ROOT/'tools/v11/wpa_core.py']
    prov={'recorded_utc':datetime.now(timezone.utc).isoformat(),'protocol_sha256':sha(PROTOCOL),'freeze_sha256':sha(FREEZE),'analysis_code_sha256':sha(__file__),'method_code_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in code_files if p.is_file()},'input_sha256':input_hashes,'python':sys.version}
    summary['provenance']=prov
    dest=OUT/f"summary-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"; dump(dest,summary); print(dest)
    print('populations', {k:v['n'] for k,v in summary['populations'].items()})

if __name__=='__main__': main()
