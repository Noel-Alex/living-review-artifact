"""Fresh B1-exact gate; writes solely WP C outputs, never edits frozen code."""
import sys,itertools,json,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from run_wpb import initialize,gate_batch
from run_wpa_gate import controlled_payloads,real_payloads
from wpa_core import loaders
def main():
    verify_freeze();write('gate-start.json',dict(utc=now()))
    counts=Counter();pins={};_,bench=loaders()
    try:
        with ProcessPoolExecutor(max_workers=6,initializer=initialize) as pool:
            pending=[]
            for payload in itertools.chain(controlled_payloads(bench),real_payloads(pins)):
                pending.append(pool.submit(gate_batch,payload))
                if len(pending)>=12:
                    counts.update(pending.pop(0).result())
                    if sum(counts[k] for k in ('main','replication','real'))%500==0:print(dict(counts),flush=True)
            while pending:counts.update(pending.pop(0).result())
        assert {k:counts[k] for k in ('main','replication','real')}==dict(main=3600,replication=3600,real=15064)
        assert counts['tracker_execution_errors']==143
        write('reproduction-gate.json',dict(passed=True,counts=dict(counts),pins=pins,completed_utc=now()))
    except BaseException as e:
        write('reproduction-gate-failure.json',dict(passed=False,counts=dict(counts),error=repr(e),traceback=traceback.format_exc()));raise
if __name__=='__main__':main()
