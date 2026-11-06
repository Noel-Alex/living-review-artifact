"""Check native path resolution on identical commits with original vs full refs."""
import sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
from wpa_core import pure_module
from analyze_wpc import load
def main():
    os.environ['GIT_NO_LAZY_FETCH']='1'
    module=pure_module(Path(__file__).with_name('wpc_cm_worker.py'),'wpc_ref_probe')
    rows=sorted((r for r in load('external-codemapper-native') if r['dataset']=='variable_test'),key=lambda r:r['index'])[:30]
    results=[]
    for r in rows:
        repo=ROOT/'tools/v11-ext/dataset-repos'/r['url'].split('github.com/')[1].replace('/','__');m=r['annotation'];result=dict(id=r['id'],full=[r['old_commit'],r['new_commit']],original=[m['source_commit'],m['target_commit']])
        for kind,a,b in [('full',r['old_commit'],r['new_commit']),('original',m['source_commit'],m['target_commit'])]:
            try:result[kind+'_path']=module.native_target(str(repo),a,b,r['source_file'])
            except Exception as e:result[kind+'_error']=repr(e)
        results.append(result)
    differences=[r for r in results if r.get('full_path')!=r.get('original_path') or r.get('full_error')!=r.get('original_error')]
    write('reference-spelling-probe.json',dict(scope='First 30 variable_test rows, deterministic index order, path resolver only; no region mapping or parameter tuning',n=len(results),different=len(differences),cases=results))
    print('path spelling probe',len(results),'differences',len(differences),flush=True)
    for r in differences[:5]:print(r['id'],r.get('full_path'),r.get('original_path'),flush=True)
if __name__=='__main__':main()
