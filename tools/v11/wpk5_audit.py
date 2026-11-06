"""WP K5: stratified, blinded adjudication of the syntax-tree reference by two hosted models (protocol V12-PROTOCOL-K5.md).

Run from paper-drafts/ with the CodeMapper interpreter:
  python -I -B tools/v11/wpk5_audit.py sample            -> evidence/v12-wpk5/sample.json (+ private/key.json)
  python -I -B tools/v11/wpk5_audit.py freeze
  python -I -B tools/v11/wpk5_audit.py run --model beam|nemotron [--workers 4]
  python -I -B tools/v11/wpk5_audit.py analyze           -> evidence/v12-wpk5/summary-<utc>.json
  python -I -B tools/v11/wpk5_audit.py packet            -> evidence/v12-wpk5/human-packet/ (+ human-packet-key.json)
The adjudicators are language models, not human annotators. They see the old excerpt with the reviewed lines marked
and the paired new file; never the reference or any method's output. Transport, the rate gate and retry rules are
WP J's (run_wpj.py, run_wpj_nim.py). Public code only (all histories are public or the authors' own); keys are never
written.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import random
import re
import sys
import threading
import time
import urllib.error
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/v12-wpk5'
PROTOCOL = ROOT / 'review/V12-PROTOCOL-K5.md'
SEED = 20261108
PER_STRATUM = 50
CONTEXT_OLD = 40
MAX_NEW = 1200
STRATA = ('S-miss', 'S-pair', 'S-del', 'S-dis', 'S-aligned', 'S-excl')
SYSTEM = ('You audit how a reviewed block of Python code changed between two versions of a file. In the OLD excerpt the '
          'reviewed lines are marked with ">>". Every line is numbered. Find the code that the reviewed lines became in '
          'the NEW file: the same statements, possibly edited or moved, not merely similar code elsewhere. Answer ONLY '
          'with a JSON object {"status": "unchanged" | "edited" | "deleted", "start": <first line number in NEW or null>, '
          '"end": <last line number in NEW or null>, "reason": "<one line>"}. unchanged: the reviewed lines are present '
          'with the same text apart from whitespace; edited: they are present but their text was modified; deleted: they '
          'are no longer in the NEW file (start and end null).')
CODE = ('wpk5_audit.py', 'run_wpj.py', 'run_wpj_nim.py')


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha(p):
    return sha_bytes(Path(p).read_bytes())


def utc():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def code_hashes():
    return {p: sha(ROOT / 'tools/v11' / p) for p in CODE}


# ---------------- pool and strata ----------------
def ref_status(cls):
    return 'edited' if cls == 'edited' else 'deleted' if cls == 'gone' else 'unchanged'


def disagreements(r):
    """Count of CodeMapper, tracker and GumTree (+quote) that disagree with the reference on location or status."""
    n = avail = 0
    changed = r['cls'] in ('edited', 'gone')
    for m in ('codemapper+quote', 'tracker+quote', 'gumtree+quote'):
        o = r['methods'].get(m)
        if not o or o.get('label') == 'execution_error':
            continue
        avail += 1
        at = o.get('placement')
        loc_bad = (at is not None) if r['truth_at'] is None else (at is None or list(at) != list(r['truth_at']))
        status_bad = bool(o.get('recheck')) != changed
        n += loc_bad or status_bad
    return n, avail


def pool():
    real = [r for p in sorted(glob.glob(str(ROOT / 'evidence/v11-wpi/transfer/rows-*.json')))
            for r in json.loads(Path(p).read_text())['data'] if r['suite'] == 'real']
    stu = json.loads((ROOT / 'evidence/v11-wpi/students/rows.json').read_text())['data']
    items = []
    for population, rows in (('real', real), ('student', stu)):
        for r in rows:
            n, avail = disagreements(r)
            items.append(dict(id=f"{population}:{r['row']}", population=population, repo=r['repo'], pair=r['pair'],
                              horizon=r['horizon'], sample=r['sample'], old_commit=r['old_commit'], new_commit=r['new_commit'],
                              path=r['anchor_at'][0], start=r['anchor_at'][1], span=r['span'], renamed_path=r['renamed_path'],
                              cls=r['cls'], how=r['how'], truth_at=r['truth_at'], disagree=n, disagree_avail=avail,
                              deployed_missed=bool(r['cls'] in ('edited', 'gone') and not r['methods']['t0.85-deployed'].get('recheck')),
                              old_file_sha256=r['old_file_sha256']))
    excl = []
    for p in sorted(glob.glob(str(ROOT / 'evidence/v11-wpa/exclusions-*.json'))):
        d = json.loads(Path(p).read_text())
        for x in (d.get('data', d) if isinstance(d, dict) else d):
            if x['status'] == 'excluded' and x['reason'] != 'unparsable':
                excl.append(dict(id=f"excluded:{x['repo']}:{x['pair']}:{x['sample']}:{x['anchor_at'][0]}:{x['anchor_at'][1]}",
                                 population='real-excluded', repo=x['repo'], pair=x['pair'], horizon=x['horizon'], sample=x['sample'],
                                 old_commit=x['old_c'], new_commit=x['new_c'], path=x['anchor_at'][0], start=x['anchor_at'][1],
                                 span=x['span'], renamed_path=None, cls=None, how=None, truth_at=None, exclusion_reason=x['reason']))
    return items, excl


def draw(rng, cands, n, taken):
    c = sorted((x for x in cands if x['id'] not in taken), key=lambda x: x['id'])
    rng.shuffle(c)
    got = c[:n]
    taken.update(x['id'] for x in got)
    return got


def sample():
    items, excl = pool()
    rng = random.Random(SEED)
    taken = set()
    strata = {}
    miss = [x for x in items if x['population'] == 'real' and x['deployed_missed']]
    strata['S-miss'] = draw(rng, miss, len(miss), taken)
    strata['S-pair'] = draw(rng, [x for x in items if x['how'] == 'edited'], PER_STRATUM, taken)
    strata['S-del'] = draw(rng, [x for x in items if x['how'] in ('deleted', 'relocated')], PER_STRATUM, taken)
    strata['S-dis'] = draw(rng, [x for x in items if x['disagree'] >= 2], PER_STRATUM, taken)
    strata['S-aligned'] = draw(rng, [x for x in items if x['how'] == 'aligned'], PER_STRATUM, taken)
    strata['S-excl'] = draw(rng, excl, PER_STRATUM, taken)
    sizes = {k: len(v) for k, v in strata.items()}
    eligible = dict(miss=len(miss), pair=sum(x['how'] == 'edited' for x in items),
                    deleted=sum(x['how'] in ('deleted', 'relocated') for x in items), disagree=sum(x['disagree'] >= 2 for x in items),
                    aligned=sum(x['how'] == 'aligned' for x in items), excluded=len(excl),
                    excluded_by_reason=dict(Counter(x['exclusion_reason'] for x in excl)))
    # Build the blinded inputs (old excerpt, paired new file) by reading the pinned histories.
    blinded = build_inputs([x for k in STRATA for x in strata[k]])
    key = {x['id']: dict(stratum=k, **{f: x.get(f) for f in ('population', 'repo', 'pair', 'cls', 'how', 'truth_at', 'span', 'path',
                                                              'start', 'renamed_path', 'deployed_missed', 'disagree', 'disagree_avail',
                                                              'exclusion_reason')})
           for k in STRATA for x in strata[k]}
    for ident, b in blinded.items():
        key[ident].update(new_path=b['new_path'], new_lines=b['new_lines'], window=b['window'], new_exists=b['new_exists'])
    (OUT / 'private').mkdir(parents=True, exist_ok=True)
    (OUT / 'private/key.json').write_text(json.dumps(dict(seed=SEED, key=key), indent=0), encoding='utf-8')
    order = [x['id'] for k in STRATA for x in strata[k]]
    (OUT / 'sample.json').write_text(json.dumps(dict(seed=SEED, per_stratum=PER_STRATUM, sizes=sizes, eligible=eligible,
                                                     items=[dict(id=i, old=blinded[i]['old'], new=blinded[i]['new']) for i in order]),
                                                indent=0), encoding='utf-8')
    print('sample', sizes, eligible)


def build_inputs(items):
    import wpb2_chains as wc
    from regenerate_history_selection import harness
    original, _ = harness()
    private = ROOT / 'evidence/v11-wph/private'
    spaths = {r['anonymous_id']: str(private / 'tmp' / str(r['repository_id'])) for r in json.loads((private / 'selected.json').read_text())}
    by_repo = defaultdict(list)
    for x in items:
        by_repo[x['repo']].append(x)
    out = {}
    for name, xs in sorted(by_repo.items()):
        history = None
        if name in spaths:
            repo = original.Repo(spaths[name])
        else:
            history = wc.one_history(name)
            repo = original.Repo(str(history.path))
        try:
            for x in xs:
                old_tree = repo.tree(x['old_commit'])
                old = repo.blob(old_tree[x['path']])
                if x.get('old_file_sha256'):
                    assert sha_bytes(old.encode()) == x['old_file_sha256'], x['id']
                ol = old.splitlines()
                s, e = x['start'], x['start'] + x['span'] - 1
                lo, hi = max(1, s - CONTEXT_OLD), min(len(ol), e + CONTEXT_OLD)
                old_ex = '\n'.join(f"{'>>' if s <= i <= e else '  '} {i:5d} | {ol[i - 1]}" for i in range(lo, hi + 1))
                new_tree = repo.tree(x['new_commit'])
                new_path = x['renamed_path'] or x['path']
                if new_path in new_tree:
                    nl = repo.blob(new_tree[new_path]).splitlines()
                    if len(nl) <= MAX_NEW:
                        a, b = 1, len(nl)
                    else:
                        a = max(1, min(s - MAX_NEW // 2, len(nl) - MAX_NEW + 1))
                        b = a + MAX_NEW - 1
                    new_ex = '\n'.join(f'{i:5d} | {nl[i - 1]}' for i in range(a, b + 1))
                    head = f'NEW FILE {new_path} (lines {a}-{b} of {len(nl)}):'
                    out[x['id']] = dict(new_path=new_path, new_lines=len(nl), window=[a, b], new_exists=True,
                                        old=f'OLD FILE {x["path"]} (lines {lo}-{hi}):\n{old_ex}', new=f'{head}\n{new_ex}')
                else:
                    out[x['id']] = dict(new_path=new_path, new_lines=0, window=None, new_exists=False,
                                        old=f'OLD FILE {x["path"]} (lines {lo}-{hi}):\n{old_ex}',
                                        new=f'NEW FILE {new_path}: the file does not exist in the new version.')
        finally:
            repo.cat.stdin.close()
            repo.cat.wait(timeout=15)
            if history is not None:
                history.close()
    return out


# ---------------- freeze and calls ----------------
def freeze():
    f = OUT / 'protocol-freeze.json'
    assert not f.exists() and not any(OUT.glob('*/responses.jsonl'))
    f.write_text(json.dumps(dict(recorded_utc=utc(), protocol_sha256=sha(PROTOCOL), code_sha256=code_hashes(),
                                 sample_sha256=sha(OUT / 'sample.json'), key_sha256=sha(OUT / 'private/key.json'),
                                 system_prompt_sha256=sha_bytes(SYSTEM.encode()), system_prompt=SYSTEM,
                                 statement='No WP K5 model call was made before this record.'), indent=1), encoding='utf-8')
    print('frozen')


def verify_freeze():
    fz = json.loads((OUT / 'protocol-freeze.json').read_text(encoding='utf-8'))
    assert fz['protocol_sha256'] == sha(PROTOCOL) and fz['sample_sha256'] == sha(OUT / 'sample.json')
    assert fz['system_prompt_sha256'] == sha_bytes(SYSTEM.encode())
    return fz


def messages(it):
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': f"{it['old']}\n\n{it['new']}"}]


def run(model, workers):
    verify_freeze()
    import run_wpj as R
    if model == 'nemotron':
        import run_wpj_nim as N
        N.KEY, N.MODEL = 'nemotron', N.NIM_MODELS['nemotron']
        N.use_nim()

    def call(it):
        msgs = messages(it)
        attempts, errors, waits = 0, [], 0
        while attempts < 8:
            attempts += 1
            R.RATE_GATE.wait()
            t0 = time.time()
            try:
                d = R.post(msgs)
                msg = d['choices'][0]['message']
                return dict(id=it['id'], status='answered', content=msg.get('content'), model=d.get('model'),
                            finish=d['choices'][0].get('finish_reason'), elapsed_s=round(time.time() - t0, 2), attempts=attempts,
                            rate_waits=waits, prompt_sha256=sha_bytes(json.dumps(msgs).encode()))
            except urllib.error.HTTPError as e:
                body = e.read()[:300].decode('utf-8', 'replace')
                if e.code == 429 and waits < R.RATE_WAITS:
                    waits += 1
                    attempts -= 1
                    R.pause_all(R.rate_pause(e.headers))
                    continue
                errors.append(dict(code=e.code, body=body))
                if e.code not in (408, 429, 500, 502, 503, 504, 520, 522, 524):
                    return dict(id=it['id'], status='http_error', content=None, attempts=attempts, errors=errors)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, KeyError, IndexError, ValueError) as e:
                errors.append(dict(code=None, body=repr(e)[:300]))
            time.sleep(min(300, 15 * 2 ** (attempts - 1)))
        return dict(id=it['id'], status='transport_failed', content=None, attempts=attempts, errors=errors)

    folder = OUT / model
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / 'responses.jsonl'
    done = set()
    if out.exists():
        for line in out.read_text(encoding='utf-8').splitlines():
            r = json.loads(line)
            if r['status'] == 'answered':
                done.add(r['id'])
    items = json.loads((OUT / 'sample.json').read_text(encoding='utf-8'))['items']
    jobs = [it for it in items if it['id'] not in done]
    lock = threading.Lock()
    print(model, 'jobs', len(jobs), flush=True)
    with ThreadPoolExecutor(workers) as pool, out.open('a', encoding='utf-8') as f:
        for n, r in enumerate(pool.map(call, jobs), 1):
            with lock:
                f.write(json.dumps(r) + '\n')
                f.flush()
            if n % 25 == 0:
                print(model, n, time.strftime('%H:%M:%S'), flush=True)
    print(model, 'complete', flush=True)


# ---------------- analysis ----------------
def verdict(content):
    if not content:
        return None
    text = re.sub(r'<think>.*?</think>', '', content, flags=re.S)
    for s in reversed(re.findall(r'\{[^{}]*\}', text)):
        try:
            v = json.loads(s)
        except ValueError:
            continue
        st = v.get('status')
        if st in ('unchanged', 'edited', 'deleted'):
            def num(x):
                return int(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None
            return dict(status=st, start=num(v.get('start')), end=num(v.get('end')))
    if not LENIENT:
        return None
    # Amendment 1 (post hoc): read the three fields when the object is invalid JSON only because the free-text
    # reason is unquoted (Nemotron). The reason is never scored.
    m = re.search(r'"status"\s*:\s*"(unchanged|edited|deleted)"', text)
    if not m:
        return None
    def field(name):
        f = re.search(rf'"{name}"\s*:\s*(\d+|null)', text)
        return int(f.group(1)) if f and f.group(1) != 'null' else None
    return dict(status=m.group(1), start=field('start'), end=field('end'), lenient=True)


LENIENT = True


def wilson(k, n, z=1.959964):
    if not n:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


def kappa(pairs, labels=('unchanged', 'edited', 'deleted')):
    pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
    n = len(pairs)
    if not n:
        return None
    po = sum(a == b for a, b in pairs) / n
    pe = sum((sum(a == l for a, _ in pairs) / n) * (sum(b == l for _, b in pairs) / n) for l in labels)
    return None if pe == 1 else round((po - pe) / (1 - pe), 3)


def pct(k, n):
    return dict(k=k, n=n, pct=round(100 * k / n, 1) if n else None, ci=wilson(k, n))


def responses(model):
    last = {}
    p = OUT / model / 'responses.jsonl'
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            r = json.loads(line)
            last[r['id']] = r
    return last


def analyze():
    key = json.loads((OUT / 'private/key.json').read_text(encoding='utf-8'))['key']
    items = json.loads((OUT / 'sample.json').read_text(encoding='utf-8'))['items']
    models = [m for m in ('beam', 'nemotron') if (OUT / m / 'responses.jsonl').exists()]
    pred = {}
    meta = {}
    for m in models:
        last = responses(m)
        c = Counter()
        for it in items:
            r = last.get(it['id'])
            if r is None or r['status'] != 'answered':
                c['missing'] += 1
                v = None
            else:
                v = verdict(r['content'])
                c['unparsed'] += v is None
                c['lenient_only'] += bool(v and v.get('lenient'))
            pred[(m, it['id'])] = v
        meta[m] = dict(c, model_ids=dict(Counter(r.get('model') for r in last.values())))

    def ref_loc(k):
        if k['truth_at'] is None:
            return None
        tp, ts = k['truth_at']
        return (tp, ts, ts + k['span'] - 1)

    def loc_events(k, v):
        """Location agreement inside the paired new file; reference locations in another file count as disagreement."""
        rl = ref_loc(k)
        if v is None or rl is None or v['start'] is None:
            return None
        same_file = rl[0] == k['new_path']
        s, e = v['start'], v['end'] if v['end'] is not None else v['start']
        return dict(exact=same_file and s == rl[1], near=same_file and abs(s - rl[1]) <= 2,
                    overlap=same_file and s <= rl[2] and e >= rl[1])

    res = {}
    for stratum in STRATA + ('all-decided',):
        ids = [it['id'] for it in items if (key[it['id']]['stratum'] == stratum if stratum != 'all-decided'
                                            else key[it['id']]['stratum'] != 'S-excl')]
        decided = stratum != 'S-excl'
        r = dict(n=len(ids), models={})
        for m in models:
            vs = {i: pred[(m, i)] for i in ids}
            mr = dict(parsed=sum(v is not None for v in vs.values()),
                      status_dist=dict(Counter(v['status'] for v in vs.values() if v)))
            if decided:
                ok = [i for i in ids if vs[i] is not None]
                agree = sum(vs[i]['status'] == ref_status(key[i]['cls']) for i in ok)
                mr['status_agree'] = pct(agree, len(ok))
                mr['status_kappa'] = kappa([(vs[i]['status'], ref_status(key[i]['cls'])) for i in ok])
                le = [loc_events(key[i], vs[i]) for i in ok]
                le = [x for x in le if x is not None]
                for f in ('exact', 'near', 'overlap'):
                    mr['loc_' + f] = pct(sum(x[f] for x in le), len(le))
            r['models'][m] = mr
        if len(models) == 2:
            both = [i for i in ids if pred[(models[0], i)] and pred[(models[1], i)]]
            r['model_model_status_agree'] = pct(sum(pred[(models[0], i)]['status'] == pred[(models[1], i)]['status'] for i in both), len(both))
            r['model_model_kappa'] = kappa([(pred[(models[0], i)]['status'], pred[(models[1], i)]['status']) for i in both])
            if decided:
                sus = [i for i in both if pred[(models[0], i)]['status'] != ref_status(key[i]['cls'])
                       and pred[(models[1], i)]['status'] != ref_status(key[i]['cls'])]
                sus_consensus = [i for i in sus if pred[(models[0], i)]['status'] == pred[(models[1], i)]['status']]
                r['suspect_status'] = pct(len(sus), len(both))
                r['suspect_status_consensus'] = pct(len(sus_consensus), len(both))
                r['suspect_ids'] = sus
                # Post hoc view: reference locations in another file cannot be seen in the blinded input.
                within = [i for i in both if not (key[i]['truth_at'] and key[i]['truth_at'][0] != key[i]['new_path'])]
                sus_w = [i for i in sus if i in within]
                r['within_file'] = dict(n=len(within), suspect=pct(len(sus_w), len(within)),
                                        suspect_consensus_as=dict(Counter(pred[(models[0], i)]['status'] for i in sus_w
                                                                          if pred[(models[0], i)]['status'] == pred[(models[1], i)]['status'])),
                                        status_agree={m: pct(sum(pred[(m, i)]['status'] == ref_status(key[i]['cls']) for i in within), len(within))
                                                      for m in models})
                r['suspect_consensus_as'] = dict(Counter(pred[(models[0], i)]['status'] for i in sus_consensus))
                if stratum == 'S-miss':
                    # A miss is a target the reference calls changed or deleted. If both models call it unchanged,
                    # removing the reference error would lower the missed count (the direction the bound predicts).
                    r['miss_suspects_lowering'] = sum(pred[(models[0], i)]['status'] == 'unchanged' == pred[(models[1], i)]['status']
                                                      for i in sus)
                    r['miss_suspects_other'] = len(sus) - r['miss_suspects_lowering']
            else:
                r['excluded_consensus'] = dict(Counter(pred[(models[0], i)]['status'] for i in both
                                                       if pred[(models[0], i)]['status'] == pred[(models[1], i)]['status']))
                r['excluded_by_reason'] = dict(Counter(key[i]['exclusion_reason'] for i in ids))
        r['cross_file_reference'] = sum(1 for i in ids if key[i]['truth_at'] and key[i]['truth_at'][0] != key[i]['new_path'])
        r['new_file_missing'] = sum(1 for i in ids if not key[i]['new_exists'])
        res[stratum] = r
    summary = dict(recorded_utc=utc(), code_sha256=code_hashes(), freeze=json.loads((OUT / 'protocol-freeze.json').read_text(encoding='utf-8')),
                   sample_sha256=sha(OUT / 'sample.json'), responses_sha256={m: sha(OUT / m / 'responses.jsonl') for m in models},
                   adjudicators='hosted language models (not human annotators)', models=meta, strata=res,
                   assumption='Suspect rates bound reference error only if a two-model consensus against the reference is right; that is an assumption, not a measurement.')
    name = 'summary-' + time.strftime('%Y%m%dT%H%M%S', time.gmtime()) + '.json'
    (OUT / name).write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(name)
    for s, r in res.items():
        print(s, r['n'], {m: (r['models'][m].get('status_agree', {}).get('pct'), r['models'][m].get('loc_near', {}).get('pct'))
                          for m in models}, r.get('suspect_status', {}).get('k'), r.get('miss_suspects_lowering'))


# ---------------- human packet ----------------
def packet(n_per=20):
    key = json.loads((OUT / 'private/key.json').read_text(encoding='utf-8'))['key']
    items = json.loads((OUT / 'sample.json').read_text(encoding='utf-8'))['items']
    rng = random.Random(SEED + 1)
    chosen = []
    for s in STRATA:
        ids = sorted(it['id'] for it in items if key[it['id']]['stratum'] == s)
        rng.shuffle(ids)
        chosen += ids[:n_per]
    rng.shuffle(chosen)
    by_id = {it['id']: it for it in items}
    folder = OUT / 'human-packet'
    folder.mkdir(parents=True, exist_ok=True)
    keyout, minutes = {}, []
    for n, i in enumerate(chosen, 1):
        it = by_id[i]
        code = f'H{n:03d}'
        lines = it['old'].count('\n') + it['new'].count('\n') + 2
        est = round(1.5 + lines / 300, 1)
        minutes.append(est)
        (folder / f'{code}.md').write_text(
            f'# Item {code}\n\nFind the code that the lines marked `>>` became in the new file. Answer in the sheet: '
            f'status (unchanged / edited / deleted), start and end line in the NEW file (blank if deleted).\n\n'
            f'```text\n{it["old"]}\n```\n\n```text\n{it["new"]}\n```\n', encoding='utf-8')
        keyout[code] = dict(id=i, stratum=key[i]['stratum'], estimated_minutes=est)
    (folder / 'answer-sheet.csv').write_text('item,status,start,end,notes\n' + ''.join(f'H{n:03d},,,,\n' for n in range(1, len(chosen) + 1)),
                                             encoding='utf-8')
    (folder / 'README.md').write_text(
        '# Blinded reference audit packet (not for distribution)\n\n'
        f'{len(chosen)} items. Each file shows an old excerpt with the reviewed lines marked `>>` and the paired new file. '
        'Record status (unchanged, edited, deleted) and the new start and end lines in `answer-sheet.csv`. Work alone; '
        'do not look at any other material about the item. Two annotators should fill separate copies of the sheet.\n\n'
        f'Estimated time: about {round(sum(minutes))} minutes per annotator (1.5 minutes per item plus reading time).\n', encoding='utf-8')
    (OUT / 'human-packet-key.json').write_text(json.dumps(dict(seed=SEED + 1, items=keyout, estimated_minutes_total=round(sum(minutes), 1)),
                                                          indent=1), encoding='utf-8')
    print('packet', len(chosen), 'items, about', round(sum(minutes)), 'minutes')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=('sample', 'freeze', 'run', 'analyze', 'packet'))
    ap.add_argument('--model', default='beam', choices=('beam', 'nemotron'))
    ap.add_argument('--workers', type=int, default=4)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    {'sample': sample, 'freeze': freeze, 'run': lambda: run(a.model, a.workers), 'analyze': analyze, 'packet': packet}[a.stage]()


if __name__ == '__main__':
    main()
