"""WP B2 stages (protocol: review/V11-PROTOCOL-B2.md). Exclusive-create outputs; no app imports or network.

python -B tools/v11/run_wpb2.py freeze|compound|chains|multianchor|scaling|analyze [--workers N]
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpa_core import ROOT, sha, read, rate  # noqa: E402

OUT = ROOT / 'evidence/v11-wpb2'
PROTOCOL = ROOT / 'review/V11-PROTOCOL-B2.md'
CODE = ['run_wpb2.py', 'wpb2_compound.py', 'wpb2_chains.py', 'wpb2_scaling.py', 'test_wpb2.py']
FROZEN_B1 = ['wpb_variants.py', 'wpa_core.py', 'wpb_stress.py', 'run_wpb.py', 'analyze_wpb.py']
SEEDS = (20261018, 20261027)
GROUP_KS = (1, 2, 3, 5, 8, 12)
GROUP_SEED = 20261101
GROUP_METHODS = ('t0.85-deployed', 't0.85-IG+AG+VW', 't0.55-deployed', 't0.55-IG+AG+VW')


def now():
    return datetime.now(timezone.utc).isoformat()


def code_hashes():
    here = Path(__file__).resolve().parent
    return {f'tools/v11/{n}': sha(here / n) for n in CODE + FROZEN_B1}


def provenance():
    freeze = OUT / 'protocol-freeze.json'
    return dict(recorded_utc=now(), python=sys.version, executable=sys.executable, code_sha256=code_hashes(),
                protocol_sha256=sha(PROTOCOL), freeze_record_sha256=sha(freeze) if freeze.exists() else None)


def write(name, data):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(dict(provenance=provenance(), data=data), stream, separators=(',', ':'))


def verify_freeze():
    f = read(OUT / 'protocol-freeze.json')['data']
    assert f['protocol_sha256'] == sha(PROTOCOL), 'protocol drift'
    amendments = sorted(OUT.glob('protocol-amendment-*.json'))
    current = read(amendments[-1])['data'] if amendments else f
    assert current['code_sha256'] == code_hashes(), 'code drift'
    b1 = read(ROOT / 'evidence/v11-wpb1/protocol-freeze.json')['data']['code_sha256']
    here = Path(__file__).resolve().parent
    for n in ('wpb_variants.py', 'wpa_core.py', 'wpb_stress.py'):
        assert b1[f'tools/v11/{n}'] == sha(here / n), f'frozen B1 file changed: {n}'
    return f


# ---------- B2a ----------
def compound_stage(workers):
    import run_wpb
    from wpb2_compound import compound
    import itertools
    gen = itertools.chain(*(compound(s) for s in SEEDS))
    audits, records, pending = [], [], []
    with ProcessPoolExecutor(max_workers=workers, initializer=run_wpb.initialize) as pool:
        batch = []
        for meta, t, old in gen:
            if meta.get('generator_audit'):
                audits.append(meta)
                print('generator', meta['seed'], meta['op'], meta['counts'], flush=True)
                continue
            batch.append((meta, t, old))
            if len(batch) == 20:
                pending.append(pool.submit(run_wpb.evaluate_batch, (batch, True)))
                batch = []
                if len(pending) >= workers * 2:
                    records.extend(pending.pop(0).result())
                    print('compound', len(records), flush=True)
        if batch:
            pending.append(pool.submit(run_wpb.evaluate_batch, (batch, True)))
        while pending:
            records.extend(pending.pop(0).result())
    write('compound/trials.json', records)
    write('compound/completion.json', dict(n=len(records), generator_audits=audits, complete=all(a['complete'] for a in audits),
                                           completed_utc=now()))


# ---------- B2b ----------
def _chain_job(args):
    import wpb2_chains
    name, rows = args
    return wpb2_chains.run_repo(name, rows)


def chains_stage(workers):
    # Amendment 1: the archived oracle parsed Python 3.12 syntax; 3.11 rejects some history files.
    assert sys.version_info[:2] >= (3, 12), 'chains need Python >= 3.12 (amendment 1)'
    import wpb2_chains
    rows = wpb2_chains.chain_rows()
    by_repo = defaultdict(list)
    for r in rows:
        by_repo[r['repo']].append(r)
    jobs = []
    for name, subset in sorted(by_repo.items(), key=lambda kv: -len(kv[1])):
        for i in range(0, len(subset), 100):
            jobs.append((name, subset[i:i + 100]))
    out = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for got in pool.map(_chain_job, jobs):
            out.extend(got)
            print('chains', len(out), flush=True)
    out.sort(key=lambda r: r['row'])
    write('chains/trials.json', out)  # amendment 1: results are kept before the gate is checked
    # Gates: recomputed h=10 reference, direct h=10 and zero-switch theta 0.85 trace reproduce the archive.
    gate = Counter()
    for r in out:
        ref = r['prefixes']['10']['reference']
        assert ref['status'] == 'ok' and ref['truth_at'] == r['archived_truth_at'] and ref['cls'] == r['archived_cls'], (r['row'], ref)
        for label in ('default', 'calibrated'):
            d = r['prefixes']['10']['direct']['deployed-' + label]
            assert d['range'] == r['archived-direct-' + label]['interval'], (r['row'], label)
        for mine, theirs in zip(r['v0.85-off'], r['archived-default']):
            assert mine['label'] == theirs['label'] and mine['interval'] == theirs['interval'], (r['row'], mine, theirs)
            assert mine['requested_recheck'] == theirs['requested_recheck']
        gate['rows'] += 1
    assert gate['rows'] == 4000
    write('chains/gate.json', dict(passed=True, rows=gate['rows'], checks='h=10 oracle truth and class; direct deployed intervals at theta 0.85 and 0.5; zero-switch theta-0.85 sequential label, interval and request at all ten hops', completed_utc=now()))


# ---------- B2c ----------
def real_records():
    records = {}
    for f in sorted((ROOT / 'evidence/v11-wpb1/evaluation').glob('trials-*.json')):
        for r in read(f)['data']:
            if r['suite'] == 'real':
                records[r['row']] = r
    assert len(records) == 15064, len(records)
    return records


def multianchor_stage():
    records = real_records()
    distinct = {}
    for row in sorted(records):
        r = records[row]
        distinct.setdefault((r['pair'], tuple(r['anchor_at'])), r)
    by_pair = defaultdict(list)
    for r in distinct.values():
        by_pair[r['pair']].append(r)
    rng = random.Random(GROUP_SEED)
    result = dict(distinct_observations=len(distinct), pairs=len(by_pair), ks={})
    for k in GROUP_KS:
        groups, support = [], 0
        for pair in sorted(by_pair):
            items = sorted(by_pair[pair], key=lambda r: r['row'])
            rng.shuffle(items)
            n = len(items) // k
            support += n > 0
            groups += [items[i * k:(i + 1) * k] for i in range(n)]
        cell = dict(pairs_supporting=support, groups=len(groups), methods={})
        for m in GROUP_METHODS:
            c = Counter()
            for g in groups:
                req = [x['methods'][m]['recheck'] for x in g]
                changed = [x['cls'] in ('edited', 'gone') for x in g]
                c['issues'] += 1
                c['recheck'] += any(req)
                c['recheck_nonprimary_only'] += any(req) and not req[0]
                c['issues_with_change'] += any(changed)
                c['any_rule_missed'] += any(changed) and not any(req)
                c['primary_only_missed'] += any(changed) and not req[0]
                c['primary_only_missed_but_any_rule_requests'] += any(changed) and not req[0] and any(req)
                c['issues_all_preserved'] += not any(changed)
                c['recheck_all_preserved'] += not any(changed) and any(req)
            cell['methods'][m] = dict(counts=dict(c), recheck_rate=rate(c['recheck'], c['issues']),
                                      nonprimary_share_of_rechecks=rate(c['recheck_nonprimary_only'], c['recheck']),
                                      any_rule_missed_rate=rate(c['any_rule_missed'], c['issues_with_change']),
                                      primary_only_missed_rate=rate(c['primary_only_missed'], c['issues_with_change']),
                                      recheck_rate_all_preserved=rate(c['recheck_all_preserved'], c['issues_all_preserved']))
        result['ks'][str(k)] = cell
    write('multianchor/summary.json', result)


# ---------- B2d ----------
def scaling_stage():
    import wpb2_scaling
    write('scaling/start.json', dict(started_utc=now()))
    write('scaling/results.json', wpb2_scaling.run())


def main():
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=('freeze', 'amend', 'compound', 'chains', 'multianchor', 'scaling'))
    p.add_argument('--reason', default='')
    p.add_argument('--workers', type=int, default=8)
    args = p.parse_args()
    OUT.mkdir(exist_ok=True)
    try:
        if args.stage == 'freeze':
            write('protocol-freeze.json', dict(timestamp_utc=now(), protocol_sha256=sha(PROTOCOL), code_sha256=code_hashes(),
                  statement='No B2 evaluation-seed trial, prefix result, grouping or benchmark exists before this record; development used seed 7 and three tracer chains for construction checks only.'))
            return
        if args.stage == 'amend':
            n = len(list(OUT.glob('protocol-amendment-*.json'))) + 1
            write(f'protocol-amendment-{n}.json', dict(timestamp_utc=now(), protocol_sha256=sha(PROTOCOL), code_sha256=code_hashes(),
                  previous_freeze_sha256=sha(OUT / 'protocol-freeze.json'), reason=args.reason))
            return
        verify_freeze()
        write(f'{args.stage}-start-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")}.json', dict(started_utc=now()))
        dict(compound=lambda: compound_stage(args.workers), chains=lambda: chains_stage(args.workers),
             multianchor=multianchor_stage, scaling=scaling_stage)[args.stage]()
        print(args.stage, 'complete', flush=True)
    except BaseException as error:
        write(f'{args.stage}-failure-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")}.json',
              dict(error=repr(error), traceback=traceback.format_exc(), failed_utc=now()))
        raise


if __name__ == '__main__':
    main()
