"""WP C immutable input gates, line/character and AST adapter contracts."""
import sys,json,hashlib,bisect,math
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/v11-wpc'
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).parent))
from wpa_core import sha,read,rate

def now():return datetime.now(timezone.utc).isoformat()
def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
def verify_freeze():
    c=read(OUT/'protocol-freeze.json')
    protocol=(ROOT/'review/V11-PROTOCOL-C.md').read_bytes()
    if c['protocol_sha256']!=hashlib.sha256(protocol).hexdigest():
        amendment=read(OUT/'c6-protocol-freeze.json')['data']
        n=amendment['original_bytes']
        assert c['protocol_sha256']==amendment['original_sha256']==hashlib.sha256(protocol[:n]).hexdigest(),'C1-C5 segment drift'
        assert amendment['amendment_sha256']==hashlib.sha256(protocol[n:]).hexdigest(),'C6 amendment drift'
        assert amendment['combined_sha256']==hashlib.sha256(protocol).hexdigest(),'combined C protocol drift'
    b=read(ROOT/'evidence/v11-wpb1/protocol-freeze.json')['data']
    assert b['protocol_sha256']==sha(ROOT/'review/V11-PROTOCOL-B.md'),'B protocol drift'
    for p,h in b['code_sha256'].items():assert sha(ROOT/p)==h,('B frozen code drift',p)
    return c
def write(name,data,inputs=()):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    inputs=list(inputs)+[OUT/'protocol-freeze.json',ROOT/'review/V11-PROTOCOL-C.md',ROOT/'evidence/v11-wpb1/protocol-freeze.json']
    code=list(Path(__file__).parent.glob('*wpc*'))+[Path(__file__).with_name('WpcGumTree.java')]
    hashes={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in inputs+code if p.is_file()}
    snapshots=OUT/'code-snapshots';snapshots.mkdir(exist_ok=True)
    for source in code:
        if source.is_file():
            target=snapshots/(sha(source)+'-'+source.name)
            if not target.exists():
                try:target.open('xb').write(source.read_bytes())
                except FileExistsError:pass
    with p.open('x',encoding='utf-8') as f:json.dump(dict(provenance=dict(utc=now(),python=sys.version,executable=sys.executable,input_sha256=hashes),data=data),f,separators=(',',':'))
def failed(error):return dict(label='execution_error',placement=None,range=None,recheck=True,error=str(error))
def removed():return dict(label='removed',placement=None,range=None,recheck=True)
def region_lines(r):
    if r is None:return None
    s,sc,e,ec=r
    return [s,e-1 if ec==0 else e]
def line_region(text,s,e):
    lines=text.splitlines()
    if not (1<=s<=e<=len(lines)):raise ValueError(('invalid line range',s,e,len(lines)))
    return [s,1,e,len(lines[e-1])]
def region_offsets(text,r):
    lines=text.splitlines(keepends=True)
    s,sc,e,ec=r
    return sum(map(len,lines[:s-1]))+sc-1,sum(map(len,lines[:e-1]))+ec
def region_text(text,r):
    if r is None:return ''
    s,e=region_offsets(text,r);return text[s:e]
def upstream_file_agrees(truth_file,truth_region,output):
    if output['label']=='execution_error':return False
    native=output.get('native')
    predicted_file=native[0].get('target_file') if native else (output['placement'][0] if output.get('placement') else None)
    return predicted_file==truth_file or (predicted_file is None and truth_region is None)
def character_score(text,truth,pred,same_file,upstream=False):
    z=dict(exact=0,overlap=0,partial=0,distance=None,precision=0.,recall=0.,f1=0.)
    if not same_file:return z
    if truth==pred:return dict(z,exact=1,overlap=1,precision=1.,recall=1.,f1=1.)
    if truth is None or pred is None:return z
    a,b=region_offsets(text,truth);x,y=region_offsets(text,pred)
    if upstream:
        # Exactly retain the artifact's +1 absolute indexing and clamped prediction.
        a+=1;b+=1;x=max(1,x+1);y+=1
    overlap=max(0,min(b,y)-max(a,x))
    if not overlap:return z
    if upstream:
        # Artifact uses longest common substring after checking positional overlap.
        from difflib import SequenceMatcher
        u,v=text[a:b],text[x:y]
        overlap=SequenceMatcher(None,u,v,autojunk=False).find_longest_match().size
        if not overlap:raise ValueError('upstream overlap assertion would fail')
    p=overlap/max(1,y-x);r=overlap/max(1,b-a)
    f=2*p*r/(p+r) if p+r else 0.
    if upstream:p,r,f=round(p,3),round(r,3),round(f,3)
    return dict(z,overlap=1,partial=1,distance=abs(a-x)+abs(b-y),precision=p,recall=r,f1=f)
def utf16_line(text,pos):
    # GumTree generators expose Java UTF-16 source offsets.
    return text.encode('utf-16-le')[:2*max(0,pos)].count(b'\n\x00')+1
def gumtree_output(data,path,old,new,start,end):
    if 'error' in data:return failed(data['error'])
    os={n[0]:n for n in data['old']};ns={n[0]:n for n in data['new']}
    def extent(n,text):return (n[4],n[5]) if len(n)>=6 else (utf16_line(text,n[2]),utf16_line(text,max(n[2],n[2]+n[3]-1)))
    selected={i for i,n in os.items() if n[3]>0 and start<=extent(n,old)[0] and extent(n,old)[1]<=end}
    if not selected:
        covering=[n for n in os.values() if n[3]>0 and extent(n,old)[0]<=start and extent(n,old)[1]>=end]
        if covering:selected={min(covering,key=lambda n:(n[3],n[0]))[0]}
    matches=dict(data['matches']);mapped={matches[i] for i in selected if i in matches}
    if not mapped:return removed()
    def descendant(nodes,child,ancestor):
        while child in nodes:
            if child==ancestor:return True
            child=nodes[child][1]
        return False
    changed=False
    for name,side,i in data['actions']:
        nodes,roots=(os,selected) if side==0 else (ns,mapped)
        if any(descendant(nodes,i,r) for r in roots):changed=True
        # A moved ancestor changes a descendant's context; tree deletions cover all.
        if name.startswith(('move','delete-tree','insert-tree')) and any(descendant(nodes,r,i) for r in roots):changed=True
    s=min(extent(ns[i],new)[0] for i in mapped);e=max(extent(ns[i],new)[1] for i in mapped)
    label='changed' if changed else 'moved' if s!=start else 'exact'
    return dict(label=label,placement=[path,s],range=[path,s,e],recheck=changed,selected_nodes=len(selected),mapped_nodes=len(mapped))
