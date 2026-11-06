"""C6 reuse completed mappings; execute only additional seed-2 stress pairs."""
import sys,os,json,itertools,time,traceback
from pathlib import Path
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_c6 import *
from wpc_adapters import Adapters,materialize,git,target_path
from run_wpb import metadata,histories,originals
from wpb_stress import b1a,duplicates,short
from analyze_wpc import merged
from acquire_wpc_datasets import records

def key(r):return tuple(r.get(k) for k in ('suite','op','index','seed','frequency','tokens'))
def small_old(t,old):return {p:old[p] for p in set(t['version'])|{t['anchor']['path']} if p in old}
def initialize(stage):
    global A,STAGE
    gate();STAGE=stage;A=Adapters(OUT/'c6'/stage/'workers'/str(os.getpid()))
    from multiprocessing.util import Finalize
    Finalize(A,A.close,exitpriority=10)

def tracked(t,saved):
    try:return strict_tracker(t,saved)
    except ValueError:
        try:
            q=A.base.request(json.dumps(dict(mode='basic',method='tracker_adapter',trial=t)))
            if 'error' in q:return failed(q['error'])
            return q['output']
        except Exception as e:return failed(repr(e))

def labels(r,t,old,bases):
    track=tracked(t,r['methods']['tracker_adapter']);deployed=r['methods']['t0.85-deployed']
    bases.update(tracker=track,hybrid=hybrid(track,deployed))
    # Do not persist all unrelated baseline families again.
    r=dict(r,methods={k:v for k,v in r['methods'].items() if k in ('t0.85-deployed','t0.85-IG+AG+VW','t0.55-IG+AG+VW','tracker_adapter','gumtree','codemapper')})
    return attach(r,t,old,bases)

def stress_batch(batch):
    gate();out=[]
    for r,t,old in batch:
        fixture=OUT/'c6/stress/fixtures'/r['id']
        if fixture.exists():
            try:
                before=git(fixture,'rev-parse','refs/heads/old').decode().strip();after=git(fixture,'rev-parse','refs/heads/evaluation').decode().strip()
                for rev,files in ((before,old),(after,{p:v[1] for p,v in t['version'].items()})):
                    actual={}
                    for item in git(fixture,'ls-tree','-rz',rev).split(b'\0'):
                        if not item:continue
                        header,path=item.split(b'\t',1);actual[path.decode()]=header.split()[2].decode()
                    expected={p:__import__('hashlib').sha1(b'blob '+str(len(text.encode())).encode()+b'\0'+text.encode()).hexdigest() for p,text in files.items()}
                    assert actual==expected,'fixture tree drift'
            except Exception as e:
                write('c6/stress/incomplete-fixture-'+r['id']+'-'+str(time.time_ns())+'.json',dict(id=r['id'],error=repr(e)))
                fixture=fixture.with_name(fixture.name+'-retry-'+str(time.time_ns()));before,after=materialize(fixture,old,t['version'])
        else:before,after=materialize(fixture,old,t['version'])
        cm=A.codemapper(t,fixture,before,after,r['id'],resolver='native-readonly')
        gt=A.gumtree(dict(t,version={t['anchor']['path']:t['version'][t['anchor']['path']]} if t['anchor']['path'] in t['version'] else {}))
        r=dict(r,c6_input_old_commit=before,c6_input_new_commit=after,c6_source_map_sha256=digest(json.dumps({p:digest(v) for p,v in old.items()},sort_keys=True)))
        out.append(labels(r,t,old,dict(gumtree=gt,codemapper=cm)))
    return out

def stress_inputs():
    prior={}
    for p in sorted((ROOT/'evidence/v11-wpb1/evaluation').glob('trials-*.json')):
        for r in read(p)['data']:
            if r['suite'] in ('indentation','duplicates','short'):prior[key(r)]=r
    audits=[];n=0
    for meta,t,old in itertools.chain(b1a(20261027),duplicates(20261027),short(20261027)):
        if meta.get('generator_audit'):audits.append(meta);continue
        r=prior[key(meta)];actual=metadata(meta,t)
        for field in ('old_file_sha256','new_file_map_sha256','truth_at','reference_range','cls','anchor_at'):assert actual[field]==r[field],(key(meta),field)
        ident='stress-'+r['suite']+'-'+r['op'].replace('/','_')+'-'+str(r['index'])+'-'+r.get('frequency','')+'-'+r.get('tokens','')
        yield dict(r,id=ident),t,small_old(t,old);n+=1
    assert n==len(prior),(n,len(prior));assert all(a['complete'] for a in audits)
    write('c6/stress-generator-audit.json',dict(complete=True,n=n,audits=audits),[ROOT/'evidence/v11-wpb1/evaluation/completion.json'])

def stress():
    gate();stage=OUT/'c6/stress';stage.mkdir(parents=True,exist_ok=True);assert not (stage/'completion.json').exists()
    done=set();n=chunk=0;counts=Counter()
    for p in sorted(stage.glob('trials-*.json')):
        rows=read(p)['data'];done.update(r['id'] for r in rows);n+=len(rows);chunk=max(chunk,int(p.stem.split('-')[1])+1)
    workers=int(os.environ.get('WPC_C6_WORKERS','16'))
    write('c6/stress/start-'+str(time.time_ns())+'.json',dict(utc=now(),preserved_rows=n,workers=workers))
    pending=[]
    with ProcessPoolExecutor(max_workers=workers,initializer=initialize,initargs=('stress',)) as pool:
        def consume():
            nonlocal n,chunk
            result=pending.pop(0).result();write(f'c6/stress/trials-{chunk:05d}.json',result);chunk+=1;n+=len(result)
            for r in result:counts.update({m:int(o['label']=='execution_error') for m,o in r['c6_bases'].items()})
            if n%200<len(result):print('C6 stress',n,dict(counts),flush=True)
        batch=[]
        for item in stress_inputs():
            if item[0]['id'] in done:continue
            batch.append(item)
            if len(batch)==10:
                pending.append(pool.submit(stress_batch,batch));batch=[]
                if len(pending)>=workers*2:consume()
        if batch:pending.append(pool.submit(stress_batch,batch))
        while pending:consume()
    write('c6/stress/completion.json',dict(complete=True,n=n,chunks=chunk,utc=now()))

def decode(blob):
    try:s=blob.decode('utf-8')
    except UnicodeDecodeError:s=blob.decode('latin-1')
    return s.replace('\r\n','\n').replace('\r','\n')

def reused_inputs():
    saved={r['id']:r for r in merged() if r['suite']!='original' or r['seed']==20261027}
    for meta,t,old in itertools.chain(originals(20261027),histories(('own','oss'))):
        ident='real-'+str(meta['row']) if meta['suite']=='real' else f"20261027-{meta['op']}-{meta['index']}"
        r=saved.pop(ident);actual=metadata(meta,t)
        for field in ('old_file_sha256','new_file_map_sha256','truth_at','reference_range','cls','anchor_at'):assert actual[field]==r[field],(ident,field)
        yield r,t,small_old(t,old)
    for raw in records():
        ident=raw['dataset']+'-'+str(raw['index']).replace('/','-');r=saved.pop(ident);m=r['annotation']
        repo=ROOT/'tools/v11-ext/dataset-repos'/raw['url'].removesuffix('.git').split('github.com/')[1].replace('/','__')
        path=m['source_file'];oldtext=decode(git(repo,'show',r['old_commit']+':'+path));assert digest(oldtext)==r['source_sha256']
        s,e=region_lines(r['source_region']);a=dict(path=path,line_start=s,line_end=e,quotation='\n'.join(oldtext.splitlines()[s-1:e]),content_hash=digest(oldtext))
        target=target_path(str(repo),r['old_commit'],r['new_commit'],path);version={};old={path:oldtext}
        predicted={o['placement'][0] for name,o in r['methods'].items() if name in ('gumtree','codemapper','tracker_adapter','t0.85-deployed') and o['placement']}
        # Read only actual predicted paths plus the label-free adapter's candidate.
        for p in predicted|({target} if target else set()):
            text=decode(git(repo,'show',r['new_commit']+':'+p));version[p]=(digest(text),text)
            rawold=__import__('subprocess').run(['git','-C',str(repo),'show',r['old_commit']+':'+p],capture_output=True,timeout=55)
            if rawold.returncode==0:old[p]=decode(rawold.stdout)
        yield r,dict(anchor=a,old_lines=oldtext.splitlines(),version=version),old
    assert not saved,len(saved)

def reuse():
    gate();initialize('reuse');stage=OUT/'c6/reuse';stage.mkdir(parents=True,exist_ok=True);assert not (stage/'completion.json').exists()
    done=set();n=chunk=0
    for p in sorted(stage.glob('trials-*.json')):
        rows=read(p)['data'];done.update(r['id'] for r in rows);n+=len(rows);chunk=max(chunk,int(p.stem.split('-')[1])+1)
    write('c6/reuse/start-'+str(time.time_ns())+'.json',dict(utc=now(),preserved_rows=n))
    batch=[]
    try:
        for r,t,old in reused_inputs():
            if r['id'] in done:continue
            batch.append(labels(r,t,old,{m:r['methods'][m] for m in ('gumtree','codemapper')}))
            if len(batch)==50:
                write(f'c6/reuse/trials-{chunk:05d}.json',batch);n+=len(batch);chunk+=1;batch=[]
                if n%500==0:print('C6 reused',n,flush=True)
        if batch:write(f'c6/reuse/trials-{chunk:05d}.json',batch);n+=len(batch);chunk+=1
    finally:A.close()
    write('c6/reuse/completion.json',dict(complete=True,n=n,chunks=chunk,utc=now()))

if __name__=='__main__':
    try:
        os.environ['GIT_NO_LAZY_FETCH']='1'
        if sys.argv[1]=='stress':stress()
        elif sys.argv[1]=='reuse':reuse()
        else:raise ValueError(sys.argv[1])
    except BaseException as e:
        write('c6/failure-'+str(time.time_ns())+'.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
