"""Distinguish true deployed execution from a timed-out frozen family call."""
import sys
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_c6 import *
from analyze_wpc import load

def main():
    gate();rows=load('external-frozen');counts=Counter();differences=[];cross=[]
    for r in rows:
        a,b=r['methods']['cascade'],r['methods']['t0.85-deployed']
        if any(a.get(k)!=b.get(k) for k in ('placement','range','label','recheck')):
            differences.append(dict(id=r['id'],dataset=r['dataset'],native=a,frozen_family=b));counts[r['dataset']]+=1
            if b['label']=='execution_error' and a['placement'] and a['placement'][0]!=r['anchor_at'][0]:cross.append(r['id'])
    text='''# C6 reporting clarification: native deployed baseline

The frozen B1 family computes variable-window candidates even for its zero-switch output. Its 60-second family deadline can therefore fail the zero-switch record on large Java regions while the separately executed, unchanged native deployed cascade completes. Both executions are retained in C1–C5. Calling that family outcome the actual deployed baseline would conflate family computation with native cascade behavior.

Before C6 aggregation, distinguish `deployed_native` from `t0.85-deployed` in every derived view. For external rows, `deployed_native` uses the existing C1–C5 `cascade` execution. On constructed/real rows, use the frozen zero-switch result, whose exact equality to native deployment passed the full per-observation gate. Retain the frozen zero-switch as a separate diagnostic comparator. Compare every safety combination with native deployed and both frozen combined variants; retain the zero-switch contrasts as well.

This changes a reporting identity only. No mapping, guard predicate, threshold, annotation, frozen file or raw output changes. Original C1–C5 and C6 protocol segments/hashes remain unchanged. `c6/baseline-identity-clarification.json` records the timestamp, differences and whether any frozen-family failure hid a native cross-file acceptance relevant to the hybrid. If such a hidden acceptance exists, report it explicitly rather than silently upgrading the hybrid.
'''
    path=ROOT/'review/V11-WPC-C6-REPORTING-CLARIFICATION.md';assert not path.exists();path.write_text(text,encoding='utf-8')
    write('c6/baseline-identity-clarification.json',dict(utc=now(),clarification_sha256=sha(path),differences_by_dataset=dict(counts),differences=differences,hidden_cross_file_acceptances=cross),[path]+sorted((OUT/'external-frozen').glob('trials-*.json')))
    print('native/frozen-family differences',dict(counts),'hidden cross-file acceptances',cross,flush=True)
if __name__=='__main__':main()
