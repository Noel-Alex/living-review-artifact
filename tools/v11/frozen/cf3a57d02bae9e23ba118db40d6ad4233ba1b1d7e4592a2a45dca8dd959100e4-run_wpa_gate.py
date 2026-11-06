"""Fresh source reconstruction and strict matcher/factorial reproduction gate.

Run with pinned Python -B. Worker processes are local CPU workers, not agents.
All writes stay in WPA evidence; old evidence is opened read-only.
"""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import random
import sys
import traceback

from wpa_core import *
from history_context import open_histories, load_rows
from regenerate_history_selection import harness
from tracker_process import TrackerProcess


def worker_init():
    global MATCHER, BENCH, TRACKER, TRACK_CACHE
    MATCHER, BENCH = loaders()
    TRACKER = TrackerProcess(ROOT / 'tools/bin/lhdiff-driver.exe')
    TRACK_CACHE = {}


def tracker_output(trial, base):
    a, files = base['anchor'], base['version']
    old = '\n'.join(trial['old_lines'])+'\n'
    new = files.get(a['path'], ('', ''))[1]
    key = (hashlib.sha256(old.encode()).digest(), hashlib.sha256(new.encode()).digest())
    if key not in TRACK_CACHE:
        TRACK_CACHE[key] = TRACKER.map(old, new) if new else ({}, None)
    mapping, error = TRACK_CACHE[key]
    if error:
        return {'label': 'execution_error', 'placement': None, 'error': error}
    start = mapping.get(a['line_start'], 0)
    if not start:
        return {'label': 'removed', 'placement': None}
    at = [a['path'], start]
    want = [x.strip() for x in a['quotation'].splitlines() if x.strip()]
    here = [x.strip() for x in new.splitlines()[start-1:start-1+a['line_end']-a['line_start']+1] if x.strip()]
    label = ('exact' if at == [a['path'], a['line_start']] else 'moved') if here == want else 'changed'
    return {'label': label, 'placement': at}


def work(payload):
    version, items = payload
    outputs = []
    for meta, trial, archived, tracker_archived, rename_path in items:
        if version is not None:
            trial['version'] = version
        MATCHER.FUZZY_CODE = .85
        base = trial if rename_path is None else dict(trial, anchor=dict(trial['anchor'], path=rename_path))
        origin = [trial['anchor']['path'], trial['anchor']['line_start']]
        f = features(trial, MATCHER)
        direct = direct_output(trial, MATCHER)
        final = cell_output(f, 'fuzzy_first', 'local', 'full', .85, origin)
        assert all(final[k] == direct[k] for k in ('label', 'placement')), (meta, 'factorial deployed mismatch')
        assert final['label'] == archived['label'], (meta, 'label', final['label'], archived['label'])
        methods = {'cascade': final}
        for name in METHODS:
            MATCHER.FUZZY_CODE = .85
            if name == 'cascade_v1':
                placed, flagged = BENCH.m_cascade_v1(trial)
                output = cell_output(f, 'cross_first', 'whole', 'legacy', .75, origin)
                expected_at = None if placed is None else [placed[0], placed[1]+1]
                assert output['placement'] == expected_at and (output['label'] != 'exact') == flagged, (meta, 'v1 corner')
                methods[name] = output
            elif name != 'cascade':
                placed, flagged = BENCH.METHODS[name](base)
                at = None if placed is None else [placed[0], placed[1]+1]
                label = 'removed' if at is None else 'exact' if not flagged else 'moved'
                methods[name] = {'placement': at, 'label': label, 'adapter_recheck': flagged}
            output = methods[name]
            placed = None if output['placement'] is None else (output['placement'][0], output['placement'][1]-1)
            flagged = output.get('adapter_recheck', output['label'] != 'exact')
            oc, silent = BENCH.score(trial, placed, flagged)
            assert oc == archived[name]['outcome'] and silent == archived[name]['silent'], (meta, name, oc, silent, archived[name])
            if 'flagged' in archived[name]:
                assert flagged == archived[name]['flagged'], (meta, name, 'flag')
        grid = []
        for order, scope, height, theta in CELLS:
            output = cell_output(f, order, scope, height, theta, origin)
            grid.append(encode_output(output, meta))
            field = 'theta' if (order, scope, height) == ('fuzzy_first', 'local', 'full') else (
                'theta_v1' if (order, scope, height) == ('cross_first', 'whole', 'legacy') else None)
            if field and field in archived and str(theta) in archived[field]:
                expected = archived[field][str(theta)]
                expected = expected[0] if isinstance(expected, list) else expected
                assert outcome(meta['truth_at'], output['placement']) == expected, (meta, field, theta)
                if field == 'theta_v1':
                    placed = None if output['placement'] is None else (output['placement'][0], output['placement'][1]-1)
                    assert BENCH.score(trial, placed, output['label'] != 'exact')[1] == archived[field][str(theta)][1]
        tracker = tracker_output(trial, base)
        assert outcome(meta['truth_at'], tracker['placement'], tracker['label'] == 'execution_error') == tracker_archived['tracker'], (meta, 'tracker mismatch')
        methods['tracker_adapter'] = tracker
        error_case = None
        if meta['cls'] in ('edited', 'gone') and final['label'] not in ('changed', 'removed'):
            same = [c for c in f['copies'] if c['path'] == trial['anchor']['path']]
            other = [c for c in f['copies'] if c['path'] != trial['anchor']['path']]
            error_case = dict(meta, label=final['label'], tier=final['tier'], placement=final['placement'],
                              copies=f['copies'], same_file_copies=len(same), other_file_copies=len(other),
                              total_copies=len(f['copies']))
        failure_case = None
        if meta['benchmark'] != 'real' and outcome(meta['truth_at'], final['placement']) != 'correct':
            cause = 'other'
            if final['tier'] == 'same_exact':
                copies = f['copies']
                exact_raw = [c for c in copies if '\n'.join(trial['version'][c['path']][1].splitlines()[c['start']-1:c['end']]) == trial['anchor']['quotation']]
                cause = 'tie-breaking among identical runs' if len(exact_raw) >= 2 else 'whitespace normalisation'
            elif final['tier'] == 'local':
                cause = 'local-window similarity'
            elif final['tier'] == 'cross_exact':
                cause = 'cross-file ordering'
            failure_case = dict(meta, cause=cause, output=final, copies=f['copies'],
                                local=f['local'], whole=f['whole_full'])
        outputs.append(dict(meta, methods=methods, grid=grid, missed_case=error_case,
                            controlled_failure=failure_case, short_file=f['short_file']))
    return outputs


def controlled_payloads(bench):
    bench.ROOTS = [CORPUS / 'vcap/app', CORPUS / 'partners/cdc-trace/cdc']
    corpus = bench.corpus()
    names = sorted(corpus)
    for label, seed in [('main', 20261018), ('replication', 20261027)]:
        reference = read(ROOT / f'evidence/synthetic-reproduction/{label}-trials.json')
        trackers = read(ROOT / f'evidence/external-comparison/{label}-trials.json')
        rng, index = random.Random(seed), 0
        for op in bench.OPS:
            batch = []
            while len(batch) < 300:
                trial = bench.make_trial(rng, corpus, names, op)
                if trial is None:
                    continue
                saved = reference[index]
                a = trial['anchor']
                truth = None if trial['truth'] is None else [trial['truth'][0], trial['truth'][1]+1]
                cls = 'gone' if truth is None else 'edited' if trial['changed'] else 'moved file' if truth[0] != a['path'] else 'in place' if truth[1] == a['line_start'] else 'shifted'
                meta = dict(benchmark=label, row=index, cls=cls, truth_at=truth,
                            anchor_at=[a['path'], a['line_start']], source_file=a['path'], span=a['line_end']-a['line_start']+1,
                            op=op, group='controlled', sample='balanced', pair=f'{label}:{index}')
                assert all(saved[k] == v for k, v in {'op': op, 'span': meta['span'], 'changed': trial['changed'], 'gone': truth is None, 'file_lines': len(trial['old_lines'])}.items())
                batch.append((meta, trial, saved, trackers[index], None))
                index += 1
                if len(batch) == 25:
                    yield None, batch
                    batch = []
                # count per operator independently of batch size
                if index % 300 == 0:
                    if batch:
                        yield None, batch
                    break
        assert index == len(reference) == 3600


def real_payloads(manifest):
    original, _ = harness()
    rows = load_rows()
    trackers = read(ROOT / 'evidence/real-tracker-comparison/trials.json')
    histories = open_histories()
    try:
        for name, history in histories.items():
            manifest[name] = {'head': history.head, 'commits': history.commits, 'pairs': {}}
            repo = original.Repo(str(history.path))
            pair, batch, version = None, [], None
            try:
                for index, row in enumerate(rows):
                    if row['repo'] != name:
                        continue
                    if row['pair'] != pair:
                        if batch:
                            yield version, batch
                        batch, pair = [], row['pair']
                        old, new = history.pair(row)
                        tree = repo.tree(new)
                        version = {p: (hashlib.sha256(repo.blob(s).encode()).hexdigest(), repo.blob(s)) for p, s in tree.items()}
                        manifest[name]['pairs'][pair] = {'old': old, 'new': new,
                            'new_file_map_sha256': hashlib.sha256(json.dumps({p:v[0] for p,v in version.items()}, sort_keys=True).encode()).hexdigest()}
                    old_text = history.blob(old, row['anchor_at'][0])
                    a = {'path': row['anchor_at'][0], 'line_start': row['anchor_at'][1],
                         'line_end': row['anchor_at'][1]+row['span']-1, 'quotation': row['quotation'],
                         'content_hash': hashlib.sha256(old_text.encode()).hexdigest()}
                    assert '\n'.join(old_text.splitlines()[a['line_start']-1:a['line_end']]) == row['quotation']
                    trial = dict(anchor=a, old_lines=old_text.splitlines(), truth=None if row['truth_at'] is None else (row['truth_at'][0],row['truth_at'][1]-1), changed=row['cls'] in ('edited','gone'))
                    meta = {k: row[k] for k in ('repo','group','sample','pair','horizon','cls','how','span','anchor_at','truth_at')}
                    meta.update(benchmark='real', row=index, source_file=a['path'], old_file_sha256=a['content_hash'])
                    renamed = history.renames(old, new).get(a['path'], a['path'])
                    assert (renamed != a['path']) == row['renamed']
                    batch.append((meta, trial, row, trackers[index], renamed if row['renamed'] else None))
                if batch:
                    yield version, batch
            finally:
                repo.cat.stdin.close()
                repo.cat.wait(timeout=15)
            runs.cache_clear()
    finally:
        for history in histories.values():
            history.close()


def main():
    _, bench = loaders()
    manifest, records = {}, []
    report = {'passed': False, 'counts': {}, 'differences': [], 'cells': CELLS}
    archived_paths = [ROOT / f'evidence/{folder}/{name}-trials.json' for folder in ('synthetic-reproduction','external-comparison') for name in ('main','replication')]
    archived_paths += [ROOT / 'evidence/real-tracker-comparison/trials.json', ROOT / 'tools/bin/lhdiff-driver.exe']
    try:
        with ProcessPoolExecutor(max_workers=6, initializer=worker_init) as pool:
            pending = []
            def consume():
                future = pending.pop(0)
                got = future.result()
                records.extend(got)
                if len(records) % 500 < len(got):
                    print('Exact gate observations:', len(records), got[-1]['benchmark'], got[-1].get('repo',''), flush=True)
            for payload in itertools.chain(controlled_payloads(bench), real_payloads(manifest)):
                pending.append(pool.submit(work, payload))
                if len(pending) >= 12:
                    consume()
            while pending:
                consume()
        records.sort(key=lambda r: (('main','replication','real').index(r['benchmark']), r['row']))
        counts = Counter(r['benchmark'] for r in records)
        assert counts == {'main':3600,'replication':3600,'real':15064}, counts
        report.update(passed=True, counts=dict(counts), tracker_execution_errors=sum(r['methods']['tracker_adapter']['label']=='execution_error' for r in records),
                      short_file_cases=sum(r['short_file'] for r in records),
                      checks='All method outcome/silent fields, controlled flags and metadata, final labels, direct deployed/v1 corners, every archived threshold outcome and v1 silent flag, tracker per-case outcomes')
        write('history-inputs.json', manifest)
        write('gate-trials.json', records, archived_paths+[OUT/'history-inputs.json'])
    except BaseException as error:
        report.update(error=repr(error), traceback=traceback.format_exc(), completed=len(records))
        write('gate-failure-partial.json', records, archived_paths)
        raise
    finally:
        write('reproduction-gate.json', report, archived_paths)
        print(json.dumps({k:v for k,v in report.items() if k != 'cells'}), flush=True)


if __name__ == '__main__':
    main()
