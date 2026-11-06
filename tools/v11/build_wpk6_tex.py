"""WP K6 macros and table from the latest evidence/v12-wpk6/summary-*.json and llm/summary.json.

Writes v11-professor-revision/generated/numbers-wpk6.tex (prefix \\wk), table-suggestion.tex and
numbers-wpk6-provenance.json. Picked up by tools/v11/build_wpk_all.py.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / 'evidence/v12-wpk6'
GEN = ROOT / 'v11-professor-revision/generated'
METHODS = (('github', 'Gh', 'GitHub outdating'), ('t0.85-deployed', 'Dep', 'Cascade, deployed'),
           ('t0.85-IG+AGi+VW', 'Gi', 'Cascade+IG+AGi+VW'), ('codemapper+quote', 'CmQ', 'CodeMapper+quote'),
           ('codemapper+IG+AG', 'CmAg', '\\quad +IG+AG'), ('codemapper+IG+AGi', 'CmGi', '\\quad +IG+AGi'))
MEAS = (('missed', 'Miss'), ('unnecessary', 'Extra'), ('placement', 'Place'), ('lost', 'Lost'), ('silent', 'Silent'),
        ('misdirected', 'Misdir'), ('gone_kept', 'GoneKept'), ('correct', 'Correct'), ('errors', 'Err'),
        ('ambiguous_request', 'AmbReq'))
LANG = {'Python': 'Py', 'TypeScript': 'Ts', 'Go': 'Go', 'Rust': 'Rs', 'Java': 'Jv'}
CLS = {'applied': 'Applied', 'untouched': 'Untouched', 'rewritten': 'Rewritten', 'ambiguous': 'Ambiguous',
       'applied-deletion': 'AppliedDel', 'gone-file': 'GoneFile'}


def fmt(x):
    return '--' if x is None else f'{x:.1f}'


def main():
    path = sorted(EV.glob('summary-*.json'))[-1]
    s = json.loads(path.read_text(encoding='utf-8'))
    mac = {}

    def m(name, value):
        assert name.isalpha(), name
        mac['wk' + name] = value

    m('Units', str(s['n_units']))
    m('Repos', str(len(s['repositories'])))
    m('PRs', str(s['prs']))
    m('Languages', str(len(s['classes_by_language'])))
    for c, tag in CLS.items():
        m('Cls' + tag, str(s['classes'].get(c, 0)))
    m('ClsGone', str(s['classes'].get('applied-deletion', 0) + s['classes'].get('gone-file', 0)))
    m('ApplyCommit', str(s['apply_commit_among_applied']))
    for meth, tag, _ in METHODS:
        o = s['overall'][meth]
        for key, mt in MEAS:
            r = o[key]
            m(tag + mt, fmt(r['pct']))
            m(tag + mt + 'K', str(r['k']))
            m(tag + mt + 'N', str(r['n']))
            if r['ci'][0] is not None:
                m(tag + mt + 'Lo', fmt(r['ci'][0]))
                m(tag + mt + 'Hi', fmt(r['ci'][1]))
        for lang, lt in LANG.items():
            if lang in s['by_language']:
                for key, mt in MEAS[:6]:
                    m(lt + tag + mt, fmt(s['by_language'][lang][meth][key]['pct']))
    for name, r in s['paired']['contrasts'].items():
        a, b = name.split(' minus ')
        ta = next(t for mm, t, _ in METHODS if mm == a)
        tb = next(t for mm, t, _ in METHODS if mm == b)
        for key, mt in MEAS[:6]:
            if key in r:
                m(f'D{ta}V{tb}{mt}', fmt(r[key]['difference_pts']))
                m(f'D{ta}V{tb}{mt}Lo', fmt(r[key]['ci95_pts'][0]))
                m(f'D{ta}V{tb}{mt}Hi', fmt(r[key]['ci95_pts'][1]))
    mech = s['mechanisms']
    m('AppliedWrap', str(mech['applied_wrapping']))
    for meth, tag, _ in METHODS:
        mm = mech['misses_by_mechanism'][meth]
        m(tag + 'MissWrap', str(mm.get('wraps_unchanged_quotation', 0)))
        m(tag + 'MissOther', str(sum(v for k, v in mm.items() if k != 'wraps_unchanged_quotation')))
    llm_path = EV / 'llm/summary.json'
    if llm_path.exists():
        L = json.loads(llm_path.read_text(encoding='utf-8'))
        m('LlmN', str(L['n']))
        m('LlmApplied', str(L['by_class'].get('applied', 0)))
        m('LlmUntouched', str(L['by_class'].get('untouched', 0)))
        for model, mt in (('beam', 'Beam'), ('nemotron', 'Nemo')):
            if model not in L['models']:
                continue
            r = L['models'][model]
            for arm, at in (('A', 'Diff'), ('B', 'Claim')):
                for k, kt in (('precision', 'Precision'), ('recall', 'Recall'), ('accuracy', 'Accuracy'), ('f1', 'Fone')):
                    m(mt + at + kt, fmt(r['arms'][arm][k]))
                for k, kt in (('tp', 'TP'), ('fp', 'FP'), ('fn', 'FN'), ('tn', 'TN')):
                    m(mt + at + kt, str(r['arms'][arm][k]))
                m(mt + at + 'RecLo', fmt(r['arms'][arm]['recall_ci'][0]))
                m(mt + at + 'RecHi', fmt(r['arms'][arm]['recall_ci'][1]))
                for k in ('unparsed', 'missing'):
                    m(mt + at + k.capitalize(), str(r['arms'][arm][k]))
                m(mt + at + 'PrecLo', fmt(r['arms'][arm]['precision_ci'][0]))
                m(mt + at + 'PrecHi', fmt(r['arms'][arm]['precision_ci'][1]))
            m(mt + 'WrapN', str(r['wrap_n']))
            m(mt + 'WrapDiff', str(r['wrap_flagged']['A']))
            m(mt + 'WrapClaim', str(r['wrap_flagged']['B']))
            m(mt + 'ClaimBetter', str(r['b_right_a_wrong']))
            m(mt + 'DiffBetter', str(r['a_right_b_wrong']))
            p = r['mcnemar_p']
            m(mt + 'McNemarP', '$<10^{-12}$' if p < 1e-12 else '$<0.001$' if p < .001 else f'{p:.3f}')
    text = '% Generated by tools/v11/build_wpk6_tex.py from ' + path.name + '; do not edit.\n' + ''.join(
        f'\\newcommand{{\\{k}}}{{{v}}}\n' for k, v in sorted(mac.items()))
    (GEN / 'numbers-wpk6.tex').write_text(text, encoding='utf-8')
    rows = []
    for meth, tag, label in METHODS:
        o = s['overall'][meth]
        rows.append(label + ' & ' + ' & '.join(fmt(o[k]['pct']) for k in ('placement', 'missed', 'silent', 'misdirected', 'lost', 'unnecessary')) + r' \\')
    table = (r"""\begin{table}[t]
\caption{Suggestion-Application Oracle: Six Outcomes (\%)}\label{tab:suggest}
\centering\footnotesize
\setlength{\tabcolsep}{3pt}
\begin{tabular}{@{}lrrrrrr@{}}\toprule
Method & Place & Miss & Silent & Misdir & Lost & Extra \\ \midrule
""" + '\n'.join(rows) + r"""
\bottomrule
\end{tabular}
\tablenote{}{\wkUnits{} review suggestions from \wkRepos{} repositories in \wkLanguages{} languages; scope is the file pair. Place and Lost: over the \wkDepPlaceN{} applied or untouched targets (applied: start inside the suggested text). Miss: over the \wkDepMissN{} changed targets (applied, rewritten, deleted). Extra: over the \wkDepExtraN{} untouched targets. Silent and Misdir: over all \wkDepSilentN{} scored targets. GitHub: the thread's current outdated flag. Ambiguous targets (\wkClsAmbiguous) are not scored.}
\end{table}
""")
    (GEN / 'table-suggestion.tex').write_text(table, encoding='utf-8')
    (GEN / 'numbers-wpk6-provenance.json').write_text(json.dumps(dict(
        summary=path.name, summary_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        llm_summary_sha256=hashlib.sha256(llm_path.read_bytes()).hexdigest() if llm_path.exists() else None,
        macros=len(mac)), indent=1), encoding='utf-8')
    print(f'numbers-wpk6.tex: {len(mac)} macros from {path.name}')


if __name__ == '__main__':
    main()
