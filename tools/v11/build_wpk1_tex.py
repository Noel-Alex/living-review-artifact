"""Build WP K1 macros and stand-alone floats from the latest saved K1 summary."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
EV=ROOT/'evidence/v12-wpk1'; GEN=ROOT/'v11-professor-revision/generated'
SUMMARY=sorted(EV.glob('summary-*.json'))[-1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def pct(x):return '--' if x is None or x.get('rate') is None else f"{100*x['rate']:.1f}"
def num(x):return f'{int(x):,}'
def word(x):
 digits={'0':'Zero','1':'One','2':'Two','3':'Three','4':'Four','5':'Five','6':'Six','7':'Seven','8':'Eight','9':'Nine'}
 return ''.join(''.join(digits[c] for c in token) if token[0].isdigit() else token.capitalize() for token in re.findall('[A-Za-z]+|[0-9]+',x))
def cell(x):return '--' if x is None else f'{100*x:.2f}'
d=read(SUMMARY); data=d.get('data',d); macros=[]
pop_alias={'fresh':'Fresh','fresh:duplicates':'FreshDuplicates','fresh:indentation':'FreshIndentation','fresh:short':'FreshShort','controlled:replication':'Controlled','real':'Real','students':'Students','external:human-AB':'Human','fresh:compound:k=4':'FreshCompoundKFour'}
for name in data['populations']:
 if name.startswith('wpj:'):
  _,model,pop=name.split(':',2); pop_alias[name]=word(model)+word(pop)
method_alias={'t0.85-deployed':'Deployed','deployed_native':'DeployedNative','t0.85-IG+AGi+VW':'CascadeGuard','t0.55-IG+AGi+VW':'CascadeGuardLow','codemapper+quote':'CodeMapperQuote','codemapper+IG+AG':'CodeMapperIGAG','codemapper+IG+AGi':'CodeMapperIGAGi','tracker+quote':'TrackerQuote','tracker+IG+AGi':'TrackerIGAGi','llm+verdict':'ModelVerdict','llm+quote':'ModelQuote','llm+IG+AGi':'ModelIGAGi','nemotron+verdict':'NemotronVerdict','nemotron+quote':'NemotronQuote','nemotron+IG+AGi':'NemotronIGAGi'}
metric_alias={'placement':'Placement','missed':'Missed','silent':'Silent','misdirected':'Misdirected','lost':'Lost','unnecessary':'Unnecessary','gone_kept':'GoneKept','correct':'Correct'}
for pop,pn in pop_alias.items():
 rec=data['populations'].get(pop)
 if not rec:continue
 for meth,mr in rec['methods'].items():
  mn=method_alias.get(meth,word(meth))
  for met,mv in metric_alias.items():
   r=mr[met]
   base='wq'+pn+mn+mv
   assert base.isalpha(),base
   macros += [(base,pct(r)),(base+'K',num(r['k'])),(base+'N',num(r['n']))]
(GEN/'numbers-wpk1.tex').write_text('% Generated from the latest K1 summary.\n'+''.join(f'\\newcommand{{\\{a}}}{{{b}}}\n' for a,b in macros),encoding='utf-8')
assert len({name for name,_ in macros})==len(macros), 'duplicate macro name after alphabetic encoding'

def tabfloat(caption,label,headers,rows,note,wide=True):
 env='table*' if wide else 'table'; cols='l'+'r'*(len(headers)-1)
 out=[f'\\begin{{{env}}}[t]',f'\\caption{{{caption}}}\\label{{{label}}}','\\centering\\scriptsize','\\setlength{\\tabcolsep}{3pt}']
 if wide: out.append('\\resizebox{\\textwidth}{!}{%')
 out += [f'\\begin{{tabular}}{{@{{}}{cols}@{{}}}}','\\toprule',' & '.join(headers)+r' \\','\\midrule']
 # Escape raw underscores in saved labels/outcome names for text-mode cells.
 out += [' & '.join(re.sub(r'(?<!\\)_',r'\\_',str(x)) for x in row)+r' \\' for row in rows]
 out += ['\\bottomrule','\\end{tabular}']
 if wide: out.append('}')
 out += [f'\\tablenote{{}}{{{note}}}',f'\\end{{{env}}}','']
 return '\n'.join(out)
def tabfloats(caption,label,headers,rows,note,limit=24,wide=True):
 if len(rows)<=limit:return tabfloat(caption,label,headers,rows,note,wide)
 return '\n'.join(tabfloat(f'{caption}, Part {i}',f'{label}-part{i}',headers,rows[start:start+limit],note,wide) for i,start in enumerate(range(0,len(rows),limit),1))
# Six-outcome table: requested configurations only, wherever saved.
req={'t0.85-deployed':'Cascade, deployed','t0.85-IG+AGi+VW':'Cascade, IG+AGi+VW','t0.55-IG+AGi+VW':'Cascade, IG+AGi+VW, theta 0.55','codemapper+quote':'CodeMapper, quote','codemapper+IG+AG':'CodeMapper, IG+AG','codemapper+IG+AGi':'CodeMapper, IG+AGi','tracker+quote':'Tracker, quote','tracker+IG+AGi':'Tracker, IG+AGi','llm+verdict':'Beam, own verdict','llm+quote':'Beam, quote','llm+IG+AGi':'Beam, IG+AGi','nemotron+verdict':'Nemotron, own verdict','nemotron+quote':'Nemotron, quote','nemotron+IG+AGi':'Nemotron, IG+AGi'}
rows=[]
for pop,p in data['populations'].items():
 label=pop_alias.get(pop,pop)
 for meth,methlabel in req.items():
  if meth not in p['methods']:continue
  x=p['methods'][meth]
  vals=[]
  for met in ('placement','missed','silent','misdirected','lost','unnecessary'):
   z=x[met]; vals.append(f"{pct(z)} ({num(z['k'])}/{num(z['n'])})")
  rows.append([label,methlabel,*vals])
six=tabfloats(r'Six Outcomes Across Saved Populations (\%)','tab:wpk1-sixoutcome',['Population','Configuration','Place','Miss','Silent','Misdirect','Lost','Extra'],rows,'Each cell shows rate (events/its outcome-specific denominator). Human-annotated and language-model cells use only the WP J populations recorded for that configuration. All results are retrospective and descriptive.',limit=24)
chainrows=[]
for name in ('v0.85-off','v0.85-alli','v0.55-alli','cm-direct','cm-direct-gi'):
 c=data['chains']['wp_i_agi']['prefixes']['10'][name]['counts']
 chainrows.append([name,num(c['correct']),num(c['wrong']),num(c['lost']),num(c['missed_last']),num(c['wrong_silent_last'])])
six+='\n'+tabfloat('Ten-Hop Chain Outcomes','tab:wpk1-chains-h10',['Base','Correct','Wrong','Lost','Missed-Last','Silent-Wrong-Last'],chainrows,'Each cell is a count among N=4,000 chain rows. Missed-last and silent-wrong-last are endpoint request outcomes. Retrospective and descriptive.')
(GEN/'table-sixoutcome.tex').write_text(six,encoding='utf-8')
# Policy minimizers and LOPO summary.
settings=[f'w{w}_m{m}' for w in (1,3,10,30) for m in (1,3)]
rows=[]
for pop,p in data['policy'].items():
 vals=[]
 for key in settings:
  v=p['minimizers'][key]; label=(v['policy'] or '--').replace('_',r'\_')
  vals.append('\\shortstack{'+label+'\\\\C='+f"{v['cost']:.3f}"+'}' if v['cost'] is not None else '--')
 rows.append([pop.replace('_',r'\_'),*vals])
policy=tabfloat('Minimum-Cost Policy by Population and Weights','tab:wpk1-policy',['Population',*[x.replace('_',r'\_') for x in settings]],rows,'Each cell gives the minimizing configuration and its C per carried target. The complete Pareto sets and all six outcomes are in the K1 JSON. Ties follow the frozen protocol. C is descriptive.' )
foldrows=[]
for split in ('real','students'):
 for f in data['selection'][split]['folds']:
  v=f['weights']['w3_m3']; fixed=v['regret_fixed']
  foldrows.append([split,str(f['held_out']).replace('_',r'\_'),v['selected'].replace('_',r'\_'),f"{v['held_cost']:.3f}",f"{v['regret_oracle']:.3f}",f"{fixed.get('t0.85-deployed',0):.3f}",f"{fixed.get('codemapper+IG+AGi',0):.3f}"])
fold=tabfloat('Leave-One-Project-Out Selection at w=3 and m=3','tab:wpk1-lopo',['Source','Held-out group','Selected','C','Oracle regret','Deployed regret','CodeMapper+IG+AGi regret'],foldrows,'All six held-out outcomes for every weight pair are in the K1 JSON. Negative fixed-policy regret means the selected policy had lower held-out cost. Real history has nine project folds; students have twenty repository folds. Retrospective and descriptive.' )
(GEN/'table-policy.tex').write_text(policy+'\n'+fold,encoding='utf-8')
# Identity floor table
rows=[]
for base,x in data['identity_floor']['replay'].items():
 for floor,v in x.get('floors',{}).items():
  c=v.get('counts',v); n=v.get('n',c.get('correct',0)+c.get('wrong',0)+c.get('lost',0))
  rows.append([base,floor,num(n),num(c.get('correct',0)),num(c.get('wrong',0)),num(c.get('lost',0)),num(c.get('missed_last',0)),num(c.get('silent_wrong',0))])
(GEN/'table-idfloor.tex').write_text(tabfloats('Identity-Floor Sensitivity at Ten Hops','tab:wpk1-idfloor',['Base','Floor','N','Correct','Wrong','Lost','Missed-last','Silent-wrong'],rows,'Counts are endpoint outcomes at h=10. Cascade traces replay from saved identity traces; CodeMapper replay is limited to floors at or above 0.50. Gate mismatches and ratio distributions are recorded in the summary.',limit=24),encoding='utf-8')
# Strata table (span bins, required methods and outcomes)
rows=[]
for pop in ('real','students','fresh'):
 rec=data['strata'][pop]
 for b,entry in rec.get('anchor_span',{}).items():
  for meth in ('t0.85-deployed','t0.85-IG+AGi+VW','codemapper+quote','codemapper+IG+AG','codemapper+IG+AGi'):
   x=entry['methods'][meth]
   for met in ('missed','silent','misdirected','unnecessary'):
    z=x[met]; rows.append([pop,b,meth,met,f"{pct(z)} ({num(z['k'])}/{num(z['n'])})"])
 for key,counts in rec.get('cascade_tier_guard_outcomes',{}).items():
  for outcome in ('missed','wrong_silent','wrong_with_recheck','false_recheck','lost'):
   den=counts.get({'missed':'changed','false_recheck':'preserved','lost':'survivors'}.get(outcome,'n'),counts.get('n',0))
   rows.append([pop,key,'Cascade deployed',outcome,f"{num(counts.get(outcome,0))}/{num(den)}"])
(GEN/'table-strata.tex').write_text(tabfloats('Anchor-Length and Confidence-by-Guard Strata','tab:wpk1-strata',['Population','Stratum','Configuration','Outcome','Rate (k/n)'],rows,'Span bins are 1, 2-3, 4-9, and at least 10 lines. The summary also contains cascade-tier by guard-fire outcome cross-tabs for real, student, and fresh rows. CodeMapper has no stored confidence field; old-copy strata and multi-anchor issue outcomes are unavailable in the saved row schema.',limit=24),encoding='utf-8')
# TikZ frontier: four primary populations, all nondominated candidates.
front=data['policy']; picks=['real','students','external:human-AB','fresh']; colors=['blue','orange','green!60!black','red']
out=[r'\begin{figure*}[t]',r'\centering',r'\begin{tikzpicture}[x=6cm,y=5cm]',r'\draw[->] (0,0) -- (1.03,0) node[right]{Missed + silent per target};',r'\draw[->] (0,0) -- (0,1.03) node[above]{Misdirected per target};',r'\foreach \x/\lab in {0/0,.25/.25,.5/.50,.75/.75,1/1} {\draw[gray!25] (\x,0)--(\x,1);\node[below] at (\x,0){\scriptsize\lab};}',r'\foreach \y/\lab in {0/0,.25/.25,.5/.50,.75/.75,1/1} {\draw[gray!25] (0,\y)--(1,\y);\node[left] at (0,\y){\scriptsize\lab};}']
legend=[]
for pop,color in zip(picks,colors):
 if pop not in front:continue
 vec=front[pop]['frontier']['vectors']; pareto=front[pop]['frontier']['pareto']
 for m in pareto:
  x,y=vec[m][:2]; out.append(f'\\fill[{color}] ({x:.5f},{y:.5f}) circle (1.2pt);')
 legend.append(f'\\draw[{color},fill={color}] (0,0) circle (1.2pt);\\node[right] at (0.02,{0.88-0.07*len(legend):.2f}){{\\scriptsize {pop.replace("_"," ")}}};')
out += legend+[r'\end{tikzpicture}',r'\caption{Deployment-Policy Pareto Frontiers on Four Saved Populations}',r'\label{fig:wpk1-frontier}',r'\footnotesize Each dot is a nondominated saved policy; the plotted axes are missed-plus-silent and misdirected requests per target. Lost and unnecessary re-checks remain the other two Pareto dimensions in the JSON summary.',r'\end{figure*}','']
(GEN/'figure-frontier.tex').write_text('\n'.join(out),encoding='utf-8')
prov={'summary':str(SUMMARY.relative_to(ROOT)).replace('\\','/'),'summary_sha256':sha(SUMMARY),'builder':str(Path(__file__).resolve().relative_to(ROOT)).replace('\\','/'),'builder_sha256':sha(__file__),'protocol_sha256':sha(ROOT/'review/V12-PROTOCOL-K1.md'),'freeze_sha256':sha(EV/'protocol-freeze.json'),'outputs':{p.name:sha(p) for p in [GEN/'numbers-wpk1.tex',GEN/'table-sixoutcome.tex',GEN/'table-policy.tex',GEN/'table-idfloor.tex',GEN/'table-strata.tex',GEN/'figure-frontier.tex']}}
(GEN/'numbers-wpk1-provenance.json').write_text(json.dumps(prov,indent=2)+'\n',encoding='utf-8')
print('built WP K1 macros and five floats from',SUMMARY.name)
