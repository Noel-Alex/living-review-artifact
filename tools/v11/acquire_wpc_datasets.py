"""Acquire Git object histories and benchmark-referenced blobs; never checkout."""
import sys,json,subprocess,hashlib,time,traceback,os
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
SRC=next((ROOT/'tools/v11-ext/codemapper/source').iterdir())
OUT=ROOT/'evidence/v11-wpc'
REPOS=ROOT/'tools/v11-ext/dataset-repos'
def records():
    for name in ('annotation_a','annotation_b','variable_test','block_test','method_test'):
        for i,r in enumerate(json.loads((SRC/f'data/annotation/{name}.json').read_text(encoding='utf-8'))):
            yield dict(dataset=name,index=i,**r)
    for p in sorted((SRC/'data/suppression_data').glob('*/*/expect_full_histories.json')):
        a,b=json.loads(p.read_text(encoding='utf-8'))
        if not a['range']:continue
        yield dict(dataset='suppression',index=str(p.parent.relative_to(SRC/'data/suppression_data')).replace('\\','/'),url=a['url'].removesuffix('.git'),mapping=dict(source_commit=a['commit'],target_commit=b['commit'],source_file=a['file_path'],target_file=b['file_path'],source_range=a['range'],target_range=b['range']))
def git(path,*args,timeout=600):
    env=dict(os.environ,GIT_TERMINAL_PROMPT='0',GIT_CONFIG_NOSYSTEM='1')
    r=subprocess.run(['git','-c','core.hooksPath='+str(REPOS/'no-hooks'),'-c','protocol.file.allow=never','-C',str(path),*args],capture_output=True,timeout=timeout,env=env)
    if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
    return r.stdout
def main():
    REPOS.mkdir(exist_ok=False);(REPOS/'no-hooks').mkdir()
    rows=list(records());(OUT/'external-input-index.json').write_text(json.dumps(rows,indent=1),encoding='utf-8')
    result=[]
    for url in sorted({r['url'].removesuffix('.git') for r in rows}):
        name=url.split('github.com/')[1].replace('/','__');p=REPOS/name
        entry=dict(url=url,path=str(p),started_utc=datetime.now(timezone.utc).isoformat())
        try:
            raw=git(REPOS,'clone','--bare','--filter=blob:none',url,str(p),timeout=900)
            entry['head']=git(p,'rev-parse','HEAD').decode().strip()
            entry['licence']='Upstream repository; per-file licence retained as source data only, not redistributed'
            entry['blobs']={};entry['failures']=[]
            subset=[r for r in rows if r['url'].removesuffix('.git')==url]
            for row in subset:
                m=row['mapping']
                for side in ('source','target'):
                    rev,path=m[side+'_commit'],m[side+'_file']
                    if not path:continue
                    key=rev+':'+path
                    if key in entry['blobs']:continue
                    try:
                        full=git(p,'rev-parse',rev+'^{commit}').decode().strip()
                        blob=git(p,'show',full+':'+path,timeout=180)
                        entry['blobs'][key]=dict(commit=full,sha256=hashlib.sha256(blob).hexdigest(),bytes=len(blob))
                    except Exception as e:entry['failures'].append(dict(key=key,error=repr(e)))
                # Same source path at target is acquired without relying on annotated target path.
                key=m['target_commit']+':'+m['source_file']
                if key not in entry['blobs']:
                    try:
                        full=git(p,'rev-parse',m['target_commit']+'^{commit}').decode().strip()
                        blob=git(p,'show',full+':'+m['source_file'],timeout=180)
                        entry['blobs'][key]=dict(commit=full,sha256=hashlib.sha256(blob).hexdigest(),bytes=len(blob))
                    except Exception as e:entry['failures'].append(dict(key=key,error=repr(e)))
            entry['status']='acquired'
        except Exception as e:entry.update(status='failed',error=repr(e),traceback=traceback.format_exc())
        result.append(entry)
        (OUT/f'acquisition-{name}.json').write_text(json.dumps(entry,indent=1),encoding='utf-8')
        print(name,entry['status'],len(entry.get('blobs',{})),len(entry.get('failures',[])),flush=True)
    (OUT/'dataset-acquisition.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
if __name__=='__main__':main()
