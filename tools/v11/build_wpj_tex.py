"""Generate WP J manuscript macros and the language-model locator table from the latest evidence/v11-wpj/summary-*.json.

Run: python -I -B tools/v11/build_wpj_tex.py   (from paper-drafts/)
Writes v11-professor-revision/generated/numbers-wpj.tex, table-llm.tex and numbers-wpj-provenance.json.
Macro pattern: \\wj<Pop><Method><Metric>[K|N] (rate in percent). Incomplete populations emit '--'.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / 'evidence/v11-wpj'
OUT = ROOT / 'v11-professor-revision' / 'generated'
POPS = {'human-AB': 'Hum', 'real-oss-targeted': 'Pub', 'students-targeted': 'Stu'}
LABELS = {'human-AB': 'Human-annotated', 'real-oss-targeted': 'Open-source, edit-targeted', 'students-targeted': 'Student, edit-targeted'}
METHODS = {'llm-self': 'Self', 'llm+quote': 'Q', 'llm+IG': 'IG', 'llm+AGi': 'AGi', 'llm+IG+AGi': 'Gi',
           'codemapper+quote': 'CmQ', 'codemapper+IG+AGi': 'CmGi', 't0.85-deployed': 'Dep', 't0.85-IG+AGi+VW': 'CasGi'}
METRICS = {'accuracy': 'Acc', 'placement_accuracy': 'Place', 'missed': 'Miss', 'false_recheck': 'False',
           'wrong_silent': 'Silent', 'wrong': 'Wrong', 'lost': 'Lost'}
macros: list[tuple[str, str]] = []


def m(name, value):
    assert re.fullmatch(r'[A-Za-z]+', name), name
    value = str(value)
    if re.fullmatch(r'-[0-9][0-9,.]*', value):
        value = '\\ensuremath{-}' + value[1:]
    macros.append((name, value))


def pct(r, nd=1):
    return '--' if r is None or r.get('rate') is None else f"{100 * r['rate']:.{nd}f}"


def num(n):
    return f'{n:,}'


def word(s):
    return ''.join(w.capitalize() for w in re.findall(r'[A-Za-z]+', s))


def latest():
    files = sorted(EV.glob('summary-*.json'))
    assert files, 'no WP J summary'
    return files[-1]


def points(x):
    return '--' if x is None else f'{100 * x:.1f}'


TABLE_ROWS = (('Language model (\\wjModel{})',(('llm-self', 'own judgment'), ('llm+quote', 'labels only'), ('llm+IG+AGi', '+IG+AGi'))),
              ('CodeMapper', (('codemapper+quote', 'labels only'), ('codemapper+IG+AGi', '+IG+AGi'))),
              ('Cascade', (('t0.85-deployed', 'deployed'),)))
TABLE_METRICS = (('placement_accuracy', 'Place'), ('missed', 'Miss'), ('wrong_silent', 'Silent'), ('wrong_with_recheck', 'Misdir'),
                 ('false_recheck', 'Extra'))


SECOND_ROWS = (('llm-self', 'own judgment'), ('llm+IG+AGi', '+IG+AGi'))


def table(pops, second=None):
    """second: (model name, populations) of a secondary model complete on every population, shown below the primary."""
    cols = len(POPS) * len(TABLE_METRICS)
    groups = list(TABLE_ROWS)
    if second:
        groups.insert(1, (f'Second model ({second[0]})', SECOND_ROWS, second[1]))
    out = ['\\begin{table*}[t]', '\\caption{A Language-Model Locator With and Without the Safety Layer (\\%)}\\label{tab:llm}',
           '\\centering\\footnotesize', '\\setlength{\\tabcolsep}{3pt}',
           '\\begin{tabular}{@{}l' + ('r' * len(TABLE_METRICS) + '@{\\hspace{8pt}}') * (len(POPS) - 1) + 'r' * len(TABLE_METRICS) + '@{}}\\toprule']
    out.append(' & ' + ' & '.join(f'\\multicolumn{{{len(TABLE_METRICS)}}}{{c}}{{{LABELS[p]}}}' for p in POPS) + ' \\\\')
    out.append(' & ' + ' & '.join(f'\\multicolumn{{{len(TABLE_METRICS)}}}{{c}}{{$n{{=}}${num(pops[p]["n"]) if pops[p].get("complete") else "--"}}}'
                                  for p in POPS) + ' \\\\')
    rules, c = [], 2
    for _ in POPS:
        rules.append(f'\\cmidrule(lr){{{c}-{c + len(TABLE_METRICS) - 1}}}')
        c += len(TABLE_METRICS)
    out.append(''.join(rules))
    out.append('Method & ' + ' & '.join(k for _ in POPS for _, k in TABLE_METRICS) + ' \\\\ \\midrule')
    for g in groups:
        group, rows, src = (g[0], g[1], g[2] if len(g) > 2 else pops)
        out.append(f'\\multicolumn{{{cols + 1}}}{{@{{}}l}}{{\\emph{{{group}}}}} \\\\')
        for meth, label in rows:
            vals = []
            for p in POPS:
                rec = src[p]['methods'].get(meth) if src[p].get('complete') else None
                vals += [pct(rec[k]) if rec else '--' for k, _ in TABLE_METRICS]
            out.append(f'\\quad {label} & ' + ' & '.join(vals) + ' \\\\')
    out += ['\\bottomrule', '\\end{tabular}',
            '\\tablenote{}{Same observations for every row. The language model (\\wjModel{}, the model of the deployed portal; temperature 0) sees the old region with '
            'context and the complete new version of the paired file. \\emph{Own judgment}: the model\'s answer of whether the region '
            'changed decides the request. \\emph{Labels only} and \\emph{+IG+AGi}: the model\'s window passes through the quotation '
            'comparison and the window guards, as for CodeMapper; placement is unchanged. Unanswerable prompts (file too large for the '
            'context, provider refusal) count as execution errors and request re-check. '
            + ('The second model received the same prompts and settings; its window is placed by its own answer, so its placement differs. ' if second else '')
            + 'Columns as in Table~\\ref{tab:locator}.}',
            '\\end{table*}', '']
    return '\n'.join(out)


def population_macros(pre, pops, only_complete=False):
    for pop, pn in POPS.items():
        p = pops.get(pop, {})
        done = bool(p.get('complete'))
        if only_complete and not done:
            continue
        m(f'{pre}{pn}Complete', 'yes' if done else 'no')
        m(f'{pre}{pn}N', num(p['n']) if done else '--')
        for meth, mn in METHODS.items():
            rec = p['methods'].get(meth) if done else None
            for met, tn in METRICS.items():
                r = rec[met] if rec else None
                m(f'{pre}{pn}{mn}{tn}', pct(r))
                m(f'{pre}{pn}{mn}{tn}K', num(r['k']) if r and r.get('k') is not None else '--')
                m(f'{pre}{pn}{mn}{tn}N', num(r['n']) if r and r.get('n') is not None else '--')
            m(f'{pre}{pn}{mn}Err', num(rec['execution_errors']) if rec else '--')
        for j, jn in (('J1', 'JOne'), ('J2', 'JTwo'), ('J3', 'JThree')):
            h = p['hypotheses'][j] if done else None
            m(f'{pre}{pn}{jn}Diff', points(h['difference']) if h else '--')
            m(f'{pre}{pn}{jn}Lo', points(h['cluster95'][0]) if h and h['cluster95'] else '--')
            m(f'{pre}{pn}{jn}Hi', points(h['cluster95'][1]) if h and h['cluster95'] else '--')
            if j != 'J3':
                m(f'{pre}{pn}{jn}Supported', ('supported' if h['supported'] else 'not supported') if h else '--')
            ep = h['exact_paired'] if h else None
            m(f'{pre}{pn}{jn}P', ('--' if not ep or ep.get('p') is None else (f"{ep['p']:.3f}" if ep['p'] >= .001 else '<0.001')))
        for key, cnt in (p.get('changed_judgement') or {}).items():
            said, cls = key.split(' / ')
            m(f'{pre}{pn}Said{word(said)}{word(cls)}', num(cnt))
        u = p.get('usage') if done else None
        m(f'{pre}{pn}MedianS', f"{u['elapsed_s']['median']:.1f}" if u and u.get('elapsed_s') else '--')
        m(f'{pre}{pn}PromptTokMedian', num(int(u['prompt_tokens']['median'])) if u and u.get('prompt_tokens') else '--')
        m(f'{pre}{pn}Refused', num(u['status'].get('http_error', 0)) if u else '--')
        m(f'{pre}{pn}TooLarge', num(u['status'].get('input_too_large', 0)) if u else '--')
        m(f'{pre}{pn}NoTarget', num(u['status'].get('no_target_file', 0)) if u else '--')


def holm_macros(pre, pops):
    """Secondary (R03 review): Holm adjustment of the exact paired p-values over the primary model's J1 and J2 tests
    on every complete population. The registered decision rule stays the cluster interval."""
    tests = []
    for pop, pn in POPS.items():
        p = pops.get(pop, {})
        if not p.get('complete'):
            continue
        for j, jn in (('J1', 'JOne'), ('J2', 'JTwo')):
            tests.append((p['hypotheses'][j]['exact_paired']['p'], f'{pre}{pn}{jn}Holm'))
    tests.sort()
    k, running = len(tests), 0.0
    for i, (p, name) in enumerate(tests):
        running = max(running, min(1.0, (k - i) * p))
        m(name, f'{running:.3f}' if running >= .001 else '<0.001')
    m(f'{pre}HolmTests', str(k))
    m(f'{pre}HolmSignificant', str(sum(1 for i, (p, _) in enumerate(tests)
                                       if max(min(1.0, (k - x) * tests[x][0]) for x in range(i + 1)) < .05)))


def main():
    path = latest()
    raw = path.read_bytes()
    data = json.loads(raw)['data']
    pops = data['populations']
    names = {'reflection/beam-1.0-501b-a23b:free': 'Beam~1.0', 'stepfun/step-3.7-flash:free': 'Step-3.7-Flash',
             'stepfun-ai/step-5-preview': 'Step~5 Preview', 'nvidia/nemotron-3.5-super-vl-120b-a12b': 'Nemotron~3.5 Super'}
    prefixes = {'step': 'Step', 'step5': 'StepFive', 'nemotron': 'Nemo'}  # macro names are letters only
    m('wjModel', names[data.get('model', 'stepfun/step-3.7-flash:free')])
    population_macros('wj', pops)
    holm_macros('wj', pops)
    second = None
    for key, sec in sorted((data.get('secondary') or {}).items()):
        m('wj' + prefixes[key] + 'Model', names[sec['model']])
        population_macros('wj' + prefixes[key], sec['populations'], only_complete=True)
        srep = sec.get('repeat_human_AB')
        if srep:
            m('wj' + prefixes[key] + 'RepN', num(srep['n']))
            m('wj' + prefixes[key] + 'RepSameAll', num(srep['same_placement_range_label']))
        if key == 'nemotron' and all(sec['populations'].get(p, {}).get('complete') for p in POPS):
            second = (names[sec['model']], sec['populations'])
    rep = data.get('repeat_human_AB')
    m('wjRepN', num(rep['n']) if rep else '--')
    m('wjRepSamePlace', num(rep['same_placement']) if rep else '--')
    m('wjRepSameAll', num(rep['same_placement_range_label']) if rep else '--')
    m('wjRepSameAllPct', f"{100 * rep['same_placement_range_label'] / rep['n']:.1f}" if rep else '--')
    seen = set()
    for n, _ in macros:
        assert n not in seen, n
        seen.add(n)
    OUT.mkdir(parents=True, exist_ok=True)
    head = '% Generated by tools/v11/build_wpj_tex.py from ' + path.name + '; do not edit.\n'
    text = head + ''.join(f'\\newcommand{{\\{n}}}{{{v}}}\n' for n, v in macros)
    body = table(pops, second)
    (OUT / 'numbers-wpj.tex').write_text(text, encoding='utf-8')
    (OUT / 'table-llm.tex').write_text(head + body, encoding='utf-8')
    (OUT / 'numbers-wpj-provenance.json').write_text(json.dumps(dict(
        summary=str(path.relative_to(ROOT)).replace('\\', '/'), summary_sha256=hashlib.sha256(raw).hexdigest(), macros=len(macros),
        output_sha256=hashlib.sha256(text.encode()).hexdigest(), tables={'table-llm.tex': hashlib.sha256((head + body).encode()).hexdigest()}),
        indent=1), encoding='utf-8')
    print(f'numbers-wpj.tex: {len(macros)} macros from {path.name}')


if __name__ == '__main__':
    main()
