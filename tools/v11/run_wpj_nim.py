"""WP J Amendment 5: the same frozen calls with Step 5 Preview through the NVIDIA API catalog (exploratory third model).

python -I -B tools/v11/run_wpj_nim.py dev|run|layers [--population P] [--workers N] [--pass N]

Only the transport differs from tools/v11/run_wpj.py: endpoint, model, API key and the name of the reasoning
setting (NVIDIA rejects the `reasoning` object; `reasoning_effort: low` is the same setting). Prompts, size caps,
retry rules, the rate gate (Amendments 1 and 3) and record formats are run_wpj's, imported unchanged.
The key is Noel's NVIDIA key: NVIDIA_API_KEY if set, else the one opencode stores. It is never written to evidence.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_wpj as R  # noqa: E402

# Amendment 5: step5. Amendment 7: faster NVIDIA-served models, chosen by a dev check.
NIM_MODELS = {'step5': 'stepfun-ai/step-5-preview', 'nemotron': 'nvidia/nemotron-3.5-super-vl-120b-a12b',
              'minimax': 'minimaxai/minimax-m3.1-flash'}
KEY = 'step5'
MODEL = NIM_MODELS[KEY]
ENDPOINT = 'https://integrate.api.nvidia.com/v1/chat/completions'
SETTINGS = {**{k: v for k, v in R.SETTINGS.items() if k != 'reasoning'}, 'reasoning_effort': R.SETTINGS['reasoning']['effort']}
OPENCODE_DB = Path(os.environ.get('USERPROFILE', '')) / '.local/share/opencode/opencode.db'


def api_key():
    if os.environ.get('NVIDIA_API_KEY'):
        return os.environ['NVIDIA_API_KEY']
    con = sqlite3.connect(f'file:{OPENCODE_DB.as_posix()}?mode=ro', uri=True)
    try:
        value = con.execute("select value from credential where integration_id='nvidia' and active=1").fetchone()[0]
    finally:
        con.close()
    try:
        d = json.loads(value)
        return d.get('key') or d.get('apiKey') or d.get('value')
    except ValueError:
        return value


AUTH = None


def post(messages):
    body = dict(model=MODEL, messages=messages, **SETTINGS)
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + AUTH})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.load(r)


def use_nim():
    global AUTH
    AUTH = api_key()
    assert AUTH and len(AUTH) > 20, 'no NVIDIA key'
    R.post = post  # run_wpj.call() looks post up at call time


def run(population, workers, npass):
    R.verify_freeze()
    assert population in R.POPULATIONS
    items = [it for it in R.load_items() if it['population'] == population]
    folder = R.base(KEY) / 'calls' / f'{population}-pass{npass}'
    if not any(folder.glob('responses-*.jsonl')):
        R.write(f'{KEY}/calls/{population}-pass{npass}-start-{R.stamp()}.json',
                dict(n=len(items), workers=workers, model=MODEL, endpoint=ENDPOINT, settings=SETTINGS, utc=R.now()))
    R.run_calls(items, folder, workers)
    got = R.responses(folder)
    missing = [it['id'] for it in items if it['id'] not in got]
    if not missing:
        R.write(f'{KEY}/calls/{population}-pass{npass}-completion-{R.stamp()}.json',
                dict(complete=True, n=len(items), status={s: sum(r['status'] == s for r in got.values()) for s in {r['status'] for r in got.values()}},
                     utc=R.now()))
    print(population, 'pass', npass, 'answered', len(got), 'missing', len(missing), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=('dev', 'run', 'layers'))
    ap.add_argument('--population')
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--pass', dest='npass', type=int, default=1)
    ap.add_argument('--model', choices=tuple(NIM_MODELS), default='step5')
    a = ap.parse_args()
    global KEY, MODEL
    KEY, MODEL = a.model, NIM_MODELS[a.model]
    os.environ['GIT_NO_LAZY_FETCH'] = '1'
    if a.stage == 'layers':
        R.layers(a.population, a.npass, KEY)
        return
    use_nim()
    if a.stage == 'dev':
        R.run_calls(R.load_items('dev-inputs.pkl'), R.base(KEY) / 'dev' / f'run-{R.stamp()}', a.workers)
    else:
        run(a.population, a.workers, a.npass)


if __name__ == '__main__':
    main()
