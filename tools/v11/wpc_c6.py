"""Registered C6 fixed-location guard transfer; frozen B1 code is read only."""
import sys,copy,hashlib
from pathlib import Path,PurePosixPath
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
from wpb_variants import profile,MATCHER
from wpa_core import runs

LAYERS=('quote','IG','AG','IG+AG')
MATCHERS=('gumtree','codemapper','tracker','hybrid')

def gate():
    verify_freeze();f=read(OUT/'c6-protocol-freeze.json')['data']
    assert read(OUT/'c15-completion.json')['data']['complete']
    assert f['c15_complete_sha256']==sha(OUT/'c15-completion.json')
    return f

def strict_tracker(t,saved):
    path=t['anchor']['path']
    if path not in t['version']:return removed()
    if saved['label']=='execution_error' or saved['placement'] is None or saved['placement'][0]==path:return saved
    raise ValueError('rename-adjusted tracker result requires fresh same-path call')

def hybrid(tracked,deployed):
    if tracked['label']=='execution_error' or tracked['placement'] is not None:return tracked
    if deployed.get('tier')=='cross_exact':return dict(deployed,hybrid_fallback=True)
    return tracked

def safety_family(t,old_files,output):
    gate();a=t['anchor'];version=t['version'];at=output['placement']
    if output['label']=='execution_error':return {k:copy.deepcopy(output) for k in LAYERS}
    if at is None:return {k:dict(output,label='removed',recheck=True,reasons=[]) for k in LAYERS}
    candidate,start=at[0],at[1]-1
    if candidate not in version:return {k:failed('returned file unavailable to C6 safety layer') for k in LAYERS}
    text=version[candidate][1];lines=text.splitlines()
    end=output['range'][2] if output.get('range') else min(start+a['line_end']-a['line_start']+1,len(lines))
    if not 0<=start<end<=len(lines):return {k:failed('invalid returned safety window') for k in LAYERS}
    window='\n'.join(lines[start:end]);wanted=tuple(x.strip() for x in a['quotation'].splitlines() if x.strip())
    exact=wanted==tuple(x.strip() for x in window.splitlines() if x.strip())
    path,origin=a['path'],a['line_start']-1
    expected=MATCHER.expected_start('\n'.join(t['old_lines'])+'\n',version[path][1].splitlines(),origin) if path in version else origin
    base='exact' if candidate==path and start==origin else 'moved'
    result={}
    for layer in LAYERS:
        label=base if exact else 'changed';recheck=not exact;reasons=[];audit=dict(normalized_equal=exact,expected_zero_based=expected,safety_window=[candidate,start+1,end])
        if exact and 'AG' in layer and (candidate!=path or start!=expected):
            old=old_files.get(candidate)
            old_count=len(runs(old,wanted)) if old is not None and wanted else 0
            new_count=len(runs(text,wanted)) if wanted else 0
            audit.update(old_candidate_available=old is not None,old_count=old_count,new_count=new_count)
            if old is not None and new_count<=old_count:
                label,recheck='moved',True;reasons.append('pre-existing-copy')
        if exact and 'IG' in layer:
            before=profile(a['quotation']);after=profile(window)
            python=PurePosixPath(path).suffix.lower() in ('.py','.pyw')
            if (before!=after if python else before[1]!=after[1]):
                label,recheck='changed',True;reasons.append('layout')
        result[layer]=dict(output,label=label,recheck=recheck,reasons=reasons,c6_audit=audit)
        if not output.get('range'):result[layer]['safety_projection']='original height clipped at EOF; native range remains absent'
    return result

def attach(r,t,old_files,bases):
    result={}
    for name,o in bases.items():
        for layer,v in safety_family(t,old_files,o).items():result[name+'+'+layer]=v
    return dict(r,methods={**r['methods'],**result},c6_bases=bases)
