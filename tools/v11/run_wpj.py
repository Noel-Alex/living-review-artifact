"""WP J runner (protocol: review/V11-PROTOCOL-J.md): a language-model locator inside the safety layer.

python -I -B tools/v11/run_wpj.py export|dev|freeze|run|layers [--population P] [--workers N] [--pass N]

Uses the CodeMapper interpreter (tools/v11-ext/codemapper/venv, Python 3.12.14), as WP I.
Model calls go through the local Hermes proxy (OpenAI-compatible, http://127.0.0.1:8645/v1).
Only public code is sent: the human-annotated benchmark, public open-source histories and public
student-authored repositories. No private portal code is exported or sent.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pickle
import random
import re
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpi_core import ROOT, read, sha, digest  # noqa: E402

OUT = ROOT / 'evidence/v11-wpj'
PRIVATE = OUT / 'private'
PROTOCOL = ROOT / 'review/V11-PROTOCOL-J.md'
CODE = ('run_wpj.py', 'wpj_core.py', 'analyze_wpj.py', 'test_wpj.py')
FROZEN = ('wpi_core.py', 'wpb_variants.py', 'wpa_core.py', 'analyze_wpc.py', 'analyze_wpb.py')
ENDPOINT = 'http://127.0.0.1:8645/v1/chat/completions'
# Amendment 2: the primary model is the one the deployed Vcap portal uses through Hermes (Beam 1.0, Nous Portal free tier).
# Step-3.7-Flash results (the frozen model of the original protocol) are kept unchanged under calls/ and layers/.
MODELS = {'beam': 'reflection/beam-1.0-501b-a23b:free', 'step': 'stepfun/step-3.7-flash:free'}
PRIMARY = 'beam'
MODEL = MODELS[PRIMARY]
SETTINGS = dict(temperature=0, seed=20261103, max_tokens=16000, reasoning={'effort': 'low'})
POPULATIONS = ('human-AB', 'real-oss-targeted', 'students-targeted')
DEV_N, DEV_SEED = 20, 20261103

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpj_core import build_prompt, parse_answer, PROMPT_VERSION  # noqa: E402


def now():
    return datetime.now(timezone.utc).isoformat()


def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')


def code_hashes():
    here = Path(__file__).resolve().parent
    return {f'tools/v11/{n}': sha(here / n) for n in CODE + FROZEN if (here / n).exists()}


def write(name, data, extra=()):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    freeze = OUT / 'protocol-freeze.json'
    prov = dict(recorded_utc=now(), python=sys.version, executable=sys.executable, code_sha256=code_hashes(),
                protocol_sha256=sha(PROTOCOL) if PROTOCOL.exists() else None,
                freeze_record_sha256=sha(freeze) if freeze.exists() else None,
                inputs={str(Path(p).relative_to(ROOT)).replace('\\', '/'): sha(p) for p in extra})
    with path.open('x', encoding='utf-8') as stream:
        json.dump(dict(provenance=prov, data=data), stream, separators=(',', ':'))
    return path


def verify_freeze():
    f = read(OUT / 'protocol-freeze.json')['data']
    amendments = sorted(OUT.glob('protocol-amendment-*.json'))
    current = read(amendments[-1])['data'] if amendments else f
    assert current['protocol_sha256'] == sha(PROTOCOL), 'WP J protocol drift'
    assert current['code_sha256'] == code_hashes(), 'WP J code drift'
    return f


# ---------------- inputs ----------------
def item(ident, population, row, t, old):
    """Compact, self-contained input for one observation (public code only)."""
    a = t['anchor']
    path = a['path']
    renamed = row.get('renamed_path')
    target = path if path in t['version'] else (renamed if renamed and renamed in t['version'] else None)
    if target is None and len(t['version']) == 1:
        target = next(iter(t['version']))  # external rows: the paired target file (C6 input scope)
    version = {p: t['version'][p] for p in {path, target} if p and p in t['version']}
    old_files = {p: old[p] for p in {path, target} if p and p in old}
    return dict(id=ident, population=population, anchor=a, old_lines=t['old_lines'], version=version,
                old_files=old_files, target=target)


def export():
    import run_wpc_c6
    from run_wpi import external_scope
    from regenerate_history_selection import harness
    from collections import defaultdict
    sys.path.insert(0, str(ROOT / 'tools/v11'))
    from run_wpi import small_old
    tr = {r['id']: r for p in sorted((ROOT / 'evidence/v11-wpi/transfer').glob('rows-*.json')) for r in read(p)['data']}
    items, dev_pool = [], []
    for r in tr.values():
        if r['suite'] == 'external' and r['dataset'] in ('annotation_a', 'annotation_b'):
            t, old = external_scope(r)
            items.append(item(r['id'], 'human-AB', r, t, old))
    print('human-AB', len(items), flush=True)
    for r, t, old in run_wpc_c6.reused_inputs():
        if r['suite'] != 'real' or r['group'] != 'oss':
            continue
        if r['sample'] == 'targeted':
            items.append(item(r['id'], 'real-oss-targeted', r, t, old))
        else:
            dev_pool.append((r, t, old))
    print('real-oss-targeted', sum(i['population'] == 'real-oss-targeted' for i in items), flush=True)
    rng = random.Random(DEV_SEED)
    dev = [item(r['id'], 'dev', r, t, old) for r, t, old in rng.sample(dev_pool, DEV_N)]
    st = {r['id']: r for r in read(ROOT / 'evidence/v11-wpi/students2/rows.json')['data']}
    private = ROOT / 'evidence/v11-wph/private'
    paths = {r['anonymous_id']: str(private / 'tmp' / str(r['repository_id'])) for r in read(private / 'selected.json')}
    original, _ = harness()
    by_pair = defaultdict(list)
    for r in st.values():
        if r['sample'] == 'targeted':
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
            items.append(item(rec['id'], 'students-targeted', rec, t, small_old(t, old_files)))
    print('students-targeted', sum(i['population'] == 'students-targeted' for i in items), flush=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    for name, data in (('inputs.pkl', items), ('dev-inputs.pkl', dev)):
        path = PRIVATE / name
        with path.open('xb') as f:
            pickle.dump(data, f, protocol=4)
    counts = {p: sum(i['population'] == p for i in items) for p in POPULATIONS}
    write('export.json', dict(n=counts, dev=[d['id'] for d in dev], no_target={p: sum(i['population'] == p and i['target'] is None for i in items) for p in POPULATIONS},
                              inputs_sha256=sha(PRIVATE / 'inputs.pkl'), dev_sha256=sha(PRIVATE / 'dev-inputs.pkl'), utc=now()))
    print('export', counts, flush=True)


def load_items(name='inputs.pkl'):
    # Pickles are written only by export() in this tree and hash-checked against export.json before loading.
    path = PRIVATE / name
    exp = read(OUT / 'export.json')['data']
    assert sha(path) == exp['inputs_sha256' if name == 'inputs.pkl' else 'dev_sha256'], 'input drift'
    with path.open('rb') as f:
        return pickle.load(f)


# ---------------- model calls ----------------
RATE_GATE = threading.Event()
RATE_GATE.set()
RATE_LOCK = threading.Lock()
RATE_PAUSE_S, RATE_WAITS = 120, 2000


def rate_pause(headers):
    """Amendment 3: Retry-After, else the IETF RateLimit header's t= (seconds to reset), else 60 s; kept within 5 to 120 s."""
    for value in (headers.get('Retry-After'), *re.findall(r';t=(\d+)', headers.get('ratelimit') or '')):
        try:
            return max(5, min(RATE_PAUSE_S, int(float(value)) + 1))
        except (TypeError, ValueError):
            continue
    return 60


def pause_all(seconds):
    """Amendment 1: on HTTP 429 every worker pauses; one thread holds the pause, the others wait at the gate."""
    if RATE_LOCK.acquire(blocking=False):
        try:
            RATE_GATE.clear()
            print('rate limited; pausing', seconds, 's', now(), flush=True)
            time.sleep(seconds)
        finally:
            RATE_GATE.set()
            RATE_LOCK.release()
    else:
        RATE_GATE.wait()


def base(key):
    """Evidence folder for one model: Step keeps the original layout, other models get their own subfolder."""
    return OUT if key == 'step' else OUT / key


def post(messages):
    body = dict(model=MODEL, messages=messages, **SETTINGS)
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer local'})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


def call(it):
    """One model call per observation. Only transport failures are retried; answers never are."""
    if it['target'] is None:
        return dict(id=it['id'], status='no_target_file', content=None, attempts=0)
    messages, meta = build_prompt(it)
    if messages is None:
        return dict(id=it['id'], status='input_too_large', content=None, attempts=0, **meta)
    attempts, errors, waits = 0, [], 0
    while attempts < 8:
        attempts += 1
        RATE_GATE.wait()
        t0 = time.time()
        try:
            d = post(messages)
            msg = d['choices'][0]['message']
            return dict(id=it['id'], status='answered', content=msg.get('content'), finish=d['choices'][0].get('finish_reason'),
                        model=d.get('model'), usage=d.get('usage'), elapsed_s=round(time.time() - t0, 2), attempts=attempts,
                        transport_errors=errors, rate_waits=waits, prompt_sha256=meta['prompt_sha256'], prompt_chars=meta['prompt_chars'])
        except urllib.error.HTTPError as e:
            body = e.read()[:400].decode('utf-8', 'replace')
            if e.code == 429 and waits < RATE_WAITS:
                # Amendment 1: a rate limit is waited out (all workers pause) and is not a failed attempt.
                # Amendment 3: the pause follows the server's reset hint instead of a fixed 120 s.
                waits += 1
                attempts -= 1
                pause_all(rate_pause(e.headers))
                continue
            errors.append(dict(code=e.code, body=body))
            if e.code not in (408, 429, 500, 502, 503, 504, 520, 522, 524):
                return dict(id=it['id'], status='http_error', content=None, attempts=attempts, transport_errors=errors)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, KeyError, IndexError, ValueError) as e:
            errors.append(dict(code=None, body=repr(e)[:400]))
        time.sleep(min(300, 15 * 2 ** (attempts - 1)))
    return dict(id=it['id'], status='transport_failed', content=None, attempts=attempts, transport_errors=errors)


def run_calls(items, folder, workers):
    folder.mkdir(parents=True, exist_ok=True)
    done = set()
    for p in folder.glob('responses-*.jsonl'):
        for line in p.read_text(encoding='utf-8').splitlines():
            if line.strip():
                done.add(json.loads(line)['id'])
    todo = [it for it in items if it['id'] not in done]
    print(folder.name, 'done', len(done), 'todo', len(todo), flush=True)
    out = (folder / f'responses-{stamp()}.jsonl').open('x', encoding='utf-8')
    lock = threading.Lock()
    n = [0]

    def one(it):
        try:
            res = call(it)
        except Exception as e:  # recorded, never hidden
            res = dict(id=it['id'], status='runner_error', content=None, error=repr(e), traceback=traceback.format_exc()[-2000:])
        res['utc'] = now()
        with lock:
            out.write(json.dumps(res) + '\n')
            out.flush()
            n[0] += 1
            if n[0] % 25 == 0:
                print(folder.name, n[0], '/', len(todo), now(), flush=True)

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(one, todo))
    finally:
        out.close()


def responses(folder):
    got = {}
    for p in sorted(folder.glob('responses-*.jsonl')):
        for line in p.read_text(encoding='utf-8').splitlines():
            if line.strip():
                r = json.loads(line)
                got[r['id']] = r
    return got


def dev(workers):
    items = load_items('dev-inputs.pkl')
    run_calls(items, base(PRIMARY) / 'dev' / f'run-{stamp()}', workers)


def amend(note):
    n = len(list(OUT.glob('protocol-amendment-*.json'))) + 1
    write(f'protocol-amendment-{n}.json', dict(number=n, note=note, protocol_sha256=sha(PROTOCOL), code_sha256=code_hashes(), utc=now()))
    print('amendment', n, 'recorded')


def freeze():
    assert not (OUT / 'protocol-freeze.json').exists()
    exp = read(OUT / 'export.json')['data']
    write('protocol-freeze.json', dict(protocol_sha256=sha(PROTOCOL), code_sha256=code_hashes(), model=MODEL, settings=SETTINGS,
                                       prompt_version=PROMPT_VERSION, export=exp, utc=now()))
    print('frozen', sha(PROTOCOL))


def run(population, workers, npass):
    verify_freeze()
    assert population in POPULATIONS
    items = [it for it in load_items() if it['population'] == population]
    rel = '' if PRIMARY == 'step' else f'{PRIMARY}/'
    folder = base(PRIMARY) / 'calls' / f'{population}-pass{npass}'
    if not any(folder.glob('responses-*.jsonl')):
        write(f'{rel}calls/{population}-pass{npass}-start-{stamp()}.json', dict(n=len(items), workers=workers, model=MODEL, utc=now()))
    run_calls(items, folder, workers)
    got = responses(folder)
    missing = [it['id'] for it in items if it['id'] not in got]
    if not missing:
        write(f'{rel}calls/{population}-pass{npass}-completion-{stamp()}.json',
              dict(complete=True, n=len(items), status={s: sum(r['status'] == s for r in got.values()) for s in {r['status'] for r in got.values()}}, utc=now()))
    print(population, 'pass', npass, 'answered', len(got), 'missing', len(missing), flush=True)


def layers(population, npass, key=PRIMARY):
    from wpj_core import methods_of
    verify_freeze()
    items = [it for it in load_items() if it['population'] == population]
    got = responses(base(key) / 'calls' / f'{population}-pass{npass}')
    assert all(it['id'] in got for it in items), 'incomplete calls'
    rows = []
    for it in items:
        r = got[it['id']]
        rows.append(dict(id=it['id'], response_status=r['status'], parsed=parse_answer(r.get('content'), it) if r['status'] == 'answered' else None,
                         methods=methods_of(it, r)))
    write(('' if key == 'step' else f'{key}/') + f'layers/{population}-pass{npass}.json', rows)
    print(population, 'layers', len(rows), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=('export', 'dev', 'freeze', 'amend', 'run', 'layers'))
    ap.add_argument('--population')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--pass', dest='npass', type=int, default=1)
    ap.add_argument('--note')
    ap.add_argument('--model', choices=tuple(MODELS), default=PRIMARY, help='layers stage only: whose responses to score')
    a = ap.parse_args()
    os.environ['GIT_NO_LAZY_FETCH'] = '1'
    if a.stage == 'export':
        export()
    elif a.stage == 'dev':
        dev(a.workers)
    elif a.stage == 'freeze':
        freeze()
    elif a.stage == 'amend':
        amend(a.note)
    elif a.stage == 'run':
        run(a.population, a.workers, a.npass)
    else:
        layers(a.population, a.npass, a.model)


if __name__ == '__main__':
    main()
