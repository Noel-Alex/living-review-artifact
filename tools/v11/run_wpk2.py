"""WP K2 runner and analysis (protocol review/V12-PROTOCOL-K2.md).

Run from paper-drafts/ with the CodeMapper interpreter:
  tools/v11-ext/codemapper/venv/Scripts/python.exe -I -B tools/v11/run_wpk2.py freeze
  tools/v11-ext/codemapper/venv/Scripts/python.exe -I -B tools/v11/run_wpk2.py run [--workers 12] [--limit N]
  tools/v11-ext/codemapper/venv/Scripts/python.exe -I -B tools/v11/run_wpk2.py analyze
Methods: deployed cascade; cascade IG+AG+VW and IG+AGi+VW at theta 0.85; CodeMapper with quote, IG+AG and IG+AGi
layers, all CodeMapper layers from one CodeMapper execution per trial. Execution errors are kept as outcomes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/v12-wpk2'
PROTOCOL = ROOT / 'review/V12-PROTOCOL-K2.md'
CODE = ('wpk2_suite.py', 'run_wpk2.py', 'wpi_core.py', 'wpb_variants.py', 'wpc_adapters.py', 'wpb_stress.py', 'wpc_cm_worker.py')
KEEP = ('label', 'placement', 'range', 'recheck', 'tier', 'reasons', 'error')
METHODS = ('t0.85-deployed', 't0.85-IG+AG+VW', 't0.85-IG+AGi+VW', 'codemapper+quote', 'codemapper+IG+AG', 'codemapper+IG+AGi')
PAIRS = (('t0.85-IG+AGi+VW', 't0.85-IG+AG+VW'), ('codemapper+IG+AGi', 'codemapper+IG+AG'),
         ('codemapper+IG+AGi', 'codemapper+quote'), ('t0.85-IG+AGi+VW', 't0.85-deployed'))
A = None


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def code_hashes():
    return {p: sha(ROOT / 'tools/v11' / p) for p in CODE}


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def slim(o):
    return {k: o[k] for k in KEEP if k in o}


def err(e):
    return dict(label='execution_error', placement=None, range=None, recheck=True, error=repr(e)[:300])


def init():
    global A
    from multiprocessing.util import Finalize
    from wpc_adapters import Adapters
    A = Adapters(OUT / 'workers' / str(os.getpid()))
    Finalize(A, A.close, exitpriority=10)


def one(item):
    from wpb_variants import prepare, choose
    from wpi_core import cascade_i, window_layers, window_layers_i
    from wpc_adapters import materialize
    meta, t, old = item
    m = {}
    for name, f in (('t0.85-deployed', lambda: choose(prepare(t, old), .85, False, False, False)),
                    ('t0.85-IG+AG+VW', lambda: choose(prepare(t, old), .85, True, True, True)),
                    ('t0.85-IG+AGi+VW', lambda: cascade_i(t, old)['t0.85-IG+AGi+VW'])):
        try:
            m[name] = slim(f())
        except Exception as e:  # kept as an outcome
            m[name] = err(e)
    ident = meta['id']
    cm = None
    for attempt in range(3):
        fixture = OUT / 'private/fixtures' / f'{ident}-{os.getpid()}-{attempt}'
        try:
            if fixture.exists():
                shutil.rmtree(fixture, ignore_errors=True)
            before, after = materialize(fixture, old, t['version'])
            cm = A.codemapper(t, fixture, before, after, ident, resolver='native-readonly')
            break
        except PermissionError as e:  # Windows file locking in the fixture harness: retry in a fresh folder
            cm = err(e)
        except Exception as e:
            cm = err(e)
            break
    m['codemapper'] = slim(cm)
    try:
        for k, v in window_layers(t, old, cm, ('quote', 'IG+AG')).items():
            m['codemapper+' + k] = slim(v)
        m['codemapper+IG+AGi'] = slim(window_layers_i(t, old, cm)['IG+AGi'])
    except Exception as e:
        for k in ('quote', 'IG+AG', 'IG+AGi'):
            m.setdefault('codemapper+' + k, err(e))
    small = {k: v for k, v in meta.items() if k not in ('old_sha256', 'new_sha256')}
    return dict(small, inputs=dict(old=meta['old_sha256'], new=meta['new_sha256']), methods=m)


def freeze():
    assert PROTOCOL.exists()
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / 'protocol-freeze.json'
    assert not f.exists(), 'already frozen'
    assert not (OUT / 'rows.json').exists()
    f.write_text(json.dumps(dict(recorded_utc=utc(), protocol_sha256=sha(PROTOCOL), code_sha256=code_hashes(),
                                 statement='No WP K2 outcome exists before this record.'), indent=1), encoding='utf-8')
    print('frozen')


def verify_freeze():
    fz = json.loads((OUT / 'protocol-freeze.json').read_text(encoding='utf-8'))
    assert fz['protocol_sha256'] == sha(PROTOCOL), 'protocol changed after freeze'
    now = code_hashes()
    changed = [p for p in fz['code_sha256'] if fz['code_sha256'][p] != now.get(p)]
    assert not changed, f'code changed after freeze: {changed}'
    return fz


def run(workers, limit):
    from wpk2_suite import generate, SEED
    # Smoke runs use another seed and one trial per cell, so no evaluated trial is seen before the freeze.
    if not limit:
        verify_freeze()
    audits, items = [], []
    for meta, t, old in (generate(seed=SEED + 1, per_cell=1) if limit else generate()):
        if meta.get('generator_audit'):
            audits.append(meta)
        else:
            items.append((meta, t, old))
    if limit:
        items = items[:limit]
    rows, begin = [], time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=init) as pool:
        for r in pool.map(one, items, chunksize=8):
            rows.append(r)
            if len(rows) % 500 == 0:
                print(len(rows), f'{time.time() - begin:.0f}s', flush=True)
    suffix = '-smoke' if limit else ''
    (OUT / f'rows{suffix}.json').write_text(json.dumps(dict(code_sha256=code_hashes(), recorded_utc=utc(), data=rows)), encoding='utf-8')
    errors = Counter(k for r in rows for k, v in r['methods'].items() if v['label'] == 'execution_error')
    (OUT / f'completion{suffix}.json').write_text(json.dumps(dict(
        n=len(rows), expected=len(items), complete=len(rows) == len(items), execution_errors=dict(errors),
        generator_audits=audits, all_cells_complete=all(a['complete'] for a in audits), seconds=round(time.time() - begin),
        utc=utc()), indent=1), encoding='utf-8')
    print('done', len(rows), dict(errors))


# ---------------- analysis ----------------
def wilson(k, n, z=1.959964):
    if not n:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


DENOM = dict(missed='n_changed', unnecessary='n_preserved', placement='n_surv', lost='n_surv', silent='n_all',
             misdirected='n_all', errors='n_all')


def events(r, o):
    e = Counter()
    error = o['label'] == 'execution_error'
    req = bool(o.get('recheck')) or error
    at = None if error else o.get('placement')
    truth = r['truth_at']
    e['n_all'] += 1
    e['errors'] += error
    if r['changed']:
        e['n_changed'] += 1
        e['missed'] += not req
    if truth is None:
        wrong = at is not None
    else:
        e['n_surv'] += 1
        ok = at is not None and list(at) == list(truth)
        e['placement'] += ok
        e['lost'] += at is None
        wrong = at is not None and not ok
        if not r['changed']:
            e['n_preserved'] += 1
            e['unnecessary'] += req
    e['silent'] += wrong and not req
    e['misdirected'] += wrong and req
    e['req'] = int(req)
    e['wrong'] = int(wrong)
    return e


def table(rows):
    res = {}
    for m in METHODS:
        c = Counter()
        for r in rows:
            c.update(events(r, r['methods'][m]))
        res[m] = {k: dict(k=c[k], n=c[DENOM[k]], pct=round(100 * c[k] / c[DENOM[k]], 1) if c[DENOM[k]] else None,
                          ci=wilson(c[k], c[DENOM[k]])) for k in DENOM}
    return res


def issues(rows):
    """Fixed grouping: within each (c, d, k) group (same-revision: each (d, k)), trials ordered by (index, fate)
    form issues of 2, 3, 4, 2, 3, 4, ... anchors. Returned if any anchor requests; silent if any anchor is
    misplaced without a request."""
    order = {f: i for i, f in enumerate(('unchanged', 'shifted', 'token-edit', 'deleted'))}
    groups = defaultdict(list)
    for r in rows:
        groups[(r['same_revision'], r['c'], r['d'], r['k'])].append(r)
    out = []
    for key in sorted(groups, key=str):
        g = sorted(groups[key], key=lambda r: (r['index'], order[r['fate']]))
        i, s = 0, 0
        while i < len(g):
            size = (2, 3, 4)[s % 3]
            out.append(g[i:i + size])
            i += size
            s += 1
    res = {}
    for m in METHODS:
        c = Counter()
        for iss in out:
            ev = [events(r, r['methods'][m]) for r in iss]
            changed = any(r['changed'] for r in iss)
            returned = any(e['req'] for e in ev)
            c['n'] += 1
            c['n_changed'] += changed
            c['n_preserved'] += not changed
            c['missed'] += changed and not returned
            c['unnecessary'] += (not changed) and returned
            c['silent'] += any(e['wrong'] and not e['req'] for e in ev)
        res[m] = dict(n=c['n'], missed=dict(k=c['missed'], n=c['n_changed'], pct=round(100 * c['missed'] / max(1, c['n_changed']), 1)),
                      unnecessary=dict(k=c['unnecessary'], n=c['n_preserved'], pct=round(100 * c['unnecessary'] / max(1, c['n_preserved']), 1)),
                      silent=dict(k=c['silent'], n=c['n'], pct=round(100 * c['silent'] / max(1, c['n']), 1)))
    return dict(n_issues=len(out), sizes=dict(Counter(len(x) for x in out)), methods=res)


def paired(rows, seed=20261031, B=10000):
    import numpy as np
    files = sorted({r['source'] for r in rows})
    fi = {f: i for i, f in enumerate(files)}
    meas = ('missed', 'unnecessary', 'silent', 'misdirected', 'placement', 'lost')
    names = sorted({m for p in PAIRS for m in p})
    num = np.zeros((len(files), len(names), len(meas)))
    den = np.zeros((len(files), len(meas)))
    for r in rows:
        i = fi[r['source']]
        for j, m in enumerate(names):
            e = events(r, r['methods'][m])
            for q, x in enumerate(meas):
                num[i, j, q] += e[x]
        e = events(r, r['methods'][names[0]])
        for q, x in enumerate(meas):
            den[i, q] += e[DENOM[x]]
    rng = np.random.default_rng(seed)
    w = rng.multinomial(len(files), np.full(len(files), 1 / len(files)), size=B).astype(float)
    out = {}
    for a, b in PAIRS:
        ia, ib = names.index(a), names.index(b)
        res = {}
        for q, x in enumerate(meas):
            d = den[:, q].sum()
            if not d:
                continue
            diff = num[:, ia, q] - num[:, ib, q]
            bs = (w @ diff) / np.maximum(w @ den[:, q], 1)
            res[x] = dict(difference_pts=round(100 * diff.sum() / d, 2), ci95_pts=[round(100 * v, 2) for v in np.quantile(bs, [.025, .975])])
        out[f'{a} minus {b}'] = res
    return dict(clusters=len(files), resamples=B, seed=seed, contrasts=out)


def analyze():
    rows_doc = json.loads((OUT / 'rows.json').read_text(encoding='utf-8'))
    rows = rows_doc['data']
    main = [r for r in rows if not r['same_revision']]
    same = [r for r in rows if r['same_revision']]
    with_copies = [r for r in main if r['c']]

    def by(rs, key):
        groups = defaultdict(list)
        for r in rs:
            groups[str(key(r))].append(r)
        return {k: table(v) for k, v in sorted(groups.items())}
    summary = dict(
        recorded_utc=utc(), rows_sha256=sha(OUT / 'rows.json'), code_sha256=code_hashes(),
        freeze=json.loads((OUT / 'protocol-freeze.json').read_text(encoding='utf-8')),
        n=len(rows), n_main=len(main), n_same_revision=len(same), sources=len({r['source'] for r in rows}),
        overall=table(main),
        by_c=by(main, lambda r: r['c']), by_d=by(with_copies, lambda r: r['d']), by_k=by(main, lambda r: r['k']),
        by_fate=by(main, lambda r: r['fate']),
        c_by_d=by(with_copies, lambda r: f"{r['c']}|{r['d']}"),
        same_revision=dict(overall=table(same), by_d=by(same, lambda r: r['d']), by_k=by(same, lambda r: r['k']),
                           by_fate=by(same, lambda r: r['fate'])),
        issues=dict(main=issues(main), same_revision=issues(same)),
        paired=dict(main=paired(main), with_copies=paired(with_copies), same_revision=paired(same)))
    name = 'summary-' + time.strftime('%Y%m%dT%H%M%S', time.gmtime()) + '.json'
    (OUT / name).write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(name, len(rows))
    for m in METHODS:
        o = summary['overall'][m]
        s = summary['same_revision']['overall'][m]
        print(f"{m:20s} miss {o['missed']['pct']} unn {o['unnecessary']['pct']} place {o['placement']['pct']} lost {o['lost']['pct']} "
              f"silent {o['silent']['pct']} misdir {o['misdirected']['pct']} err {o['errors']['k']} | same-rev miss {s['missed']['pct']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=('freeze', 'run', 'analyze'))
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    os.environ['GIT_NO_LAZY_FETCH'] = '1'
    {'freeze': freeze, 'run': lambda: run(a.workers, a.limit), 'analyze': analyze}[a.stage]()


if __name__ == '__main__':
    main()
