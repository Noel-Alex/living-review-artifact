"""Score filled K5 human answer sheets against the reference and the two model adjudicators.

python -I -B tools/v11/score_wpk5_human.py SHEET.csv [SHEET2.csv]  -> evidence/v12-wpk5/human-score-<utc>.json
Sheets are copies of evidence/v12-wpk5/human-packet/answer-sheet.csv filled by annotators who worked alone.
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wpk5_audit as W  # noqa: E402

OUT = W.OUT


def read_sheet(p):
    with open(p, encoding='utf-8', newline='') as f:
        rows = list(csv.DictReader(f))
    got = {}
    for r in rows:
        st = (r.get('status') or '').strip().lower()
        if st in ('unchanged', 'edited', 'deleted'):
            def num(x):
                x = (x or '').strip()
                return int(x) if x.isdigit() else None
            got[r['item']] = dict(status=st, start=num(r.get('start')), end=num(r.get('end')))
    return got


def main():
    sheets = [read_sheet(p) for p in sys.argv[1:]]
    if not sheets:
        raise SystemExit('give one or two filled answer sheets')
    hk = json.loads((OUT / 'human-packet-key.json').read_text(encoding='utf-8'))['items']
    key = json.loads((OUT / 'private/key.json').read_text(encoding='utf-8'))['key']
    preds = {m: {i: W.verdict(r['content']) if r['status'] == 'answered' else None for i, r in W.responses(m).items()}
             for m in ('beam', 'nemotron')}
    res = {}
    for n, sh in enumerate(sheets, 1):
        pairs_ref, pairs_m = [], {m: [] for m in preds}
        for code, a in sh.items():
            ident = hk[code]['id']
            k = key[ident]
            if k['stratum'] != 'S-excl':
                pairs_ref.append((a['status'], W.ref_status(k['cls'])))
            for m in preds:
                v = preds[m].get(ident)
                if v:
                    pairs_m[m].append((a['status'], v['status']))
        res[f'annotator{n}'] = dict(answered=len(sh),
                                    vs_reference=dict(n=len(pairs_ref), agree=sum(a == b for a, b in pairs_ref), kappa=W.kappa(pairs_ref)),
                                    vs_models={m: dict(n=len(p), agree=sum(a == b for a, b in p), kappa=W.kappa(p)) for m, p in pairs_m.items()})
    if len(sheets) == 2:
        common = sorted(set(sheets[0]) & set(sheets[1]))
        pairs = [(sheets[0][c]['status'], sheets[1][c]['status']) for c in common]
        res['inter_annotator'] = dict(n=len(pairs), agree=sum(a == b for a, b in pairs), kappa=W.kappa(pairs))
    name = 'human-score-' + time.strftime('%Y%m%dT%H%M%S', time.gmtime()) + '.json'
    (OUT / name).write_text(json.dumps(dict(recorded_utc=W.utc(), sheets=sys.argv[1:], results=res), indent=1), encoding='utf-8')
    print(json.dumps(res, indent=1))


if __name__ == '__main__':
    main()
