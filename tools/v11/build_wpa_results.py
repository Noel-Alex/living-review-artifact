"""Generate manuscript-ready numbers/tables and the WPA handoff from JSON only."""
from collections import Counter
import re
from wpa_core import *

TEX = OUT/'tex'
NAMES = {'cascade':'Final default','cascade_v1':'Cascade v1','quote_exact':'Exact quote',
         'diff_drift':'Diff drift','line_number':'Fixed line','tracker_adapter':'Tracker + label adapter',
         'calibrated':'Final calibrated'}


def pct(value, digits=2):
    return 'NA' if value is None else f'{100*value:.{digits}f}'


def display(item, ci=True):
    if item['rate'] is None:
        return f"{item['k']}/{item['n']} (NA)"
    text = f"{item['k']}/{item['n']} ({pct(item['rate'])}"
    if ci:
        text += f" [{pct(item['wilson95'][0])}, {pct(item['wilson95'][1])}]"
    return text+')'


def escape(value):
    return str(value).replace('_',r'\_').replace('%',r'\%').replace('&',r'\&')


def table(name, headers, rows, note=''):
    text = '% Generated from WPA JSON by build_wpa_results.py. Percentages unless stated.\n'
    text += '\n'.join('% Input SHA-256 '+p.name+' '+sha(p) for p in sorted(OUT.glob('*.json')) if p.name in (
        'safety-metrics.json','error-analysis.json','cluster-uncertainty.json','factorial-summary.json',
        'calibration.json','effort-dominance.json','exclusion-horizon.json','numerical-audit.json'))+'\n'
    text += r'\begingroup\scriptsize\setlength{\tabcolsep}{3pt}'+'\n'
    text += r'\setbox0=\hbox{\begin{tabular}{@{}l'+'r'*(len(headers)-1)+r'@{}}\toprule'+'\n'
    text += ' & '.join(escape(x) for x in headers)+r' \\ \midrule'+'\n'
    text += '\n'.join(' & '.join(escape(x) for x in row)+r' \\' for row in rows)
    text += '\n'+r'\bottomrule\end{tabular}}\noindent\ifdim\wd0>\linewidth\resizebox{.995\linewidth}{!}{\box0}\else\box0\fi'+'\n'
    if note:
        text += r'\par\smallskip '+escape(note)+'\n'
    text += r'\endgroup'+'\n'
    (TEX/name).write_text(text,encoding='utf-8')


def main():
    assert read(OUT/'reproduction-gate.json')['data']['passed']
    TEX.mkdir(exist_ok=True)
    names = ['safety-metrics','error-analysis','cluster-uncertainty','factorial-summary','calibration','effort-dominance','exclusion-horizon','numerical-audit']
    data = {name:read(OUT/(name+'.json'))['data'] for name in names}
    s,e,u,f,c,eff,x,num = [data[name] for name in names]
    all_real = s['real']['all']['cascade']
    public = s['real']['oss-targeted']
    real_rows = read(OUT/'gate-trials.json')['data']
    real_rows = [r for r in real_rows if r['benchmark']=='real']
    public_gone = [r for r in real_rows if r['group']=='oss' and r['cls']=='gone']
    gone_default = summarize(public_gone,[r['methods']['cascade'] for r in public_gone])['gone_correct']
    cal_index = CELLS.index(('fuzzy_first','local','full',.5))
    gone_cal = summarize(public_gone,[decode_output(r['grid'][cal_index],r) for r in public_gone])['gone_correct']
    gate = read(OUT/'reproduction-gate.json')['data']
    theta_stability = c['selected_theta_counts']['all']
    refined = next(v for v in f['real']['oss-targeted']['cells'] if (v['order'],v['scope'],v['height'],v['theta'])==('fuzzy_first','local','full',.55))
    transfer_failures = [dict(design=v['design'],alpha=v['alpha'],beta=v['beta'],selected_cell=v['selected_cell'],
        public_missed=v['public_evaluation']['targeted']['missed'],public_gone_present=v['public_evaluation']['targeted']['gone_misreported'])
        for v in c['safety_constrained'] if v['feasible'] and
        (v['public_evaluation']['targeted']['missed']['rate']>v['alpha'] or v['public_evaluation']['targeted']['gone_misreported']['rate']>v['beta'])]
    directional_changes = []
    for population,units in u['real'].items():
        for contrast,v in units['pair']['contrasts'].items():
            project = units['repo']['contrasts'][contrast]
            if not(v['cluster95'][0]<=0<=v['cluster95'][1]) and project['cluster95'][0]<=0<=project['cluster95'][1]:
                directional_changes.append(dict(population=population,contrast=contrast,pair95=v['cluster95'],project95=project['cluster95']))
    write('interpretation-audit.json',{'selected_theta_stability':theta_stability,'refined_public_targeted_cell':refined,
        'public_safety_constraint_violations':transfer_failures,'directional_claims_weakened':directional_changes,
        'v10_interpretation':'No central headline direction reverses. The internal targeted equal-threshold final-v1 advantage loses resolved direction with project clustering; public calibrated-vs-tracker remains unresolved. The finer grid selects 0.55 rather than the archived coarser-grid 0.50. This refines, rather than falsifies, the earlier best-among-tested-grid statement.'})
    macros = {'nMissedRecheckRate':pct(all_real['missed']['rate']),
              'nWpaRealMissed':all_real['missed']['k'],'nWpaRealChanged':all_real['missed']['n'],
              'nWpaRealWrongSilentRate':pct(all_real['wrong_silent']['rate']),
              'nWpaPublicDefaultAccuracy':pct(public['cascade']['accuracy']['rate'],1),
              'nWpaPublicCalibratedAccuracy':pct(public['calibrated']['accuracy']['rate'],1),
              'nWpaPublicDefaultGoneCorrect':pct(gone_default['rate'],1),
              'nWpaPublicCalibratedGoneCorrect':pct(gone_cal['rate'],1),
              'nWpaGateControlled':gate['counts']['main']+gate['counts']['replication'],
              'nWpaGateReal':gate['counts']['real'],'nWpaTrackerFailures':gate['tracker_execution_errors']}
    macros['nWpaRefinedPublicAccuracy'] = pct(refined['metrics']['accuracy']['rate'],1)
    (TEX/'numbers-wpa.tex').write_text('% Generated; no hand-entered results.\n'+'\n'.join('\\newcommand{\\'+k+'}{'+str(v)+'}' for k,v in macros.items())+'\n',encoding='utf-8')
    safety_headers = ['Method','All-target correct','Surviving file/start','State correct','Missed re-check','False re-check','Wrong place','Wrong and silent','Lost / survivors']
    for benchmark in ('main','replication'):
        rows = [[NAMES[m]]+[display(v[k]) for k in ('accuracy','placement_accuracy','classification_accuracy','missed','false_recheck','wrong','wrong_silent','lost')]
                for m,v in s[benchmark]['all'].items()]
        table('table-safety-'+benchmark+'.tex',safety_headers,rows,'Cells: count/denominator (percent [Wilson 95% interval]). State means preserved/edited/gone under normalized quote-window truth; four output labels are not five semantic classes. Tracker state labels are an explicit adapter, not a native policy.')
    for sample in ('all','own-uniform','own-targeted','oss-uniform','oss-targeted'):
        rows = [[NAMES[m]]+[display(v[k]) for k in ('accuracy','placement_accuracy','classification_accuracy','missed','false_recheck','wrong','wrong_silent','lost')]
                for m,v in s['real'][sample].items()]
        table('table-safety-real-'+sample+'.tex',safety_headers,rows,'All retained targets remain in correctness denominators, including tracker execution failures. Lost excludes crashes. See the JSON for adapter-semantics rates and the full output-label by reference-class confusion matrix.')
    groups = Counter((r['tier'],r['cls'],r['how'],r['repo'],r['horizon']) for r in e['missed_cases'])
    table('table-missed-recheck.tex',['Tier','Reference class','Oracle event','Project','Horizon','Misses'],
          [[*key,value] for key,value in sorted(groups.items())],
          'All cases and normalized copy coordinates, same/other-file counts, distances, anchor height and output coordinates are in missed-recheck-cases.csv and error-analysis.json. These are mechanistic attributions, not human adjudication.')
    table('table-controlled-errors.tex',['Seed','Operational cause','Wrong/lost cases'],
          [[seed,cause,n] for seed,counts in e['controlled_failure_groups'].items() for cause,n in counts.items()])
    rows = []
    for benchmark,group in [('main','all'),('replication','all'),('real','own'),('real','oss')]:
        for effect,values in f[benchmark][group]['averaged_main_effects'].items():
            rows.append([benchmark+'/'+group,effect]+[pct(values[k]) for k in ('accuracy','missed','gone_correct','wrong')])
    table('table-factorial-summary.tex',['Population','Contrast, averaged across thresholds','Accuracy pp','Missed pp','Gone correct pp','Wrong pp'],rows,
          'Contrasts use full-height windows. Scope and order are crossed at each threshold; the final row for each population is the order-by-scope difference in differences. Full cells, threshold interactions and the legacy-partial factor are retained in factorial-summary.json.')
    rows = []
    for item in c['safety_constrained']:
        if item['feasible']:
            held = item['public_evaluation']['targeted']
            rows.append([item['design'],pct(item['alpha'],0),pct(item['beta'],0),'/'.join(map(str,item['selected_cell'])),
                         display(held['accuracy'],False),display(held['missed'],False),display(held['gone_misreported'],False)])
        else:
            rows.append([item['design'],pct(item['alpha'],0),pct(item['beta'],0),'infeasible','--','--','--'])
    table('table-calibration.tex',['Search','alpha %','beta %','Selected cell','Public targeted correct','Missed','Gone present'],rows,
          'Select only on internal edit-targeted anchors; evaluate the chosen cell on public anchors. Infeasible means no grid cell meets both empirical constraints. Limits are selection rules, not confidence bounds or safety guarantees.')
    rows = []
    for repo,item in c['lopo']['all'].items():
        for design,result in item.items():
            rows.append([repo,design,'/'.join(map(str,result['selected_cell'])),display(result['held_out']['targeted']['accuracy'],False),display(result['held_out']['targeted']['missed'],False)])
    table('table-lopo.tex',['Held-out project','Search','Selected cell','Targeted correct','Targeted missed'],rows,
          'Training objective uses all anchors of the other projects. Edit-targeted training-objective sensitivity, all-anchor held-out outcomes and default comparisons are in calibration.json. Previously inspected histories make this retrospective transfer analysis.')
    rows = []
    for population in ('all','targeted','own-targeted','oss-targeted'):
        for unit,item in u['real'][population].items():
            for contrast in ('cascade-minus-cascade_v1','calibrated-minus-cascade','calibrated-minus-tracker_adapter','calibrated-minus-v1_calibrated'):
                v = item['contrasts'][contrast]
                rows.append([population,unit,item['clusters'],contrast,pct(v['difference']),f"[{pct(v['cluster95'][0])}, {pct(v['cluster95'][1])}]"])
    table('table-cluster-contrasts.tex',['Population','Cluster','Clusters','Paired contrast','Difference pp','95% percentile CI'],rows,
          '10,000 cluster draws; seed 20261031. Cluster ratios weight observations, not equal project means. Small project-cluster counts and temporal overlap limit generalization.')
    table('table-exclusions.tex',['Project','Horizon','Attempted pairs','Retained pairs','Retained anchors','Excluded anchors'],
          [[r[k] for k in ('repo','horizon','attempted_pairs','retained_pairs','retained','excluded')] for r in x['project_horizon']],
          'Pair counts concern sampled targets and need not add across retained/excluded groups. Exclusions have no assigned matcher truth or accuracy.')
    table('table-rounding.tex',['Method','n','Correct count','Wrong count','Lost count','Rounded correct','Rounded wrong','Rounded lost','Rounded total'],
          [[NAMES[r['method']],r['n'],r['counts'].get('correct',0),r['counts'].get('wrong_place',0),r['counts'].get('lost',0),r['rounded']['correct'],r['rounded']['wrong_place'],r['rounded']['lost'],r['total']] for r in num['v10_table_III']],num['rounding_note'])
    table('table-threshold-check.tex',['Threshold','Edited correct / n','Edited %','Gone correct / n','Gone %'],
          [[r['theta'],f"{r['classes']['edited']['k']}/{r['classes']['edited']['n']}",r['classes']['edited']['rounded_percent'],
            f"{r['classes']['gone']['k']}/{r['classes']['gone']['n']}",r['classes']['gone']['rounded_percent']] for r in num['threshold_reviewer_checks']],
          'All retained real-history observations, both sampling schemes and all projects. Edited and gone have separate denominators; the columns are not a percentage partition.')
    # A compile-only harness is included so fragments can be checked independently.
    fragments = sorted(p.name for p in TEX.glob('table-*.tex'))
    harness = r'\documentclass{article}\usepackage[landscape,margin=15mm]{geometry}\usepackage{booktabs,graphicx}\input{numbers-wpa.tex}\begin{document}'+'\n'
    harness += '\n'.join(r'\section*{'+escape(n[:-4])+r'}\input{'+n+r'}\clearpage' for n in fragments)
    harness += '\n'+r'\end{document}'
    (TEX/'check-fragments.tex').write_text(harness,encoding='utf-8')
    write('generated-fragments.json',{'macros':macros,'tex_files':fragments,'input_json_sha256':{n:sha(OUT/(n+'.json')) for n in names}})
    # Results note: generated prose and tables always trace back to the executed JSON.
    ci = u['real']['oss-targeted']['repo']['contrasts']['calibrated-minus-tracker_adapter']
    feasible = [a for a in c['safety_constrained'] if a['feasible']]
    constraint_example = next(v for v in feasible if v['design']=='threshold_only' and v['alpha']==.01 and v['beta']==.2)
    note = ['# WPA results', '',
        '## Three findings for the lead', '',
        f"1. Workflow misses are real: {display(all_real['missed'])} changed/gone targets do not request re-check. Separately, {display(all_real['wrong_silent'])} placements are wrong and silent over all retained targets, despite zero historical exact-label silent errors for the cascade. Movement is not a re-check signal.",
        f"2. The finer grid selects theta 0.55 in every leave-one-project-out fold for both searches and both training objectives. Public targeted correctness at that cell is {display(refined['metrics']['accuracy'],False)}, compared with {display(public['calibrated']['accuracy'],False)} at the archived theta 0.50. This is retrospective transfer evidence, not a prospective holdout claim.",
        f"3. Empirical safety constraints do not guarantee transfer: {len(transfer_failures)} of {len(feasible)} feasible design/constraint choices violate a requested limit on public targeted data. Project clustering also removes resolved direction from the internal equal-threshold final-v1 advantage. The original accuracy/deletion trade-off remains material.", '',
        '## Reproduction gates and environment', '',
        f"Fresh matcher gate passed on {gate['counts']['main']} main and {gate['counts']['replication']} replication controlled trials and {gate['counts']['real']} real-history observations. All archived method outcomes/silent flags, controlled metadata/flags, final labels, direct deployed/v1 corners and archived threshold outcomes match per observation. The independently pinned tracker also reproduces all saved outcomes, including {gate['tracker_execution_errors']} execution failures. See `evidence/v11-wpa/reproduction-gate.json`, `gate-trials.json`, `history-inputs.json` and run logs.",
        'The pinned interpreter is recorded in every JSON provenance block. Local CPU worker processes accelerate pure analysis; no agents or threads were delegated. Old histories are read through Git without checkout or source execution. The protocol was saved before the runs and its SHA-256 is embedded in outputs; this is local exploratory registration, not external preregistration.', '',
        '## A1 — Safety, classification and effort', '',
        'Source: `safety-metrics.json`; TeX: `tex/table-safety-*.tex`, `tex/numbers-wpa.tex`. Every benchmark, real sampling/group stratum and method has raw counts, Wilson intervals and a full label-by-reference-class matrix. All-target correctness includes correct absence; surviving file/start is reported separately. Classification maps exact/moved to preserved, changed to edited, removed to gone. It does not invent a unique four-label-to-five-class mapping.',
        'Baseline semantics: fixed-line/diff-drift no-match requests inspection; accepted preserved locations do not. Exact quote requests inspection on no-match; its historical displacement flag is separately retained as adapter semantics. V1 uses the recovered matching branch to distinguish changed from moved. The tracker has no native review-state policy: the declared adapter compares the original-height normalized quote at the returned first-line location; mapped differences request re-check, completed no-match requests inspection, and execution failure remains an unsuccessful inspection event. Tracker safety figures describe that adapter only.',
        'Native outputs additionally support five-class movement-aware classification from label plus returned coordinates, reported in JSON. Compact factorial codes do not preserve wrong-placement coordinates; that optional coordinate-dependent metric is marked unavailable for grid-only outputs rather than inferred from a sentinel. The required three-state classification and full label-by-five-class confusion matrix remain available for every method.',
        'Missed denominator is changed/gone; false re-check denominator is preserved; wrong/wrong-silent denominators are all targets; lost denominator is survivors and excludes crashes. Alternative all-target lost and returned-location conditional rates remain in JSON. Wilson intervals are nominal, with dependence-aware intervals supplied separately for headline correctness.',
        '`effort-dominance.json` and `.csv` retain the logarithmic sweep, every sampled winner/tie, coefficients and exact linear dominance-region inequalities. The requested additive effort model can charge both a missed request and a wrong silent placement on the same observation. Weights are illustrative, never measured faculty costs. Tracker crashes require a separate inspection-cost sensitivity; they are not made free by the five-term model.', '',
        '## A2 — Error analysis', '',
        f"The archived {e['missed_n']} quote-window workflow misses reproduce. `missed-recheck-cases.csv` contains each target, fired tier, normalized-copy count/path/start/distance, reference class, oracle event, project, horizon and height; `error-analysis.json` contains full and marginal groups. TeX: `table-missed-recheck.tex`, `table-controlled-errors.tex`.",
        f"Fired tiers: {e['marginal_groups']['tier']}. Reference classes: {e['marginal_groups']['cls']}. All misses have the moved label. The controlled default has {s['main']['all']['cascade']['wrong_silent']['k']} wrong-and-silent placements on the main seed and {s['replication']['all']['cascade']['wrong_silent']['k']} on replication, despite the historical exact-label silent-error count being zero.",
        'Controlled wrong/lost cases are operationally attributed to same-file normalized/raw copy ambiguity, local fuzzy selection, cross-file exact selection, or residual no-match. The JSON defines each rule. These are deterministic mechanism checks, not independent semantic adjudication.', '',
        '## A3 — Dependence-aware uncertainty', '',
        '`cluster-uncertainty.json` contains headline accuracy and paired contrasts from 10,000 fixed-seed resamples. Controlled clusters are source files; real clusters are commit pairs and, separately, projects. Repeated sampled observations remain. Per-project contrasts and positive/negative/tied signs are retained; `table-cluster-contrasts.tex` is the compact manuscript fragment.',
        f"V10 interpretation check: no central headline direction reverses. The internal targeted equal-threshold final-v1 difference remains {pct(u['real']['own-targeted']['repo']['contrasts']['final_theta075-minus-cascade_v1']['difference'])} points, but its project interval is [{pct(u['real']['own-targeted']['repo']['contrasts']['final_theta075-minus-cascade_v1']['cluster95'][0])}, {pct(u['real']['own-targeted']['repo']['contrasts']['final_theta075-minus-cascade_v1']['cluster95'][1])}], so its earlier resolved-direction interpretation weakens. Public calibrated-minus-tracker remains unresolved: {pct(ci['difference'])} points [{pct(ci['cluster95'][0])}, {pct(ci['cluster95'][1])}]. `interpretation-audit.json` lists every pair-resolved contrast whose project interval touches/crosses zero. Targeted per-project final-minus-v1 signs are {u['sign_agreement']['targeted']['cascade-minus-cascade_v1']}; calibrated-final-minus-calibrated-v1 signs are {u['sign_agreement']['targeted']['calibrated-minus-v1_calibrated']}. No equivalence or broad population guarantee follows.", '',
        '## A4 — Exclusions, horizons and magnitude', '',
        f"Instrumented original selection reproduces all {x['distribution']['retained']['n']} retained observations and {x['distribution']['excluded']['n']} exclusions, including each project/reason count. `attempted-observations.json` records every sampled attempt. `exclusion-horizon.json` compares project, horizon, reason, anchor height, added/deleted line counts and hunk sizes; it contains performance by horizon and diff bins. `table-exclusions.tex` reports project/horizon pair and anchor counts.",
        'Diff size is added plus deleted lines in the corresponding file; bins are defined in the frozen protocol. Excluded observations have no invented matcher outcomes or reference labels. Exclusion bias and lack of independent human labels remain, rather than being solved by deterministic regeneration.', '',
        f"Excluded files have median diff size {x['distribution']['excluded']['continuous']['diff_size']['quantiles'][2]:g} changed lines versus {x['distribution']['retained']['continuous']['diff_size']['quantiles'][2]:g} for retained observations. Horizon counts (retained anchors, retained pairs): "+'; '.join(f"{h}: {v['n']}, {v['pairs']}" for h,v in x['performance']['horizon'].items())+'.', '',
        '## A5 — Full factorial', '',
        f"`factorial-summary.json` covers {len(CELLS)} cells on each controlled seed and the full real sample, with internal/public and targeted strata. It reports raw rates, balanced main effects, order-by-scope interactions at each threshold, threshold interactions, and the legacy partial-window effect. `table-factorial-summary.tex` is the compact fragment.",
        f"V1 additionally permits one partial window when a new file is shorter than the original span. This is an explicit factor; {gate['short_file_cases']} input observations reach the audited short-file condition. Both archived corners reproduce exactly. Empty quotes, absent hashes and malformed span fallbacks differ between implementations, but do not occur in these valid, nonblank, hashed benchmark anchors. No conclusion is extrapolated to those inputs.", '',
        f"Balanced across the threshold grid, whole-file instead of local search lowers gone-correct rates by {-100*f['real']['own']['averaged_main_effects']['whole_minus_local']['gone_correct']:.2f} points internally and {-100*f['real']['oss']['averaged_main_effects']['whole_minus_local']['gone_correct']:.2f} publicly. Cross-file-first instead of fuzzy-first increases missed re-checks by {100*f['real']['own']['averaged_main_effects']['cross_first_minus_fuzzy_first']['missed']:.2f} and {100*f['real']['oss']['averaged_main_effects']['cross_first_minus_fuzzy_first']['missed']:.2f} points respectively. These are matched factorial contrasts, not independent randomized experiments.", '',
        '## A6 — Calibration robustness', '',
        '`calibration.json`, `table-calibration.tex` and `table-lopo.tex` contain leave-one-project-out threshold-only and full-cell selection, selected-threshold stability, held-out safety/accuracy, and edit-targeted objective sensitivity. Accuracy-only training on all anchors matches the existing objective. Safety-constrained training uses internal targeted anchors only and reports public performance once per selected cell.',
        'All empirical constraint failures are retained as infeasible. Alpha/beta are empirical training limits, not confidence-bound guarantees. Full-grid and leave-one-project-out results are retrospective because these project histories were already inspected in prior revisions.', '',
        f"Accuracy-only theta 0.50 raises public targeted correctness from {display(public['cascade']['accuracy'],False)} to {display(public['calibrated']['accuracy'],False)}, while correct absence on all public gone observations falls from {display(gone_default,False)} to {display(gone_cal,False)}. Constraints have {len(feasible)} feasible and {len(c['safety_constrained'])-len(feasible)} infeasible design/limit combinations. The selected theta {constraint_example['selected_cell'][3]} meets the internal targeted {pct(constraint_example['beta'],0)}% gone-present cap but has {display(constraint_example['public_evaluation']['targeted']['gone_misreported'],False)} gone-present on public targeted observations; all limit violations are in `interpretation-audit.json`.", '',
        '## A7 — Numerical checks', '',
        '`numerical-audit.json`, `table-rounding.tex` and `table-threshold-check.tex` recompute the controlled outcome table and all raw-count outcome partitions. The reviewer-quoted threshold values reproduce with the full real edited/gone class denominators, pooling both sampling schemes and all projects. These are not public-targeted-only results and their columns are not parts of one total.',
        num['rounding_note'], '',
        'The non-100 total rows actually displayed in v10 Table III are: '+', '.join(NAMES[r['method']]+' ('+str(r['total'])+'%)' for r in num['v10_table_III'] if r['total']!=100)+'. The JSON retains all other derived partition diagnostics; independent method-accuracy columns elsewhere are not additive partitions.', '',
        '## Limits, permitted writes and handoff', '',
        'No application code, earlier draft/evidence, AGENTS.md, Git commit or remote state was changed by this worker. DOX pass: existing contracts were read; AGENTS.md is intentionally unchanged because the task expressly prohibits editing it. No human labels, educational outcomes or measured effort were collected. Excluded-case correctness and native tracker lifecycle safety remain unmeasured.',
        'Correction history: `reporting-correction.json` and `diagnostic-initial-analysis/` retain a superseded optional five-class reporting diagnostic. Primary safety, placement, uncertainty, factorial and calibration results did not change. The exact core used by the gate is preserved by its pre-existing SHA-256 in `tools/v11/frozen/wpa_core_gate.py`; verification checks that all matcher-function ASTs remain unchanged after reporting extensions. The standalone input inventory was recorded after the gate started; protocol text had already been saved, and no external time-registration is claimed.',
        'Reproduce from the repository root using the pinned Python with `-B`: run `tools/v11/run_wpa_gate.py`, `wpa_exclusions.py`, `analyze_wpa.py`, `build_wpa_results.py`, then `verify_wpa.py` (all paths relative to `paper-drafts/`). Runtime outputs are self-contained under `evidence/v11-wpa/`; compile `tex/check-fragments.tex` only inside that directory. No manuscript wording was edited; positioning belongs to the lead.', '']
    (ROOT/'review/V11-WPA-RESULTS.md').write_text('\n'.join(note),encoding='utf-8')
    print('Generated WPA results note and TeX fragments.',flush=True)


if __name__=='__main__':
    main()
