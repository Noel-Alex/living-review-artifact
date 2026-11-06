"""Compare fresh outputs with official retained outputs; no matcher retuning."""
import sys,json,csv
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
BASE=ROOT/'tools/v11-ext/codemapper-archived-results/source/results'
def main():
    tag=sys.argv[1] if len(sys.argv)>1 else 'corrected'
    stage='external-codemapper-native' if 'native' in tag else 'external-codemapper'
    records=[r for p in sorted((OUT/stage).glob('trials-*.json')) for r in read(p)['data']]
    differences=[];same=0;missing=0;csvs={}
    for r in records:
        d=r['dataset'];directory=BASE/'tracked_maps'/d/f'mapped_regions_{d}_15'/str(r['index'])
        if not directory.exists():directory=BASE/'tracked_maps'/d/f'mapped_regions_{d}'/str(r['index'])
        p=directory/'target.json'
        if d=='suppression':p=BASE/'tracked_maps'/d/f'mapped_regions_{d}_15'/str(r['index']).split('/')[0]/'target.json'
        if not p.exists():missing+=1;continue
        native=read(p)
        if d=='suppression':native=[v for v in native if str(v.get('iteration'))==str(r['index']).split('/')[-1]]
        fresh=r['methods']['codemapper'];old=native[0] if len(native)==1 else {}
        old_range=old.get('target_range');old_range=json.loads(old_range) if isinstance(old_range,str) else old_range
        if old_range and old_range.count(0)>=3:old_range=None
        current=fresh.get('character_range')
        if fresh['label']!='execution_error' and old_range==current and (current is None or fresh.get('placement',[None])[0]==old.get('target_file')):same+=1
        else:differences.append(dict(id=r['id'],dataset=d,archived=old,fresh=fresh,annotation=r['annotation']))
    for d in ('annotation_a','annotation_b','suppression','variable_test','block_test','method_test'):
        p=BASE/'measurement_results'/d/f'measurement_results_metrics_{d}_15.csv'
        if not p.exists():p=BASE/'measurement_results'/d/f'measurement_results_metrics_{d}.csv'
        if not p.exists():continue
        with p.open(encoding='utf-8',newline='') as f:rows=list(csv.reader(f))
        # Retain literal summary cells rather than mistaking fast-mode outputs for execution.
        csvs[d]=dict(sha256=sha(p),headers=rows[0],last_rows=rows[-3:],observed_labels=dict(Counter(r[7] for r in rows[1:] if len(r)>7 and r[7] in ('Y','M','W'))))
    write('codemapper-archive-audit-'+tag+'-'+str(len(records))+'.json',dict(rows=len(records),same_native_output=same,missing_archived_output=missing,differences=differences,archived_csvs=csvs,scope='archived upstream outputs only; not fresh reproduction'))
    print('native agreement',same,'differences',len(differences),'archive missing',missing)
    for r in differences[:10]:print(r['id'],r['archived'].get('target_file'),r['archived'].get('target_range'),r['fresh'].get('character_range'))
if __name__=='__main__':main()
