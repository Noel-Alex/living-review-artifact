"""Fetch only residual objects requested by native Git history/path commands."""
import sys,time,os,subprocess,traceback
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
def acquire(item):
    url,rows=item;name=url.split('github.com/')[1].replace('/','__');repo=ROOT/'tools/v11-ext/dataset-repos'/name;folder=OUT/'native-targeted-acquisition'/name;folder.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,GIT_TERMINAL_PROMPT='0');env.pop('GIT_NO_LAZY_FETCH',None)
    def command(args,timeout=600):return subprocess.run(['git','--no-pager','-c','core.hooksPath='+str(OUT/'no-hooks'),'-c','fetch.negotiationAlgorithm=noop','-c','gc.auto=0','-C',str(repo),*args],capture_output=True,timeout=timeout,env=env)
    result=dict(url=url,queries=[],complete=True);seen=set();dates={}
    for row in rows:
        old,new,path=row['old_commit'],row['new_commit'],row['source_file']
        try:
            for rev in (old,new):
                if rev not in dates:
                    r=command(['cat-file','commit',rev]);assert r.returncode==0,r.stderr;dates[rev]=int(next(x for x in r.stdout.splitlines() if x.startswith(b'committer ')).rsplit(b' ',2)[1])
            newer=new if dates[old]<dates[new] else old
            queries=[('log',newer,path),('diff',old,new)]
            for query in queries:
                if query in seen:continue
                seen.add(query);index=len(result['queries']);begin=time.monotonic()
                args=['log',newer,'--follow','--name-status','--no-ext-diff','--no-textconv','--',path] if query[0]=='log' else ['diff','--no-ext-diff','--no-textconv','--name-status','--diff-filter=RC',old,new]
                r=command(args);(folder/f'query-{index}.log').write_bytes(r.stdout+b'\n'+r.stderr)
                result['queries'].append(dict(command=args,returncode=r.returncode,elapsed_seconds=time.monotonic()-begin,log_sha256=sha(folder/f'query-{index}.log')))
                if r.returncode:result['complete']=False
        except Exception as e:result['complete']=False;result['queries'].append(dict(id=row['id'],error=repr(e),traceback=traceback.format_exc()))
    (folder/'manifest.json').write_text(__import__('json').dumps(result,indent=1),encoding='utf-8');return result
def main():
    deadline=time.monotonic()+7200
    while not (OUT/'external-codemapper-native-repair/completion.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('First acquisition repair incomplete')
        time.sleep(10)
    grouped=defaultdict(list)
    for p in (OUT/'external-codemapper-native-repair').glob('trials-*.json'):
        for r in read(p)['data']:
            error=r['methods']['codemapper'].get('error','')
            if 'promisor remote' in error or 'lazy fetching disabled' in error:grouped[r['url']].append(r)
    result=[]
    with ProcessPoolExecutor(max_workers=6) as pool:
        for r in pool.map(acquire,sorted(grouped.items())):result.append(r);print(r['url'],r['complete'],len(r['queries']),flush=True)
    write('native-targeted-acquisition.json',result,sorted((OUT/'external-codemapper-native-repair').glob('trials-*.json')))
if __name__=='__main__':main()
