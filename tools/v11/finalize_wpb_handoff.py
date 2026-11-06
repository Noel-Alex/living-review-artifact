"""Record final visual inspection and make stratum-specific costs prominent."""
from datetime import datetime,timezone
from pathlib import Path
from wpa_core import ROOT,read,sha
from run_wpb import OUT,write,verify_freeze


def main():
    freeze=verify_freeze()
    verification=read(OUT/'verification.json')['data']
    tex=read(OUT/'tex-verification.json')['data']
    assert verification['passed'] and tex['compiled'] and tex['no_overfull_or_undefined']
    summary=read(OUT/'evaluation-summary-corrected.json')['data']
    paired=read(OUT/'evaluation-paired.json')['data']
    report=ROOT/'review/V11-WPB1-RESULTS.md'
    before=report.read_text(encoding='utf-8')
    backup=ROOT/'review/V11-WPB1-RESULTS-precloseout.md'
    with backup.open('x',encoding='utf-8') as stream:stream.write(before)
    guard_costs={}
    for stratum in ('real','real:oss:targeted'):
        guard_costs[stratum]={}
        for theta in (.85,.55):
            guard_costs[stratum][str(theta)]={}
            for guard in ('IG','AG','VW'):
                m=summary['strata'][stratum]['methods'][f't{theta:.2f}-{guard}']
                guard_costs[stratum][str(theta)][guard]=dict(extra_per_100=m['extra_rechecks_per_100_preserved'],
                                                           counts=m['extra_recheck_counts'])
    pc=guard_costs['real:oss:targeted']['0.85']
    public_cost=f" On the public edit-targeted preserved subset specifically, gross extra requests per 100 are IG {pc['IG']['extra_per_100']:.2f}, AG {pc['AG']['extra_per_100']:.2f}, VW {pc['VW']['extra_per_100']:.2f} at both thresholds; the pooled history cost should not obscure this concentration."
    assert all(guard_costs['real:oss:targeted']['0.85'][g]['extra_per_100']==guard_costs['real:oss:targeted']['0.55'][g]['extra_per_100'] for g in ('IG','AG','VW'))
    lines=before.splitlines()
    matches=[i for i,s in enumerate(lines) if s.startswith('2. **AG changes')]
    assert len(matches)==1
    lines[matches[0]]+=public_cost
    contrast=paired['real:oss:targeted']['contrasts']['t0.85-VW minus t0.85-deployed']
    pa=contrast['accuracy'];pr=contrast['range_correct']
    ms=summary['strata']['real:oss:targeted']['methods']
    control=summary['strata']['original']['methods']
    pm=ms['t0.55-deployed'];pv=ms['t0.55-VW']
    adverse=dict(original055_base_correct=control['t0.55-deployed']['accuracy'],original055_VW_correct=control['t0.55-VW']['accuracy'],
                 public085_gone_base=ms['t0.85-deployed']['gone_correct'],public085_gone_VW=ms['t0.85-VW']['gone_correct'])
    extra=[
        '', '## Closeout checks and interpretation details', '',
        f"The independent verifier passes all {verification['n']} held-out-evaluation targets, all requested construction cells, original/inherited input SHA-256s, exact archived safety-case identities, event-count conservation, the common surviving-range subset and {verification['unit_tests']} focused tests. Frozen-code and UTC ordering checks pass. See `evidence/v11-wpb1/verification.json`.",
        f"Generated TeX compiles into {tex['pages']} check pages without overfull boxes or undefined controls/references. Every table on all contact sheets was visually inspected: legible text, aligned rows/columns, no clipping or overlap. This checks the fragment document, not a revised manuscript. The optional PyMuPDF import was unavailable on the first verification attempt; its log is retained. The installed Poppler renderer succeeded without installing packages. `tex-verification.json` records compilation/render hashes; `tex-visual-review.json` records completed visual inspection.",
        f"Public edit-targeted VW-minus-baseline at theta 0.85 is {100*pa['difference']:.2f} percentage points for all-target correctness (commit-pair bootstrap 95% [{100*pa['cluster95'][0]:.2f}, {100*pa['cluster95'][1]:.2f}]) and {100*pr['difference']:.2f} points for exact ranges (95% [{100*pr['cluster95'][0]:.2f}, {100*pr['cluster95'][1]:.2f}]). These nominal paired intervals remain retrospective. At theta 0.55, public all-target correctness is {100*pv['accuracy']['rate']:.2f}% with VW versus {100*pm['accuracy']['rate']:.2f}% without it, and exact ranges are {100*pv['range_correct']['rate']:.2f}% versus {100*pm['range_correct']['rate']:.2f}%.",
        f"Adverse outcomes remain: on the original seed-2 operators at theta 0.55, VW correctness is {100*adverse['original055_VW_correct']['rate']:.2f}% versus {100*adverse['original055_base_correct']['rate']:.2f}% without VW; on public edit-targeted gone cases at theta 0.85, correct absence is {adverse['public085_gone_VW']['k']}/{adverse['public085_gone_VW']['n']} with VW versus {adverse['public085_gone_base']['k']}/{adverse['public085_gone_base']['n']} without it. IG requests re-check for every benign continuation-realignment trial; that workload cost is separate from the successful semantic stress detection. AG still misses requests in the newly held-out duplicate constructions. No variant is presented as a universal solution.",
        'All real-history contrasts remain retrospective, all genuine new seed-2 stress inputs were generated after freeze, and no frozen variant code changed. The closeout adds interpretation and verification records only. No application code or AGENTS.md was changed; no commit, push, external message, subagent or new conversation was started.'
    ]
    report.write_text('\n'.join(lines+extra)+'\n',encoding='utf-8')
    sheets={str(Path(p).relative_to(ROOT)).replace('\\','/'):sha(p) for p in tex['contact_sheets']}
    write('tex-visual-review.json',dict(completed=True,pages=tex['pages'],contact_sheet_sha256=sheets,
          pdf_sha256=tex['pdf_sha256'],review='Every table inspected across all seven contact sheets; aligned, legible, no clipping or overlap.',
          limit='Fragment QA document only; no revised manuscript or application UI review.',reviewed_utc=datetime.now(timezone.utc).isoformat()))
    write('closeout.json',dict(passed=True,protocol_sha256=freeze['protocol_sha256'],variant_sha256=freeze['code_sha256']['tools/v11/wpb_variants.py'],
          report_before_sha256=sha(backup),report_after_sha256=sha(report),guard_costs=guard_costs,adverse_outcomes=adverse,
          verification_sha256=sha(OUT/'verification.json'),tex_verification_sha256=sha(OUT/'tex-verification.json'),
          visual_review_sha256=sha(OUT/'tex-visual-review.json'),script_sha256=sha(Path(__file__)),
          source_sha256={n:sha(OUT/n) for n in ('evaluation-summary-corrected.json','evaluation-paired.json','handoff-numbers.json')},
          all_frozen_code_unchanged=True,no_blocked_B1_cells=True,remaining='WP C/H held-out evaluations; no human behavioral study supplied.'))
    print('Closeout PASS',report,verification['unit_tests'],'tests',tex['pages'],'visually checked fragment pages',flush=True)


if __name__=='__main__':main()
