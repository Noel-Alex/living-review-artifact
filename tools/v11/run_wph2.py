"""WP H2 (protocol: review/V11-PROTOCOL-H2.md): original selection/oracle and all methods on S1-S20.

python -B tools/v11/run_wph2.py freeze|run|analyze [--workers N]
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpa_core import ROOT, sha, read, rate  # noqa: E402

OUT = ROOT / 'evidence/v11-wph2'
PRIVATE = ROOT / 'evidence/v11-wph/private'
PROTOCOL = ROOT / 'review/V11-PROTOCOL-H2.md'
CODE = ['run_wph2.py']
FROZEN = ['wpb_variants.py', 'wpa_core.py', 'wpb_stress.py', 'run_wpb.py', 'analyze_wpb.py']
SEED = 20261028
BOOT_SEED = 20261031
METHODS = ('t0.85-deployed', 't0.85-IG+AG+VW', 't0.55-deployed', 't0.55-IG+AG+VW', 't0.85-AG', 't0.85-IG', 't0.85-VW',
           'cascade_v1', 'quote_exact', 'diff_drift', 'line_number', 'tracker_adapter')


def now():
    return datetime.now(timezone.utc).isoformat()


def code_hashes():
    here = Path(__file__).resolve().parent
    return {f'tools/v11/{n}': sha(here / n) for n in CODE + FROZEN} | {
        'tools/regenerate_history_selection.py': sha(ROOT / 'tools/regenerate_history_selection.py'),
        'evidence/source-snapshot/real_history.py': sha(ROOT / 'evidence/source-snapshot/real_history.py'),
        'tools/bin/lhdiff-driver.exe': sha(ROOT / 'tools/bin/lhdiff-driver.exe')}


def write(name, data):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    freeze = OUT / 'protocol-freeze.json'
    prov = dict(recorded_utc=now(), python=sys.version, executable=sys.executable, code_sha256=code_hashes(),
                protocol_sha256=sha(PROTOCOL), freeze_record_sha256=sha(freeze) if freeze.exists() else None)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(dict(provenance=prov, data=data), stream, separators=(',', ':'))


def verify_freeze():
    f = read(OUT / 'protocol-freeze.json')['data']
    assert f['protocol_sha256'] == sha(PROTOCOL) and f['code_sha256'] == code_hashes(), 'drift'
    b1 = read(ROOT / 'evidence/v11-wpb1/protocol-freeze.json')['data']['code_sha256']
    here = Path(__file__).resolve().parent
    for n in ('wpb_variants.py', 'wpa_core.py', 'wpb_stress.py'):
        assert b1[f'tools/v11/{n}'] == sha(here / n), n


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def selection():
    from regenerate_history_selection import harness
    original, harness_sha = harness()
    rng = random.Random(SEED)
    repos = sorted(read(PRIVATE / 'selected.json'), key=lambda r: int(r['anonymous_id'][1:]))
    items, report = [], {}
    for r in repos:
        sid, path = r['anonymous_id'], PRIVATE / 'tmp' / str(r['repository_id'])
        repo = original.Repo(str(path))
        head = repo.git('rev-parse', 'HEAD').strip()
        if head != r['head_commit_sha']:
            report[sid] = dict(status='unavailable', reason='head mismatch')
            continue
        rows, excluded, n_commits = original.run_repo(str(path), sid, rng)
        commits = repo.git('rev-list', '--first-parent', '--reverse', 'HEAD').split()
        assert len(commits) == n_commits
        report[sid] = dict(status='ok', commits=n_commits, observations=len(rows), excluded=dict(excluded),
                           pairs=len({x['pair'] for x in rows}))
        print(sid, report[sid], flush=True)
        items.append((sid, str(path), commits, rows))
        repo.cat.stdin.close()
    return items, report, harness_sha


def build_batches(sid, path, commits, rows):
    from regenerate_history_selection import harness
    original, _ = harness()
    repo = original.Repo(path)
    by_pair = defaultdict(list)
    for i, row in enumerate(rows):
        by_pair[row['pair']].append((i, row))
    for pair, members in by_pair.items():
        _, k, i = pair.split(':')
        old_c, new_c = commits[int(i)], commits[int(i) + int(k)]
        old_files = {p: repo.blob(s) for p, s in repo.tree(old_c).items()}
        version = {p: (digest(repo.blob(s)), repo.blob(s)) for p, s in repo.tree(new_c).items()}
        renames = {}
        for line in repo.git('diff', '--name-status', '-M', old_c, new_c, '--', '*.py').splitlines():
            parts = line.split('\t')
            if parts[0].startswith('R') and len(parts) == 3:
                renames[parts[1]] = parts[2]
        batch = []
        for index, row in members:
            p, start = row['anchor_at']
            text = old_files[p]
            assert '\n'.join(text.splitlines()[start - 1:start - 1 + row['span']]) == row['quotation']
            truth = row['truth_at']
            t = dict(anchor=dict(path=p, line_start=start, line_end=start + row['span'] - 1, quotation=row['quotation'],
                                 content_hash=digest(text)),
                     old_lines=text.splitlines(), version=version,
                     truth=None if truth is None else (truth[0], truth[1] - 1),
                     changed=row['cls'] in ('edited', 'gone'),
                     truth_end=None)  # the oracle gives starts only; no range reference in H2
            meta = {k2: row[k2] for k2 in ('repo', 'sample', 'pair', 'horizon', 'cls', 'how')}
            meta.update(suite='real', group='student', row=index, oracle_AST_equal=None, old_commit=old_c, new_commit=new_c,
                        renamed_path=renames.get(p))
            batch.append((meta, t, old_files))
            if len(batch) == 20:
                yield batch
                batch = []
        if batch:
            yield batch
    repo.cat.stdin.close()


def run(workers):
    import run_wpb
    items, report, harness_sha = selection()
    write('selection.json', dict(repositories=report, harness_sha256=harness_sha, observations=sum(len(x[3]) for x in items)))
    for sid, path, commits, rows in items:
        records, pending = [], []
        with ProcessPoolExecutor(max_workers=workers, initializer=run_wpb.initialize) as pool:
            for batch in build_batches(sid, path, commits, rows):
                pending.append(pool.submit(run_wpb.evaluate_batch, (batch, True)))
                if len(pending) >= workers * 2:
                    records.extend(pending.pop(0).result())
            while pending:
                records.extend(pending.pop(0).result())
        assert len(records) == len(rows)
        write(f'trials/{sid}.json', records)
        print(sid, 'evaluated', len(records), flush=True)
    write('completion.json', dict(completed_utc=now(), repositories=len(items)))


def analyze():
    from analyze_wpb import event, denominators, DENOMS
    sel = read(OUT / 'selection.json')['data']
    records = []
    for f in sorted((OUT / 'trials').glob('S*.json')):
        records.extend(read(f)['data'])
    metrics = ('accuracy', 'placement_accuracy', 'missed', 'wrong_silent', 'wrong', 'lost', 'false_recheck',
               'gone_correct')

    def summary(rs):
        out = {}
        for m in METHODS:
            k, d = Counter(), Counter()
            for r in rs:
                k.update(event(r, r['methods'][m]))
                d.update(denominators(r))
            out[m] = {x: rate(k[x], d[DENOMS.get(x, 'n')]) for x in metrics}
            out[m]['execution_errors'] = k['failure']
        return dict(n=len(rs), pairs=len({r['pair'] for r in rs}), classes=dict(Counter(r['cls'] for r in rs)), methods=out)
    res = dict(selection=sel, overall=summary(records), strata={}, repositories={})
    for s in ('uniform', 'targeted'):
        res['strata']['sample:' + s] = summary([r for r in records if r['sample'] == s])
    for h in (1, 10):
        res['strata'][f'horizon:{h}'] = summary([r for r in records if r['horizon'] == h])
    for sid in sorted({r['repo'] for r in records}, key=lambda x: int(x[1:])):
        sub = [r for r in records if r['repo'] == sid]
        res['repositories'][sid] = dict(summary(sub), flagged_small=len(sub) < 30)
    # Pair-cluster bootstrap for the deployed cascade and the deployed - tracker difference.
    clusters = defaultdict(lambda: Counter())
    for r in records:
        c = clusters[r['pair']]
        dep, trk = event(r, r['methods']['t0.85-deployed']), event(r, r['methods']['tracker_adapter'])
        c['n'] += 1
        c['changed'] += r['cls'] in ('edited', 'gone')
        c['dep'] += dep['accuracy']
        c['trk'] += trk['accuracy']
        c['dep_missed'] += dep['missed']
    keys = list(clusters.values())
    rng = random.Random(BOOT_SEED)
    acc, diff, miss = [], [], []
    for _ in range(10000):
        t = Counter()
        for _ in keys:
            t.update(rng.choice(keys))
        acc.append(t['dep'] / t['n'])
        diff.append((t['dep'] - t['trk']) / t['n'])
        if t['changed']:
            miss.append(t['dep_missed'] / t['changed'])
    q = lambda v: [sorted(v)[int(.025 * (len(v) - 1))], sorted(v)[int(.975 * (len(v) - 1))]]
    res['bootstrap'] = dict(resamples=10000, seed=BOOT_SEED, clusters=len(keys), deployed_accuracy=q(acc),
                            deployed_minus_tracker_accuracy=q(diff), deployed_missed=q(miss), missed_defined=len(miss))
    write(f'summary-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")}.json', res)
    return res


def main():
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=('freeze', 'run', 'analyze'))
    p.add_argument('--workers', type=int, default=8)
    a = p.parse_args()
    OUT.mkdir(exist_ok=True)
    assert sys.version_info[:2] >= (3, 12)
    try:
        if a.stage == 'freeze':
            write('protocol-freeze.json', dict(timestamp_utc=now(), protocol_sha256=sha(PROTOCOL), code_sha256=code_hashes(),
                  statement='No H2 selection, oracle label or method output exists before this record.'))
            return
        verify_freeze()
        if a.stage == 'run':
            write(f'run-start-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")}.json', dict(started_utc=now()))
            run(a.workers)
        else:
            analyze()
    except BaseException as error:
        write(f'{a.stage}-failure-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")}.json',
              dict(error=repr(error), traceback=traceback.format_exc()))
        raise


if __name__ == '__main__':
    main()
