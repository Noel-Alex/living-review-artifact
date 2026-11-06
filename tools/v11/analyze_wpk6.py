"""WP K6 analysis: six outcomes per method on the suggestion oracle (protocol V12-PROTOCOL-K6.md, D6).

Run from paper-drafts/: python -I -B tools/v11/analyze_wpk6.py  -> evidence/v12-wpk6/summary-<utc>.json
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/v12-wpk6'
METHODS = ('github', 't0.85-deployed', 't0.85-IG+AGi+VW', 'codemapper+quote', 'codemapper+IG+AG', 'codemapper+IG+AGi')
GONE = ('applied-deletion', 'gone-file')
SCORED = ('applied', 'untouched') + GONE
CHANGED = ('applied', 'rewritten') + GONE
CONTRASTS = (('codemapper+IG+AGi', 'codemapper+quote'), ('codemapper+IG+AG', 'codemapper+quote'),
             ('t0.85-IG+AGi+VW', 't0.85-deployed'), ('codemapper+IG+AGi', 't0.85-deployed'), ('codemapper+quote', 'github'),
             ('codemapper+IG+AGi', 'github'))
MEASURES = ('missed', 'unnecessary', 'placement', 'lost', 'silent', 'misdirected', 'gone_kept', 'correct', 'errors')


def wilson(k, n, z=1.959964):
    if not n:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


def github_output(u):
    if u['github_outdated']:
        return dict(label='changed', placement=None, recheck=True)
    if u['github_line'] is None:
        return dict(label='removed', placement=None, recheck=True)
    # Multi-line threads: GitHub's `line` is the last line and `startLine` the first.
    return dict(label='exact', placement=[u['path_c1'] or u['path_c0'], u['github_start'] or u['github_line']], recheck=False)


def events(u, o):
    """Indicator counts (numerator, denominator key) for one unit and one method output."""
    cls, err = u['cls'], o.get('label') == 'execution_error'
    req = bool(o.get('recheck')) or err
    at = None if err else o.get('placement')
    e = Counter()
    e['errors'] += err
    e['n_all'] += 1
    if cls in CHANGED:
        e['n_changed'] += 1
        e['missed'] += not req
    if cls == 'ambiguous':
        e['n_ambiguous'] += 1
        e['ambiguous_request'] += req
        return e
    if cls not in SCORED:
        return e
    e['n_scored'] += 1
    if cls in GONE:
        e['n_gone'] += 1
        wrong = at is not None
        e['gone_kept'] += wrong and not req
        e['correct'] += req and at is None
    else:
        e['n_surv'] += 1
        path, s, end = u['truth']
        if cls == 'applied':
            ok = at is not None and at[0] == path and s <= at[1] <= end
            e['placement_exact'] += at is not None and at[0] == path and at[1] == s
        else:
            e['n_preserved'] += 1
            ok = at is not None and at[0] == path and at[1] == s
            e['unnecessary'] += req
        e['placement'] += ok
        e['lost'] += at is None
        wrong = at is not None and not ok
        want_req = cls == 'applied'
        e['correct'] += ok and req == want_req
    e['silent'] += wrong and not req
    e['misdirected'] += wrong and req
    return e


DENOM = dict(missed='n_changed', unnecessary='n_preserved', placement='n_surv', lost='n_surv', silent='n_scored',
             misdirected='n_scored', gone_kept='n_gone', correct='n_scored', errors='n_all', placement_exact='n_surv',
             ambiguous_request='n_ambiguous')


def wraps(u):
    """The suggestion adds lines around the unchanged quoted lines (normalized O is a contiguous run of S)."""
    o = [x.strip() for x in u['O'].splitlines() if x.strip()]
    s = [x.strip() for x in u['suggestion'].splitlines() if x.strip()]
    return bool(s) and any(s[i:i + len(o)] == o for i in range(len(s) - len(o) + 1))


def mechanisms(units, outs):
    res = {}
    for m in METHODS:
        c = Counter()
        for u in units:
            if events(u, outs[(u['repo'], u['comment_id'])][m])['missed']:
                c['wraps_unchanged_quotation' if (u['cls'] == 'applied' and wraps(u)) else u['cls']] += 1
        res[m] = dict(c)
    return dict(misses_by_mechanism=res, applied_wrapping=sum(u['cls'] == 'applied' and wraps(u) for u in units))


def table(units, outs):
    res = {}
    for m in METHODS:
        c = Counter()
        for u in units:
            c.update(events(u, outs[(u['repo'], u['comment_id'])][m]))
        res[m] = {k: dict(k=c[k], n=c[DENOM[k]], pct=round(100 * c[k] / c[DENOM[k]], 1) if c[DENOM[k]] else None,
                          ci=wilson(c[k], c[DENOM[k]])) for k in DENOM}
    return res


def bootstrap(units, outs, seed=20261031, B=10000):
    by_pr = defaultdict(list)
    for u in units:
        by_pr[(u['repo'], u['pr'])].append(u)
    keys = sorted(by_pr)
    names = sorted({m for p in CONTRASTS for m in p})
    meas = ('missed', 'unnecessary', 'silent', 'misdirected', 'placement', 'lost')
    num = np.zeros((len(keys), len(names), len(meas)))
    den = np.zeros((len(keys), len(meas)))
    for i, k in enumerate(keys):
        for u in by_pr[k]:
            for j, m in enumerate(names):
                e = events(u, outs[(u['repo'], u['comment_id'])][m])
                for q, x in enumerate(meas):
                    num[i, j, q] += e[x]
            e = events(u, outs[(u['repo'], u['comment_id'])][names[0]])
            for q, x in enumerate(meas):
                den[i, q] += e[DENOM[x]]
    rng = np.random.default_rng(seed)
    w = rng.multinomial(len(keys), np.full(len(keys), 1 / len(keys)), size=B).astype(float)
    out = {}
    for a, b in CONTRASTS:
        ia, ib = names.index(a), names.index(b)
        r = {}
        for q, x in enumerate(meas):
            d = den[:, q].sum()
            if not d:
                continue
            diff = (num[:, ia, q] - num[:, ib, q])
            bs = (w @ diff) / np.maximum(w @ den[:, q], 1)
            r[x] = dict(difference_pts=round(100 * diff.sum() / d, 2), ci95_pts=[round(100 * v, 2) for v in np.quantile(bs, [.025, .975])])
        out[f'{a} minus {b}'] = r
    return dict(clusters=len(keys), resamples=B, seed=seed, contrasts=out)


def main():
    units_doc = json.loads((OUT / 'units.json').read_text(encoding='utf-8'))
    rows_doc = json.loads((OUT / 'rows.json').read_text(encoding='utf-8'))
    units = units_doc['units']
    outs = {}
    for r in rows_doc['data']:
        outs[(r['repo'], r['comment_id'])] = r['methods']
    for u in units:
        outs[(u['repo'], u['comment_id'])]['github'] = github_output(u)
    classes = Counter(u['cls'] for u in units)
    by_lang = defaultdict(Counter)
    for u in units:
        by_lang[u['language']][u['cls']] += 1
    summary = dict(
        recorded_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        inputs={p: hashlib.sha256((OUT / p).read_bytes()).hexdigest() for p in ('units.json', 'rows.json', 'selection.json', 'exclusions.json')},
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        n_units=len(units), repositories=sorted({u['repo'] for u in units}), prs=len({(u['repo'], u['pr']) for u in units}),
        classes=dict(classes), classes_by_language={k: dict(v) for k, v in by_lang.items()},
        apply_commit_among_applied=sum(u['apply_suggestion_commit'] for u in units if u['cls'] == 'applied'),
        renamed=sum(bool(u.get('rename')) for u in units),
        overall=table(units, outs),
        by_language={lang: table([u for u in units if u['language'] == lang], outs) for lang in sorted(by_lang)},
        paired=bootstrap(units, outs),
        mechanisms=mechanisms(units, outs))
    name = 'summary-' + time.strftime('%Y%m%dT%H%M%S', time.gmtime()) + '.json'
    (OUT / name).write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(name, summary['n_units'], dict(classes))
    for m in METHODS:
        o = summary['overall'][m]
        print(f"{m:22s} miss {o['missed']['pct']} unn {o['unnecessary']['pct']} place {o['placement']['pct']} "
              f"lost {o['lost']['pct']} silent {o['silent']['pct']} misdir {o['misdirected']['pct']} err {o['errors']['k']}")


if __name__ == '__main__':
    main()
