"""Acquire remaining rename-follow objects offline-first; never map regions."""
import sys,json,re,time,subprocess,traceback
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
from acquire_wpc_datasets import records
from acquire_wpc_native_history import run
def warm(item):
    url,rows,stage=item;name=url.split('github.com/')[1].replace('/','__');repo=ROOT/'tools/v11-ext/dataset-repos'/name
    folder=OUT/stage/name;folder.mkdir(parents=True,exist_ok=False)
    report=dict(url=url,rounds=[],queries=0,complete=False);dates={};queries=set()
    try:
        for raw in rows:
            m=raw['mapping'];a,b=m['source_commit'],m['target_commit']
            for rev in (a,b):
                if rev not in dates:
                    resolved=run(repo,['rev-parse',rev+'^{commit}']);assert resolved.returncode==0,resolved.stderr
                    full=resolved.stdout.decode().strip();r=run(repo,['cat-file','commit',full]);assert r.returncode==0,r.stderr
                    committer=next(line for line in r.stdout.splitlines() if line.startswith(b'committer '))
                    dates[rev]=int(committer.rsplit(b' ',2)[1])
            newer=b if dates[a]<dates[b] else a;queries.add((newer,m['source_file']))
        report['queries']=len(queries);pending=sorted(queries)
        for iteration in range(10):
            failed=[];missing=set();errors=[]
            for index,(rev,path) in enumerate(pending):
                try:
                    r=run(repo,['log',rev,'--follow','--name-status','--',path],timeout=60)
                    if r.returncode:
                        (folder/f'error-{iteration}-{index}.log').write_bytes(r.stdout+b'\n'+r.stderr)
                        failed.append((rev,path));message=r.stderr.decode(errors='replace');missing.update(re.findall(r'could not fetch ([0-9a-f]{40})',message));errors.append(dict(rev=rev,path=path,error=message))
                except Exception as e:failed.append((rev,path));errors.append(dict(rev=rev,path=path,error=repr(e)))
            report['rounds'].append(dict(iteration=iteration,attempted=len(pending),failed=len(failed),missing_objects=sorted(missing),errors=errors))
            if not failed:report['complete']=True;break
            if not missing:break
            r=run(repo,['fetch','--no-tags','--no-auto-maintenance','--no-write-fetch-head','--recurse-submodules=no','--filter=blob:none','origin','--stdin'],('\n'.join(sorted(missing))+'\n').encode(),timeout=180)
            (folder/f'fetch-{iteration}.log').write_bytes(r.stdout+b'\n'+r.stderr)
            if r.returncode:report['fetch_error']=r.stderr.decode(errors='replace');break
            pending=failed
    except Exception as e:report.update(error=repr(e),traceback=traceback.format_exc())
    (folder/'manifest.json').write_text(json.dumps(report,indent=1),encoding='utf-8');return report
def main():
    deadline=time.monotonic()+3600
    while not (OUT/'native-history-acquisition-retry.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('bulk acquisition incomplete')
        time.sleep(10)
    grouped=defaultdict(list)
    for row in records():grouped[row['url'].removesuffix('.git')].append(row)
    reports=[];stage=sys.argv[1] if len(sys.argv)>1 else 'native-history-warmup'
    with ProcessPoolExecutor(max_workers=6) as pool:
        for r in pool.map(warm,[(url,rows,stage) for url,rows in sorted(grouped.items())]):reports.append(r);print(r['url'],r['complete'],r['queries'],flush=True)
    write(stage+'.json',reports,[OUT/'native-history-acquisition-retry.json'])
    if stage.endswith('-retry') and not (OUT/'native-history-warmup.json').exists():
        write('native-history-warmup.json',dict(complete=False,superseded_by=stage+'.json',reason='Initial acquisition probe was stopped; git show could read an unavailable mailmap while probing dates. Raw commit-date reads fix the probe; initial logs remain.'))
if __name__=='__main__':main()
