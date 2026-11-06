"""Prepare a blinded 60-case disagreement packet; never supply human judgments."""
import sys,json,random,csv
from pathlib import Path
from collections import defaultdict,Counter
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
from analyze_wpc import load,ev
from history_context import PRIVATE
from wpc_adapters import git,target_path
def main():
    rows=[r for r in load('gumtree-living') if r['suite']=='real']
    strata=defaultdict(list)
    for r in rows:
        e=ev(r,r['output'])
        if e['accuracy']:continue
        kind='execution_error' if e['failure'] else 'lost' if e['lost'] else 'wrong_placement'
        strata[(r['cls'],r['group'],kind)].append(r)
    rng=random.Random(20261031)
    for group in strata.values():rng.shuffle(group)
    queues={k:list(v) for k,v in strata.items()};selected=[]
    while len(selected)<60 and any(queues.values()):
        for key in sorted(queues):
            if queues[key] and len(selected)<60:selected.append((key,queues[key].pop()))
    rng.shuffle(selected)
    packet=OUT/'disagreement-packet';packet.mkdir(exist_ok=False)
    key=[]
    for index,(stratum,r) in enumerate(selected,1):
        ident=f'C{index:03d}';folder=packet/ident;folder.mkdir()
        repo=PRIVATE[r['repo']][0] if r['repo'] in PRIVATE else ROOT/'evidence/public-histories'/r['repo']
        path=r['anchor_at'][0];new_path=target_path(str(repo),r['old_commit'],r['new_commit'],path)
        old=git(repo,'show',r['old_commit']+':'+path).decode('utf-8',errors='replace').replace('\r\n','\n')
        (folder/'old.py').write_text(old,encoding='utf-8',newline='')
        if new_path is not None:
            new=git(repo,'show',r['new_commit']+':'+new_path).decode('utf-8',errors='replace').replace('\r\n','\n')
            (folder/'new.py').write_text(new,encoding='utf-8',newline='')
        metadata=dict(case_id=ident,old_path=path,old_start=r['anchor_at'][1],old_end=r['anchor_at'][1]+r['span']-1,new_path_from_git_rename_only=new_path,new_file_present=new_path is not None,old_commit=r['old_commit'],new_commit=r['new_commit'],local_history=str(repo),note='Inspect the complete pinned tree for cross-file questions; do not execute source. No expected target or matcher output is supplied.')
        (folder/'case.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
        key.append(dict(case_id=ident,observation_id=r['id'],row=r['row'],stratum=stratum,frame_n=len(strata[stratum]),sampled_n=sum(k==stratum for k,_ in selected),oracle_class=r['cls'],oracle_target=r['truth_at'],oracle_range=r['reference_range'],gumtree=r['output']))
    with (packet/'reviewer-responses.csv').open('x',encoding='utf-8',newline='') as f:
        writer=csv.writer(f);writer.writerow(['case_id','reviewer_id','classification','new_path','new_start','new_end','confidence','rationale']);writer.writerows([[r['case_id']]+['']*7 for r in key])
    (packet/'README.md').write_text('# Blinded source-reference review\n\nNo human review has been performed. Review independently before discussion. For each case read case.json, old.py and complete new.py where present. Identify the corresponding entity and classify preserved, changed, deleted, ambiguous or insufficient_context. Give one-based inclusive coordinates and reasons. Inspect the complete pinned tree for cross-file cases; never execute source. Lock independent answers before adjudication or opening the separate key.\n\nThis is a fixed-seed stratified disagreement sample, not a prevalence sample. Sampling information and expected answers are outside this packet. It contains local private source and must not be distributed without source-sharing authorization.\n',encoding='utf-8')
    write('disagreement-key.json',dict(seed=20261031,n=len(key),frame_n=sum(map(len,strata.values())),frame_strata={str(k):len(v) for k,v in strata.items()},cases=key))
    write('packet-manifest.json',dict(n=len(key),files={str(p.relative_to(OUT)).replace('\\','/'):sha(p) for p in packet.rglob('*') if p.is_file()},human_responses=0))
    print('blinded packet',len(key),'frame',sum(map(len,strata.values())),flush=True)
if __name__=='__main__':main()
