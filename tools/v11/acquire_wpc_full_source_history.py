"""Acquire source-sized blobs across the exact native history ancestry, offline later."""
import sys,subprocess,os,traceback,shutil
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
from acquire_wpc_datasets import records
from acquire_wpc_native_history import run
def acquire(item):
    url,rows=item;name=url.split('github.com/')[1].replace('/','__');repo=ROOT/'tools/v11-ext/dataset-repos'/name;folder=OUT/'native-source-acquisition'/name;folder.mkdir(parents=True,exist_ok=False)
    result=dict(url=url,started_utc=now(),filter='blob:limit=5m',complete=False)
    try:
        assert shutil.disk_usage(ROOT).free>40*1024**3,'workspace reserve below 40 GiB'
        refs=sorted({r['mapping'][k+'_commit']+'^{commit}' for r in rows for k in ('source','target')})
        tips=run(repo,['merge-base','--independent',*refs]);assert tips.returncode==0,tips.stderr
        result['tips']=tips.stdout.decode().split();before=run(repo,['rev-parse','HEAD']).stdout.decode().strip()
        r=run(repo,['fetch','--refetch','--no-tags','--no-auto-maintenance','--no-write-fetch-head','--recurse-submodules=no','--filter=blob:limit=5m','origin','--stdin'],tips.stdout,timeout=1800)
        (folder/'fetch.log').write_bytes(r.stdout+b'\n'+r.stderr);assert r.returncode==0,r.stderr
        result['head_before']=before;result['head_after']=run(repo,['rev-parse','HEAD']).stdout.decode().strip();assert result['head_after']==before
        result.update(complete=True,finished_utc=now())
    except BaseException as e:result.update(error=repr(e),traceback=traceback.format_exc())
    (folder/'manifest.json').write_text(__import__('json').dumps(result,indent=1),encoding='utf-8');return result
def main():
    grouped=defaultdict(list)
    for r in records():grouped[r['url'].removesuffix('.git')].append(r)
    results=[]
    with ProcessPoolExecutor(max_workers=6) as pool:
        for r in pool.map(acquire,sorted(grouped.items())):results.append(r);print(r['url'],r['complete'],flush=True)
    write('native-source-acquisition.json',results,[OUT/'external-input-index.json'])
    if not (OUT/'native-history-warmup.json').exists():write('native-history-warmup.json',dict(complete=False,superseded_by='native-source-acquisition.json',reason='Path-only probes require one-by-one rename-candidate objects; preserve their failures and acquire source-sized history blobs for all pinned ancestry instead.'))
if __name__=='__main__':main()
