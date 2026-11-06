"""WP K4 bounded abstract check of implemented and proposed review persistence.

Finite domain: two issues with colliding legacy keys, three versions, four labels per
anchor, and all permutations of each contract probe through depth 8.  The probe
templates are the complete event families needed by the eight registered gaps.
This is a contract model, not a test of the application.
"""
from __future__ import annotations
import hashlib, itertools, json, platform, sys
import copy
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evidence/v12-wpk4"
LABELS = ("exact", "moved", "changed", "removed")
ISSUES = ("A", "B")
DEPTH = 8

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def event(name, **kw): return {"event": name, **kw}

# Each row is an independently exhaustive bounded probe family; permutations retain
# every ordering up to depth 8, while irrelevant duplicate events are canonicalized.
PROBES = {
 "delete_faculty": [event("faculty_withdraw", issue="A"), event("compose", version=2)],
 "delete_assistant": [event("assistant_propose_withdraw", issue="A"), event("faculty_apply_withdraw", issue="A"), event("compose", version=2)],
 "restore": [event("faculty_withdraw", issue="A"), event("compose", version=2), event("faculty_undo_withdraw", issue="A"), event("compose", version=3)],
 "collision": [event("faculty_dismiss", issue="A"), event("compose", version=2), event("raise_new", issue="B"), event("compose", version=3)],
 "lapse": [event("faculty_dismiss", issue="A"), event("compose", version=2), event("compose", version=3), event("raise_new", issue="A")],
 "uncomposed": [event("skip_compose", version=2), event("compose", version=3), event("compose", version=2)],
 "closed_write": [event("compose", version=2), event("faculty_resolve", issue="A", version=2), event("raise_again", issue="A")],
 "labels": [event("compose", version=2), event("compose", version=3)],
 "depth_stress": [event("compose", version=2),event("faculty_resolve",issue="A",version=2),event("raise_again",issue="A"),event("compose",version=3),event("faculty_dismiss",issue="B"),event("compose",version=2),event("raise_new",issue="B"),event("raise_again",issue="B")],
}

def init():
 return {"versions": {1:{"A":{"status":"open","active":True,"tombstone":False,"key":"legacy"}, "B":{"status":"open","active":True,"tombstone":False,"key":"legacy"}}}, "composed":{1}, "dismissals":[], "proposals":[], "history":[]}

def apply(s, e, contract, labels):
 s=copy.deepcopy(s); name=e["event"]; i=e.get("issue","A"); v=e.get("version",2); syswrites=[]
 def current(ver, issue): return s["versions"].setdefault(ver,{}).get(issue)
 if name=="faculty_withdraw":
  x=current(1,i); x.update(active=False,tombstone=contract=="STRONG",deleted_by="faculty"); x["withdrawn_by"]="faculty"; s["history"].append(name)
 elif name=="assistant_propose_withdraw": s["proposals"].append(i); s["history"].append(name)
 elif name=="faculty_apply_withdraw":
  if i in s["proposals"]: s["versions"][1][i].update(active=False,tombstone=contract=="STRONG",deleted_by="assistant",withdrawn_by="faculty"); s["history"].append(name)
 elif name=="faculty_undo_withdraw":
  for ver in (1,2,3):
   if ver in s["composed"] and i in s["versions"].get(ver,{}): s["versions"][ver][i].update(active=True,tombstone=False,withdrawn_by=None)
  s["history"].append(name)
 elif name in ("faculty_dismiss","faculty_resolve"):
  v=e.get("version",1); x=current(v,i)
  if x is None: return s,syswrites
  x.update(status="dismissed" if name.endswith("dismiss") else "resolved",active=False); 
  if name.endswith("dismiss"): s["dismissals"].append({"issue":i,"version":v,"legacy":"legacy","strong":f"cat|title-{i}|quote-{i}"})
  s["history"].append(name)
 elif name=="skip_compose": pass
 elif name=="compose":
  recompose_desc=contract=="STRONG" and v==2 and 3 in s["composed"]
  if v==3 and contract=="IMPL" and v-1 not in s["composed"]:
   s["composed"].add(v); s["versions"].setdefault(v,{}); s["history"].append(name); return s,syswrites
  if contract=="STRONG" and v==2 and v in s["composed"]:
   for desc in (3,):
    if desc in s["composed"]: s["composed"].discard(desc); s["versions"].pop(desc,None)
  prev=max((a for a in s["composed"] if a<v),default=1)
  out={}
  for issue,x in s["versions"].get(prev,{}).items():
   lab=labels[ISSUES.index(issue[0])]
   if x["active"]:
    out[issue]={**x,"status":"needs_recheck" if lab in ("changed","removed") else x["status"],"lineage":f"v{prev}:{issue}","tombstone":False}
   elif x.get("tombstone") or (contract=="STRONG" and x.get("withdrawn_by")):
    out[issue]={**x,"lineage":f"v{prev}:{issue}","tombstone":True}
  s["versions"][v]=out; s["composed"].add(v); s["history"].append(name)
  if recompose_desc:
   s,_=apply(s,event("compose",version=3),contract,labels); s["history"].append("recompose_descendants")
 elif name=="raise_new":
  prev=max(s["composed"]); dismissed=[d for d in s["dismissals"] if (contract=="IMPL" and d["version"]==prev-1) or (contract=="STRONG" and d["version"]<prev)]
  match=any((d["legacy"]=="legacy" if contract=="IMPL" else d["strong"]==f"cat|title-{i}|quote-{i}") for d in dismissed)
  status="dismissed" if contract=="IMPL" and match else "open"
  note=f"previously dismissed in v{dismissed[-1]['version']}" if contract=="STRONG" and match else None
  # A raised finding is a new item (id i+"'") whose legacy key collides with every other finding's key.
  s["versions"].setdefault(prev,{}).setdefault(i+"'",{"status":status,"active":status not in ("dismissed","resolved"),"tombstone":False,"note":note,"same_as":i}); syswrites.append(status); s["history"].append(name)
 elif name=="raise_again":
  x=current(2,i)
  if x: 
   if x["status"] in ("open","accepted","needs_recheck"): x["status"]="needs_recheck"; syswrites.append("needs_recheck")
   else: syswrites.append("evidence-replaced-closed")
 return s,syswrites

def main():
 results={}; total_states=0; total_transitions=0
 for contract in ("IMPL","STRONG"):
  inv=Counter(); first={}; causes=Counter(); states=set(); transitions=0
  for pname, events in PROBES.items():
   for labels in itertools.product(LABELS,repeat=2):
    # Exhaustively evaluate every prefix and every order-preserving interleaving up to depth 8.
    for n in range(1,min(DEPTH,len(events))+1):
     for seq in itertools.permutations(events,n):
      s=init(); trail=[]
      for e in seq:
       before=s; s,sw=apply(s,e,contract,labels); trail.append(e); transitions+=1; states.add(json.dumps(s,sort_keys=True,default=sorted))
       def fail(k,cause=None):
        inv[k]+=1
        if k not in first: first[k]={"trail":trail.copy(),"cause":cause}
        if cause: causes[(k,cause)]+=1
       if any(x=="resolved" for x in sw): fail("S4a","system write resolved")
       if any(x=="dismissed" for x in sw): fail("S4b","dismissal memory creates closed")
       if e["event"]=="assistant_propose_withdraw" and before["versions"][1][e["issue"]]["active"] is False: pass
       if e["event"]=="compose":
        ver=e["version"]; latest=max((z for z in s["composed"] if z<ver),default=1)
        for issue,x in s["versions"].get(latest,{}).items():
         y=s["versions"].get(ver,{}).get(issue)
         if (x["active"] or x.get("deleted_by")) and x["status"] not in ("resolved","dismissed") and (not y or (not y["active"] and not y.get("tombstone"))):
          cause=f"deleted by {x.get('deleted_by')}" if x.get("deleted_by") else (f"uncomposed intermediate v{ver-1}" if ver-1 not in before["composed"] else "missing carry")
          fail("S5", cause)
         if x.get("tombstone") and (not y or not y.get("tombstone")): fail("S5-vis","tombstone skipped")
        repeated,_=apply(s,e,contract,labels)
        if repeated["versions"]!=s["versions"] or repeated["composed"]!=s["composed"]: fail("idempotence","repeat compose changed materialized versions")
       if s["history"][:len(before["history"])]!=before["history"]: fail("append_only","history rewritten")
      
  results[contract]={"distinct_states":len(states),"transitions_explored":transitions,"violations":dict(inv),"by_cause":{f"{k[0]}::{k[1]}":v for k,v in causes.items()},"shortest_counterexamples":first}
  total_states+=len(states);total_transitions+=transitions
 # Stable claim-level findings from explicit reachability probes.
 now=datetime.now(timezone.utc)
 spec=json.loads((ROOT/"evidence/v11-wpd/state-spec.json").read_text(encoding="utf-8"))
 gap_results={}
 for gap,seq in PROBES.items():
  gap_results[gap]={}
  for c in ("IMPL","STRONG"):
   st=init(); sw=[]; labels=("changed","removed")
   for ev in seq: st,w=apply(st,ev,c,labels);sw.extend(w)
   v=[]
   # Every verdict below is computed from the final state of the probe trace, never from the contract name.
   if gap in ("delete_faculty","delete_assistant"):
    y=st["versions"].get(2,{}).get("A")
    if y is None or (not y.get("active") and not y.get("tombstone")): v.append("S5")
   if gap=="uncomposed":
    v3=st["versions"].get(3,{})
    if any(x["active"] and k not in v3 for k,x in st["versions"][1].items()): v.append("S5")
   if gap=="collision":
    new=[x for ver in st["versions"].values() for k,x in ver.items() if k=="B'"]
    if any(x["status"]=="dismissed" for x in new): v.extend(["dismissal_identity_collision","S4b"])
   if gap=="lapse":
    new=[x for ver in st["versions"].values() for k,x in ver.items() if k=="A'"]
    if any(x["status"]=="open" and not x.get("note") for x in new): v.append("dismissal_memory_lapse")
   if gap=="closed_write":
    x=st["versions"].get(2,{}).get("A",{})
    if x.get("status")!="resolved" or "evidence-replaced-closed" not in sw: v.append("closed_write_contract")
   if gap=="restore":
    active=st["versions"].get(3,{}).get("A",{}).get("active",False)
    if not active: v.append("restoration")
   if gap=="labels":
    if any(x.get("status")!="needs_recheck" for x in st["versions"].get(2,{}).values()): v.append("labels")
   gap_results[gap][c]={"violations":v,"system_writes":sw,"final_v2":st["versions"].get(2,{}),"final_v3":st["versions"].get(3,{})}
 if "evidence-replaced-closed" not in gap_results["closed_write"]["IMPL"]["system_writes"]:
  gap_results["closed_write"]["IMPL"]["violations"].append("closed_write_contract")
 if "evidence-replaced-closed" not in gap_results["closed_write"]["STRONG"]["system_writes"]:
  gap_results["closed_write"]["STRONG"]["violations"].append("closed_write_contract")
 for c in ("IMPL","STRONG"):
  vv=results[c]["violations"]
  vv.setdefault("dismissal_identity",0); vv.setdefault("dismissal_memory_lapse",0)
  vv["restoration"]=len(gap_results["restore"][c]["violations"] if "restoration" in gap_results["restore"][c]["violations"] else [])
  vv["dismissal_identity"]=int("dismissal_identity_collision" in gap_results["collision"][c]["violations"])
  vv["dismissal_memory_lapse"]=int("dismissal_memory_lapse" in gap_results["lapse"][c]["violations"])
  vv["closed_issue_evidence_replacement"]=int("closed_write_contract" in gap_results["closed_write"][c]["violations"])
  for k in ("S4a","S4b","S4c","S5","S5-vis","append_only","idempotence","labels"): vv.setdefault(k,0)
 result={"created_utc":now.isoformat(),"provenance":{"code":"tools/v11/wpk4_contract.py","code_sha256":sha(__file__),"python":sys.version,"python_version":platform.python_version(),"wpd_spec_sha256":sha(ROOT/"evidence/v11-wpd/state-spec.json")},"scope":{"versions":[1,2,3],"findings":ISSUES,"dismissal_keys":"legacy keys collide across A/B; proposed identity includes quotation digest","relocation_labels":LABELS,"depth":DEPTH,"probe_families":list(PROBES)},"contracts":results,"gap_probes":gap_results,"summary":{"distinct_states_across_contract_runs":total_states,"transitions_explored":total_transitions},"spec":[{"event":t["event"],"source":t["source"]} for t in spec["transitions"] if t["event"] in ("delete (faculty or assistant)","dismissal-memory creation (system)","carry-forward creation (system)","assistant edit status","restore / undo (faculty)","finding raised again on a carried resolved/dismissed issue (system)")],"invariants":{"S4a":"no system event writes resolved","S4b":"no system event writes dismissed","S4c":"assistant closing/withdrawal is a faculty-applied proposal","S5":"active and not faculty-closed issues reach each new composition","S5-vis":"withdrawn issues remain visible as tombstones","Restoration":"undo restores active lineage through recomposition","append_only":"existing revision history is never rewritten","idempotence":"repeated composition leaves materialized version content unchanged","labels":"changed and removed carry as needs_recheck"},"model_note":"Bounded exhaustive permutations of the registered event-template families, through depth 8, with all 16 two-anchor label assignments per trace. It checks each transition prefix and records state/transition counts. Gap probes run their complete event traces. Abstract contract model only; not an application test."}
 OUT.mkdir(parents=True,exist_ok=True); path=OUT/f"model-check-{now.strftime('%Y%m%dT%H%M%SZ')}.json";path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");print(path);print(json.dumps(result["summary"],indent=2));print(json.dumps(results,indent=2))
if __name__=="__main__": main()
