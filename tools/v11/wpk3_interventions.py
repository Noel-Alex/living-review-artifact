"""WP K3: simulated supervisor interventions inside the 4,000 ten-commit chains (protocol review/V12-PROTOCOL-K3.md).

Run from paper-drafts/ with the CodeMapper interpreter:
  tools/v11-ext/codemapper/venv/Scripts/python.exe -I -B tools/v11/wpk3_interventions.py freeze
  tools/v11-ext/codemapper/venv/Scripts/python.exe -I -B tools/v11/wpk3_interventions.py run [--workers 12] [--limit N]
  tools/v11-ext/codemapper/venv/Scripts/python.exe -I -B tools/v11/wpk3_interventions.py analyze

The hop logic is chain_job's (run_wpi.py, frozen), copied verbatim; P0 must reproduce the stored chains-agi traces.
The supervisor acts only at reference prefix hops h in {1, 2, 3, 5} on which the method requested a check, and only
when the reference there is decided (status ok). Policies: P0 none; P1 correct; P2 accept; P3 correct + accept;
P4 dismiss at the first request.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/v12-wpk3'
PROTOCOL = ROOT / 'review/V12-PROTOCOL-K3.md'
WPI = ROOT / 'evidence/v11-wpi'
CODE = ('wpk3_interventions.py', 'run_wpi.py', 'wpi_core.py', 'wpb_variants.py', 'wpb2_chains.py', 'wpc_adapters.py',
        'wpc_core.py', 'wpc_cm_worker.py')
ACT_HOPS = (1, 2, 3, 5)
PREFIXES = (1, 2, 3, 5, 10)
POLICIES = ('P0', 'P1', 'P2', 'P3', 'P4')
CASCADE = {'v0.85-off': (.85, False, False, False, None), 'v0.85-alli': (.85, True, True, True, 'agi'),
           'v0.55-alli': (.55, True, True, True, 'agi')}
FLOOR = .5
METHODS = tuple(m for k in CASCADE for m in (k, k + '-id')) + ('cm-seq-gi', 'cm-seq-gi-id')
A = None


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def code_hashes():
    return {p: sha(ROOT / 'tools/v11' / p) for p in CODE}


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def init():
    global A
    from multiprocessing.util import Finalize
    from wpc_adapters import Adapters
    A = Adapters(OUT / 'workers' / str(os.getpid()))
    Finalize(A, A.close, exitpriority=10)


def acts(policy):
    return dict(P0=(), P1=('correct',), P2=('accept',), P3=('correct', 'accept'), P4=('dismiss',))[policy]


def job(args):
    import wpb2_chains as wc
    import wpb_variants
    from wpb_variants import prepare, choose
    from wpc_core import line_region, region_lines
    from wpi_core import choose_i, window_layers, window_layers_i, identity_hop, wanted_of, choose2
    from wpa_core import outcome
    name, recs = args
    if A is None:
        init()
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

    # ---- verbatim from run_wpi.chain_job ----
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
    # ---- end verbatim ----

    def guard_layers(trial, old_files, o):
        fam = window_layers(trial, old_files, o, ('quote',))
        fam['IG+AGi'] = window_layers_i(trial, old_files, o)['IG+AGi']
        return fam

    out = []
    try:
        for row, saved, stored in recs:
            commits = row['commits']
            path, start = row['anchor_at']
            span = row['span']
            v0 = version(commits[0])
            digest0, old_text = v0[path]
            q_orig = '\n'.join(old_text.splitlines()[start - 1:start - 1 + span])
            anchor = dict(path=path, line_start=start, line_end=start + span - 1, quotation=q_orig, content_hash=digest0)
            refs = {h: saved['prefixes'][str(h)]['reference'] for h in PREFIXES}

            def ref_text(h):
                r = refs[h]
                if r['status'] != 'ok' or r['truth_at'] is None:
                    return None
                tp, ts = r['truth_at']
                return '\n'.join(version(commits[h])[tp][1].splitlines()[ts - 1:ts - 1 + span])

            def decide(policy, i, hop, placement):
                """Supervisor action at hop i, or None. Returns (kind, payload)."""
                if i not in ACT_HOPS or not hop['requested_recheck'] or policy == 'P0':
                    return None
                r = refs[i]
                if r['status'] != 'ok':
                    return None
                a = acts(policy)
                if 'dismiss' in a:
                    return ('dismiss', None)
                oc = outcome(r['truth_at'], placement)
                if 'correct' in a and oc in ('wrong_place', 'lost'):
                    if r['truth_at'] is None:
                        return ('stop', None)
                    return ('correct', r['truth_at'])
                if 'accept' in a and oc == 'correct' and r['truth_at'] is not None and hop['label'] == 'changed':
                    return ('accept', None)
                return None

            record = dict(row=row['row'], repo=name, group=row['group'], refs=refs, traces={}, gate=[])
            memo = {}
            for key, (theta, ig, ag, vw, rule) in CASCADE.items():
                for floor in (None, FLOOR):
                    mname = key if floor is None else key + '-id'
                    for policy in POLICIES:
                        state, hops, q0, actions = dict(anchor), [], q_orig, []
                        stopped = dismissed = False
                        for i in range(1, 11):
                            if stopped or dismissed:
                                hops.append(dict(label='removed' if stopped else 'dismissed', interval=None,
                                                 requested_recheck=bool(stopped), reasons=['supervisor']))
                                continue
                            mk = (key, i, json.dumps(state, sort_keys=True))
                            if mk not in memo:
                                memo[mk] = cascade_hop(state, version(commits[i - 1]), version(commits[i]), theta, ig, ag, vw, rule)
                            new, o, window = memo[mk]
                            if floor is None:
                                state = new
                                hop = dict(label=o['label'], interval=o['range'], requested_recheck=o['recheck'], reasons=o['reasons'])
                                hops.append(hop)
                            else:
                                keep, request, ratio = identity_hop(q0, window, o['label'], o['recheck'], floor)
                                if not keep:
                                    state = dict(state, match='removed')
                                    hop = dict(label='removed', interval=None, requested_recheck=True, reasons=['identity-floor'], ratio=ratio)
                                else:
                                    state = new
                                    hop = dict(label=id_label(q0, window, o['label']), interval=o['range'], requested_recheck=request,
                                               reasons=o['reasons'], ratio=ratio)
                                hops.append(hop)
                            placement = None if hop['interval'] is None else hop['interval'][:2]
                            d = decide(policy, i, hop, placement)
                            if d is None:
                                continue
                            kind, at = d
                            actions.append(dict(hop=i, kind=kind))
                            if kind == 'dismiss':
                                dismissed = True
                            elif kind == 'stop':
                                stopped = True
                            elif kind == 'correct':
                                tp, ts = at
                                vt = version(commits[i])
                                text = '\n'.join(vt[tp][1].splitlines()[ts - 1:ts - 1 + span])
                                # Amendment 1: the reference keeps the original height; clip it to the new file.
                                state = dict(path=tp, line_start=ts, line_end=min(ts + span - 1, len(vt[tp][1].splitlines())),
                                             quotation=text, content_hash=vt[tp][0])
                                if floor is not None:
                                    q0 = text
                            elif kind == 'accept' and floor is not None:
                                q0 = window
                        record['traces'][f'{mname}|{policy}'] = dict(hops=[dict(label=h['label'], interval=h['interval'],
                                                                              requested_recheck=h['requested_recheck']) for h in hops],
                                                                   actions=actions)
                    p0 = record['traces'][f'{mname}|P0']['hops']
                    for mine, theirs in zip(p0, stored[mname]):
                        if (mine['label'], mine['interval'], mine['requested_recheck']) != (theirs['label'], theirs['interval'], theirs['requested_recheck']):
                            record['gate'].append(dict(method=mname, mine=mine, saved=theirs))
                            break
            # CodeMapper sequential with the IG+AGi layer (chain_job's cm-seq-gi and cm-seq-gi-id).
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

            for floor in (None, FLOOR):
                mname = 'cm-seq-gi' if floor is None else 'cm-seq-gi-id'
                for policy in POLICIES:
                    st = dict(ci=0, path=path, region=region0, quotation=q_orig, start=start)
                    q0, hops, actions = q_orig, [], []
                    stopped = dismissed = False
                    for i in range(1, 11):
                        if stopped or dismissed:
                            hops.append(dict(label='removed' if stopped else 'dismissed', interval=None,
                                             requested_recheck=bool(stopped)))
                            continue
                        o = cm(st['ci'], i, st['path'], st['region'])
                        window = None
                        if o['label'] in ('execution_error', 'removed') or o.get('placement') is None:
                            hop = dict(label=o['label'], interval=None, requested_recheck=True)
                        else:
                            t_anchor = dict(path=st['path'], line_start=st['start'], line_end=st['start'] + len(st['quotation'].splitlines()) - 1)
                            src = version(commits[st['ci']])
                            trial = dict(anchor=dict(t_anchor, quotation=st['quotation'], content_hash=src[st['path']][0]),
                                         old_lines=src[st['path']][1].splitlines(), version=version(commits[i]))
                            fam = guard_layers(trial, {q: x for q, (_, x) in src.items()}, o)
                            target, s, e = o['range']
                            window = '\n'.join(version(commits[i])[target][1].splitlines()[s - 1:e])
                            label, req_g = fam['quote']['label'], fam['IG+AGi']['recheck']
                            req = fam['quote']['recheck']
                            removed = False
                            if floor is not None:
                                keep, request, ratio = identity_hop(q0, window, 'changed' if req else 'exact', req, floor)
                                if not keep:
                                    removed = True
                                else:
                                    req_g = bool(req_g or wanted_of(q0) != wanted_of(window))
                                    label = id_label(q0, window, label)
                            if removed:
                                hop = dict(label='removed', interval=None, requested_recheck=True)
                            else:
                                hop = dict(label=label, interval=[target, s, e], requested_recheck=req_g)
                                st = dict(ci=i, path=target, region=o['character_range'], quotation=window, start=s)
                        hops.append(hop)
                        placement = None if hop['interval'] is None else hop['interval'][:2]
                        d = decide(policy, i, hop, placement)
                        if d is None:
                            continue
                        kind, at = d
                        actions.append(dict(hop=i, kind=kind))
                        if kind == 'dismiss':
                            dismissed = True
                        elif kind == 'stop':
                            stopped = True
                        elif kind == 'correct':
                            tp, ts = at
                            vt = version(commits[i])
                            text = '\n'.join(vt[tp][1].splitlines()[ts - 1:ts - 1 + span])
                            st = dict(ci=i, path=tp, region=line_region(vt[tp][1], ts, min(ts + span - 1, len(vt[tp][1].splitlines()))),
                                      quotation=text, start=ts)
                            if floor is not None:
                                q0 = text
                        elif kind == 'accept' and floor is not None:
                            q0 = window
                    record['traces'][f'{mname}|{policy}'] = dict(hops=hops, actions=actions)
                p0 = record['traces'][f'{mname}|P0']['hops']
                agree = sum((a['label'], a['interval'], a['requested_recheck']) == (b['label'], b['interval'], b['requested_recheck'])
                            for a, b in zip(p0, stored[mname]))
                record.setdefault('cm_agreement', {})[mname] = agree
            # Texts needed for scoring against the last review (stripped as the reference oracle strips them).
            record['ref_stripped'] = {str(h): (None if ref_text(h) is None else list(original.stripped(ref_text(h).splitlines())))
                                      for h in PREFIXES}
            record['orig_stripped'] = list(original.stripped(q_orig.splitlines()))
            out.append(record)
    finally:
        repo.cat.stdin.close()
        repo.cat.wait(timeout=15)
        history.close()
    return out


def safe_job(args):
    """Amendment 1: a failing chain is recorded as an error row instead of stopping the run."""
    try:
        return job(args)
    except Exception:
        name, recs = args
        out = []
        for rec in recs:
            try:
                out.extend(job((name, [rec])))
            except Exception as e:
                out.append(dict(row=rec[0]['row'], repo=name, error=repr(e)[:300], gate=[], cm_agreement={}))
        return out


def freeze():
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / 'protocol-freeze.json'
    assert not f.exists() and not (OUT / 'rows.json').exists()
    f.write_text(json.dumps(dict(recorded_utc=utc(), protocol_sha256=sha(PROTOCOL), code_sha256=code_hashes(),
                                 statement='No WP K3 outcome exists before this record.'), indent=1), encoding='utf-8')
    print('frozen')


def verify_freeze():
    fz = json.loads((OUT / 'protocol-freeze.json').read_text(encoding='utf-8'))
    assert fz['protocol_sha256'] == sha(PROTOCOL)
    allowed = dict(fz['code_sha256'])
    am = OUT / 'protocol-amendment-1.json'
    if am.exists():  # amendments recorded before any outcome may replace code hashes
        allowed.update(json.loads(am.read_text(encoding='utf-8'))['code_sha256'])
    now = code_hashes()
    bad = [p for p in allowed if allowed[p] != now.get(p)]
    assert not bad, bad
    return fz


def load_inputs():
    import wpb2_chains as wc
    rows = wc.chain_rows()
    saved = {r['row']: r for r in json.loads((ROOT / 'evidence/v11-wpb2/chains/trials.json').read_text())['data']}
    agi = {r['row']: r for r in json.loads((WPI / 'chains-agi/rows.json').read_text())['data']}
    return rows, saved, agi


def run(workers, limit):
    if not limit:
        verify_freeze()
    rows, saved, agi = load_inputs()
    by_repo = defaultdict(list)
    for r in rows:
        a = agi[r['row']]
        by_repo[r['repo']].append((r, dict(prefixes=saved[r['row']]['prefixes']), {m: a[m] for m in METHODS}))
    jobs = [(name, subset[i:i + 25]) for name, subset in sorted(by_repo.items(), key=lambda kv: -len(kv[1]))
            for i in range(0, len(subset), 25)]
    if limit:
        jobs = jobs[:limit]
    out, begin = [], time.time()
    with ProcessPoolExecutor(max_workers=workers, initializer=init) as pool:
        for got in pool.map(safe_job, jobs):
            out.extend(got)
            print(len(out), f'{time.time() - begin:.0f}s', flush=True)
    out.sort(key=lambda r: r['row'])
    suffix = '-smoke' if limit else ''
    (OUT / f'rows{suffix}.json').write_text(json.dumps(dict(code_sha256=code_hashes(), recorded_utc=utc(), data=out)), encoding='utf-8')
    gate = [dict(row=r['row'], **g) for r in out for g in r['gate']]
    cm_agree = {m: sum(r['cm_agreement'].get(m, 0) for r in out) for m in ('cm-seq-gi', 'cm-seq-gi-id')}
    (OUT / f'gate{suffix}.json').write_text(json.dumps(dict(rows=len(out), cascade_mismatches=len(gate), first=gate[:50],
                                                            passed=not gate, cm_hops_agreeing=cm_agree, cm_hops=10 * len(out)), indent=1), encoding='utf-8')
    (OUT / f'completion{suffix}.json').write_text(json.dumps(dict(n=len(out), complete=len(out) == (4000 if not limit else len(out)) and not gate,
                                                                  seconds=round(time.time() - begin), utc=utc()), indent=1), encoding='utf-8')
    print('done', len(out), 'gate mismatches', len(gate), cm_agree)


# ---------------- analysis ----------------
def endpoint(rec, trace):
    """Hop-10 events, with change measured since the last supervisor review (the last correct/accept/stop)."""
    from wpa_core import outcome
    hops, actions = trace['hops'], trace['actions']
    if any(a['kind'] == 'dismiss' for a in actions):
        return None
    ref = rec['refs']['10']
    review = max([a['hop'] for a in actions if a['kind'] in ('correct', 'accept', 'stop')] + [0])
    at = None if hops[9]['interval'] is None else hops[9]['interval'][:2]
    oc = outcome(ref['truth_at'], at)
    if review == 0:
        changed = ref['cls'] in ('edited', 'gone')
    else:
        base = rec['ref_stripped'][str(review)]
        now = rec['ref_stripped']['10']
        changed = False if base is None else (now is None or now != base)
    request = hops[9]['requested_recheck']
    since = hops[review:]
    any_req = any(h['requested_recheck'] for h in since)
    wrong = oc == 'wrong_place'
    return dict(correct=int(oc == 'correct'), wrong=int(wrong), lost=int(oc == 'lost'), changed=int(changed),
                missed_last=int(changed and not request), missed_cumulative=int(changed and not any_req),
                wrong_silent_last=int(wrong and not request), actions=len(actions),
                requests_seen=sum(hops[h - 1]['requested_recheck'] for h in PREFIXES))


MEAS = ('correct', 'wrong', 'lost', 'missed_last', 'missed_cumulative', 'wrong_silent_last', 'actions', 'requests_seen', 'changed')


def analyze():
    import numpy as np
    doc = json.loads((OUT / 'rows.json').read_text(encoding='utf-8'))
    rows = [r for r in doc['data'] if 'error' not in r and r['refs']['10']['status'] == 'ok']
    res, boot = {}, {}
    rng = np.random.default_rng(20261031)
    W = rng.multinomial(len(rows), np.full(len(rows), 1 / len(rows)), size=10000).astype(np.float64)
    for m in METHODS:
        res[m] = {}
        mats = {}
        for p in POLICIES[:4]:
            ev = [endpoint(r, r['traces'][f'{m}|{p}']) for r in rows]
            mat = np.array([[e[k] for k in MEAS] for e in ev], dtype=np.float64)
            mats[p] = mat
            tot = mat.sum(0)
            res[m][p] = {k: int(tot[j]) for j, k in enumerate(MEAS)}
            res[m][p]['chains'] = len(rows)
            res[m][p]['actions_per_chain'] = round(tot[MEAS.index('actions')] / len(rows), 3)
        for p in POLICIES[1:4]:
            diff = mats[p] - mats['P0']
            bs = W @ diff / len(rows)
            boot[f'{m}|{p} minus P0'] = {k: dict(difference=round(float(diff[:, j].sum()), 1),
                                                 per_chain=round(float(diff[:, j].mean()), 5),
                                                 ci95_per_chain=[round(float(x), 5) for x in np.quantile(bs[:, j], [.025, .975])])
                                         for j, k in enumerate(MEAS)}
        # P4: dismissal at the first request; changes the workflow will never surface.
        d = Counter()
        for r in rows:
            tr = r['traces'][f'{m}|P4']
            dis = [a['hop'] for a in tr['actions'] if a['kind'] == 'dismiss']
            if not dis:
                continue
            h = dis[0]
            d['dismissed'] += 1
            later = [x for x in PREFIXES if x > h and r['refs'][str(x)]['status'] == 'ok']
            base = r['ref_stripped'][str(h)]
            changed_later = [x for x in later if base is not None and r['ref_stripped'][str(x)] != base]
            d['changed_after_dismissal'] += bool(changed_later)
            d['changed_after_dismissal_by_10'] += (base is not None and r['ref_stripped']['10'] != base)
            d['dismissed_at_' + str(h)] += 1
        res[m]['P4'] = dict(d, chains=len(rows))
    summary = dict(recorded_utc=utc(), rows_sha256=sha(OUT / 'rows.json'), code_sha256=code_hashes(),
                   gate=json.loads((OUT / 'gate.json').read_text(encoding='utf-8')),
                   freeze=json.loads((OUT / 'protocol-freeze.json').read_text(encoding='utf-8')),
                   chains_scored=len(rows), methods=res, paired=boot, resamples=10000, seed=20261031)
    name = 'summary-' + time.strftime('%Y%m%dT%H%M%S', time.gmtime()) + '.json'
    (OUT / name).write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(name)
    for m in METHODS:
        print(m, {p: (res[m][p]['correct'], res[m][p]['wrong'], res[m][p]['lost'], res[m][p]['missed_last'],
                      res[m][p]['wrong_silent_last'], res[m][p]['actions']) for p in POLICIES[:4]}, res[m]['P4'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=('freeze', 'run', 'analyze'))
    ap.add_argument('--workers', type=int, default=12)
    ap.add_argument('--limit', type=int, default=0)
    a = ap.parse_args()
    os.environ['GIT_NO_LAZY_FETCH'] = '1'
    try:
        {'freeze': freeze, 'run': lambda: run(a.workers, a.limit), 'analyze': analyze}[a.stage]()
    except BaseException:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f'failure-{time.strftime("%Y%m%dT%H%M%S")}.txt').write_text(traceback.format_exc(), encoding='utf-8')
        raise


if __name__ == '__main__':
    main()
