"""B2 summaries, generated TeX and figures from evidence/v11-wpb2 (derived outputs; rerunnable)."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpa_core import ROOT, read, rate, sha  # noqa: E402
from analyze_wpb import event, denominators, DENOMS  # noqa: E402

OUT = ROOT / 'evidence/v11-wpb2'
TEX = OUT / 'tex'
FIG = OUT / 'figures'
METRICS = ('placement_accuracy', 'range_correct', 'missed', 'wrong_silent', 'wrong', 'lost', 'false_recheck')
SHOW = {'t0.85-deployed': 'Deployed cascade', 't0.85-IG+AG+VW': 'All guards, $\\theta=0.85$', 't0.55-IG+AG+VW': 'All guards, $\\theta=0.55$',
        'cascade_v1': 'Cascade v1', 'tracker_adapter': 'Contextual tracker', 'diff_drift': 'Diff drift', 'quote_exact': 'Exact quote',
        'line_number': 'Line number'}


def summarize(records, method):
    k, d = Counter(), Counter()
    for r in records:
        e = event(r, r['methods'][method])
        k.update(e)
        d.update(denominators(r))
    out = {}
    for m in METRICS:
        out[m] = rate(k[m], d[DENOMS.get(m, 'n')])
    return out


def compound():
    records = read(OUT / 'compound/trials.json')['data']
    completion = read(OUT / 'compound/completion.json')['data']
    methods = sorted(records[0]['methods'])
    res = dict(n=len(records), complete=completion['complete'], audits=completion['generator_audits'], cells={}, by_operator={})
    for seed in sorted({r['seed'] for r in records}):
        for kk in (1, 2, 3, 4):
            sub = [r for r in records if r['seed'] == seed and r['k'] == kk]
            res['cells'][f'{seed}:k={kk}'] = dict(n=len(sub), classes=dict(Counter(r['cls'] for r in sub)),
                                                  methods={m: summarize(sub, m) for m in methods})
    for kk in (1, 2, 3, 4):
        sub = [r for r in records if r['k'] == kk]
        res['cells'][f'pooled:k={kk}'] = dict(n=len(sub), classes=dict(Counter(r['cls'] for r in sub)),
                                              methods={m: summarize(sub, m) for m in methods})
    ops = sorted({o for r in records for o in r['operators']})
    for op in ops:
        sub = [r for r in records if op in r['operators']]
        res['by_operator'][op] = dict(n=len(sub), methods={m: summarize(sub, m) for m in ('t0.85-deployed', 't0.85-IG+AG+VW', 'tracker_adapter', 'cascade_v1')})
    return res


def chains():
    import wpb2_chains as wc
    rows = read(OUT / 'chains/trials.json')['data']
    seq = ('archived-default', 'archived-calibrated', 'v0.85-off', 'v0.85-all', 'v0.55-off', 'v0.55-all')
    direct = ('deployed-default', 'deployed-calibrated', 'v0.85-off', 'v0.85-all', 'v0.55-off', 'v0.55-all')
    res = dict(n=len(rows), exclusions={}, decidable={}, prefixes={})
    every = [r for r in rows if all(r['prefixes'][str(h)]['reference']['status'] == 'ok' for h in wc.PREFIXES)]
    res['decidable_at_every_prefix'] = len(every)
    for h in wc.PREFIXES:
        refs = [r['prefixes'][str(h)]['reference'] for r in rows]
        res['exclusions'][str(h)] = dict(Counter(x.get('reason', x['status']) for x in refs if x['status'] != 'ok'))
        res['decidable'][str(h)] = sum(x['status'] == 'ok' for x in refs)
        cell = {}
        for subset_name, subset in (('decidable', rows), ('every', every)):
            for kind, names in (('sequential', seq), ('direct', direct)):
                for m in names:
                    c, n = Counter(), 0
                    for r in subset:
                        s = wc.score(r, m, h, direct=kind == 'direct')
                        if s is None:
                            continue
                        n += 1
                        c.update(s)
                    cell[f'{subset_name}:{kind}:{m}'] = dict(
                        n=n, accuracy=rate(c['correct'], n), wrong=rate(c['wrong'], n), lost=rate(c['lost'], n),
                        missed_cumulative=rate(c['missed_cumulative'], c['changed']), missed_last=rate(c['missed_last'], c['changed']),
                        wrong_silent_cumulative=rate(c['wrong_silent_cumulative'], n), wrong_silent_last=rate(c['wrong_silent_last'], n),
                        last_exact_wrong=c['last_exact_wrong'], changed=c['changed'])
        res['prefixes'][str(h)] = cell
    return res


def pc(x, nd=1):
    return '--' if x is None or x['rate'] is None else f"{100 * x['rate']:.{nd}f}"


def figures(comp, ch):
    sys.path.insert(0, str(ROOT / 'tools/vendor'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'serif', 'font.size': 8, 'axes.spines.top': False, 'axes.spines.right': False,
                         'pdf.fonttype': 42})
    FIG.mkdir(parents=True, exist_ok=True)
    styles = {'t0.85-deployed': ('k', '-', 'o'), 't0.85-IG+AG+VW': ('0.35', '--', 's'), 'cascade_v1': ('0.55', ':', '^'),
              'tracker_adapter': ('0.2', '-.', 'D')}
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.45))
    for ax, metric, title in zip(axes, ('placement_accuracy', 'missed', 'wrong_silent'),
                                 ('Placement accuracy (%)', 'Missed re-checks (%)', 'Wrong and silent (%)')):
        for m, (col, ls, mk) in styles.items():
            ys = [100 * comp['cells'][f'pooled:k={k}']['methods'][m][metric]['rate'] for k in (1, 2, 3, 4)]
            ax.plot((1, 2, 3, 4), ys, color=col, ls=ls, marker=mk, ms=3.5, lw=1.1, label=SHOW[m])
        ax.set_title(title)
        ax.set_xticks((1, 2, 3, 4))
        ax.set_xlabel('operators composed (k)')
    fig.legend(*axes[0].get_legend_handles_labels(), loc='lower center', ncol=4, frameon=False, fontsize=7)
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    fig.savefig(FIG / 'compound-v11.pdf')
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.45))
    hs = (1, 2, 3, 5, 10)
    lines = {'every:sequential:archived-default': ('Deployed, successive', 'k', '-', 'o'),
             'every:direct:deployed-default': ('Deployed, direct', 'k', ':', 'o'),
             'every:sequential:v0.85-all': ('All guards, successive', '0.45', '--', 's'),
             'every:direct:v0.85-all': ('All guards, direct', '0.45', '-.', 's')}
    for ax, metric, title in zip(axes, ('accuracy', 'missed_cumulative'), ('Endpoint accuracy (%)', 'Missed re-checks, cumulative (%)')):
        for key, (lab, col, ls, mk) in lines.items():
            ax.plot(hs, [100 * ch['prefixes'][str(h)][key][metric]['rate'] for h in hs], color=col, ls=ls, marker=mk, ms=3.5, lw=1.1, label=lab)
        ax.set_xticks(hs)
        ax.set_xlabel('commits from the anchored version (h)')
        ax.set_title(title)
    fig.legend(*axes[0].get_legend_handles_labels(), loc='lower center', ncol=4, frameon=False, fontsize=7)
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    fig.savefig(FIG / 'chains-v11.pdf')
    plt.close(fig)


def tex(comp, ch, ma, sc):
    TEX.mkdir(parents=True, exist_ok=True)
    macros = {}

    def m(name, value):
        assert name.isalpha(), name
        macros[name] = value
    words = {1: 'One', 2: 'Two', 3: 'Three', 4: 'Four'}
    for k in (1, 2, 3, 4):
        cell = comp['cells'][f'pooled:k={k}']
        m(f'bTwoN{words[k]}', f"{cell['n']:,}")
        for mm, short in (('t0.85-deployed', 'Dep'), ('t0.85-IG+AG+VW', 'All'), ('tracker_adapter', 'Trk'), ('cascade_v1', 'Vone')):
            v = cell['methods'][mm]
            m(f'bTwo{short}Acc{words[k]}', pc(v['placement_accuracy']))
            m(f'bTwo{short}Miss{words[k]}', pc(v['missed']))
            m(f'bTwo{short}Silent{words[k]}', pc(v['wrong_silent']))
            m(f'bTwo{short}Range{words[k]}', pc(v['range_correct']))
            m(f'bTwo{short}Lost{words[k]}', pc(v['lost']))
            m(f'bTwo{short}False{words[k]}', pc(v['false_recheck']))
    hw = {1: 'One', 2: 'Two', 3: 'Three', 5: 'Five', 10: 'Ten'}
    m('bTwoChainEvery', f"{ch['decidable_at_every_prefix']:,}")
    for h in (1, 2, 3, 5, 10):
        p = ch['prefixes'][str(h)]
        m(f'bTwoDecidable{hw[h]}', f"{ch['decidable'][str(h)]:,}")
        for key, short in (('every:sequential:archived-default', 'Seq'), ('every:direct:deployed-default', 'Dir'),
                           ('every:sequential:v0.85-all', 'SeqAll'), ('every:direct:v0.85-all', 'DirAll')):
            m(f'bTwo{short}Acc{hw[h]}', pc(p[key]['accuracy']))
            m(f'bTwo{short}Miss{hw[h]}', pc(p[key]['missed_cumulative']))
            m(f'bTwo{short}Silent{hw[h]}', pc(p[key]['wrong_silent_cumulative']))
    p10 = ch['prefixes']['10']
    seq, cal, sall = (p10['every:sequential:archived-default'], p10['every:sequential:archived-calibrated'],
                      p10['every:sequential:v0.55-all'])
    m('bTwoSeqLostTen', pc(seq['lost']))
    m('bTwoSeqWrongTen', pc(seq['wrong']))
    m('bTwoSeqMissLastTen', pc(seq['missed_last']))
    m('bTwoSeqSilentLastTen', pc(seq['wrong_silent_last']))
    m('bTwoSeqLastExactWrongTen', f"{seq['last_exact_wrong']:,}")
    m('bTwoChangedTen', f"{seq['changed']:,}")
    m('bTwoCalAccTen', pc(cal['accuracy']))
    m('bTwoCalWrongTen', pc(cal['wrong']))
    m('bTwoCalMissTen', pc(cal['missed_cumulative']))
    m('bTwoCalSilentTen', pc(cal['wrong_silent_cumulative']))
    m('bTwoCalSilentLastTen', pc(cal['wrong_silent_last']))
    m('bTwoCalLastExactWrongTen', f"{cal['last_exact_wrong']:,}")
    m('bTwoCalAllAccTen', pc(sall['accuracy']))
    m('bTwoCalAllWrongTen', pc(sall['wrong']))
    m('bTwoSeqAllLostTen', pc(p10['every:sequential:v0.85-all']['lost']))
    m('bTwoSeqAllWrongTen', pc(p10['every:sequential:v0.85-all']['wrong']))
    kw = {1: 'One', 2: 'Two', 3: 'Three', 5: 'Five', 8: 'Eight', 12: 'Twelve'}
    m('bTwoDistinctObs', f"{ma['distinct_observations']:,}")
    for k, c in ma['ks'].items():
        k = int(k)
        v = c['methods']['t0.85-deployed']
        m(f'bTwoGroups{kw[k]}', f"{c['groups']:,}")
        m(f'bTwoGroupPairs{kw[k]}', f"{c['pairs_supporting']:,}")
        m(f'bTwoIssueRecheck{kw[k]}', pc(v['recheck_rate']))
        m(f'bTwoNonPrimary{kw[k]}', pc(v['nonprimary_share_of_rechecks']))
        m(f'bTwoPrimaryMiss{kw[k]}', pc(v['primary_only_missed_rate']))
        m(f'bTwoAnyMiss{kw[k]}', pc(v['any_rule_missed_rate']))
        m(f'bTwoAllPresRecheck{kw[k]}', pc(c['methods']['t0.85-IG+AG+VW']['recheck_rate_all_preserved']))
    if sc:
        for name, short in (('django', 'Dj'), ('cpython-Lib', 'Py')):
            info = sc['corpora'][name]
            m(f'bTwo{short}Files', f"{info['files_new']:,}")
            m(f'bTwo{short}Lines', f"{info['lines_new']:,}")
            for meth, ms in (('deployed', 'Dep'), ('variant', 'All')):
                r = info['results'][meth]['1000']
                m(f'bTwo{short}{ms}AnchorMed', f"{1000 * r['per_anchor_p50']:.1f}")
                m(f'bTwo{short}{ms}AnchorPninetyfive', f"{1000 * r['per_anchor_p95']:.1f}")
                m(f'bTwo{short}{ms}ComposeThousand', f"{r['composition_p50']:.1f}")
                m(f'bTwo{short}{ms}PeakMB', f"{info['results'][meth]['peak_traced_bytes']['bytes'] / 2**20:.0f}")
                if meth == 'deployed':
                    m(f'bTwo{short}RemovedCount', str(r['tier_counts'].get('removed-after-all-tiers', 0)))
                    m(f'bTwo{short}RemovedShare', f"{100 * r['tier_time_share'].get('removed-after-all-tiers', 0):.0f}")
                a = info['adversarial_tier4'][meth]['100']
                m(f'bTwo{short}{ms}AbsentMed', f"{1000 * a['per_anchor_p50']:.0f}")
    (TEX / 'numbers-wpb2.tex').write_text('% Generated by tools/v11/analyze_wpb2.py; do not edit.\n' +
                                          '\n'.join('\\newcommand{\\' + k + '}{' + v + '}' for k, v in macros.items()) + '\n', encoding='utf-8')
    # Compound table
    rows = []
    for k in (1, 2, 3, 4):
        cell = comp['cells'][f'pooled:k={k}']
        for mm in ('t0.85-deployed', 't0.85-IG+AG+VW', 't0.55-IG+AG+VW', 'cascade_v1', 'tracker_adapter', 'diff_drift'):
            v = cell['methods'][mm]
            rows.append(f"{k if mm == 't0.85-deployed' else ''} & {SHOW[mm]} & {pc(v['placement_accuracy'])} & {pc(v['range_correct'])} & "
                        f"{pc(v['missed'])} & {pc(v['wrong_silent'])} & {pc(v['lost'])} \\\\" + (' \\midrule' if mm == 'diff_drift' and k < 4 else ''))
    (TEX / 'table-compound.tex').write_text(
        '% Generated by tools/v11/analyze_wpb2.py; do not edit.\n\\begin{table}[t]\n\\caption{Compound Edits: Both Seeds Pooled}\\label{tab:compound}\n'
        '\\centering\\footnotesize\\setlength{\\tabcolsep}{3pt}\n\\begin{tabular}{@{}rlrrrrr@{}}\\toprule\n'
        '$k$ & Method & Place & Range & Missed & Silent & Lost \\\\ \\midrule\n' + '\n'.join(rows) +
        '\n\\bottomrule\n\\end{tabular}\n\\tablenote{}{Percentages. Place: file and start among surviving targets. Range: exact file/start/end '
        '(blank for line-only methods, scored as incorrect). Missed: changed targets without a re-check request. Silent: wrong placement without a request.}\n\\end{table}\n',
        encoding='utf-8')
    return macros


def main():
    comp, ch = compound(), chains()
    ma = read(OUT / 'multianchor/summary.json')['data']
    sc = read(OUT / 'scaling/results.json')['data'] if (OUT / 'scaling/results.json').exists() else None
    summary = dict(compound=comp, chains=ch, multianchor=ma, scaling=sc)
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    figures(comp, ch)
    macros = tex(comp, ch, ma, sc)
    inputs = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(OUT.rglob('*.json')) if 'external' not in p.parts and p.name != 'provenance.json'}
    (TEX / 'provenance.json').write_text(json.dumps(dict(generator='tools/v11/analyze_wpb2.py', generator_sha256=sha(Path(__file__)),
                                                         inputs=inputs, macros=macros), indent=1), encoding='utf-8')
    print(len(macros), 'macros')


if __name__ == '__main__':
    main()
