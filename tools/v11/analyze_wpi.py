"""WP I reporting (written after the freeze; implements only the registered measures).

python -I -B tools/v11/analyze_wpi.py
"""
from collections import Counter, defaultdict
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpi_core import OUT, ROOT, read, write, rate, verify_freeze, LOCATORS, LAYERS  # noqa: E402
from analyze_wpc import ev  # noqa: E402
from analyze_wpb import denominators, DENOMS, exact_binomial  # noqa: E402

MEASURES = ('accuracy', 'placement_accuracy', 'missed', 'false_recheck', 'wrong', 'wrong_silent', 'wrong_with_recheck',
            'lost', 'gone_correct', 'range_correct')
PAIR = ('accuracy', 'missed', 'wrong_silent', 'lost', 'false_recheck')
CASCADE = ('deployed_native', 't0.85-deployed', 't0.85-AG', 't0.85-AG2', 't0.85-IG+AG', 't0.85-IG+AG2',
           't0.85-IG+AG+VW', 't0.85-IG+AG2+VW', 't0.55-IG+AG+VW', 't0.55-IG+AG2+VW',
           't0.85-AGi', 't0.85-IG+AGi+VW', 't0.55-IG+AGi+VW')
TRANSFER = tuple(f'{b}+{l}' for b in LOCATORS for l in LAYERS + ('AGi', 'IG+AGi')) + ('cmhybrid+quote', 'cmhybrid+AG2', 'cmhybrid+IG+AG2', 'cmhybrid+IG+AGi')
CONTRASTS = [('cmhybrid+IG+AGi', 'cmhybrid+quote'), ('cmhybrid+IG+AGi', 'deployed_native'), ('cmhybrid+IG+AGi', 't0.85-IG+AGi+VW'),
             ('codemapper+IG+AGi', 'deployed_native'), ('codemapper+IG+AGi', 'codemapper+quote'), ('codemapper+IG+AGi', 'codemapper+IG+AG'), ('tracker+IG+AGi', 'tracker+IG+AG'),
             ('t0.85-IG+AGi+VW', 't0.85-IG+AG+VW'), ('t0.55-IG+AGi+VW', 't0.55-IG+AG+VW'), ('t0.85-AGi', 't0.85-AG'), ('codemapper+AGi', 'codemapper+AG'),
             ('codemapper+IG+AG2', 'codemapper+quote'), ('cmhybrid+IG+AG2', 'cmhybrid+quote'), ('cmhybrid+IG+AG2', 'deployed_native'), ('cmhybrid+IG+AG2', 't0.85-IG+AG2+VW'), ('codemapper+IG+AG', 'codemapper+quote'),
             ('codemapper+IG+AG2', 'codemapper+IG+AG'), ('codemapper+AG2', 'codemapper+AG'),
             ('tracker+IG+AG2', 'tracker+quote'), ('tracker+IG+AG2', 'tracker+IG+AG'),
             ('gumtree+IG+AG2', 'gumtree+quote'), ('gumtree+IG+AG2', 'gumtree+IG+AG'),
             ('hybrid+IG+AG2', 'hybrid+IG+AG'),
             ('t0.85-IG+AG2+VW', 't0.85-IG+AG+VW'), ('t0.55-IG+AG2+VW', 't0.55-IG+AG+VW'), ('t0.85-AG2', 't0.85-AG'),
             ('codemapper+IG+AG2', 'deployed_native'), ('t0.85-IG+AG2+VW', 'deployed_native'),
             ('codemapper+IG+AG2', 't0.85-IG+AG2+VW')]
HEADLINE = ('stress:indentation', 'stress:duplicates', 'stress:short', 'controlled:replication', 'real', 'real:oss:targeted',
            'external', 'external:human-AB', 'external:human-AB:non-Python-code', 'compound', 'compound:k=1', 'compound:k=4',
            'students', 'students:targeted', 'fresh:indentation', 'fresh:duplicates', 'fresh:short', 'fresh:compound',
            'fresh:compound:k=1', 'fresh:compound:k=4', 'fresh')


def load(stage, pattern):
    completion = read(OUT / stage / 'completion.json')['data']
    paths = sorted((OUT / stage).glob(pattern))
    rows = [r for p in paths for r in read(p)['data']]
    assert len(rows) == completion['n'], (stage, len(rows), completion['n'])
    extra = []
    if stage == 'transfer' and not completion['complete']:
        # Amendment 2: only the external cascade gate may fail; its rows are recomputed in scope.
        bad = {(r['suite'], m['method']) for r in rows for m in r['gate_mismatch']}
        assert bad <= {('external', 't0.85-IG+AG+VW'), ('external', 't0.55-IG+AG+VW')}, bad
        ext = read(OUT / 'external-cascade/completion.json')['data']
        assert ext['complete'], 'external cascade gate'
        fixed = {r['id']: r['methods'] for r in read(OUT / 'external-cascade/rows.json')['data']}
        for r in rows:
            if r['suite'] == 'external':
                r['methods'].update(fixed.pop(r['id']))
        assert not fixed
        extra = [OUT / 'external-cascade/rows.json', OUT / 'external-cascade/completion.json', OUT / 'transfer/gate.json']
    elif stage == 'chains-agi' and not completion['complete']:
        # Amendment 8: only CodeMapper (nondeterministic) may fail this gate; the caller checks the methods.
        assert len(rows) == 4000
        extra = [OUT / stage / 'gate.json']
    else:
        assert completion['complete'], stage
    return rows, paths + [OUT / stage / 'completion.json'] + extra


def add_cmhybrid(r):
    """Amendment 1: CodeMapper with the cascade's cross-file fallback after a completed no-match."""
    m = r['methods']
    fallback = (m['codemapper+quote']['label'] == 'removed' and m['codemapper+quote']['placement'] is None
                and m['t0.85-deployed'].get('tier') == 'cross_exact')
    r['cmhybrid_fallback'] = fallback
    if fallback:
        m['cmhybrid+quote'] = m['t0.85-deployed']
        m['cmhybrid+AG2'] = m['t0.85-AG2']
        m['cmhybrid+IG+AG2'] = m['t0.85-IG+AG2']
    else:
        for layer in ('quote', 'AG2', 'IG+AG2'):
            m['cmhybrid+' + layer] = m['codemapper+' + layer]
    # Post-hoc composition P1 (exploratory, chosen after outcomes were read): the same fallback with the AGi layers.
    if 'codemapper+IG+AGi' in m and 't0.85-IG+AGi+VW' in m:
        m['cmhybrid+IG+AGi'] = m['t0.85-IG+AGi+VW'] if fallback else m['codemapper+IG+AGi']


def strata_of(r, origin):
    if origin == 'transfer':
        if r['suite'] in ('indentation', 'duplicates', 'short'):
            names = ['stress', 'stress:' + r['suite'], 'stress:' + r['suite'] + ':' + r['op']]
        elif r['suite'] == 'original':
            names = ['controlled:replication', 'controlled:replication:' + r['op']]
        elif r['suite'] == 'real':
            names = ['real', 'real:' + r['group'], 'real:' + r['sample'], 'real:' + r['group'] + ':' + r['sample'],
                     'real:project:' + r['repo']]
        else:
            names = ['external', 'external:' + r['dataset']]
            if r['dataset'] in ('annotation_a', 'annotation_b'):
                names += ['external:human-AB']
                if r['language'] != 'Python' and not r['language'].startswith('Other'):
                    names += ['external:human-AB:non-Python-code']
        return names
    if origin == 'compound':
        return ['compound', 'compound:' + r['op']]
    if origin == 'students':
        return ['students', 'students:' + r['sample'], 'students:horizon:' + str(r['horizon']), 'students:repo:' + r['repo']]
    s = r['suite']
    names = ['fresh', 'fresh:' + s, 'fresh:' + s + ':' + r['op']]
    return names


def cluster_key(r, origin):
    if origin in ('students',) or (origin == 'transfer' and r['suite'] in ('real', 'external')):
        return r['pair']
    return r['source_file']


def metric(rows, name):
    c, d = Counter(), Counter()
    for r in rows:
        o = r['methods'][name]
        c.update(ev(r, o))
        d.update(denominators(r))
    return dict(n=len(rows), execution_errors=c['failure'], counts=dict(c), denominators=dict(d),
                **{m: rate(c[m], d[DENOMS.get(m, 'n')]) for m in MEASURES})


def paired(rows, keys, contrasts, seed=20261031, resamples=10000):
    names = sorted({m for pair in contrasts for m in pair})
    clusters = defaultdict(lambda: np.zeros((len(PAIR), len(names) + 1), dtype=np.int64))
    disc = defaultdict(lambda: [0, 0])
    for r, key in zip(rows, keys):
        ds = denominators(r)
        es = {m: ev(r, r['methods'][m]) for m in names}
        for j, m in enumerate(PAIR):
            den = ds[DENOMS.get(m, 'n')]
            clusters[key][j] += [den] + [es[n][m] for n in names]
            if den:
                for a, b in contrasts:
                    x, y = es[a][m], es[b][m]
                    disc[a, b, m][0] += int(x and not y)
                    disc[a, b, m][1] += int(y and not x)
    matrix = np.stack(list(clusters.values()))
    tot = matrix.sum(axis=0)
    rng = np.random.default_rng(seed)
    boots = []
    for start in range(0, resamples, 200):
        w = rng.multinomial(len(matrix), np.full(len(matrix), 1 / len(matrix)), size=min(200, resamples - start))
        sums = np.einsum('bc,cmn->bmn', w, matrix, optimize=True)
        with np.errstate(divide='ignore', invalid='ignore'):
            boots.append(sums[:, :, 1:] / sums[:, :, :1])
    boots = np.concatenate(boots)
    out = {}
    for a, b in contrasts:
        ia, ib = names.index(a), names.index(b)
        res = {}
        for j, m in enumerate(PAIR):
            vals = boots[:, j, ia] - boots[:, j, ib]
            fin = vals[np.isfinite(vals)]
            res[m] = dict(n=int(tot[j, 0]), difference=float((tot[j, ia + 1] - tot[j, ib + 1]) / tot[j, 0]) if tot[j, 0] else None,
                          cluster95=np.quantile(fin, [.025, .975]).tolist() if len(fin) else None,
                          exact_paired=exact_binomial(*disc[a, b, m]))
        out[f'{a} minus {b}'] = dict(clusters=len(matrix), resamples=resamples, seed=seed, metrics=res)
    return out


def verdicts(pairs, contrast, rule):
    """H1/H2 descriptive and supported flags for one contrast in one population."""
    p = pairs.get(contrast)
    if p is None:
        return None
    m = p['metrics']
    d = {k: m[k]['difference'] for k in PAIR}
    if any(d[k] is None for k in ('missed', 'wrong_silent')):
        safety_ok = False
    else:
        safety_ok = d['missed'] <= 0 and d['wrong_silent'] <= 0
    if rule == 'H1':
        descriptive = safety_ok and (d['missed'] < 0 or d['wrong_silent'] < 0)
    else:  # H2: fewer false re-checks, safety no worse
        descriptive = safety_ok and d['false_recheck'] is not None and d['false_recheck'] < 0
    upper = all(m[k]['cluster95'] is not None and m[k]['cluster95'][1] <= 0 for k in ('missed', 'wrong_silent'))
    if rule == 'H2':
        upper = upper and m['false_recheck']['cluster95'] is not None and m['false_recheck']['cluster95'][1] < 0
    return dict(descriptive=descriptive, supported=bool(descriptive and upper), differences=d)


# ---------------- chains ----------------
CHAIN_METHODS = ('v0.85-off', 'v0.85-all', 'v0.85-all2', 'v0.55-all2', 'cm-seq', 'cm-seq-g')
# Amendment 7: the recommended guard AGi on the same chains (stage chains-agi).
CHAIN_METHODS_I = ('v0.85-alli', 'v0.55-alli', 'cm-seq-gi')
CHAIN_MEASURES = ('correct', 'wrong', 'lost', 'missed_cumulative', 'missed_last', 'wrong_silent_cumulative',
                  'wrong_silent_last', 'last_exact_wrong')


def chain_analysis(rows, agi=False):
    import wpb2_chains as wc
    # Amendment 8: in the AGi analysis every CodeMapper trace comes from the chains-agi run (no AG2 CodeMapper traces).
    bases = tuple(b for b in CHAIN_METHODS if b != 'cm-seq-g') + CHAIN_METHODS_I if agi else CHAIN_METHODS
    methods = [m for base in bases for m in (base, base + '-id')]
    methods += [f'{b}-id{f:.1f}' for b in bases if not b.startswith('cm') for f in (.3, .7)]
    out = {}
    for h in (1, 2, 3, 5, 10):
        res = {}
        for m in methods + (['cm-direct', 'cm-direct-gi'] if agi else ['cm-direct', 'cm-direct-g']):
            c, decidable = Counter(), 0
            for r in rows:
                s = wc.score(r, m, h, direct=m.startswith('cm-direct'))
                if s is None:
                    continue
                decidable += 1
                c.update(s)
            res[m] = dict(decidable=decidable, counts=dict(c),
                          **{k: rate(c[k], c['changed'] if k.startswith('missed') else decidable) for k in CHAIN_MEASURES})
        out[str(h)] = res
    # Paired chain bootstrap at h=10 for the identity rule.
    contrasts = [(b + '-id', b) for b in bases]
    if not agi:
        contrasts += [('cm-seq-g', 'v0.85-all2'), ('cm-seq-g-id', 'v0.85-all2-id')]
    else:
        contrasts += [('cm-seq-gi', 'v0.85-alli'), ('cm-seq-gi-id', 'v0.85-alli-id'), ('v0.55-alli-id', 'v0.55-all2-id')]
    keep = [r for r in rows if wc.score(r, 'v0.85-off', 10) is not None]
    rng = np.random.default_rng(20261031)
    names = sorted({m for p in contrasts for m in p})
    mat = np.array([[[wc.score(r, m, 10)[k] for k in CHAIN_MEASURES] + [wc.score(r, m, 10)['changed']] for m in names] for r in keep])
    boot = {}
    flat = mat.reshape(len(keep), -1).astype(np.float64)
    parts = []
    for start in range(0, 10000, 500):
        w = rng.multinomial(len(keep), np.full(len(keep), 1 / len(keep)), size=500).astype(np.float64)
        parts.append(w @ flat)
    sums = np.concatenate(parts).reshape(10000, len(names), -1)  # (B, methods, measures+1)
    for a, b in contrasts:
        ia, ib = names.index(a), names.index(b)
        res = {}
        for j, k in enumerate(CHAIN_MEASURES):
            denom = sums[:, ia, -1] if k.startswith('missed') else len(keep)
            with np.errstate(divide='ignore', invalid='ignore'):
                vals = (sums[:, ia, j] - sums[:, ib, j]) / denom
            fin = vals[np.isfinite(vals)]
            x, y = mat[:, ia, j], mat[:, ib, j]
            res[k] = dict(difference=float((x.sum() - y.sum()) / (mat[:, ia, -1].sum() if k.startswith('missed') else len(keep))),
                          cluster95=np.quantile(fin, [.025, .975]).tolist(), exact_paired=exact_binomial(int(((x == 1) & (y == 0)).sum()), int(((y == 1) & (x == 0)).sum())))
        boot[f'{a} minus {b}'] = dict(chains=len(keep), resamples=10000, seed=20261031, metrics=res)
    return dict(prefixes=out, h10_contrasts=boot)


def main():
    verify_freeze()
    data, inputs = {}, []
    for stage, pattern, origin in (('transfer', 'rows-*.json', 'transfer'), ('compound', 'rows.json', 'compound'),
                                   ('students2', 'rows.json', 'students'), ('fresh', 'rows-*.json', 'fresh')):
        if not (OUT / stage / 'completion.json').exists():
            print('skip', stage, flush=True)
            continue
        rows, paths = load(stage, pattern)
        inputs += paths
        agi_rows = {r['id']: r['methods'] for p in sorted((OUT / 'agi').glob(stage + '-*.json')) for r in read(p)['data']}
        assert len(agi_rows) == len(rows), (stage, len(agi_rows), len(rows))
        inputs += sorted((OUT / 'agi').glob(stage + '-*.json'))
        for r in rows:
            r['methods'].update(agi_rows[r['id']])
        for r in rows:
            if origin in ('students', 'compound', 'fresh'):
                r['methods']['deployed_native'] = r['methods']['t0.85-deployed']
            add_cmhybrid(r)
            for name in strata_of(r, origin):
                data.setdefault(name, (origin, []))[1].append(r)
    summaries, pairs, hyp = {}, {}, []
    for name, (origin, rows) in sorted(data.items()):
        avail = [m for m in CASCADE + TRANSFER if all(r['methods'].get(m) is not None for r in rows)]
        summaries[name] = dict(n=len(rows), origin=origin, methods={m: metric(rows, m) for m in avail})
        if name in HEADLINE:
            cs = [c for c in CONTRASTS if c[0] in avail and c[1] in avail]
            pairs[name] = paired(rows, [cluster_key(r, origin) for r in rows], cs)
            for a, b in cs:
                plain_ag = 'AG' in b and 'AG2' not in b and 'AGi' not in b
                rule = 'H1' if b.endswith('+quote') else 'H2' if (('AG2' in a or 'AGi' in a) and plain_ag) else None
                if a == 'cmhybrid+IG+AGi':
                    rule = None  # post-hoc composition P1: descriptive only
                if rule:
                    v = verdicts(pairs[name], f'{a} minus {b}', rule)
                    hyp.append(dict(population=name, hypothesis=rule, contrast=f'{a} minus {b}', held_out=name.startswith('fresh'), **v))
            print('paired', name, len(rows), flush=True)
    result = dict(strata=summaries, paired=pairs, hypotheses=hyp)
    if (OUT / 'chains/completion.json').exists():
        rows, paths = load('chains', 'rows.json')
        inputs += paths
        result['chains'] = chain_analysis(rows)
        if (OUT / 'chains-agi/completion.json').exists():
            # Amendment 8: the CodeMapper gate failed on 3 chains through CodeMapper nondeterminism (cascade gate passed).
            gate = read(OUT / 'chains-agi/gate.json')['data']
            assert gate['rows'] == 4000 and all(g['method'].startswith('cm-') for g in gate['first']), 'chains-agi cascade gate'
            more, paths = load('chains-agi', 'rows.json')
            inputs += paths
            old = {r['row']: r for r in rows}
            for r in more:
                o = old[r['row']]
                for k in o:
                    if k.startswith(('v0.85-all', 'v0.55-all2')) and not k.startswith('v0.85-alli'):
                        r[k] = o[k]  # deterministic cascade AG/AG2 traces from the chains stage
            result['chains_agi'] = chain_analysis(more, agi=True)
            result['chains_agi']['gate'] = dict(mismatches=gate['mismatches'], chains=sorted({g['row'] for g in gate['first']}))
    write(f'summary-{__import__("datetime").datetime.now().strftime("%Y%m%dT%H%M%S")}.json', result, inputs + [Path(__file__)])
    print('WP I summary written', flush=True)


if __name__ == '__main__':
    main()
