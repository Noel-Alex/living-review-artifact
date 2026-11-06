"""Frozen variant calls behind a killable 60-second boundary; no code changes."""
import sys,json,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
from wpb_variants import all_outputs
from run_wpb import initialize,basic,tracker
from wpa_core import loaders
initialize();matcher,_=loaders()
for line in sys.stdin:
    try:
        verify_freeze();q=json.loads(line)
        if q.get('mode')=='basic':
            t=q['trial'];name=q['method']
            if name=='cascade':
                matcher.FUZZY_CODE=.85;o=matcher.relocate_code(t['anchor'],t['version'],'\n'.join(t['old_lines'])+'\n')
                result={'output':dict(label=o['match'],placement=None if o['match']=='removed' else [o['path'],o['line_start']],range=None if o['match']=='removed' else [o['path'],o['line_start'],o['line_end']],recheck=o['match'] in ('changed','removed'))}
            else:result={'output':tracker(t) if name=='tracker_adapter' else basic(t,name)}
        else:result={'outputs':all_outputs(q['trial'],q['old_files'])}
    except BaseException as e:result=dict(error=repr(e),traceback=traceback.format_exc())
    print(json.dumps(result),flush=True)
