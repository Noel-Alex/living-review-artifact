"""WP J reporting (review/V11-PROTOCOL-J.md). Reuses the WP I scoring, denominators and cluster bootstrap unchanged.

python -I -B tools/v11/analyze_wpj.py
"""
from collections import Counter
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze_wpi as AI  # noqa: E402
from run_wpj import OUT, POPULATIONS, MODELS, PRIMARY, base, read, write, verify_freeze, load_items, responses  # noqa: E402
from wpj_core import parse_answer  # noqa: E402

LLM = ('llm-self', 'llm+quote', 'llm+IG', 'llm+AGi', 'llm+IG+AGi')
COMPARATORS = ('codemapper+quote', 'codemapper+IG+AGi', 't0.85-deployed', 't0.85-IG+AGi+VW')
CONTRASTS = [('llm+IG+AGi', 'llm-self'), ('llm+quote', 'llm-self'), ('llm+IG+AGi', 'llm+quote'),
             ('llm+IG+AGi', 'codemapper+IG+AGi'), ('llm-self', 'codemapper+quote'), ('llm+IG+AGi', 't0.85-deployed')]
WPI = AI.OUT
# Amendment 5: exploratory third model, the same frozen calls through the NVIDIA API catalog (tools/v11/run_wpj_nim.py).
ALL_MODELS = {**MODELS, 'step5': 'stepfun-ai/step-5-preview',
              'nemotron': 'nvidia/nemotron-3.5-super-vl-120b-a12b'}  # Amendment 7: second model on all populations


def base_rows():
    """WP I rows (with AGi layers) for the three populations, keyed by id."""
    out = {}
    rows, _ = AI.load('transfer', 'rows-*.json')
    agi = {r['id']: r['methods'] for p in sorted((WPI / 'agi').glob('transfer-*.json')) for r in read(p)['data']}
    for r in rows:
        if r['suite'] == 'external' and r['dataset'] in ('annotation_a', 'annotation_b'):
            pop = 'human-AB'
        elif r['suite'] == 'real' and r['group'] == 'oss' and r['sample'] == 'targeted':
            pop = 'real-oss-targeted'
        else:
            continue
        r['methods'].update(agi[r['id']])
        out[r['id']] = (pop, 'transfer', r)
    rows, _ = AI.load('students2', 'rows.json')
    agi = {r['id']: r['methods'] for p in sorted((WPI / 'agi').glob('students2-*.json')) for r in read(p)['data']}
    for r in rows:
        if r['sample'] != 'targeted':
            continue
        r['methods'].update(agi[r['id']])
        out[r['id']] = ('students-targeted', 'students', r)
    return out


def changed_judgement(rows, items, got):
    """The model's own `changed` flag against the reference class, on answered valid observations."""
    c = Counter()
    for r in rows:
        resp = got.get(r['id'])
        if not resp or resp['status'] != 'answered':
            continue
        p = parse_answer(resp.get('content'), items[r['id']])
        if not p['valid']:
            continue
        said = 'deleted' if p['status'] == 'deleted' else ('changed' if p['changed'] else 'unchanged')
        c[f"{said} / {r['cls']}"] += 1
    return dict(c)


def agreement(items_by_id, pop, key=PRIMARY):
    a, b = (responses(base(key) / 'calls' / f'{pop}-pass{k}') for k in (1, 2))
    if not b or set(a) != set(b) or set(a) != {i for i, it in items_by_id.items() if it['population'] == pop}:
        return None
    from wpj_core import methods_of
    same_place = same_all = 0
    for i in a:
        x, y = methods_of(items_by_id[i], a[i])['llm-self'], methods_of(items_by_id[i], b[i])['llm-self']
        same_place += x['placement'] == y['placement']
        same_all += (x['placement'], x.get('range'), x['label']) == (y['placement'], y.get('range'), y['label'])
    return dict(n=len(a), same_placement=same_place, same_placement_range_label=same_all)


def usage(got):
    st = Counter(r['status'] for r in got.values())
    ans = [r for r in got.values() if r['status'] == 'answered']
    pt = [r['usage']['prompt_tokens'] for r in ans if r.get('usage')]
    ct = [r['usage']['completion_tokens'] for r in ans if r.get('usage')]
    el = [r['elapsed_s'] for r in ans if r.get('elapsed_s') is not None]
    q = lambda v: dict(median=float(np.median(v)), p95=float(np.quantile(v, .95)), total=float(sum(v))) if v else None
    return dict(status=dict(st), finish=dict(Counter(r.get('finish') for r in ans)), models=dict(Counter(r.get('model') for r in ans)),
                prompt_tokens=q(pt), completion_tokens=q(ct), elapsed_s=q(el),
                transport_retries=sum(len(r.get('transport_errors', [])) for r in got.values()))


def analyze(key, items, inputs):
    """All populations whose pass-1 layers exist for one model (Amendment 2: beam primary, step secondary; Amendment 5: step5)."""
    base_by_id = base_rows()
    result = dict(model=ALL_MODELS[key], populations={})
    for pop in POPULATIONS:
        lay = base(key) / 'layers' / f'{pop}-pass1.json'
        if not lay.exists():
            result['populations'][pop] = dict(complete=False)
            continue
        inputs.append(lay)
        llm = {r['id']: r for r in read(lay)['data']}
        ids = [i for i, it in items.items() if it['population'] == pop]
        assert set(ids) == set(llm), pop
        rows = []
        origin = None
        for i in ids:
            p, origin, r = base_by_id[i]
            assert p == pop
            r['methods'].update(llm[i]['methods'])
            rows.append(r)
        got = responses(base(key) / 'calls' / f'{pop}-pass1')
        methods = {m: AI.metric(rows, m) for m in LLM + COMPARATORS}
        pairs = AI.paired(rows, [AI.cluster_key(r, origin) for r in rows], CONTRASTS)
        hyp = {}
        for name, measure in (('J1', 'missed'), ('J2', 'wrong_silent')):
            m = pairs['llm+IG+AGi minus llm-self']['metrics'][measure]
            hyp[name] = dict(measure=measure, difference=m['difference'], cluster95=m['cluster95'], exact_paired=m['exact_paired'],
                             supported=bool(m['cluster95'] is not None and m['cluster95'][1] < 0))
        m = pairs['llm+IG+AGi minus llm-self']['metrics']['false_recheck']
        hyp['J3'] = dict(measure='false_recheck', difference=m['difference'], cluster95=m['cluster95'], exact_paired=m['exact_paired'])
        result['populations'][pop] = dict(complete=True, n=len(rows), methods=methods, paired=pairs, hypotheses=hyp,
                                          changed_judgement=changed_judgement(rows, items, got), usage=usage(got),
                                          invalid=dict(Counter(llm[i]['methods']['llm-self'].get('error') for i in ids
                                                               if llm[i]['methods']['llm-self']['label'] == 'execution_error')))
        print(key, pop, len(rows), json.dumps({k: v['supported'] for k, v in hyp.items() if 'supported' in v}), flush=True)
    rep = agreement(items, 'human-AB', key)
    if rep is not None:
        result['repeat_human_AB'] = rep
    return result


def main():
    verify_freeze()
    items = {it['id']: it for it in load_items()}
    inputs = []
    result = analyze(PRIMARY, items, inputs)
    result['secondary'] = {k: analyze(k, items, inputs) for k in ALL_MODELS if k != PRIMARY}
    write(f'summary-{__import__("datetime").datetime.now().strftime("%Y%m%dT%H%M%S")}.json', result, inputs + [Path(__file__)])
    print('WP J summary written', flush=True)


if __name__ == '__main__':
    main()
