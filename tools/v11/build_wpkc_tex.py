"""Compact v12 floats from the WP K1 summary: identity-floor sensitivity and policy selection on unseen projects.

Writes v11-professor-revision/generated/numbers-wpkc.tex (prefix \\wz), table-idfloor-compact.tex and
table-policy-compact.tex. Picked up by tools/v11/build_wpk_all.py.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / 'evidence/v12-wpk1'
GEN = ROOT / 'v11-professor-revision/generated'
FLOORS = ('0.3', '0.5', '0.7', '0.9', '1.0')
BASES = (('chains-agi:v0.85-off', 'Dep', 'Cascade, deployed'), ('chains-agi:v0.85-alli', 'Gi', 'Cascade+IG+AGi+VW'),
         ('chains-agi:v0.55-alli', 'Gic', '\\quad $\\theta{=}0.55$'), ('chains-agi:cm-seq-gi-id', 'Cm', 'CodeMapper+IG+AGi'))
WEIGHTS = (('w1_m1', 'One', '1, 1'), ('w3_m3', 'Three', '3, 3'), ('w10_m3', 'Ten', '10, 3'))
NAMES = {'hybrid': 'tracker$\\to$cascade', 'cmhybrid': 'CodeMapper$\\to$cascade', 'codemapper': 'CodeMapper',
         'tracker': 'tracker', 'gumtree': 'GumTree'}
WORD = {'0.3': 'Three', '0.5': 'Five', '0.7': 'Seven', '0.9': 'Nine', '1.0': 'Ten'}


def pretty(policy):
    if policy == 'tracker_adapter':
        return 'tracker, own labels'
    base, _, layer = policy.partition('+')
    if policy.startswith('t0.'):
        return policy.replace('t0.85-', 'cascade ').replace('t0.55-', 'cascade $\\theta{=}0.55$ ')
    return NAMES.get(base, base) + ('+' + layer if layer else '')


def main():
    path = sorted(EV.glob('summary-*.json'))[-1]
    s = json.loads(path.read_text(encoding='utf-8'))
    mac = {}

    def m(k, v):
        assert k.isalpha(), k
        mac['wz' + k] = v

    rep = s['identity_floor']['replay']
    rows = []
    for key, tag, label in BASES:
        fl = rep[key]['floors']
        cells = []
        for f in FLOORS:
            if f not in fl:
                cells.append('--')
                continue
            c = fl[f].get('counts', fl[f])
            for k in ('wrong', 'lost', 'missed_last', 'correct'):
                m(f'{tag}F{WORD[f]}{k.replace("_", "").capitalize()}', f"{c[k]:,}")
            cells.append(f"{c['wrong']}/{c['lost']}")
        miss = sorted({fl[f].get('counts', fl[f])['missed_last'] for f in FLOORS if f in fl})
        miss_cell = '--'.join(str(x) for x in (miss[0], miss[-1])) if len(miss) > 1 else str(miss[0])
        m(tag + 'MissRange', miss_cell)
        rows.append(f'{label} & {miss_cell} & ' + ' & '.join(cells) + ' ' + chr(92) * 2)
        r = rep[key].get('changed_hop_ratio_by_reference')
        if r:
            for part, pt in (('true_target', 'True'), ('wrong_window', 'Wrong')):
                m(tag + 'Ratio' + pt + 'Med', f"{r[part]['median']:.2f}")
                m(tag + 'Ratio' + pt + 'N', f"{r[part]['n']:,}")
                m(tag + 'Ratio' + pt + 'Lo', f"{r[part]['q1']:.2f}")
                m(tag + 'Ratio' + pt + 'Hi', f"{r[part]['q3']:.2f}")
    idt = (r"""\begin{table}[t]
\caption{Identity-Rule Floor: Wrong/Lost Endpoints After Ten Commits}\label{tab:idfloor}
\centering\footnotesize
\setlength{\tabcolsep}{2.5pt}
\begin{tabular}{@{}lrrrrrr@{}}\toprule
 & & \multicolumn{5}{c}{Floor} \\ \cmidrule(l){3-7}
Locator & Miss & 0.3 & 0.5 & 0.7 & 0.9 & 1.0 \\ \midrule
""" + '\n'.join(rows) + r"""
\bottomrule
\end{tabular}
\tablenote{}{Counts over 4,000 ten-commit chains (CodeMapper 3,998; its traces are replayed only from 0.5 upward). Miss: changes since review never signaled at the last commit, which is the same at every floor. Cells: wrong/lost endpoints. Replays reproduce the stored 0.3, 0.5 and 0.7 traces exactly.}
\end{table}
""")
    (GEN / 'table-idfloor-compact.tex').write_text(idt, encoding='utf-8')

    prow = []
    for pop, ptag, plabel in (('real', 'Real', 'Real (9 projects)'), ('students', 'Stu', 'Student (20 repositories)')):
        sel = s['selection'][pop]
        nf = len(sel['folds'])
        for w, wt, wl in WEIGHTS:
            st, oo = sel['stability'][w], sel['out_of_sample'][w]
            mode = pretty(st['mode'])
            share = round(100 * st['mode_share'])
            m(ptag + wt + 'Mode', mode)
            m(ptag + wt + 'ModeShare', str(share))
            m(ptag + wt + 'Folds', str(nf))
            m(ptag + wt + 'Distinct', str(len(st['selected_counts'])))
            for k, v in (('Sel', oo['selected_mean_cost']), ('Orc', oo['oracle_mean_cost']),
                         ('Dep', oo['fixed_mean_cost']['t0.85-deployed']), ('Cm', oo['fixed_mean_cost']['codemapper+IG+AGi'])):
                m(ptag + wt + 'Cost' + k, f'{v:.3f}')
            m(ptag + wt + 'BeatDep', str(oo['beats_fixed_count']['t0.85-deployed']))
            m(ptag + wt + 'BeatCm', str(oo['beats_fixed_count']['codemapper+IG+AGi']))
            prow.append(f"{plabel if w == WEIGHTS[0][0] else ''} & {wl} & {mode} ({share}\\%) & {len(st['selected_counts'])} & "
                        f"{oo['selected_mean_cost']:.3f} & {oo['fixed_mean_cost']['t0.85-deployed']:.3f} & "
                        f"{oo['fixed_mean_cost']['codemapper+IG+AGi']:.3f} & {oo['oracle_mean_cost']:.3f} & "
                        f"{oo['beats_fixed_count']['t0.85-deployed']}/{nf} & {oo['beats_fixed_count']['codemapper+IG+AGi']}/{nf} \\\\")
    pt = (r"""\begin{table*}[t]
\caption{Policy Selection on Held-Out Projects: Mean Cost per Carried Target}\label{tab:policysel}
\centering\footnotesize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{@{}llp{.25\textwidth}rrrrrrr@{}}\toprule
Population & $w, m$ & Most often selected (share of folds) & Distinct & Selected & Deployed & CM+IG+AGi & Best & Beats dep. & Beats CM \\ \midrule
""" + '\n'.join(prow) + r"""
\bottomrule
\end{tabular}
\tablenote{}{Leave one project out: the policy minimizing $C=w(\text{missed}+\text{silent})+m\,\text{misdirected}+\text{lost}+\text{unnecessary}$ per carried target on the other projects is evaluated on the held-out one. Candidates are every recorded locator and layer. Best: the held-out project's own minimum (an oracle). Distinct: number of different policies selected across folds. tracker$\to$cascade and CodeMapper$\to$cascade use the cascade's cross-file exact match when the first locator finds nothing. Post hoc: all records had been read.}
\end{table*}
""")
    (GEN / 'table-policy-compact.tex').write_text(pt, encoding='utf-8')
    mis = s['misdirection_cost']
    for pop, ptag in (('real', 'Real'), ('students', 'Stu'), ('external:human-AB', 'Hum'), ('fresh', 'Fr')):
        for meth, mt in (('t0.85-deployed', 'Dep'), ('t0.85-IG+AGi+VW', 'Gi'), ('codemapper+IG+AG', 'CmAg'), ('codemapper+IG+AGi', 'CmGi')):
            for kind, kt in (('misdirected', 'Mis'), ('silent', 'Sil')):
                r = mis[pop][meth][kind]
                m(ptag + mt + kt + 'N', f"{r['n']:,}")
                if r['n']:
                    m(ptag + mt + kt + 'Same', f"{100 * r['same_file_share']:.0f}")
                    if r.get('distance_median') is not None:
                        m(ptag + mt + kt + 'Dist', f"{r['distance_median']:g}")
                        m(ptag + mt + kt + 'DistLo', f"{r['distance_q1']:g}")
                        m(ptag + mt + kt + 'DistHi', f"{r['distance_q3']:g}")
    text = '% Generated by tools/v11/build_wpkc_tex.py from ' + path.name + '; do not edit.\n' + ''.join(
        f'\\newcommand{{\\{k}}}{{{v}}}\n' for k, v in sorted(mac.items()))
    (GEN / 'numbers-wpkc.tex').write_text(text, encoding='utf-8')
    (GEN / 'numbers-wpkc-provenance.json').write_text(json.dumps(dict(summary=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                                                      macros=len(mac)), indent=1), encoding='utf-8')
    print(f'numbers-wpkc.tex: {len(mac)} macros from {path.name}')


if __name__ == '__main__':
    main()
