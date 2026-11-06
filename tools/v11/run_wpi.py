"""WP I runner (protocol: review/V11-PROTOCOL-I.md).

python -I -B tools/v11/run_wpi.py freeze|transfer|export-compound|compound|students|fresh|chains|chains-agi [--workers N]

Interpreters: export-compound needs Python 3.11.4 (as WP B2a); every other stage uses the
CodeMapper interpreter (tools/v11-ext/codemapper/venv, Python 3.12.14).
"""
import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pickle
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpi_core import (OUT, PROTOCOL, LOCATORS, LAYERS, CASCADE2, ID_FLOOR, ID_SENSITIVITY, ROOT, code_hashes, sha,  # noqa: E402
                      read, write, verify_freeze, window_layers, choose2, digest, wanted_of, identity_hop)

PRIVATE = OUT / 'private'
FRESH_SEED = 20261102
C6 = ROOT / 'evidence/v11-wpc/c6'
KEEP = ('label', 'placement', 'range', 'recheck', 'tier', 'reasons', 'error')
A = None


def now():
    return datetime.now(timezone.utc).isoformat()


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')


def slim(o):
    return {k: o[k] for k in KEEP if k in o}


def same(a, b):
    return (a['label'], a['placement'], bool(a['recheck'])) == (b['label'], b['placement'], bool(b['recheck']))


def small_old(t, old):
    return {p: old[p] for p in set(t['version']) | {t['anchor']['path']} if p in old}


def init_adapters(stage):
    global A
    from wpc_adapters import Adapters
    from multiprocessing.util import Finalize
    A = Adapters(OUT / 'workers' / stage / str(os.getpid()))
    Finalize(A, A.close, exitpriority=10)


def init_fresh():
    import run_wpb
    run_wpb.initialize()
    init_adapters('fresh')


def layered(prefix, t, old, output):
    return {f'{prefix}+{k}': v for k, v in window_layers(t, old, output).items()}


def cascade_family(t, old, saved=None):
    """Cascade AG2 variants plus a gate against the saved frozen IG+AG+VW corners."""
    from wpb_variants import prepare, choose
    if saved is not None and any(saved[m]['label'] == 'execution_error' for m in ('t0.85-IG+AG+VW', 't0.55-IG+AG+VW')):
        err = dict(label='execution_error', placement=None, range=None, recheck=True, error='frozen family boundary error')
        return {n: dict(err) for n in CASCADE2}, []
    data = prepare(t, old)
    mismatch = []
    if saved is not None:
        for name, theta in (('t0.85-IG+AG+VW', .85), ('t0.55-IG+AG+VW', .55)):
            mine = choose(data, theta, True, True, True)
            if not same(mine, saved[name]):
                mismatch.append(dict(method=name, mine=slim(mine), saved=slim(saved[name])))
    return {n: choose2(data, *args) for n, args in CASCADE2.items()}, mismatch


# ---------------- I2 transfer ----------------
def c6_saved():
    out = {}
    for stage in ('stress', 'reuse'):
        assert read(C6 / stage / 'completion.json')['data']['complete']
        for p in sorted((C6 / stage).glob('trials-*.json')):
            for r in read(p)['data']:
                meta = {k: v for k, v in r.items() if k not in ('methods', 'c6_bases', 'character_scores')}
                out[r['id']] = (meta, {k: slim(v) for k, v in r['methods'].items()},
                                {k: slim(v) for k, v in r['c6_bases'].items()})
    return out


def c6_stress_inputs():
    """run_wpc_c6.stress_inputs without its evidence write (C6 already holds that record)."""
    import itertools
    from run_wpc_c6 import key
    from run_wpb import metadata
    from wpb_stress import b1a, duplicates, short
    prior = {}
    for p in sorted((ROOT / 'evidence/v11-wpb1/evaluation').glob('trials-*.json')):
        for r in read(p)['data']:
            if r['suite'] in ('indentation', 'duplicates', 'short'):
                prior[key(r)] = r
    n = 0
    for meta, t, old in itertools.chain(b1a(20261027), duplicates(20261027), short(20261027)):
        if meta.get('generator_audit'):
            continue
        r = prior[key(meta)]
        actual = metadata(meta, t)
        for field in ('old_file_sha256', 'new_file_map_sha256', 'truth_at', 'reference_range', 'cls', 'anchor_at'):
            assert actual[field] == r[field], (key(meta), field)
        ident = 'stress-' + r['suite'] + '-' + r['op'].replace('/', '_') + '-' + str(r['index']) + '-' + r.get('frequency', '') + '-' + r.get('tokens', '')
        yield ident, t, small_old(t, old)
        n += 1
    assert n == len(prior), (n, len(prior))


def transfer_batch(batch):
    out = []
    for ident, meta, methods, bases, t, old in batch:
        mismatch = []
        new = {}
        for b in LOCATORS:
            fam = window_layers(t, old, bases[b])
            for layer in ('quote', 'IG', 'AG', 'IG+AG'):
                if not same(fam[layer], methods[b + '+' + layer]):
                    mismatch.append(dict(method=b + '+' + layer, mine=fam[layer], saved=methods[b + '+' + layer]))
            new[b + '+AG2'] = fam['AG2']
            new[b + '+IG+AG2'] = fam['IG+AG2']
        fam, more = cascade_family(t, old, methods)
        new.update(fam)
        mismatch += more
        keep = {k: v for k, v in methods.items() if k in ('t0.85-deployed', 't0.85-IG+AG+VW', 't0.55-IG+AG+VW')
                or any(k == b + '+' + layer for b in LOCATORS for layer in LAYERS)}
        out.append(dict(meta, methods={**keep, **new}, gate_mismatch=mismatch))
    return out


def transfer(workers):
    import itertools
    import run_wpc_c6
    from analyze_wpc import load
    saved = c6_saved()
    native = {r['id']: slim(r['methods']['cascade']) for r in load('external-frozen')}
    print('C6 rows', len(saved), flush=True)

    def items():
        for ident, t, old in c6_stress_inputs():
            yield ident, t, old
        for r, t, old in run_wpc_c6.reused_inputs():
            yield r['id'], t, old

    rows, pending, batch, seen = [], [], [], set()
    stage = OUT / 'transfer'
    stage.mkdir(parents=True, exist_ok=True)
    write(f'transfer/start-{stamp()}.json', dict(utc=now(), workers=workers))
    chunk = 0

    def flush(final=False):
        nonlocal rows, chunk
        while rows and (final or len(rows) >= 2000):
            part, rows = rows[:2000], rows[2000:]
            write(f'transfer/rows-{chunk:04d}.json', part)
            chunk += 1

    with ProcessPoolExecutor(max_workers=workers) as pool:
        for ident, t, old in items():
            meta, methods, bases = saved[ident]
            methods = dict(methods)
            methods['deployed_native'] = native[ident] if meta['suite'] == 'external' else methods['t0.85-deployed']
            seen.add(ident)
            batch.append((ident, meta, methods, bases, t, old))
            if len(batch) == 20:
                pending.append(pool.submit(transfer_batch, batch))
                batch = []
                if len(pending) >= workers * 3:
                    rows.extend(pending.pop(0).result())
                    flush()
                    if len(seen) % 2000 < 20:
                        print('transfer', len(seen), flush=True)
        if batch:
            pending.append(pool.submit(transfer_batch, batch))
        while pending:
            rows.extend(pending.pop(0).result())
            flush()
    flush(True)
    assert seen == set(saved), (len(seen), len(saved))
    mism = []
    for p in sorted(stage.glob('rows-*.json')):
        for r in read(p)['data']:
            mism += [dict(id=r['id'], **m) for m in r['gate_mismatch']]
    write('transfer/gate.json', dict(rows=len(seen), mismatches=len(mism), first=mism[:200], passed=not mism, utc=now()))
    write('transfer/completion.json', dict(complete=not mism, n=len(seen), chunks=chunk, utc=now()))
    print('transfer done', len(seen), 'gate mismatches', len(mism), flush=True)


def external_one(r):
    from wpc_adapters import git, target_path
    from wpc_core import region_lines
    from run_wpc_c6 import decode
    repo = ROOT / 'tools/v11-ext/dataset-repos' / r['url'].split('github.com/')[1].replace('/', '__')
    path = r['source_file']
    old_text = decode(git(repo, 'show', r['old_commit'] + ':' + path))
    assert digest(old_text) == r['source_sha256'], r['id']
    s, e = region_lines(r['source_region'])
    a = dict(path=path, line_start=s, line_end=e, quotation='\n'.join(old_text.splitlines()[s - 1:e]), content_hash=digest(old_text))
    target = target_path(str(repo), r['old_commit'], r['new_commit'], path)
    version = {}
    if target is not None:
        new_text = decode(git(repo, 'show', r['new_commit'] + ':' + target))
        version[target] = (digest(new_text), new_text)
    t = dict(anchor=a, old_lines=old_text.splitlines(), version=version)
    fam, more = cascade_family(t, {path: old_text}, r['methods'])
    return r['id'], fam, more


def external_cascade(workers):
    """Amendment 2 (amendment 5: same computation over a process pool)."""
    rows = [r for p in sorted((OUT / 'transfer').glob('rows-*.json')) for r in read(p)['data'] if r['suite'] == 'external']
    assert len(rows) == 2392, len(rows)
    out, mism = [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for ident, fam, more in pool.map(external_one, rows, chunksize=4):
            mism += [dict(id=ident, **m) for m in more]
            out.append(dict(id=ident, methods=fam))
    write('external-cascade/rows.json', out)
    write('external-cascade/gate.json', dict(rows=len(out), mismatches=len(mism), first=mism[:50], passed=not mism, utc=now()))
    write('external-cascade/completion.json', dict(complete=not mism, n=len(out), utc=now()))
    print('external cascade', len(out), 'gate mismatches', len(mism), flush=True)


def agi_batch(items):
    """Amendment 4: AGi layers on saved locator outputs and AGi cascade variants."""
    from wpi_core import window_layers_i, cascade_i
    out = []
    for ident, t, old, bases, scoped in items:
        methods = {}
        for b, o in bases.items():
            for k, v in window_layers_i(t, old, o).items():
                methods[f'{b}+{k}'] = v
        ct, co = scoped if scoped is not None else (t, old)
        if ct is None:
            err = dict(label='execution_error', placement=None, range=None, recheck=True, error='frozen family boundary error')
            methods.update({n: dict(err) for n in ('t0.85-AGi', 't0.85-IG+AGi+VW', 't0.55-IG+AGi+VW')})
        else:
            methods.update(cascade_i(ct, co))
        out.append(dict(id=ident, methods=methods))
    return out


def external_scope(r):
    from wpc_adapters import git, target_path
    from wpc_core import region_lines
    from run_wpc_c6 import decode
    repo = ROOT / 'tools/v11-ext/dataset-repos' / r['url'].split('github.com/')[1].replace('/', '__')
    path = r['source_file']
    old_text = decode(git(repo, 'show', r['old_commit'] + ':' + path))
    s, e = region_lines(r['source_region'])
    a = dict(path=path, line_start=s, line_end=e, quotation='\n'.join(old_text.splitlines()[s - 1:e]), content_hash=digest(old_text))
    target = target_path(str(repo), r['old_commit'], r['new_commit'], path)
    version = {}
    if target is not None:
        new_text = decode(git(repo, 'show', r['new_commit'] + ':' + target))
        version[target] = (digest(new_text), new_text)
    return dict(anchor=a, old_lines=old_text.splitlines(), version=version), {path: old_text}


def agi(workers):
    import itertools
    import pickle as pk
    import run_wpc_c6
    from regenerate_history_selection import harness
    from wpb_stress import b1a, duplicates, short
    from wpb2_compound import compound as compound_gen

    def bases_of(methods, names):
        return {b: methods[b + '+quote'] for b in names if b + '+quote' in methods}

    def rows_of(stage, pattern):
        return {r['id']: r for p in sorted((OUT / stage).glob(pattern)) for r in read(p)['data']}

    def items():
        tr = rows_of('transfer', 'rows-*.json')
        for ident, t, old in c6_stress_inputs():
            yield 'transfer', (ident, t, old, bases_of(tr[ident]['methods'], LOCATORS), None)
        for r, t, old in run_wpc_c6.reused_inputs():
            row = tr[r['id']]
            scoped = None
            if row['suite'] == 'external':
                frozen_err = any(row['methods'][m]['label'] == 'execution_error' for m in ('t0.85-IG+AG+VW', 't0.55-IG+AG+VW'))
                scoped = (None, None) if frozen_err else external_scope(row)
            yield 'transfer', (r['id'], t, old, bases_of(row['methods'], LOCATORS), scoped)
        cm_rows = rows_of('compound', 'rows.json')
        with (PRIVATE / 'compound-inputs.pkl').open('rb') as f:
            for m, t, o in pk.load(f):
                ident = f"compound-{m['seed']}-{m['k']}-{m['index']}"
                yield 'compound', (ident, t, o, bases_of(cm_rows[ident]['methods'], ('codemapper', 'tracker', 'hybrid')), None)
        fr = rows_of('fresh', 'rows-*.json')
        for meta, t, old in itertools.chain(b1a(FRESH_SEED), duplicates(FRESH_SEED), short(FRESH_SEED), compound_gen(FRESH_SEED)):
            if meta.get('generator_audit'):
                continue
            ident = '-'.join(str(meta.get(k, '')) for k in ('suite', 'op', 'index', 'frequency', 'tokens')).replace('/', '_').replace('=', '')
            so = small_old(t, old)
            yield 'fresh', (ident, t, so, bases_of(fr[ident]['methods'], ('codemapper', 'tracker', 'hybrid')), None)
        st = rows_of('students2', 'rows.json')
        private = ROOT / 'evidence/v11-wph/private'
        paths = {r['anonymous_id']: str(private / 'tmp' / str(r['repository_id'])) for r in read(private / 'selected.json')}
        original, _ = harness()
        by_pair = defaultdict(list)
        for r in st.values():
            by_pair[(r['repo'], r['old_commit'], r['new_commit'])].append(r)
        for (sid, old_c, new_c), members in sorted(by_pair.items()):
            repo = original.Repo(paths[sid])
            try:
                old_files = {p: repo.blob(s) for p, s in repo.tree(old_c).items()}
                version = {}
                for p, s in repo.tree(new_c).items():
                    text = repo.blob(s)
                    version[p] = (digest(text), text)
            finally:
                repo.cat.stdin.close()
                repo.cat.wait(timeout=15)
            for rec in members:
                p, start = rec['anchor_at']
                text = old_files[p]
                assert digest(text) == rec['old_file_sha256']
                t = dict(anchor=dict(path=p, line_start=start, line_end=start + rec['span'] - 1,
                                     quotation='\n'.join(text.splitlines()[start - 1:start - 1 + rec['span']]), content_hash=digest(text)),
                         old_lines=text.splitlines(), version=version)
                yield 'students2', (rec['id'], t, small_old(t, old_files), bases_of(rec['methods'], ('codemapper', 'tracker', 'hybrid')), (t, old_files))

    results, pending, batch, last = defaultdict(list), [], [], None
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for origin, item in items():
            if batch and origin != last:
                pending.append((last, pool.submit(agi_batch, batch)))
                batch = []
            last = origin
            batch.append(item)
            if len(batch) == 20:
                pending.append((origin, pool.submit(agi_batch, batch)))
                batch = []
            while len(pending) >= workers * 3:
                o, fut = pending.pop(0)
                results[o].extend(fut.result())
        if batch:
            pending.append((last, pool.submit(agi_batch, batch)))
        for o, fut in pending:
            results[o].extend(fut.result())
    for origin, rows in results.items():
        for i in range(0, len(rows), 5000):
            write(f'agi/{origin}-{i // 5000:03d}.json', rows[i:i + 5000])
    write('agi/completion.json', dict(complete=True, n={o: len(r) for o, r in results.items()}, utc=now()))
    print('agi', {o: len(r) for o, r in results.items()}, flush=True)


# ---------------- I3a compound ----------------
def export_compound():
    assert sys.version_info[:3] == (3, 11, 4), 'B2a generation used Python 3.11.4'
    import itertools
    from run_wpb import metadata
    from wpb2_compound import compound
    saved = {(r['seed'], r['k'], r['index']): r for r in read(ROOT / 'evidence/v11-wpb2/compound/trials.json')['data']}
    items = []
    for meta, t, old in itertools.chain(*(compound(s) for s in (20261018, 20261027))):
        if meta.get('generator_audit'):
            continue
        r = saved[(meta['seed'], meta['k'], meta['index'])]
        actual = metadata(meta, t)
        for field in ('old_file_sha256', 'new_file_map_sha256', 'truth_at', 'reference_range', 'cls', 'anchor_at'):
            assert actual[field] == r[field], (meta, field)
        items.append((meta, t, small_old(t, old)))
    assert len(items) == len(saved) == 2400
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / 'compound-inputs.pkl'
    with path.open('xb') as f:
        pickle.dump(items, f, protocol=4)
    write('compound/export.json', dict(n=len(items), sha256=sha(path), python=sys.version, utc=now()))


def cm_fixture(kind, ident, t, old):
    from wpc_adapters import materialize
    fixture = PRIVATE / 'fixtures' / kind / ident
    before, after = materialize(fixture, old, t['version'])
    return A.codemapper(t, fixture, before, after, ident, resolver='native-readonly')


def compound_batch(batch):
    from wpc_c6 import hybrid
    out = []
    for meta, t, old, saved in batch:
        ident = f"compound-{meta['seed']}-{meta['k']}-{meta['index']}"
        cm = cm_fixture('compound', ident, t, old)
        methods = dict(saved['methods'])
        methods['codemapper'] = slim(cm)
        methods.update(layered('codemapper', t, old, cm))
        tr = methods['tracker_adapter']
        methods.update(layered('tracker', t, old, tr))
        methods.update(layered('hybrid', t, old, hybrid(tr, methods['t0.85-deployed'])))
        methods.update(cascade_family(t, old)[0])
        out.append(dict({k: v for k, v in saved.items() if k != 'methods'}, id=ident, methods=methods,
                        cm_elapsed_ms=cm.get('elapsed_ms')))
    return out


def compound(workers):
    export = read(OUT / 'compound/export.json')['data']
    path = PRIVATE / 'compound-inputs.pkl'
    assert sha(path) == export['sha256']
    with path.open('rb') as f:
        items = pickle.load(f)
    saved = {(r['seed'], r['k'], r['index']): r for r in read(ROOT / 'evidence/v11-wpb2/compound/trials.json')['data']}
    jobs = [[(m, t, o, saved[(m['seed'], m['k'], m['index'])]) for m, t, o in items[i:i + 10]] for i in range(0, len(items), 10)]
    rows = []
    with ProcessPoolExecutor(max_workers=workers, initializer=init_adapters, initargs=('compound',)) as pool:
        for got in pool.map(compound_batch, jobs):
            rows.extend(got)
            if len(rows) % 200 == 0:
                print('compound', len(rows), flush=True)
    write('compound/rows.json', rows)
    write('compound/completion.json', dict(complete=len(rows) == 2400, n=len(rows), utc=now()))


# ---------------- I3b students ----------------
def student_batch(args):
    from regenerate_history_selection import harness
    from run_wpc_c6 import strict_tracker
    from wpc_c6 import hybrid
    sid, path, old_c, new_c, members = args
    original, _ = harness()
    repo = original.Repo(path)
    try:
        old_files = {p: repo.blob(s) for p, s in repo.tree(old_c).items()}
        version = {}
        for p, s in repo.tree(new_c).items():
            text = repo.blob(s)
            version[p] = (digest(text), text)
    finally:
        repo.cat.stdin.close()
        repo.cat.wait(timeout=15)
    out = []
    for rec in members:
        p, start = rec['anchor_at']
        text = old_files[p]
        assert digest(text) == rec['old_file_sha256'], (sid, rec['row'])
        assert digest(json.dumps({q: v[0] for q, v in version.items()}, sort_keys=True)) == rec['new_file_map_sha256']
        span = rec['span']
        t = dict(anchor=dict(path=p, line_start=start, line_end=start + span - 1,
                             quotation='\n'.join(text.splitlines()[start - 1:start - 1 + span]), content_hash=digest(text)),
                 old_lines=text.splitlines(), version=version)
        so = small_old(t, old_files)
        ident = f"{sid}-{rec['row']}"
        cm = A.codemapper(t, path, old_c, new_c, ident, resolver='native-readonly')
        methods = dict(rec['methods'])
        methods['codemapper'] = slim(cm)
        methods.update(layered('codemapper', t, so, cm))
        try:
            tr = strict_tracker(t, methods['tracker_adapter'])
        except ValueError:
            q = A.base.request(json.dumps(dict(mode='basic', method='tracker_adapter', trial=t)))
            tr = q['output'] if 'error' not in q else dict(label='execution_error', placement=None, range=None, recheck=True, error=q['error'])
        methods['tracker_strict'] = slim(tr)
        methods.update(layered('tracker', t, so, tr))
        methods.update(layered('hybrid', t, so, hybrid(tr, methods['t0.85-deployed'])))
        methods.update(cascade_family(t, old_files)[0])
        out.append(dict({k: v for k, v in rec.items() if k != 'methods'}, id=ident, methods=methods,
                        cm_elapsed_ms=cm.get('elapsed_ms')))
    return out


def students(workers, folder='students'):
    private = ROOT / 'evidence/v11-wph/private'
    paths = {r['anonymous_id']: str(private / 'tmp' / str(r['repository_id'])) for r in read(private / 'selected.json')}
    jobs = []
    for f in sorted((ROOT / 'evidence/v11-wph2/trials').glob('S*.json'), key=lambda x: int(x.stem[1:])):
        by_pair = defaultdict(list)
        for rec in read(f)['data']:
            by_pair[(rec['old_commit'], rec['new_commit'])].append(rec)
        for (old_c, new_c), members in by_pair.items():
            for i in range(0, len(members), 25):
                jobs.append((f.stem, paths[f.stem], old_c, new_c, members[i:i + 25]))
    rows = []
    with ProcessPoolExecutor(max_workers=workers, initializer=init_adapters, initargs=('students',)) as pool:
        for got in pool.map(student_batch, jobs):
            rows.extend(got)
            if len(rows) % 500 < len(got):
                print('students', len(rows), flush=True)
    write(f'{folder}/rows.json', rows)
    write(f'{folder}/completion.json', dict(complete=len(rows) == 7882, n=len(rows), utc=now()))


# ---------------- I3c fresh held-out seed ----------------
def fresh_batch(batch):
    import run_wpb
    from wpc_c6 import hybrid
    records = run_wpb.evaluate_batch(([(m, t, o) for m, t, o in batch], True))
    out = []
    for rec, (meta, t, old) in zip(records, batch):
        so = small_old(t, old)
        ident = '-'.join(str(meta.get(k, '')) for k in ('suite', 'op', 'index', 'frequency', 'tokens')).replace('/', '_').replace('=', '')
        cm = cm_fixture('fresh', ident, t, so)
        methods = {k: slim(v) for k, v in rec['methods'].items()}
        methods['codemapper'] = slim(cm)
        methods.update(layered('codemapper', t, so, cm))
        tr = methods['tracker_adapter']
        methods.update(layered('tracker', t, so, tr))
        methods.update(layered('hybrid', t, so, hybrid(tr, methods['t0.85-deployed'])))
        methods.update(cascade_family(t, so)[0])
        out.append(dict({k: v for k, v in rec.items() if k != 'methods'}, id=ident, methods=methods,
                        cm_elapsed_ms=cm.get('elapsed_ms')))
    return out


def fresh(workers):
    import itertools
    from wpb_stress import b1a, duplicates, short
    from wpb2_compound import compound as compound_gen
    gen = itertools.chain(b1a(FRESH_SEED), duplicates(FRESH_SEED), short(FRESH_SEED), compound_gen(FRESH_SEED))
    audits, rows, pending, batch = [], [], [], []
    with ProcessPoolExecutor(max_workers=workers, initializer=init_fresh) as pool:
        for meta, t, old in gen:
            if meta.get('generator_audit'):
                audits.append(meta)
                continue
            batch.append((meta, t, small_old(t, old)))
            if len(batch) == 10:
                pending.append(pool.submit(fresh_batch, batch))
                batch = []
                if len(pending) >= workers * 3:
                    rows.extend(pending.pop(0).result())
                    if len(rows) % 1000 < 10:
                        print('fresh', len(rows), flush=True)
        if batch:
            pending.append(pool.submit(fresh_batch, batch))
        while pending:
            rows.extend(pending.pop(0).result())
    assert len({r['id'] for r in rows}) == len(rows)
    for i in range(0, len(rows), 3000):
        write(f'fresh/rows-{i // 3000:03d}.json', rows[i:i + 3000])
    write('fresh/completion.json', dict(complete=all(a.get('complete', True) for a in audits), n=len(rows),
                                        generator_audits=audits, seed=FRESH_SEED, utc=now()))


# ---------------- I4 chains ----------------
CASCADE_CHAINS = {'v0.85-off': (.85, False, False, False, None), 'v0.85-all': (.85, True, True, True, None),
                  'v0.85-all2': (.85, True, False, True, 'ag2'), 'v0.55-all2': (.55, True, False, True, 'ag2')}
# Amendment 7: the recommended guard (AGi) on the same chains; v0.85-off is recomputed only as the gate.
CASCADE_CHAINS_I = {'v0.85-off': (.85, False, False, False, None), 'v0.85-alli': (.85, True, True, True, 'agi'),
                    'v0.55-alli': (.55, True, True, True, 'agi')}


def chain_job(args):
    import wpb2_chains as wc
    import wpb_variants
    from wpb_variants import prepare, choose
    from wpc_core import line_region, region_lines
    from wpi_core import choose_i, window_layers_i
    name, recs, mode = args if len(args) == 3 else (*args, 'base')
    configs = CASCADE_CHAINS if mode == 'base' else CASCADE_CHAINS_I
    guard = 'IG+AG2' if mode == 'base' else 'IG+AGi'
    gsuffix = '-g' if mode == 'base' else '-gi'

    def guard_layers(trial, old_files, o):
        fam = window_layers(trial, old_files, o, ('quote', 'IG+AG2') if mode == 'base' else ('quote',))
        if mode != 'base':
            fam[guard] = window_layers_i(trial, old_files, o)[guard]
        return fam
    if A is None:
        init_adapters('chains')
    proxy = wc._Expected(wpb_variants.MATCHER)
    wpb_variants.MATCHER = proxy
    from regenerate_history_selection import harness
    original, _ = harness()
    history = wc.one_history(name)
    repo = original.Repo(str(history.path))
    versions = {}

    def version(commit):
        if commit not in versions:
            if len(versions) > 24:
                versions.pop(next(iter(versions)))
            files = {}
            for p, s in repo.tree(commit).items():
                text = repo.blob(s)
                files[p] = (wc.digest(text), text)
            versions[commit] = files
        return versions[commit]

    def cascade_hop(state, previous, current, theta, ig, ag, vw, rule):
        prev_text = previous.get(state['path'], (None, None))[1]
        trial = dict(anchor=state, version=current, old_lines=(prev_text or '').splitlines())
        proxy.missing = prev_text is None
        try:
            data = prepare(trial, {p: t for p, (_, t) in previous.items()})
            out = (choose2(data, theta, ig, vw) if rule == 'ag2' else choose_i(data, theta, ig, vw) if rule == 'agi'
                   else choose(data, theta, ig, ag, vw))
        finally:
            proxy.missing = False
        new = dict(state)
        if out['label'] == 'removed':
            new['match'] = 'removed'
            return new, out, None
        if out['tier'] == 'hash':
            new['match'] = 'exact'
            return new, out, state['quotation']
        candidate, start, end = out['range']
        window = '\n'.join(current[candidate][1].splitlines()[start - 1:end])
        new.update(path=candidate, line_start=start, line_end=end, content_hash=current[candidate][0], match=out['label'])
        if out['tier'] in ('local', 'variable'):
            new['quotation'] = window
        return new, out, window

    def id_label(q0, window, label):
        return label if label in ('exact', 'moved') and wanted_of(q0) == wanted_of(window) else 'changed'

    out = []
    try:
        for row, saved in recs:
            commits = row['commits']
            path, start = row['anchor_at']
            span = row['span']
            v0 = version(commits[0])
            digest0, old_text = v0[path]
            q0 = '\n'.join(old_text.splitlines()[start - 1:start - 1 + span])
            anchor = dict(path=path, line_start=start, line_end=start + span - 1, quotation=q0, content_hash=digest0)
            record = dict(row=row['row'], repo=name, group=row['group'], sample=row['sample'], pair=row['pair'],
                          prefixes={h: dict(reference=saved['prefixes'][h]['reference'], direct={}) for h in saved['prefixes']},
                          gate=[])
            for key, (theta, ig, ag, vw, rule) in configs.items():
                memo = {}
                for floor in (None, ID_FLOOR) + ID_SENSITIVITY:
                    state, hops = dict(anchor), []
                    for i in range(1, 11):
                        mk = (i, json.dumps(state, sort_keys=True))
                        if mk not in memo:
                            memo[mk] = cascade_hop(state, version(commits[i - 1]), version(commits[i]), theta, ig, ag, vw, rule)
                        new, o, window = memo[mk]
                        if floor is None:
                            state = new
                            hops.append(dict(label=o['label'], interval=o['range'], requested_recheck=o['recheck'], reasons=o['reasons']))
                            continue
                        keep, request, ratio = identity_hop(q0, window, o['label'], o['recheck'], floor)
                        if not keep:
                            state = dict(state, match='removed')
                            hops.append(dict(label='removed', interval=None, requested_recheck=True, reasons=['identity-floor'], ratio=ratio))
                        else:
                            state = new
                            hops.append(dict(label=id_label(q0, window, o['label']), interval=o['range'], requested_recheck=request,
                                             reasons=o['reasons'], ratio=ratio))
                    name_ = key if floor is None else f'{key}-id' if floor == ID_FLOOR else f'{key}-id{floor:.1f}'
                    record[name_] = hops
                if key in saved['hops']:
                    for mine, theirs in zip(record[key], saved['hops'][key]):
                        if (mine['label'], mine['interval'], mine['requested_recheck']) != (theirs['label'], theirs['interval'], theirs['requested_recheck']):
                            record['gate'].append(dict(method=key, mine=mine, saved=theirs))
                            break
            # CodeMapper sequential (state = last located commit, path, character region, current quotation).
            region0 = line_region(old_text, start, start + span - 1)
            cache = {}

            def cm(ci, i, p, region):
                k = (ci, i, p, tuple(region))
                if k not in cache:
                    src = version(commits[ci])
                    t = dict(anchor=dict(path=p, line_start=region_lines(region)[0], line_end=region_lines(region)[1],
                                         quotation='', content_hash=src[p][0]), old_lines=src[p][1].splitlines(), version=version(commits[i]))
                    cache[k] = A.codemapper(t, str(history.path), commits[ci], commits[i], f'{name}-{row["row"]}-{ci}-{i}',
                                            source_region=list(region), resolver='native-readonly')
                return cache[k]

            for floor in (None, ID_FLOOR):
                st = dict(ci=0, path=path, region=region0, quotation=q0, start=start)
                hops = []
                for i in range(1, 11):
                    o = cm(st['ci'], i, st['path'], st['region'])
                    if o['label'] in ('execution_error', 'removed') or o.get('placement') is None:
                        hops.append(dict(label=o['label'], interval=None, requested_recheck=True, requested_guard=True,
                                         error=o.get('error')))
                        continue
                    # Line-anchor view of the current state for the window rules.
                    t_anchor = dict(path=st['path'], line_start=st['start'], line_end=st['start'] + len(st['quotation'].splitlines()) - 1)
                    src = version(commits[st['ci']])
                    trial = dict(anchor=dict(t_anchor, quotation=st['quotation'], content_hash=src[st['path']][0]),
                                 old_lines=src[st['path']][1].splitlines(), version=version(commits[i]))
                    fam = guard_layers(trial, {q: x for q, (_, x) in src.items()}, o)
                    target, s, e = o['range']
                    window = '\n'.join(version(commits[i])[target][1].splitlines()[s - 1:e])
                    label, req, req_g = fam['quote']['label'], fam['quote']['recheck'], fam[guard]['recheck']
                    if floor is not None:
                        keep, request, ratio = identity_hop(q0, window, 'changed' if req else 'exact', req, floor)
                        if not keep:
                            hops.append(dict(label='removed', interval=None, requested_recheck=True, requested_guard=True,
                                             reasons=['identity-floor'], ratio=ratio))
                            continue
                        req, req_g = request, bool(req_g or wanted_of(q0) != wanted_of(window))
                        label = id_label(q0, window, label)
                    hops.append(dict(label=label, interval=[target, s, e], requested_recheck=req, requested_guard=req_g))
                    st = dict(ci=i, path=target, region=o['character_range'], quotation=window, start=s)
                record['cm-seq' if floor is None else 'cm-seq-id'] = hops
                record['cm-seq' + gsuffix + ('' if floor is None else '-id')] = [dict(h, requested_recheck=h['requested_guard']) for h in hops]
            for h in record['prefixes']:
                o = cm(0, int(h), path, region0)
                d = dict(label=o['label'], placement=o.get('placement'), range=o.get('range'), recheck=True)
                if o['label'] not in ('execution_error', 'removed') and o.get('placement') is not None:
                    fam = guard_layers(dict(anchor=anchor, old_lines=old_text.splitlines(), version=version(commits[int(h)])),
                                       {q: x for q, (_, x) in v0.items()}, o)
                    d.update(label=fam['quote']['label'], recheck=fam['quote']['recheck'])
                    record['prefixes'][h]['direct']['cm-direct' + gsuffix] = dict(d, recheck=fam[guard]['recheck'])
                else:
                    record['prefixes'][h]['direct']['cm-direct' + gsuffix] = dict(d)
                record['prefixes'][h]['direct']['cm-direct'] = d
            if mode != 'base':
                # Gate: CodeMapper is deterministic and guards never move a window, so the labels-only
                # CodeMapper traces must equal the WP I chain stage exactly.
                wpi = saved['wpi']
                for m in ('cm-seq', 'cm-seq-id'):
                    for mine, theirs in zip(record[m], wpi[m]):
                        if (mine['label'], mine['interval'], mine['requested_recheck']) != (theirs['label'], theirs['interval'], theirs['requested_recheck']):
                            record['gate'].append(dict(method=m, mine=mine, saved=theirs))
                            break
                for h in record['prefixes']:
                    mine, theirs = record['prefixes'][h]['direct']['cm-direct'], wpi['prefixes'][h]['direct']['cm-direct']
                    if (mine['label'], mine['range'], mine['recheck']) != (theirs['label'], theirs['range'], theirs['recheck']):
                        record['gate'].append(dict(method='cm-direct', prefix=h, mine=mine, saved=theirs))
            out.append(record)
    finally:
        repo.cat.stdin.close()
        repo.cat.wait(timeout=15)
        history.close()
    return out


def chains(workers):
    import wpb2_chains as wc
    assert sys.version_info[:2] >= (3, 12)
    rows = wc.chain_rows()
    saved = {r['row']: r for r in read(ROOT / 'evidence/v11-wpb2/chains/trials.json')['data']}
    by_repo = defaultdict(list)
    for r in rows:
        s = saved[r['row']]
        by_repo[r['repo']].append((r, dict(prefixes=s['prefixes'], hops={k: s[k] for k in ('v0.85-off', 'v0.85-all') if k in s})))
    jobs = [(name, subset[i:i + 25]) for name, subset in sorted(by_repo.items(), key=lambda kv: -len(kv[1]))
            for i in range(0, len(subset), 25)]
    out = []
    with ProcessPoolExecutor(max_workers=workers, initializer=init_adapters, initargs=('chains',)) as pool:
        for got in pool.map(chain_job, jobs):
            out.extend(got)
            print('chains', len(out), flush=True)
    out.sort(key=lambda r: r['row'])
    write('chains/rows.json', out)
    gate = [dict(row=r['row'], **g) for r in out for g in r['gate']]
    write('chains/gate.json', dict(rows=len(out), mismatches=len(gate), first=gate[:100], passed=not gate, utc=now()))
    write('chains/completion.json', dict(complete=len(out) == 4000 and not gate, n=len(out), utc=now()))


def chains_agi(workers):
    """Amendment 7: chains with the recommended guard AGi (cascade and CodeMapper), gated against B2 and WP I."""
    import wpb2_chains as wc
    assert sys.version_info[:2] >= (3, 12)
    assert read(OUT / 'chains/completion.json')['data']['complete']
    rows = wc.chain_rows()
    saved = {r['row']: r for r in read(ROOT / 'evidence/v11-wpb2/chains/trials.json')['data']}
    wpi = {r['row']: r for r in read(OUT / 'chains/rows.json')['data']}
    by_repo = defaultdict(list)
    for r in rows:
        s = saved[r['row']]
        by_repo[r['repo']].append((r, dict(prefixes=s['prefixes'], hops={k: s[k] for k in ('v0.85-off',) if k in s}, wpi=wpi[r['row']])))
    jobs = [(name, subset[i:i + 25], 'agi') for name, subset in sorted(by_repo.items(), key=lambda kv: -len(kv[1]))
            for i in range(0, len(subset), 25)]
    out = []
    with ProcessPoolExecutor(max_workers=workers, initializer=init_adapters, initargs=('chains-agi',)) as pool:
        for got in pool.map(chain_job, jobs):
            out.extend(got)
            print('chains-agi', len(out), flush=True)
    out.sort(key=lambda r: r['row'])
    write('chains-agi/rows.json', out)
    gate = [dict(row=r['row'], **g) for r in out for g in r['gate']]
    write('chains-agi/gate.json', dict(rows=len(out), mismatches=len(gate), first=gate[:100], passed=not gate, utc=now()))
    write('chains-agi/completion.json', dict(complete=len(out) == 4000 and not gate, n=len(out), utc=now()))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=('freeze', 'transfer', 'export-compound', 'compound', 'students', 'fresh', 'chains', 'external-cascade', 'students2', 'agi', 'chains-agi'))
    p.add_argument('--workers', type=int, default=12)
    a = p.parse_args()
    os.environ['GIT_NO_LAZY_FETCH'] = '1'
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        if a.stage == 'freeze':
            write('protocol-freeze.json', dict(timestamp_utc=now(), protocol_sha256=sha(PROTOCOL), code_sha256=code_hashes(),
                                               statement='No WP I output exists before this record.'))
            return
        verify_freeze()
        write(f'{a.stage}-start-{stamp()}.json', dict(utc=now(), workers=a.workers, python=sys.version))
        begin = time.time()
        dict(transfer=transfer, compound=compound, students=students, fresh=fresh, chains=chains, **{'external-cascade': external_cascade, 'students2': lambda w: students(w, 'students2'), 'agi': agi, 'chains-agi': chains_agi}).get(
            a.stage, lambda w: export_compound())(a.workers)
        write(f'{a.stage}-end-{stamp()}.json', dict(utc=now(), seconds=time.time() - begin))
    except BaseException as error:
        write(f'{a.stage}-failure-{stamp()}.json', dict(error=repr(error), traceback=traceback.format_exc()))
        raise


if __name__ == '__main__':
    main()
