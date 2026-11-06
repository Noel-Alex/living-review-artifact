"""WP K6 step 1: locators and the safety layer on the suggestion-oracle units.

Run from paper-drafts/ with the CodeMapper interpreter:
  tools/v11-ext/codemapper/venv/Scripts/python.exe -I -B tools/v11/run_wpk6.py [--workers 8] [--limit N]
Methods (protocol V12-PROTOCOL-K6.md, decisions D7): deployed cascade (t0.85-deployed), cascade IG+AGi+VW at
theta 0.85, and CodeMapper with quote, IG+AG and IG+AGi layers, all from one CodeMapper execution per unit.
Scope: the file pair (c0 file -> c1 file). Writes evidence/v12-wpk6/rows.json and completion.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/v12-wpk6'
BLOBS = OUT / 'blobs'
KEEP = ('label', 'placement', 'range', 'recheck', 'tier', 'reasons', 'error')
A = None


def slim(o):
    return {k: o[k] for k in KEEP if k in o}


def text_of(digest):
    if digest is None:
        return None
    with open(BLOBS / digest[:2] / digest, encoding='utf-8', newline='') as f:
        return f.read()


def init():
    global A
    from multiprocessing.util import Finalize
    from wpc_adapters import Adapters
    A = Adapters(OUT / 'workers' / str(os.getpid()))
    Finalize(A, A.close, exitpriority=10)


def one(u):
    from wpb_variants import prepare, choose
    from wpi_core import cascade_i, window_layers, window_layers_i, digest
    from wpc_adapters import materialize
    t0, t1 = text_of(u['c0_sha256']), text_of(u['c1_sha256'])
    assert hashlib.sha256(t0.encode()).hexdigest() == u['c0_sha256']
    lines = t0.splitlines()
    a = dict(path=u['path_c0'], line_start=u['start'], line_end=u['end'],
             quotation='\n'.join(lines[u['start'] - 1:u['end']]), content_hash=digest(t0))
    version = {u['path_c1']: (digest(t1), t1)} if t1 is not None else {}
    t = dict(anchor=a, old_lines=lines, version=version)
    old = {u['path_c0']: t0}
    m = {}
    try:
        m['t0.85-deployed'] = slim(choose(prepare(t, old), .85, False, False, False))
    except Exception as e:  # kept as an outcome
        m['t0.85-deployed'] = dict(label='execution_error', placement=None, range=None, recheck=True, error=repr(e)[:300])
    try:
        m['t0.85-IG+AGi+VW'] = slim(cascade_i(t, old)['t0.85-IG+AGi+VW'])
    except Exception as e:
        m['t0.85-IG+AGi+VW'] = dict(label='execution_error', placement=None, range=None, recheck=True, error=repr(e)[:300])
    ident = f"{u['repo'].replace('/', '__')}-{u['comment_id']}"
    try:
        fixture = OUT / 'private/fixtures' / ident
        if fixture.exists():
            import shutil
            shutil.rmtree(fixture)
        before, after = materialize(fixture, old, version)
        cm = A.codemapper(t, fixture, before, after, ident, resolver='native-readonly')
    except Exception as e:
        cm = dict(label='execution_error', placement=None, range=None, recheck=True, error=repr(e)[:300])
    m['codemapper'] = slim(cm)
    for k, v in window_layers(t, old, cm, ('quote', 'IG+AG')).items():
        m['codemapper+' + k] = slim(v)
    m['codemapper+IG+AGi'] = slim(window_layers_i(t, old, cm)['IG+AGi'])
    return dict(repo=u['repo'], comment_id=u['comment_id'], methods=m)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()
    from wpi_core import code_hashes  # noqa: F401  (imports the frozen modules; fails loudly if they moved)
    units = json.loads((OUT / 'units.json').read_text(encoding='utf-8'))['units']
    if args.limit:
        units = units[:args.limit]
    rows, begin = [], time.time()
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init) as pool:
        for r in pool.map(one, units, chunksize=4):
            rows.append(r)
            if len(rows) % 100 == 0:
                print(len(rows), f'{time.time() - begin:.0f}s', flush=True)
    code = {p: hashlib.sha256((ROOT / 'tools/v11' / p).read_bytes()).hexdigest()
            for p in ('run_wpk6.py', 'wpk6_mine.py', 'wpi_core.py', 'wpb_variants.py', 'wpc_adapters.py')}
    units_sha = hashlib.sha256((OUT / 'units.json').read_bytes()).hexdigest()
    name = 'rows-smoke.json' if args.limit else 'rows.json'
    (OUT / name).write_text(json.dumps(dict(code_sha256=code, units_sha256=units_sha, data=rows)), encoding='utf-8')
    errors = sum(r['methods'][k]['label'] == 'execution_error' for r in rows for k in r['methods'])
    (OUT / ('completion-smoke.json' if args.limit else 'completion.json')).write_text(json.dumps(
        dict(n=len(rows), units=len(units), execution_errors=errors, complete=len(rows) == len(units),
             utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))), encoding='utf-8')
    print('done', len(rows), 'errors', errors)


if __name__ == '__main__':
    main()
