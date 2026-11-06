"""Bulk-fetch path histories required by native --follow; no region matching."""
import sys,os,json,subprocess,traceback
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
from acquire_wpc_datasets import records
def run(repo,args,data=None,timeout=300):
    return subprocess.run(['git','-c','core.hooksPath='+str(OUT/'no-hooks'),'-c','fetch.negotiationAlgorithm=noop','-c','maintenance.auto=false','-c','gc.auto=0','-C',str(repo),*args],input=data,capture_output=True,timeout=timeout,env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_TERMINAL_PROMPT='0'))
def acquire(item):
    url,rows,stage=item;name=url.split('github.com/')[1].replace('/','__');repo=ROOT/'tools/v11-ext/dataset-repos'/name
    folder=OUT/stage/name;folder.mkdir(parents=True,exist_ok=False)
    result=dict(url=url,started_utc=now(),paths=[],missing_objects=[],fetch_attempts=[])
    try:
        refs=sorted({r['mapping'][side+'_commit'] for r in rows for side in ('source','target')})
        paths=sorted({r['mapping'][side+'_file'] for r in rows for side in ('source','target') if r['mapping'][side+'_file']})
        missing=set();result['paths']=paths;result['refs']=refs
        for index in range(0,len(paths),30):
            r=run(repo,['rev-list','--objects','--missing=print','--stdin','--',*paths[index:index+30]],('\n'.join(refs)+'\n').encode())
            (folder/f'rev-list-{index//30}.log').write_bytes(r.stdout+b'\n'+r.stderr)
            if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
            missing.update(line[1:] for line in r.stdout.decode().splitlines() if line.startswith('?'))
        result['missing_objects']=sorted(missing)
        for index in range(0,len(missing),256):
            batch=sorted(missing)[index:index+256]
            r=run(repo,['fetch','--no-tags','--no-auto-maintenance','--no-write-fetch-head','--recurse-submodules=no','--filter=blob:none','origin','--stdin'],('\n'.join(batch)+'\n').encode(),timeout=300)
            (folder/f'fetch-{index//256}.log').write_bytes(r.stdout+b'\n'+r.stderr)
            result['fetch_attempts'].append(dict(n=len(batch),returncode=r.returncode))
            if r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
        result.update(complete=True,finished_utc=now())
    except BaseException as e:result.update(complete=False,error=repr(e),traceback=traceback.format_exc())
    (folder/'manifest.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
    return result
def main():
    grouped=defaultdict(list)
    for row in records():grouped[row['url'].removesuffix('.git')].append(row)
    retry=len(sys.argv)>1 and sys.argv[1]=='retry'
    stage='native-history-acquisition-retry' if retry else 'native-history-acquisition'
    items=[]
    for url,rows in sorted(grouped.items()):
        if retry:
            old=OUT/'native-history-acquisition'/url.split('github.com/')[1].replace('/','__')/'manifest.json'
            assert old.exists(),'initial acquisition still running'
            if read(old)['complete']:continue
        items.append((url,rows,stage))
    results=[]
    with ProcessPoolExecutor(max_workers=6) as pool:
        for result in pool.map(acquire,items):
            results.append(result);print(result['url'],result['complete'],len(result.get('missing_objects',[])),flush=True)
    write(stage+'.json',results,[OUT/'external-input-index.json',OUT/'dataset-acquisition.json'])
if __name__=='__main__':main()
