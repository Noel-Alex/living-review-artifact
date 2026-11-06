"""WP K7: locators and the safety layer on ReviewAnchorBench cases (protocol review/V12-PROTOCOL-K7.md).

Run from paper-drafts/ with the CodeMapper interpreter:
  tools/v11-ext/codemapper/venv/Scripts/python.exe -I -B tools/v11/run_wpk7.py units
  tools/v11-ext/codemapper/venv/Scripts/python.exe -I -B tools/v11/run_wpk7.py run [--workers 8] [--limit N]
`units` writes evidence/v12-wpk7/units.json: every case of both strata with its reconstruction status.
`run` executes the methods of run_wpk6.py (same frozen layer code) on the rebuilt cases and writes rows.json.
Targets are rebuilt in the worker from the fetched blob and accepted only on the released target hash.
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'v12'))
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/v12-wpk7'
PKG = OUT / 'download/pkg/ReviewAnchorBench_Replication_Package_1.1.0'
BLOBS = OUT / 'blobs'
STRATA = (('population', 'results/review_anchor_population_sampled_benchmark_v3.json', None),
          ('heldout', 'results/review_anchor_benchmark_v1.json', 'HELD_OUT_TEST'))
CLS = dict(IDENTITY='untouched', PREFIX_INSERT='untouched', BLOCK_MOVE='untouched', SURROUNDING_CONTEXT_EDIT='untouched',
           REPLACEMENT_APPLIED='applied', MOVE_AND_REPLACE='applied', INTERNAL_LINE_EDIT='applied',
           TARGET_DELETE='applied-deletion', DUPLICATE_PREIMAGE='ambiguous', WHITESPACE_INSIDE='whitespace')
KEEP = ('label', 'placement', 'range', 'recheck', 'tier', 'reasons', 'error')
A = None


def sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def build_units():
    from rab_cases import decode, rebuild
    units = []
    for stratum, rel, split in STRATA:
        for c in json.loads((PKG / rel).read_text(encoding='utf-8'))['cases']:
            if split and c['split'] != split:
                continue
            b = BLOBS / f"{c['source_blob_sha256']}.bin"
            status = 'ok'
            if not b.exists():
                status = 'blob-unavailable'
            else:
                try:
                    tgt, rule = rebuild(c, decode(b.read_bytes()))
                    if tgt is None:
                        status = 'not-rebuildable'
                except UnicodeDecodeError:
                    status = 'decode-error'
            units.append(dict(case=c['benchmark_case_id'], stratum=stratum, family=c['family'], cls=CLS[c['family']],
                              repo=c['repository'], anchor=c['source_case_id'], path=c['path'],
                              blob=c['source_blob_sha256'], source_range=c['source_range'],
                              oracle_range=c['oracle_range'], oracle_state=c['oracle_state'], status=status))
    data = dict(package_zip_sha256='d56601eb3ab0c4bd3d4b5d2ef7dd096538ca797909f726ab16a2c50869183fd9',
                sources={rel: sha_file(PKG / rel) for _, rel, _ in STRATA}, units=units)
    (OUT / 'units.json').write_text(json.dumps(data, indent=1) + '\n', encoding='utf-8')
    from collections import Counter
    print(Counter((u['stratum'], u['status']) for u in units))


def slim(o):
    return {k: o[k] for k in KEEP if k in o}


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
    from rab_cases import decode, rebuild
    case = dict(family=u['family'], parameters=u['parameters'], source_range=u['source_range'],
                raw_replacement_lines=u['raw_replacement_lines'], target_content_sha256=u['target_sha256'],
                target_line_n=u['target_line_n'])
    src = decode((BLOBS / f"{u['blob']}.bin").read_bytes())
    tgt, _ = rebuild(case, src)
    assert tgt is not None, u['case']
    t0, t1 = '\n'.join(src), '\n'.join(tgt)
    lines = t0.splitlines()
    s, e = u['source_range']
    a = dict(path=u['path'], line_start=s, line_end=e, quotation='\n'.join(src[s - 1:e]), content_hash=digest(t0))
    version = {u['path']: (digest(t1), t1)}
    t = dict(anchor=a, old_lines=lines, version=version)
    old = {u['path']: t0}
    m = {}
    try:
        m['t0.85-deployed'] = slim(choose(prepare(t, old), .85, False, False, False))
    except Exception as ex:  # kept as an outcome
        m['t0.85-deployed'] = dict(label='execution_error', placement=None, range=None, recheck=True, error=repr(ex)[:300])
    try:
        m['t0.85-IG+AGi+VW'] = slim(cascade_i(t, old)['t0.85-IG+AGi+VW'])
    except Exception as ex:
        m['t0.85-IG+AGi+VW'] = dict(label='execution_error', placement=None, range=None, recheck=True, error=repr(ex)[:300])
    ident = u['case']
    try:
        fixture = OUT / 'private/fixtures' / ident
        if fixture.exists():
            import shutil
            shutil.rmtree(fixture)
        before, after = materialize(fixture, old, version)
        cm = A.codemapper(t, fixture, before, after, ident, resolver='native-readonly')
        import shutil
        shutil.rmtree(fixture, ignore_errors=True)
    except Exception as ex:
        cm = dict(label='execution_error', placement=None, range=None, recheck=True, error=repr(ex)[:300])
    m['codemapper'] = slim(cm)
    for k, v in window_layers(t, old, cm, ('quote', 'IG+AG')).items():
        m['codemapper+' + k] = slim(v)
    m['codemapper+IG+AGi'] = slim(window_layers_i(t, old, cm)['IG+AGi'])
    return dict(case=u['case'], stratum=u['stratum'], methods=m)


def run(workers, limit):
    from wpi_core import code_hashes  # noqa: F401  (imports the frozen modules; fails loudly if they moved)
    meta = {}
    for _, rel, split in STRATA:
        for c in json.loads((PKG / rel).read_text(encoding='utf-8'))['cases']:
            meta[c['benchmark_case_id']] = c
    units = [u for u in json.loads((OUT / 'units.json').read_text(encoding='utf-8'))['units'] if u['status'] == 'ok']
    for u in units:
        c = meta[u['case']]
        u.update(parameters=c['parameters'], raw_replacement_lines=c['raw_replacement_lines'],
                 target_sha256=c['target_content_sha256'], target_line_n=c['target_line_n'])
    if limit:
        units = units[:limit]
    rows, begin = [], time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=init) as pool:
        for r in pool.map(one, units, chunksize=4):
            rows.append(r)
            if len(rows) % 200 == 0:
                print(len(rows), f'{time.time() - begin:.0f}s', flush=True)
    code = {p: sha_file(ROOT / 'tools/v11' / p)
            for p in ('run_wpk7.py', 'wpi_core.py', 'wpb_variants.py', 'wpc_adapters.py')}
    code['tools/v12/rab_cases.py'] = sha_file(ROOT / 'tools/v12/rab_cases.py')
    name = 'rows-smoke.json' if limit else 'rows.json'
    (OUT / name).write_text(json.dumps(dict(code_sha256=code, units_sha256=sha_file(OUT / 'units.json'), data=rows)),
                            encoding='utf-8')
    errors = sum(r['methods'][k]['label'] == 'execution_error' for r in rows for k in r['methods'])
    (OUT / ('completion-smoke.json' if limit else 'completion.json')).write_text(json.dumps(
        dict(n=len(rows), units=len(units), execution_errors=errors, complete=len(rows) == len(units),
             utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))), encoding='utf-8')
    print('done', len(rows), 'errors', errors)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('step', choices=('units', 'run'))
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()
    if args.step == 'units':
        build_units()
    else:
        run(args.workers, args.limit)


if __name__ == '__main__':
    main()
