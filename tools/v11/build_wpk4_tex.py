"""Generate WP K4 macros and gap table from model evidence."""
from __future__ import annotations
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; E=ROOT/"evidence/v12-wpk4"; G=ROOT/"v11-professor-revision/generated"
def esc(s):
 return str(s).replace("\\",r"\textbackslash{}").replace("&",r"\&").replace("%",r"\%").replace("_",r"\_").replace("#",r"\#")
def main():
 p=max(E.glob("model-check-*.json"),key=lambda x:x.stat().st_mtime); d=json.loads(p.read_text(encoding="utf-8")); i=d["contracts"]["IMPL"]; s=d["contracts"]["STRONG"]
 gaps=[("Deletion (faculty)","Deleted item excluded from carry","Faculty withdrawal leaves visible tombstone","S5, S5-vis"),("Deletion (assistant)","Assistant deletion stops carry","Assistant proposal; faculty applies withdrawal","S4c, S5, S5-vis"),("Restoration across versions","Undo restores prior snapshot only","Recompose descendants after undo","Restoration, S5"),("Dismissal key collision","Category plus first paragraph key conflates anchors","Category + normalized title + reviewed-quotation digest","Dismissal identity, S4b"),("Dismissal lapse after absent version","Only immediately previous version is checked","Compare dismissals across all earlier versions","Dismissal memory, S5"),("Dismissed finding created closed by system","Matching new finding is created dismissed","Create open with prior-dismissal annotation","S4b"),("Uncomposed intermediate version","v3 reads only v2 and skips v1 issues","Compose latest ancestor; later v2 recomposes descendants","S5"),("System write on closed issue (evidence replaced)","System replaces evidence and retains closed state","Evidence replacement never writes a closed state","S4a, S4b")]
 rows=[]
 probe_keys=("delete_faculty","delete_assistant","restore","collision","lapse","collision","uncomposed","closed_write")
 for n,(name,impl,prop,inv) in enumerate(gaps):
  iv=d["gap_probes"][probe_keys[n]]["IMPL"]["violations"]; sv=d["gap_probes"][probe_keys[n]]["STRONG"]["violations"]
  if n==5: iv=[x for x in iv if x=="S4b"]
  rows.append((name,impl,prop,inv,str(len(iv)),str(len(sv))))
 def texrow(r): return " & ".join(esc(x) for x in r)+r" \\"
 G.mkdir(parents=True,exist_ok=True)
 macros={"wcDepth":str(d["scope"]["depth"]),"wcStatesImpl":str(i["distinct_states"]),"wcStatesStrong":str(s["distinct_states"]),"wcTransitionsImpl":str(i["transitions_explored"]),"wcTransitionsStrong":str(s["transitions_explored"]),"wcImplViolations":str(sum(i["violations"].values())),"wcStrongViolations":str(sum(s["violations"].values())),"wcGapRows":str(len(rows))}
 assert all(re.fullmatch(r"\\wc[A-Za-z]+","\\"+k) for k in macros)
 (G/"numbers-wpk4.tex").write_text("% Generated from evidence/v12-wpk4; do not edit.\n"+"\n".join("\\newcommand{\\"+k+"}{"+v+"}" for k,v in macros.items())+"\n",encoding="utf-8")
 table=("% Generated from evidence/v12-wpk4; do not edit.\n\\begin{table*}[t]\n\\caption{Implemented and Proposed Review-Persistence Contracts}\\label{tab:contract}\n\\centering\\scriptsize\\setlength{\\tabcolsep}{2pt}\n\\begin{tabular}{@{}p{.16\\textwidth}p{.27\\textwidth}p{.31\\textwidth}p{.11\\textwidth}>{\\raggedleft\\arraybackslash}p{.045\\textwidth}>{\\raggedleft\\arraybackslash}p{.045\\textwidth}@{}}\\toprule\nGap & Implemented & Proposed rule & Invariant & Impl. & Prop. \\\\ \\midrule\n"+"\n".join(texrow(r) for r in rows)+"\n\\bottomrule\n\\end{tabular}\n\\end{table*}\n")
 (G/"table-contract.tex").write_text(table,encoding="utf-8")
 print(json.dumps({"model":p.name,"macros":macros,"table_rows":len(rows)},indent=2))
if __name__=="__main__": main()
