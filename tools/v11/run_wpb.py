"""Isolated, staged B1 execution. No application imports, checkout, or network."""
import argparse
import ast
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import itertools
import json
from pathlib import Path
import random
import sys
import traceback

from wpa_core import ROOT, CORPUS, SOURCE, loaders, sha, read, outcome, features, cell_output
from wpb_variants import all_outputs, relocate
from wpb_stress import b1a, duplicates, short, corpus, digest, scope_dump
from history_context import History, PRIVATE, load_rows
from regenerate_history_selection import harness
from run_wpa_gate import controlled_payloads, real_payloads
from tracker_process import TrackerProcess

OUT = ROOT/'evidence/v11-wpb1'
CODE = ['wpb_variants.py','wpb_stress.py','run_wpb.py','test_variants.py','wpa_core.py',
        'run_wpa_gate.py','analyze_wpb.py']
HELPERS = ['history_context.py','regenerate_history_selection.py','tracker_process.py','range_metrics.py']
INPUTS = [SOURCE/n for n in ('bench_relocation.py','real_history.py','analysis_v3.py','results-v3.json',
                           'results-real-v1.json','results-oss-v1.json')]
INPUTS += [CORPUS/'vcap/app/modules/review_studio/carry.py',ROOT/'tools/bin/lhdiff-driver.exe',
           ROOT/'evidence/v11-wpa/gate-trials.json',ROOT/'evidence/v11-wpa/reproduction-gate.json',
           ROOT/'evidence/v11-wpa/history-inputs.json',ROOT/'evidence/v11-wpa/missed-recheck-cases.csv',
           ROOT/'evidence/source-context-validation/source-rows.json',ROOT/'evidence/range-evaluation/trials.json',
           ROOT/'evidence/real-tracker-comparison/trials.json']


def now():return datetime.now(timezone.utc).isoformat()


def code_hashes():
    paths=[Path(__file__).with_name(n) for n in CODE]+[ROOT/'tools'/n for n in HELPERS]
    return {str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in paths}


def provenance():
    return dict(recorded_utc=now(),python=sys.version,executable=sys.executable,
                input_manifest_sha256=sha(OUT/'input-manifest.json') if (OUT/'input-manifest.json').exists() else None,
                code_sha256=code_hashes(), protocol_sha256=sha(ROOT/'review/V11-PROTOCOL-B.md') if (ROOT/'review/V11-PROTOCOL-B.md').exists() else None,
                freeze_record_sha256=sha(OUT/'protocol-freeze.json') if (OUT/'protocol-freeze.json').exists() else None)


def write(path,data):
    path=OUT/path
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:
        json.dump(dict(provenance=provenance(),data=data),stream,separators=(',',':'))


def verify_freeze():
    f=read(OUT/'protocol-freeze.json')['data']
    assert f['protocol_sha256']==sha(ROOT/'review/V11-PROTOCOL-B.md'),'protocol drift'
    assert f['code_sha256']==code_hashes(),'frozen code drift'
    return f


def initialize():
    global M,B,T,TRACK_CACHE
    M,B=loaders()
    T=TrackerProcess(ROOT/'tools/bin/lhdiff-driver.exe')
    TRACK_CACHE={}


def tracker(t,rename=None):
    a=t['anchor']
    path=rename or a['path']
    old='\n'.join(t['old_lines'])+'\n'
    new=t['version'].get(path,('',''))[1]
    key=(digest(old),digest(new))
    if key not in TRACK_CACHE:
        TRACK_CACHE[key]=T.map(old,new) if new else ({},None)
        if len(TRACK_CACHE)>256:
            TRACK_CACHE.pop(next(iter(TRACK_CACHE)))
    mapping,error=TRACK_CACHE[key]
    if error:return dict(label='execution_error',placement=None,range=None,recheck=True,reasons=[],error=error)
    start=mapping.get(a['line_start'],0)
    if not start:return dict(label='removed',placement=None,range=None,recheck=True,reasons=[])
    want=[x.strip() for x in a['quotation'].splitlines() if x.strip()]
    here=[x.strip() for x in new.splitlines()[start-1:start-1+a['line_end']-a['line_start']+1] if x.strip()]
    label=('exact' if [path,start]==[a['path'],a['line_start']] else 'moved') if here==want else 'changed'
    return dict(label=label,placement=[path,start],range=None,recheck=label=='changed',reasons=[])


def basic(t,name):
    M.FUZZY_CODE=.85
    p,flagged=B.METHODS[name](t)
    at=None if p is None else [p[0],p[1]+1]
    label='removed' if at is None else 'moved' if flagged else 'exact'
    if name=='cascade_v1':
        f=features(t,M)
        o=cell_output(f,'cross_first','whole','legacy',.75,[t['anchor']['path'],t['anchor']['line_start']])
        assert at==o['placement']
        label=o['label']
    return dict(label=label,placement=at,range=None,recheck=label in ('changed','removed') if name=='cascade_v1' else at is None,
                adapter_recheck=flagged,reasons=[])


def metadata(meta,t):
    a=t['anchor']
    truth=None if t['truth'] is None else [t['truth'][0],t['truth'][1]+1]
    cls='gone' if truth is None else 'edited' if t['changed'] else 'moved file' if truth[0]!=a['path'] else 'in place' if truth[1]==a['line_start'] else 'shifted'
    result=dict(meta,cls=cls,truth_at=truth,anchor_at=[a['path'],a['line_start']],span=a['line_end']-a['line_start']+1,
                source_file=a['path'],old_file_sha256=a['content_hash'],new_file_map_sha256=digest(json.dumps({p:v[0] for p,v in t['version'].items()},sort_keys=True)))
    if 'duplicate_construction' in t:result['duplicate_construction']=t['duplicate_construction']
    if meta['suite']=='short':result['quotation']=a['quotation']
    result['reference_range']=None if truth is None or t.get('truth_end') is None else truth+[t['truth_end']]
    return result


def audit_reindent(t):
    old='\n'.join(t['old_lines'])+'\n'
    new=t['version'][t['anchor']['path']][1]
    result={}
    for k,text in [('old',old),('new',new)]:
        try:ast.parse(text);result[k+'_parseable']=True
        except (SyntaxError,ValueError) as e:result[k+'_parseable']=False;result[k+'_error']=type(e).__name__
    if result['old_parseable'] and result['new_parseable']:
        result['module_AST_changed']=ast.dump(ast.parse(old))!=ast.dump(ast.parse(new))
        a=t['anchor']
        result['enclosing_AST_changed']=scope_dump(old,a['line_start'],a['line_end'])!=scope_dump(new,a['line_start'],a['line_end'])
    return result


def evaluate_batch(payload):
    items,include_baselines=payload
    outputs=[]
    for meta,t,old_files in items:
        record=metadata(meta,t)
        record['methods']=all_outputs(t,old_files)
        if include_baselines:
            for name in ('cascade_v1','quote_exact','diff_drift','line_number'):
                base=t if not meta.get('renamed_path') or name=='cascade_v1' else dict(t,anchor=dict(t['anchor'],path=meta['renamed_path']))
                record['methods'][name]=basic(base,name)
            record['methods']['tracker_adapter']=tracker(t,meta.get('renamed_path'))
        if meta.get('op')=='reindent' and meta['suite']=='original':record['original_reindent_audit']=audit_reindent(t)
        if meta['suite']=='real':
            base=record['methods']['t0.85-deployed']
            if base['range'] is not None:
                p,s,e=base['range']
                before=[x.strip() for x in t['anchor']['quotation'].splitlines() if x.strip()]
                text='\n'.join(t['version'][p][1].splitlines()[s-1:e])
                after=[x.strip() for x in text.splitlines() if x.strip()]
                from wpb_variants import profile
                if before==after and profile(t['anchor']['quotation'])!=profile(text):
                    record['indentation_match']=dict(old_profile=profile(t['anchor']['quotation']),new_profile=profile(text),
                        label=base['label'],tier=base['tier'],oracle_class=meta['cls'],oracle_how=meta['how'],
                        quotation=t['anchor']['quotation'],located_quotation=text,oracle_AST_equal=meta['oracle_AST_equal'])
        outputs.append(record)
    return outputs


def gate_batch(payload):
    version,items=payload
    counts=Counter()
    for meta,t,archived,tracker_saved,rename in items:
        if version is not None:t['version']=version
        old='\n'.join(t['old_lines'])+'\n'
        M.FUZZY_CODE=.85
        native=M.relocate_code(t['anchor'],t['version'],old)
        parameterized=relocate(t,{t['anchor']['path']:old})
        want_range=None if native['match']=='removed' else [native['path'],native['line_start'],native['line_end']]
        assert parameterized['label']==native['match'] and parameterized['range']==want_range,(meta,'native-range')
        assert native['match']==archived['label'],(meta,'native-label')
        for name in ('cascade','cascade_v1','quote_exact','diff_drift','line_number'):
            base=t if rename is None or name in ('cascade','cascade_v1') else dict(t,anchor=dict(t['anchor'],path=rename))
            p,flag=B.METHODS[name](base)
            oc,silent=B.score(t,p,flag)
            assert oc==archived[name]['outcome'] and silent==archived[name]['silent'],(meta,name,oc,silent)
            if 'flagged' in archived[name]:assert flag==archived[name]['flagged'],(meta,name,'flag')
        tracked=tracker(t,rename)
        assert outcome(meta['truth_at'],tracked['placement'],tracked['label']=='execution_error')==tracker_saved['tracker'],(meta,'tracker')
        counts[meta['benchmark']]+=1
        counts['tracker_execution_errors']+=tracked['label']=='execution_error'
    return dict(counts)


def originals(seed):
    bench,files,old_files=corpus()
    rng=random.Random(seed)
    label='main' if seed==20261018 else 'replication'
    for op in bench.OPS:
        made=0
        while made<300:
            t=bench.make_trial(rng,files,sorted(files),op)
            if t is None:continue
            t['truth_end']=None if t['truth'] is None else t['truth'][1]+t['anchor']['line_end']-t['anchor']['line_start']+1
            yield dict(suite='original',seed=seed,benchmark=label,op=op,index=made),t,old_files
            made+=1


def histories(groups):
    original,_=harness()
    rows=load_rows()
    contexts=read(ROOT/'evidence/source-context-validation/source-rows.json')
    pins=read(ROOT/'evidence/v11-wpa/history-inputs.json')['data']
    specifications=dict(PRIVATE)
    if 'oss' in groups:
        for entry in read(ROOT/'evidence/public-histories/manifest.json'):
            specifications[entry['name']]=(ROOT/'evidence/public-histories'/entry['name'],entry['head'],entry['expected_count'])
    for name,spec in specifications.items():
        if not any(r['repo']==name and r['group'] in groups for r in rows):continue
        history=History(name,*spec)
        repo=original.Repo(str(history.path))
        pair=None
        try:
            for index,row in enumerate(rows):
                if row['repo']!=name or row['group'] not in groups:continue
                old,new=history.pair(row)
                assert pins[name]['pairs'][row['pair']]['old']==old and pins[name]['pairs'][row['pair']]['new']==new
                if row['pair']!=pair:
                    pair=row['pair']
                    old_files={p:repo.blob(s) for p,s in repo.tree(old).items()}
                    version={p:(digest(repo.blob(s)),repo.blob(s)) for p,s in repo.tree(new).items()}
                    renames=history.renames(old,new)
                path,start=row['anchor_at']
                text=old_files[path]
                assert digest(text)==contexts[index]['old_file_sha256']
                assert '\n'.join(text.splitlines()[start-1:start-1+row['span']])==row['quotation']
                truth=row['truth_at']
                t=dict(anchor=dict(path=path,line_start=start,line_end=start+row['span']-1,quotation=row['quotation'],content_hash=digest(text)),
                       old_lines=text.splitlines(),version=version,truth=None if truth is None else (truth[0],truth[1]-1),
                       changed=row['cls'] in ('edited','gone'),truth_end=None if truth is None or 'new_span' not in contexts[index] else truth[1]+contexts[index]['new_span']-1)
                meta={k:row[k] for k in ('repo','group','sample','pair','horizon','cls','how')}
                meta.update(suite='real',row=index,oracle_AST_equal=contexts[index].get('ast_equal'),
                            old_commit=old,new_commit=new,renamed_path=renames.get(path))
                yield meta,t,old_files
        finally:
            repo.cat.stdin.close();repo.cat.wait(timeout=15)
            history.close()


def batches(generator,size=20):
    batch=[]
    for item in generator:
        batch.append(item)
        if len(batch)==size:yield batch;batch=[]
    if batch:yield batch


def execute(stage,generator,workers=6):
    audits,records,n=[],[],0
    chunk=0
    directory=OUT/stage
    directory.mkdir(exist_ok=False)
    pending=[]
    with ProcessPoolExecutor(max_workers=workers,initializer=initialize) as pool:
        def consume():
            nonlocal n,chunk,records
            got=pending.pop(0).result()
            records.extend(got);n+=len(got)
            if len(records)>=200:
                write(f'{stage}/trials-{chunk:04d}.json',records)
                records=[];chunk+=1
            if n%500<len(got):print(stage,n,got[-1]['suite'],got[-1].get('op',got[-1].get('repo')),flush=True)
        batch=[]
        for meta,t,old_files in generator:
            if meta.get('generator_audit'):
                audits.append(meta)
                print(stage,'generator',meta['suite'],meta['op'],meta['counts'],flush=True)
                continue
            batch.append((meta,t,old_files))
            if len(batch)==20:
                pending.append(pool.submit(evaluate_batch,(batch,True)))
                batch=[]
                if len(pending)>=workers*2:consume()
        if batch:pending.append(pool.submit(evaluate_batch,(batch,True)))
        while pending:consume()
    if records:write(f'{stage}/trials-{chunk:04d}.json',records);chunk+=1
    result=dict(n=n,chunks=chunk,generator_audits=audits,completed_utc=now(),
                complete=all(a['complete'] for a in audits))
    write(f'{stage}/completion.json',result)
    return result


def manifest():
    _,_,files=corpus()
    write('input-manifest.json',dict(inputs={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in INPUTS},
          controlled_corpus={p:digest(t) for p,t in files.items()},code_sha256=code_hashes()))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('stage',choices=('manifest','dev-pilot','development','development-correction','gate','evaluation','freeze'))
    p.add_argument('--workers',type=int,default=6)
    args=p.parse_args()
    OUT.mkdir(exist_ok=True)
    try:
        if args.stage=='manifest':manifest();return
        if args.stage=='freeze':
            assert (OUT/'development/completion.json').exists()
            assert read(OUT/'development/completion.json')['data']['complete']
            assert read(OUT/'development-correction/completion.json')['data']['complete']
            write('protocol-freeze.json',dict(timestamp_utc=now(),protocol_sha256=sha(ROOT/'review/V11-PROTOCOL-B.md'),
                  code_sha256=code_hashes(),development_completion_sha256=sha(OUT/'development/completion.json'),
                  correction_completion_sha256=sha(OUT/'development-correction/completion.json'),
                  statement='No seed-2 stress inputs generated and no public observation evaluated with variants before this record. All histories remain retrospective.'))
            return
        if args.stage=='gate':
            verify_freeze()
            write('gate-start.json',dict(started_utc=now()))
            m,b=loaders();pins={}
            counts=Counter()
            with ProcessPoolExecutor(max_workers=args.workers,initializer=initialize) as pool:
                pending=[]
                def consume():
                    counts.update(pending.pop(0).result())
                    print('gate',dict(counts),flush=True)
                for payload in itertools.chain(controlled_payloads(b),real_payloads(pins)):
                    pending.append(pool.submit(gate_batch,payload))
                    if len(pending)>=args.workers*2:consume()
                while pending:consume()
            assert {k:counts[k] for k in ('main','replication','real')}==dict(main=3600,replication=3600,real=15064)
            assert counts['tracker_execution_errors']==143
            write('reproduction-gate.json',dict(passed=True,counts=dict(counts),completed_utc=now(),
                  checks='Per-observation original method outcomes/silent flags and controlled flags; default native label and full range versus zero-switch matcher; unchanged external tracker outcomes, including all execution failures.'))
            return
        if args.stage in ('development','dev-pilot','development-correction'):
            assert not (OUT/'protocol-freeze.json').exists(),'development after freeze forbidden'
            n=10 if args.stage=='dev-pilot' else 300
            g=itertools.chain(b1a(20261018,n),duplicates(20261018,max(1,n//2)),short(20261018,max(1,n//2)))
            if args.stage=='development':g=itertools.chain(g,originals(20261018),histories(('own',)))
            if args.stage=='development-correction':g=duplicates(20261018)
        else:
            verify_freeze()
            assert read(OUT/'reproduction-gate.json')['data']['passed']
            write('evaluation-start.json',dict(started_utc=now(),one_shot=True))
            g=itertools.chain(b1a(20261027),duplicates(20261027),short(20261027),originals(20261027),histories(('own','oss')))
        result=execute(args.stage,g,args.workers)
        print(json.dumps(result),flush=True)
    except BaseException as error:
        failure=f'{args.stage}-failure-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")}.json'
        write(failure,dict(error=repr(error),traceback=traceback.format_exc(),failed_utc=now()))
        raise


if __name__=='__main__':main()
