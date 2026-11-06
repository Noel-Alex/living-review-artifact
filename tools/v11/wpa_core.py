"""WPA metrics and exact, candidate-cached factorial matcher (no application imports)."""
import ast
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/v11-wpa'
SOURCE = ROOT / 'evidence/source-snapshot'
CORPUS = ROOT / 'evidence/pinned-corpus'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tools/vendor'))
METHODS = ('cascade', 'cascade_v1', 'quote_exact', 'diff_drift', 'line_number')
THETAS = [i / 100 for i in range(50, 96, 5)]
CELLS = [(o, s, h, t) for o, s, h, t in itertools.product(
    ('fuzzy_first', 'cross_first'), ('local', 'whole'), ('full', 'legacy'), THETAS)]
CLASSES = ('in place', 'shifted', 'moved file', 'edited', 'gone')
LABELS = ('exact', 'moved', 'changed', 'removed', 'execution_error')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def provenance(extra=()):
    paths = [SOURCE / n for n in ('bench_relocation.py', 'real_history.py', 'analysis_v3.py',
        'results-real-v1.json', 'results-oss-v1.json', 'results-v3.json')]
    paths += [CORPUS / 'vcap/app/modules/review_studio/carry.py',
              ROOT / 'review/V11-WPA-PROTOCOL.md']
    paths += list(Path(__file__).parent.glob('*.py')) + list(extra)
    return {'input_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): sha(p) for p in paths},
            'python': sys.version, 'executable': sys.executable, 'seed': 20261031}


def write(name, data, extra=()):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'provenance': provenance(extra), 'data': data}, indent=1), encoding='utf-8')


def pure_module(path, name, functions=None):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    body = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            if all(a.name not in ('bench_relocation',) for a in node.names):
                body.append(node)
        elif isinstance(node, ast.ImportFrom):
            if not (node.module or '').startswith(('app', 'sqlalchemy')):
                body.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            body.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if node.name != 'main' and (functions is None or node.name in functions):
                body.append(node)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(ast.Module(body=body, type_ignores=[]), str(path), 'exec'), module.__dict__)
    return module


def loaders():
    path = CORPUS / 'vcap/app/modules/review_studio/carry.py'
    matcher = pure_module(path, 'wpa_pinned_carry', {'_lines', '_runs', 'expected_start', 'relocate_code'})
    # bench methods refer to relocate_code at runtime; install the extracted pure callable.
    bench = pure_module(SOURCE / 'bench_relocation.py', 'wpa_bench')
    bench.relocate_code = matcher.relocate_code
    return matcher, bench


def check_gate(actual, archived, fields):
    assert len(actual) == len(archived), (len(actual), len(archived))
    for i, (a, b) in enumerate(zip(actual, archived)):
        for key in fields:
            assert a[key] == b[key], (i, key, a[key], b[key])


def outcome(truth, placement, failure=False):
    if failure:
        return 'execution_error'
    if truth is None:
        return 'correct' if placement is None else 'wrong_place'
    return 'lost' if placement is None else 'correct' if placement == truth else 'wrong_place'


def events(row, output):
    label, at = output['label'], output['placement']
    failure = label == 'execution_error'
    changed = row['cls'] in ('edited', 'gone')
    survives = row['truth_at'] is not None
    oc = outcome(row['truth_at'], at, failure)
    request = label in ('changed', 'removed') or failure
    adapter = output.get('adapter_recheck', label != 'exact')
    predicted = {'exact': 'preserved', 'moved': 'preserved', 'changed': 'edited',
                 'removed': 'gone', 'execution_error': 'execution_error'}[label]
    predicted_five = predicted
    if predicted == 'preserved' and at is not None and row.get('anchor_at') is not None:
        predicted_five = 'moved file' if at[0] != row['anchor_at'][0] else ('in place' if at[1] == row['anchor_at'][1] else 'shifted')
    actual = row['cls'] if changed else 'preserved'
    wrong = oc == 'wrong_place'
    return dict(accuracy=int(oc == 'correct'), placement_accuracy=int(survives and oc == 'correct'),
                classification_accuracy=int(predicted == actual), classification_five_accuracy=int(output.get('classification_five_available', True) and predicted_five == row['cls']),
                missed=int(changed and not request),
                adapter_missed=int(changed and not adapter), false_recheck=int(not changed and request),
                adapter_false_recheck=int(not changed and adapter), wrong=int(wrong),
                wrong_silent=int(wrong and not request), wrong_with_recheck=int(wrong and request),
                lost=int(oc == 'lost'), gone_correct=int(not survives and oc == 'correct'),
                gone_misreported=int(not survives and at is not None and not failure),
                failure=int(failure), returned=int(at is not None and not failure))


def rate(k, n):
    if not n:
        return {'k': int(k), 'n': int(n), 'rate': None, 'wilson95': None}
    p, z = k / n, 1.959963984540054
    d = 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/d
    return {'k': int(k), 'n': int(n), 'rate': p, 'wilson95': [max(0, c-h), min(1, c+h)]}


def summarize(rows, outputs):
    assert len(rows) == len(outputs)
    ev = [events(r, o) for r, o in zip(rows, outputs)]
    total = Counter({k: sum(e[k] for e in ev) for k in ev[0]}) if ev else Counter()
    n = len(rows)
    changed = sum(r['cls'] in ('edited', 'gone') for r in rows)
    survive = sum(r['truth_at'] is not None for r in rows)
    denoms = {'placement_accuracy': survive, 'missed': changed, 'adapter_missed': changed,
              'false_recheck': n-changed, 'adapter_false_recheck': n-changed,
              'lost': survive, 'gone_correct': n-survive, 'gone_misreported': n-survive}
    denoms['classification_five_accuracy'] = sum(o.get('classification_five_available',True) and r.get('anchor_at') is not None for r,o in zip(rows,outputs))
    result = {'n': n, 'execution_errors': total['failure'], 'event_counts': dict(total),
              'confusion': {label: {cls: sum(o['label'] == label and r['cls'] == cls
                  for r, o in zip(rows, outputs)) for cls in CLASSES} for label in LABELS}}
    result.update({k: rate(total[k], denoms.get(k, n)) for k in (
        'accuracy', 'placement_accuracy', 'classification_accuracy', 'classification_five_accuracy', 'missed', 'adapter_missed',
        'false_recheck', 'adapter_false_recheck', 'wrong', 'wrong_silent', 'wrong_with_recheck',
        'lost', 'gone_correct', 'gone_misreported')})
    result['lost_all_target'] = rate(total['lost'], n)
    result['wrong_given_returned'] = rate(total['wrong'], total['returned'])
    return result


@lru_cache(maxsize=8192)
def runs(text, wanted):
    lines = [line.strip() for line in text.splitlines()]
    found = []
    for s in range(len(lines)):
        if lines[s] != wanted[0]:
            continue
        got, e = [], s
        while e < len(lines) and len(got) < len(wanted):
            if lines[e]:
                got.append(lines[e])
            e += 1
        if tuple(got) == wanted:
            found.append((s, e))
    return tuple(found)


@lru_cache(maxsize=4096)
def fuzzy(text, wanted, span, starts):
    lines = text.splitlines()
    target = ' '.join(wanted)
    best, at = 0.0, None
    # A ratio upper bound avoids expensive matching only when it cannot beat best.
    # SequenceMatcher.quick_ratio is itself an upper bound, including autojunk=False.
    for s in starts:
        window = ' '.join(x.strip() for x in lines[s:s+span] if x.strip())
        if 2 * min(len(target), len(window)) / max(1, len(target)+len(window)) <= best:
            continue
        sm = SequenceMatcher(None, target, window, autojunk=False)
        if sm.quick_ratio() <= best:
            continue
        score = sm.ratio()
        if score > best:
            best, at = score, s
    return best, at


def features(trial, matcher):
    a, version = trial['anchor'], trial['version']
    path, origin = a['path'], a['line_start']-1
    wanted = tuple(x.strip() for x in a['quotation'].splitlines() if x.strip())
    span = a['line_end']-a['line_start']+1
    assert a['content_hash'] and wanted and span >= len(a['quotation'].splitlines())
    out = dict(hash=None, same=None, cross=None, local=[0, None], whole_full=[0, None], whole_legacy=[0, None],
               short_file=False, copies=[])
    if path in version and version[path][0] == a['content_hash']:
        out['hash'] = [path, origin+1]
        return out
    for candidate in ([path] if path in version else []) + sorted(p for p in version if p != path):
        found = runs(version[candidate][1], wanted)
        for start, end in found:
            out['copies'].append({'path': candidate, 'start': start+1, 'end': end,
                                  'distance': start-origin if candidate == path else None})
        if candidate == path and found:
            out['same'] = [path, min(found, key=lambda r: abs(r[0]-origin))[0]+1]
        elif found and out['cross'] is None:
            out['cross'] = [candidate, found[0][0]+1]
    if out['same'] is not None:
        return out
    if path in version:
        text = version[path][1]
        lines = text.splitlines()
        old = '\n'.join(trial['old_lines'])+'\n'
        expected = matcher.expected_start(old, lines, origin)
        radius = max(10, 2*span)
        ranges = {'local': range(max(0, expected-radius), max(0, min(expected+radius+1, len(lines)-span+1))),
                  'whole_full': range(max(0, len(lines)-span+1)),
                  'whole_legacy': range(max(1, len(lines)-span+1))}
        out['short_file'] = len(lines) < span
        for key, starts in ranges.items():
            score, at = fuzzy(text, wanted, span, starts)
            out[key] = [score, None if at is None else [path, at+1]]
    return out


def cell_output(f, order, scope, height, theta, origin=None):
    if f['hash'] is not None:
        return {'label': 'exact', 'placement': f['hash'], 'tier': 'hash'}
    if f['same'] is not None:
        return {'label': 'exact' if origin == f['same'] else 'moved', 'placement': f['same'], 'tier': 'same_exact'}
    if order == 'cross_first' and f['cross'] is not None:
        return {'label': 'moved', 'placement': f['cross'], 'tier': 'cross_exact'}
    key = 'local' if scope == 'local' else 'whole_'+height
    score, at = f[key]
    if at is not None and score >= theta:
        return {'label': 'changed', 'placement': at, 'tier': key, 'similarity': score}
    if f['cross'] is not None:
        return {'label': 'moved', 'placement': f['cross'], 'tier': 'cross_exact'}
    return {'label': 'removed', 'placement': None, 'tier': 'no_match'}


def direct_output(trial, matcher, theta=.85):
    matcher.FUZZY_CODE = theta
    o = matcher.relocate_code(trial['anchor'], trial['version'], '\n'.join(trial['old_lines'])+'\n')
    return {'label': o['match'], 'placement': None if o['match'] == 'removed' else [o['path'], o['line_start']]}


def encode_output(output, row):
    label = LABELS.index(output['label'])
    oc = ('correct', 'wrong_place', 'lost', 'execution_error').index(outcome(row['truth_at'], output['placement'], label == 4))
    return label*4+oc


def decode_output(code, row):
    label, oc = LABELS[code//4], ('correct', 'wrong_place', 'lost', 'execution_error')[code%4]
    placement = (row['truth_at'] if row['truth_at'] is not None else None) if oc == 'correct' else (
        None if oc in ('lost', 'execution_error') else ['__wrong__', -1])
    return {'label': label, 'placement': placement, 'classification_five_available': False}
