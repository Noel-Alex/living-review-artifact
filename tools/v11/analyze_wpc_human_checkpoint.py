"""Read only the completed A/B subset while the separate Java jobs continue."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
from analyze_wpc import groups,metrics,fix_upstream_file_absence
def main():
    paths=sorted((OUT/'external-frozen').glob('trials-*.json'))
    native_paths=sorted((OUT/'external-codemapper-native').glob('trials-*.json'))
    frozen=[r for p in paths for r in read(p)['data'] if r['dataset'] in ('annotation_a','annotation_b')]
    native={r['id']:r for p in native_paths for r in read(p)['data'] if r['dataset'] in ('annotation_a','annotation_b')}
    repaired=len(sys.argv)>1 and sys.argv[1]=='repaired'
    if repaired:
        corrections={r['id']:r for p in (OUT/'external-codemapper-native-repair').glob('trials-*.json') for r in read(p)['data'] if r['dataset'] in ('annotation_a','annotation_b')}
        needed={i for i,r in native.items() if 'promisor remote' in r['methods']['codemapper'].get('error','') or 'lazy fetching disabled' in r['methods']['codemapper'].get('error','')}
        assert needed<=corrections.keys(),('human acquisition corrections pending',len(needed-corrections.keys()))
        native.update(corrections)
        paths+=sorted((OUT/'external-codemapper-native-repair').glob('trials-*.json'))
    assert len(frozen)==len(native)==200
    for r in frozen:
        n=native[r['id']];r['methods']['codemapper']=n['methods']['codemapper'];r['character_scores']['codemapper']=n['character_scores']['codemapper']
    names=('cascade','t0.85-IG+AG+VW','t0.55-IG+AG+VW','gumtree','codemapper')
    frozen=fix_upstream_file_absence(frozen)
    selected={k:v for k,v in groups(frozen).items() if k in ('external:human-AB','external:human-AB:non-Python-code') or k.startswith('external:language:')}
    result={k:dict(n=len(v),methods={m:metrics(v,m) for m in names}) for k,v in selected.items()}
    write('human-AB-checkpoint'+('-repaired' if repaired else '')+'.json',dict(scope='Completed fixed A/B subset only; other datasets continue separately; acquisition repair explicitly named where applied',strata=result),paths+native_paths)
    for key in ('external:human-AB','external:human-AB:non-Python-code'):
        print(key,result[key]['n'],flush=True)
        for method,m in result[key]['methods'].items():
            c=m['characters']['upstream'];print(method,'line',m['accuracy']['k'],'character',c['exact']['k'],'F1',round(c['f1'],3),'errors',m['execution_errors'],flush=True)
if __name__=='__main__':main()
