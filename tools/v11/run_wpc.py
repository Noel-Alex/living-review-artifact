"""Staged external evaluations; exclusive outputs and immutable frozen methods."""
import sys,json,itertools,traceback,random,os
from pathlib import Path
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,wait,FIRST_COMPLETED
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_adapters import *
from run_wpb import histories,originals,metadata
from history_context import PRIVATE
from acquire_wpc_datasets import records

def initialize(stage):
    global A,STAGE
    STAGE=stage;verify_freeze();A=Adapters(OUT/stage/'workers'/str(os.getpid()))
    from multiprocessing.util import Finalize
    Finalize(A,A.close,exitpriority=10)
def work(items):
    verify_freeze();result=[]
    for r,t,repo,old,new in items:
        if STAGE.startswith('gumtree'):o=A.gumtree(t)
        else:
            if r['suite']=='original':
                fixture=OUT/STAGE/'fixtures'/r['id']
                old,new=materialize(fixture,{t['anchor']['path']:'\n'.join(t['old_lines'])+'\n'},t['version']);repo=fixture
            o=A.codemapper(t,repo,old,new,r['id'],resolver='native-readonly' if STAGE.endswith('-native') else None)
        result.append(dict(r,output=o))
    return result
def prior_index():
    result={}
    for stage in ('development','evaluation'):
        for p in sorted((ROOT/'evidence/v11-wpb1'/stage).glob('trials-*.json')):
            for r in read(p)['data']:
                if r['suite']=='original':result[(r['seed'],r['op'],r['index'])]=r
                elif r['suite']=='real':result[('real',r['row'])]=r
    return result
def living_inputs(cm=False):
    prior=prior_index()
    for seed in (20261018,20261027):
        for meta,t,old_files in originals(seed):
            r=prior[(seed,meta['op'],meta['index'])]
            r=dict(r,id=f"{seed}-{meta['op']}-{meta['index']}")
            # GumTree receives only same-path old/new text, never reference location.
            path=t['anchor']['path'];short=dict(t,version={path:t['version'][path]} if path in t['version'] else {})
            yield r,t if cm else short,None,None,None
    for meta,t,old_files in histories(('own','oss')):
        r=dict(prior[('real',meta['row'])],id='real-'+str(meta['row']),old_commit=meta['old_commit'],new_commit=meta['new_commit'])
        repo=PRIVATE[meta['repo']][0] if meta['repo'] in PRIVATE else ROOT/'evidence/public-histories'/meta['repo']
        path=t['anchor']['path'];short=dict(t,version={path:t['version'][path]} if path in t['version'] else {})
        yield r,short,str(repo),meta['old_commit'],meta['new_commit']
def execute(stage,source,workers=4):
    verify_freeze();assert read(OUT/'reproduction-gate.json')['data']['passed']
    workers=int(os.environ.get('WPC_WORKERS',8 if stage.endswith('-native') else workers))
    stage_path=OUT/stage;stage_path.mkdir(exist_ok=True)
    assert not (stage_path/'completion.json').exists(),'completed stage is immutable'
    done=set();n=chunk=0;counts=Counter();pending=[]
    for p in sorted(stage_path.glob('trials-*.json')):
        rows=read(p)['data'];done.update(r['id'] for r in rows);n+=len(rows)
        counts.update(r['output']['label'] for r in rows);chunk=max(chunk,int(p.stem.split('-')[1])+1)
    write(stage+('/start.json' if not done else '/resume-'+str(__import__('time').time_ns())+'.json'),dict(utc=now(),preserved_rows=n,workers=workers,reason='resume incomplete stage; earlier process no longer exists' if done else None))
    with ProcessPoolExecutor(max_workers=workers,initializer=initialize,initargs=(stage,)) as pool:
        def consume():
            nonlocal n,chunk
            got=pending.pop(0).result();write(f'{stage}/trials-{chunk:05d}.json',got);chunk+=1;n+=len(got)
            counts.update(r['output']['label'] for r in got)
            if n%200<len(got):print(stage,n,dict(counts),flush=True)
        batch=[]
        for item in source:
            if item[0]['id'] in done:continue
            batch.append(item)
            if len(batch)>=20:
                pending.append(pool.submit(work,batch));batch=[]
                if len(pending)>=workers*2:consume()
        if batch:pending.append(pool.submit(work,batch))
        while pending:consume()
    write(stage+'/completion.json',dict(n=n,chunks=chunk,counts=dict(counts),complete=True,utc=now()))
def external_task(raw,cm_only):
    verify_freeze();m=raw['mapping'];url=raw['url'].removesuffix('.git');repo=ROOT/'tools/v11-ext/dataset-repos'/url.split('github.com/')[1].replace('/','__')
    ident=raw['dataset']+'-'+str(raw['index']).replace('/','-')
    r=dict(suite='external',dataset=raw['dataset'],id=ident,index=raw['index'],url=url,repo=url.split('/')[-1],input_scope='paired files only',annotation=m)
    try:
        old=git(repo,'rev-parse',m['source_commit']+'^{commit}').decode().strip();new=git(repo,'rev-parse',m['target_commit']+'^{commit}').decode().strip()
        def text(rev,path):
            b=git(repo,'show',rev+':'+path)
            try:return b.decode('utf-8').replace('\r\n','\n').replace('\r','\n')
            except UnicodeDecodeError:return b.decode('latin-1').replace('\r\n','\n').replace('\r','\n')
        path=m['source_file'];old_text=text(old,path);source_region=json.loads(m['source_range']);s,e=region_lines(source_region)
        target=target_path(str(repo),old,new,path);version={}
        if target is not None:
            new_text=text(new,target);version[target]=(digest(new_text),new_text)
        a=dict(path=path,line_start=s,line_end=e,quotation='\n'.join(old_text.splitlines()[s-1:e]),content_hash=digest(old_text))
        t=dict(anchor=a,old_lines=old_text.splitlines(),version=version,truth=None,changed=False)
        # Annotation used for scoring only, after native input assembly.
        truth_region=json.loads(m['target_range']) if m['target_range'] else None
        truth_text=text(new,m['target_file']) if truth_region is not None else ''
        r.update(old_commit=old,new_commit=new,source_sha256=digest(old_text),target_sha256=digest(truth_text),anchor_at=[path,s],span=e-s+1,source_file=path,source_region=source_region,truth_region=truth_region,
                 truth_at=None if truth_region is None else [m['target_file'],region_lines(truth_region)[0]],reference_range=None if truth_region is None else [m['target_file'],*region_lines(truth_region)],pair=url+':'+old+':'+new,
                 cls='gone' if truth_region is None else 'edited' if region_text(old_text,source_region)!=region_text(truth_text,truth_region) else 'moved file' if m['target_file']!=path else 'shifted' if s!=region_lines(truth_region)[0] else 'in place',
                 language={'.py':'Python','.java':'Java','.js':'JavaScript','.jsx':'JavaScript','.cs':'C#','.cpp':'C++','.cc':'C++','.h':'C++','.hpp':'C++','.go':'Go','.rb':'Ruby','.ts':'TypeScript','.tsx':'TypeScript','.php':'PHP','.html':'HTML','.htm':'HTML'}.get(Path(path).suffix.lower(),'Other '+Path(path).suffix.lower()))
        outputs={}
        if cm_only:outputs['codemapper']=A.codemapper(t,repo,old,new,ident,source_region,resolver='native-readonly' if '-native' in STAGE else None)
        else:
            outputs=A.living(t,{path:old_text});outputs['gumtree']=A.gumtree(t)
        scores={}
        for name,o in outputs.items():
            pred=o.get('character_range');at=o.get('placement');full=o.get('range')
            if at is not None and pred is None:
                pred_text=version.get(at[0],('',''))[1]
                end=full[2] if full else min(at[1]+r['span']-1,len(pred_text.splitlines()))
                try:pred=line_region(pred_text,at[1],end)
                except ValueError:o.update(failed('invalid line projection'));at=None
                if not full:o['character_projection']='original height clipped at EOF; no native end'
            o['scored_character_range']=pred
            same=o['label']!='execution_error' and ((truth_region is None and at is None) or (at is not None and at[0]==m['target_file']))
            scores[name]=dict(positional=character_score(truth_text,truth_region,pred,same),upstream=character_score(truth_text,truth_region,pred,upstream_file_agrees(m['target_file'],truth_region,o),upstream=True))
        r.update(methods=outputs,character_scores=scores)
    except Exception as error:
        r.update(input_error=repr(error),traceback=traceback.format_exc(),methods={name:failed('input unavailable: '+repr(error)) for name in (['codemapper'] if cm_only else ['gumtree','cascade_v1','quote_exact','diff_drift','line_number','tracker_adapter']+[f't{th:.2f}-'+suffix for th in (.85,.55) for suffix in ('deployed','VW','AG','AG+VW','IG','IG+VW','IG+AG','IG+AG+VW')])})
    return r
def external_batch(args):return [external_task(raw,args[0]) for raw in args[1]]
def external(stage,cm_only,workers=4):
    verify_freeze();assert read(OUT/'reproduction-gate.json')['data']['passed']
    if stage.endswith(('-repair','-repair2')):
        import time
        deadline=time.monotonic()+7200
        marker='native-targeted-acquisition.json' if stage.endswith('-repair2') else 'native-history-warmup.json'
        while not (OUT/marker).exists():
            if time.monotonic()>deadline:raise TimeoutError('native history acquisition warmup incomplete')
            time.sleep(10)
    workers=int(os.environ.get('WPC_WORKERS',workers))
    if not cm_only:assert (OUT/'external-codemapper/completion.json').exists(),'CodeMapper reproduction must precede frozen-method evaluation'
    directory=OUT/stage;directory.mkdir(exist_ok=True);assert not (directory/'completion.json').exists()
    done=set();n=chunk=0;pending=[]
    for path in sorted(directory.glob('trials-*.json')):
        saved=read(path)['data'];n+=len(saved);done.update(r['id'] for r in saved);chunk=max(chunk,int(path.stem.split('-')[1])+1)
    write(stage+('/start.json' if not done else '/resume-'+str(__import__('time').time_ns())+'.json'),dict(utc=now(),cm_only=cm_only,preserved_rows=n,workers=workers))
    raw=list(records())
    if stage.endswith(('-repair','-repair2')):
        source_stage='external-codemapper-native-repair' if stage.endswith('-repair2') else 'external-codemapper-native'
        initial=[r for p in (OUT/source_stage).glob('trials-*.json') for r in read(p)['data']]
        affected={r['id'] for r in initial if 'lazy fetching disabled' in r['methods']['codemapper'].get('error','') or 'promisor remote' in r['methods']['codemapper'].get('error','')}
        raw=[r for r in raw if r['dataset']+'-'+str(r['index']).replace('/','-') in affected]
        if not done:write(stage+'/repair-selection.json',dict(ids=sorted(affected),reason='Missing offline history objects only; unchanged matching and annotations'),sorted((OUT/source_stage).glob('trials-*.json')))
    rows=[r for r in raw if r['dataset']+'-'+str(r['index']).replace('/','-') not in done]
    with ProcessPoolExecutor(max_workers=workers,initializer=initialize,initargs=(stage,)) as pool:
        def consume():
            nonlocal n,chunk
            ready,_=wait(pending,return_when=FIRST_COMPLETED);future=next(f for f in pending if f in ready);pending.remove(future)
            got=future.result();write(f'{stage}/trials-{chunk:05d}.json',got);n+=len(got);chunk+=1
            print(stage,n,'input errors',sum('input_error' in r for r in got),flush=True)
        for i in range(0,len(rows),10):
            pending.append(pool.submit(external_batch,(cm_only,rows[i:i+10])))
            if len(pending)>=workers*4:consume()
        while pending:consume()
    write(stage+'/completion.json',dict(n=n,complete=True,chunks=chunk,utc=now()))
def main():
    stage=sys.argv[1]
    try:
        if stage=='gumtree-living':execute(stage,living_inputs())
        elif stage=='codemapper-living':
            assert (OUT/'external-codemapper/completion.json').exists(),'external CodeMapper reproduction must run first'
            execute(stage,living_inputs(cm=True))
        elif stage=='codemapper-living-native':
            assert (OUT/'external-codemapper-native/completion.json').exists()
            execute(stage,living_inputs(cm=True))
        elif stage=='external-codemapper':external(stage,True)
        elif stage=='external-codemapper-native':external(stage,True)
        elif stage=='external-codemapper-native-repair':external(stage,True)
        elif stage=='external-codemapper-native-repair2':external(stage,True)
        elif stage=='external-frozen':external(stage,False)
        else:raise ValueError(stage)
    except BaseException as e:write(stage+'-failure-'+str(__import__('time').time_ns())+'.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
if __name__=='__main__':main()
