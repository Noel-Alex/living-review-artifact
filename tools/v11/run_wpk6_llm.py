"""WP K6 step 2 (decision D8): claim-relative versus diff question on applied and untouched suggestions.

python -I -B tools/v11/run_wpk6_llm.py sample            -> evidence/v12-wpk6/llm/sample.json
python -I -B tools/v11/run_wpk6_llm.py run --model beam|nemotron [--workers 4]
python -I -B tools/v11/run_wpk6_llm.py analyze           -> evidence/v12-wpk6/llm/summary.json
Prompts are D8 verbatim (review/briefs/WPK6-decisions.md). Transport, settings, the rate gate and retry rules are
WP J's (run_wpj.py, run_wpj_nim.py), imported unchanged. Public code only; keys are never written.
The signal never resolves or keeps an issue; it is evaluated as an optional annotation.
"""
from __future__ import annotations

import argparse
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
import run_wpj as R  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/v12-wpk6'
LLM = OUT / 'llm'
FENCE = re.compile(r'```suggestion[^\n]*\n.*?```', re.S)
SYS_A = ('You compare two versions of a piece of code. Answer ONLY with a JSON object {"changed_meaningfully": true or false}. '
         'Say true if the change could matter to a code reviewer; say false for no change or for formatting-only change.')
SYS_B = ('A reviewer left a COMMENT on the OLD code. Decide whether the reviewer\'s specific concern has been addressed in the '
         'NEW code. Answer ONLY with a JSON object {"addressed": true or false}.')
CONTEXT, PER_CELL, SEED = 5, 60, 20261031


def text(h):
    with open(OUT / 'blobs' / h[:2] / h, encoding='utf-8', newline='') as f:
        return f.read()


def region(t, s, e):
    lines = t.splitlines()
    return '\n'.join(lines[max(0, s - 1 - CONTEXT):min(len(lines), e + CONTEXT)])


def sample():
    units = json.loads((OUT / 'units.json').read_text(encoding='utf-8'))['units']
    cells = defaultdict(list)
    for u in units:
        if u['cls'] in ('applied', 'untouched') and len(u['comment'].split()) >= 4:
            cells[(u['language'], u['cls'])].append(u)
    rng = random.Random(SEED)
    items = []
    for key in sorted(cells):
        pool = sorted(cells[key], key=lambda u: (u['repo'], u['comment_id']))
        rng.shuffle(pool)
        for u in pool[:PER_CELL]:
            old = region(text(u['c0_sha256']), u['start'], u['end'])
            new = region(text(u['c1_sha256']), u['truth'][1], u['truth'][2])
            items.append(dict(id=f"{u['repo']}#{u['comment_id']}", language=u['language'], cls=u['cls'], repo=u['repo'], pr=u['pr'],
                              comment=u['comment'], old=old, new=new))
    LLM.mkdir(parents=True, exist_ok=True)
    (LLM / 'sample.json').write_text(json.dumps(dict(seed=SEED, per_cell=PER_CELL, eligible={f'{a}|{b}': len(v) for (a, b), v in cells.items()},
                                                     items=items), indent=0), encoding='utf-8')
    print('sample', len(items), Counter((i['language'], i['cls']) for i in items))


def messages(it, arm):
    if arm == 'A':
        return [{'role': 'system', 'content': SYS_A}, {'role': 'user', 'content': f"OLD:\n{it['old']}\n\nNEW:\n{it['new']}"}]
    return [{'role': 'system', 'content': SYS_B},
            {'role': 'user', 'content': f"COMMENT:\n{it['comment']}\n\nOLD:\n{it['old']}\n\nNEW:\n{it['new']}"}]


def call(job):
    it, arm = job
    msgs = messages(it, arm)
    attempts, errors, waits = 0, [], 0
    while attempts < 8:
        attempts += 1
        R.RATE_GATE.wait()
        t0 = time.time()
        try:
            d = R.post(msgs)
            msg = d['choices'][0]['message']
            return dict(id=it['id'], arm=arm, status='answered', content=msg.get('content'), model=d.get('model'),
                        finish=d['choices'][0].get('finish_reason'), elapsed_s=round(time.time() - t0, 2), attempts=attempts,
                        rate_waits=waits, prompt_sha256=hashlib.sha256(json.dumps(msgs).encode()).hexdigest())
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode('utf-8', 'replace')
            if e.code == 429 and waits < R.RATE_WAITS:
                waits += 1
                attempts -= 1
                R.pause_all(R.rate_pause(e.headers))
                continue
            errors.append(dict(code=e.code, body=body))
            if e.code not in (408, 429, 500, 502, 503, 504, 520, 522, 524):
                return dict(id=it['id'], arm=arm, status='http_error', content=None, attempts=attempts, errors=errors)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, KeyError, IndexError, ValueError) as e:
            errors.append(dict(code=None, body=repr(e)[:300]))
        time.sleep(min(300, 15 * 2 ** (attempts - 1)))
    return dict(id=it['id'], arm=arm, status='transport_failed', content=None, attempts=attempts, errors=errors)


def run(model, workers):
    if model == 'nemotron':
        import run_wpj_nim as N
        N.KEY, N.MODEL = 'nemotron', N.NIM_MODELS['nemotron']
        N.use_nim()
    folder = LLM / model
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / 'responses.jsonl'
    done = set()
    if out.exists():
        for line in out.read_text(encoding='utf-8').splitlines():
            r = json.loads(line)
            if r['status'] == 'answered':
                done.add((r['id'], r['arm']))
    items = json.loads((LLM / 'sample.json').read_text(encoding='utf-8'))['items']
    jobs = [(it, arm) for it in items for arm in ('A', 'B') if (it['id'], arm) not in done]
    lock = threading.Lock()
    print(model, 'jobs', len(jobs), flush=True)
    with ThreadPoolExecutor(workers) as pool, out.open('a', encoding='utf-8') as f:
        for n, r in enumerate(pool.map(call, jobs), 1):
            with lock:
                f.write(json.dumps(r) + '\n')
                f.flush()
            if n % 50 == 0:
                print(model, n, time.strftime('%H:%M:%S'), flush=True)
    print(model, 'complete', flush=True)


def verdict(content, key):
    if not content:
        return None
    m = re.findall(r'\{[^{}]*\}', content)
    for s in reversed(m):
        try:
            v = json.loads(s).get(key)
            if isinstance(v, bool):
                return v
        except ValueError:
            continue
    return None


def wilson(k, n, z=1.959964):
    if not n:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (c - h), 1), round(100 * (c + h), 1)]


def exact_mcnemar(b, c):
    n = b + c
    if not n:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def analyze():
    items = {i['id']: i for i in json.loads((LLM / 'sample.json').read_text(encoding='utf-8'))['items']}
    from analyze_wpk6 import wraps
    units = {f"{u['repo']}#{u['comment_id']}": u for u in json.loads((OUT / 'units.json').read_text(encoding='utf-8'))['units']}
    wrap_ids = sorted(i for i, it in items.items() if it['cls'] == 'applied' and wraps(units[i]))
    res = {}
    for folder in sorted(p for p in LLM.iterdir() if p.is_dir()):
        last = {}
        for line in (folder / 'responses.jsonl').read_text(encoding='utf-8').splitlines():
            r = json.loads(line)
            last[(r['id'], r['arm'])] = r
        arms = {}
        pred = {}
        for arm, key in (('A', 'changed_meaningfully'), ('B', 'addressed')):
            tp = fp = fn = tn = unparsed = missing = 0
            for ident, it in items.items():
                r = last.get((ident, arm))
                v = verdict(r['content'], key) if r and r['status'] == 'answered' else None
                if r is None or r['status'] != 'answered':
                    missing += 1
                elif v is None:
                    unparsed += 1
                pred[(ident, arm)] = v
                truth = it['cls'] == 'applied'
                if v is None:
                    continue
                tp += v and truth
                fp += v and not truth
                fn += (not v) and truth
                tn += (not v) and not truth
            prec = tp / (tp + fp) if tp + fp else None
            rec = tp / (tp + fn) if tp + fn else None
            arms[arm] = dict(tp=tp, fp=fp, fn=fn, tn=tn, unparsed=unparsed, missing=missing,
                             precision=round(100 * prec, 1) if prec is not None else None, precision_ci=wilson(tp, tp + fp),
                             recall=round(100 * rec, 1) if rec is not None else None, recall_ci=wilson(tp, tp + fn),
                             accuracy=round(100 * (tp + tn) / max(1, tp + fp + fn + tn), 1),
                             f1=round(200 * prec * rec / (prec + rec), 1) if prec and rec else None)
        b = c = 0
        for ident, it in items.items():
            a, bb = pred[(ident, 'A')], pred[(ident, 'B')]
            if a is None or bb is None:
                continue
            truth = it['cls'] == 'applied'
            b += (bb == truth) and (a != truth)
            c += (a == truth) and (bb != truth)
        # Applied suggestions that wrap the unchanged quoted lines: the mechanism every locator misses (post hoc).
        wrap = {a: sum(pred[(i, a)] is True for i in wrap_ids) for a in ('A', 'B')}
        res[folder.name] = dict(arms=arms, b_right_a_wrong=b, a_right_b_wrong=c, mcnemar_p=exact_mcnemar(b, c),
                                wrap_n=len(wrap_ids), wrap_flagged=wrap)
    summary = dict(recorded_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), n=len(items),
                   by_class=dict(Counter(i['cls'] for i in items.values())), models=res,
                   code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (LLM / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    print(json.dumps(summary, indent=1)[:3000])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=('sample', 'run', 'analyze'))
    ap.add_argument('--model', default='beam', choices=('beam', 'nemotron'))
    ap.add_argument('--workers', type=int, default=4)
    a = ap.parse_args()
    {'sample': sample, 'run': lambda: run(a.model, a.workers), 'analyze': analyze}[a.stage]()


if __name__ == '__main__':
    main()
