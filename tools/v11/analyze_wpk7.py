"""WP K7 analysis: six outcomes per method on ReviewAnchorBench (protocol review/V12-PROTOCOL-K7.md).

Run from paper-drafts/: python -I -B tools/v11/analyze_wpk7.py  -> evidence/v12-wpk7/summary-<utc>.json
Scoring reuses analyze_wpk6.events unchanged. rab-cascade rows are the benchmark's released predictions, re-scored.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_wpk6 import events, DENOM, wilson  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/v12-wpk7'
PKG = OUT / 'download/pkg/ReviewAnchorBench_Replication_Package_1.1.0'
RUN = ('t0.85-deployed', 't0.85-IG+AGi+VW', 'codemapper+quote', 'codemapper+IG+AG', 'codemapper+IG+AGi')
METHODS = RUN + ('rab-cascade',)
RECORDS = dict(population='evidence/population_component_records_v3.json', heldout='evidence/hard_component_records_v3.json')
CONTRASTS = (('t0.85-IG+AGi+VW', 't0.85-deployed'), ('codemapper+IG+AGi', 'codemapper+quote'),
             ('t0.85-IG+AGi+VW', 'rab-cascade'), ('codemapper+IG+AGi', 'rab-cascade'))
MEAS = ('missed', 'silent', 'unnecessary', 'ambiguous_request', 'placement', 'lost', 'misdirected', 'gone_kept')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def rab_output(path, pred):
    st, state, rng = pred['status'], pred.get('predicted_state'), pred.get('predicted_range')
    if st == 'LOCATED':
        return dict(label='rab-' + str(state).lower(), placement=[path, rng[0]], recheck=state != 'PREIMAGE')
    return dict(label='rab-' + st.lower(), placement=None, recheck=True)


def scored_unit(u):
    o = u['oracle_range']
    return dict(cls=u['cls'], truth=(u['path'], o[0], o[1]) if o else None)


def table(units, outs, methods):
    res = {}
    for m in methods:
        c = Counter()
        for u in units:
            if m in outs[u['case']]:
                c.update(events(scored_unit(u), outs[u['case']][m]))
        res[m] = {k: dict(k=c[k], n=c[DENOM[k]], pct=round(100 * c[k] / c[DENOM[k]], 2) if c[DENOM[k]] else None,
                          ci=wilson(c[k], c[DENOM[k]])) for k in DENOM}
    return res


def by_family(units, outs, methods):
    res = {}
    for fam in sorted({u['family'] for u in units}):
        sub = [u for u in units if u['family'] == fam]
        t = table(sub, outs, methods)
        res[fam] = {m: {k: t[m][k] for k in ('missed', 'unnecessary', 'silent', 'placement', 'ambiguous_request', 'errors')
                        if t[m][k]['n']} for m in methods}
        if fam == 'WHITESPACE_INSIDE':  # descriptive only: placement at oracle start and request rate
            for m in methods:
                rows = [outs[u['case']][m] for u in sub if m in outs[u['case']]]
                n = len(rows)
                at = sum(1 for o, u in zip(rows, sub) if o.get('placement') and o['placement'][1] == u['oracle_range'][0])
                rq = sum(1 for o in rows if o.get('recheck'))
                res[fam][m] = dict(n=n, placement_at_start=at, requests=rq)
    return res


def bootstrap(units, outs, seed=20261106, B=10000):
    by_repo = defaultdict(list)
    for u in units:
        by_repo[u['repo']].append(u)
    keys = sorted(by_repo)
    names = sorted({m for p in CONTRASTS for m in p})
    num = np.zeros((len(keys), len(names), len(MEAS)))
    den = np.zeros((len(keys), len(MEAS)))
    for i, k in enumerate(keys):
        for u in by_repo[k]:
            su = scored_unit(u)
            for j, m in enumerate(names):
                e = events(su, outs[u['case']][m])
                for q, x in enumerate(MEAS):
                    num[i, j, q] += e[x]
            e = events(su, outs[u['case']][names[0]])
            for q, x in enumerate(MEAS):
                den[i, q] += e[DENOM[x]]
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(B, len(keys)))
    res = {}
    for a, b in CONTRASTS:
        ja, jb = names.index(a), names.index(b)
        res[f'{a} - {b}'] = {}
        for q, x in enumerate(MEAS):
            d = den[:, q]
            if d.sum() == 0:
                continue
            point = 100 * (num[:, ja, q].sum() - num[:, jb, q].sum()) / d.sum()
            na, nb, dd = num[idx, ja, q].sum(1), num[idx, jb, q].sum(1), d[idx].sum(1)
            ok = dd > 0
            diff = 100 * (na[ok] - nb[ok]) / dd[ok]
            res[f'{a} - {b}'][x] = dict(diff=round(point, 2), ci=[round(float(np.percentile(diff, 2.5)), 2),
                                                                   round(float(np.percentile(diff, 97.5)), 2)])
    return dict(seed=seed, B=B, clusters=len(keys), contrasts=res)


def codemapper_agreement(units, outs):
    """Start-line agreement between this run's raw CodeMapper and the benchmark's released CodeMapper records."""
    rel = json.loads((PKG / 'evidence/codemapper_population_v3.json').read_text(encoding='utf-8'))['records']
    theirs = {r['benchmark_case_id']: r['prediction'] for r in rel}
    c = Counter()
    for u in units:
        if u['stratum'] != 'population' or u['status'] != 'ok' or u['case'] not in theirs:
            continue
        ours = outs[u['case']].get('codemapper', {})
        tp = theirs[u['case']]
        ot = (ours.get('placement') or [None, None])[1] if ours.get('label') != 'execution_error' else 'error'
        th = (tp.get('predicted_range') or [None])[0] if tp.get('status') == 'LOCATED' else None
        c['n'] += 1
        c['both_none'] += ot is None and th is None
        c['same_start'] += ot is not None and ot == th
        c['ours_error'] += ot == 'error'
    return dict(c)


def exploratory(units, outs):
    """Amendment 1 (post-hoc, descriptive): where duplicated pre-images are placed; why moved blocks are requested."""
    meta = {}
    for _, rel in (('p', 'results/review_anchor_population_sampled_benchmark_v3.json'), ('h', 'results/review_anchor_benchmark_v1.json')):
        for c in json.loads((PKG / rel).read_text(encoding='utf-8'))['cases']:
            meta[c['benchmark_case_id']] = c
    dup, mv = defaultdict(Counter), defaultdict(Counter)
    for u in units:
        c = meta[u['case']]
        s, e = c['source_range']
        if u['family'] == 'DUPLICATE_PREIMAGE':
            d = c['parameters']['duplicate_insert_before_line']
            orig = s + (e - s + 1) if d <= s else s
            for m in RUN:
                o = outs[u['case']][m]
                p = o.get('placement')
                where = 'none' if not p else 'original' if p[1] == orig else 'inserted' if p[1] == d else 'other'
                dup[f"{u['stratum']}/{m}"][where + ('+request' if o.get('recheck') else '')] += 1
        if u['family'] == 'BLOCK_MOVE':
            for m in RUN:
                o = outs[u['case']][m]
                if o.get('recheck'):
                    mv[f"{u['stratum']}/{m}"]['+'.join(sorted(o.get('reasons') or [])) or o.get('label')] += 1
                mv[f"{u['stratum']}/{m}"]['n'] += 1
    return dict(duplicate_placement={k: dict(v) for k, v in dup.items()},
                block_move_requests={k: dict(v) for k, v in mv.items()})


def main():
    meta = json.loads((OUT / 'units.json').read_text(encoding='utf-8'))
    allu = meta['units']
    rows = json.loads((OUT / 'rows.json').read_text(encoding='utf-8'))
    comp = json.loads((OUT / 'completion.json').read_text(encoding='utf-8'))
    assert rows['units_sha256'] == sha(OUT / 'units.json') and comp['complete']
    outs = defaultdict(dict)
    for r in rows['data']:
        outs[r['case']].update(r['methods'])
    for stratum, rel in RECORDS.items():
        recs = json.loads((PKG / rel).read_text(encoding='utf-8'))['records']
        path = {u['case']: u['path'] for u in allu if u['stratum'] == stratum}
        for r in recs:
            if r['method'] == 'FULL_DUAL_ANCHOR_CASCADE_V3' and r['benchmark_case_id'] in path:
                outs[r['benchmark_case_id']]['rab-cascade'] = rab_output(path[r['benchmark_case_id']], r['prediction'])
    res = dict(protocol_sha256=sha(ROOT / 'review/V12-PROTOCOL-K7.md'), rows_sha256=sha(OUT / 'rows.json'),
               units_sha256=sha(OUT / 'units.json'), code_sha256=rows['code_sha256'],
               record_sha256={k: sha(PKG / v) for k, v in RECORDS.items()},
               status_counts={f'{a}/{b}': n for (a, b), n in Counter((u['stratum'], u['status']) for u in allu).items()},
               strata={})
    for stratum in ('population', 'heldout'):
        ok = [u for u in allu if u['stratum'] == stratum and u['status'] == 'ok']
        every = [u for u in allu if u['stratum'] == stratum]
        missing = [u for u in every if 'rab-cascade' not in outs[u['case']]]
        assert not missing, (stratum, len(missing))
        res['strata'][stratum] = dict(
            cases=len(ok), anchors=len({u['anchor'] for u in ok}), repos=len({u['repo'] for u in ok}),
            seven_family=table(ok, outs, METHODS),
            seven_family_by_family=by_family(ok, outs, METHODS),
            rab_all_families=table([u for u in every if u['cls'] != 'whitespace'], outs, ('rab-cascade',)),
            rab_all_by_family=by_family(every, outs, ('rab-cascade',)),
            rab_all_cases=len(every),
            bootstrap=bootstrap(ok, outs))
    res['codemapper_agreement_population'] = codemapper_agreement(allu, outs)
    res['exploratory_amendment_1'] = exploratory([u for u in allu if u['status'] == 'ok'], outs)
    stamp = time.strftime('%Y%m%dT%H%M%S', time.gmtime())
    (OUT / f'summary-{stamp}.json').write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')
    print('wrote', f'summary-{stamp}.json')


if __name__ == '__main__':
    main()
