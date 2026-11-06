"""WP I (review/V11-PROTOCOL-I.md): AG2 guard, locator-agnostic safety layers and the identity rule.

Pure functions; frozen B1/C6 code is imported read only.
"""
from difflib import SequenceMatcher
from functools import lru_cache
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpa_core import ROOT, runs, sha, read, rate  # noqa: E402
from wpb_variants import prepare, profile  # noqa: E402

OUT = ROOT / 'evidence/v11-wpi'
PROTOCOL = ROOT / 'review/V11-PROTOCOL-I.md'
CODE = ('wpi_core.py', 'run_wpi.py', 'test_wpi.py', 'smoke_wpi.py', 'acquire_wpi_student_objects.py')
FROZEN = ('wpb_variants.py', 'wpa_core.py', 'wpb_stress.py', 'wpc_c6.py', 'wpc_cm_worker.py', 'wpc_adapters.py',
          'wpc_core.py', 'run_wpc_c6.py', 'run_wpb.py', 'wpb2_compound.py', 'wpb2_chains.py', 'run_wph2.py')
LOCATORS = ('codemapper', 'gumtree', 'tracker', 'hybrid')
LAYERS = ('quote', 'IG', 'AG', 'IG+AG', 'AG2', 'IG+AG2')
CASCADE2 = {'t0.85-AG2': (.85, False, False), 't0.85-IG+AG2': (.85, True, False),
            't0.85-IG+AG2+VW': (.85, True, True), 't0.55-IG+AG2+VW': (.55, True, True)}
ID_FLOOR = .5
ID_SENSITIVITY = (.3, .7)


def code_hashes():
    here = Path(__file__).resolve().parent
    return {f'tools/v11/{n}': sha(here / n) for n in CODE + FROZEN if (here / n).exists()}


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def stripped(text):
    return tuple(x.strip() for x in text.splitlines())


def wanted_of(quotation):
    return tuple(x.strip() for x in quotation.splitlines() if x.strip())


@lru_cache(maxsize=64)
def _blocks(old_text, new_text):
    sm = SequenceMatcher(None, stripped(old_text), stripped(new_text), autojunk=False)
    return tuple((i1, j1, i2 - i1) for tag, i1, i2, j1, _ in sm.get_opcodes() if tag == 'equal')


def old_image(old_text, new_text, j):
    """Old line whose equal-block image is new line j, else None."""
    for i1, j1, n in _blocks(old_text, new_text):
        if j1 <= j < j1 + n:
            return i1 + (j - j1)
    return None


def new_image(old_text, new_text, i):
    for i1, j1, n in _blocks(old_text, new_text):
        if i1 <= i < i1 + n:
            return j1 + (i - i1)
    return None


def starts(text, wanted):
    return {s for s, _ in runs(text, wanted)}


def ag2(anchor, wanted, old_files, version, candidate, start):
    """Protocol I1 decision for an exact window starting at zero-based `start` in `candidate`.

    Returns (accept, reason)."""
    path, origin = anchor['path'], anchor['line_start'] - 1
    new_c = version[candidate][1]
    old_p = old_files.get(path)
    if candidate == path:
        if old_p is None:
            return (len(runs(new_c, wanted)) < 2, 'no-previous-text')
        co, cn = len(runs(old_p, wanted)), len(runs(new_c, wanted))
        if co >= 2 and cn < co:
            return False, 'copy-count-decreased'
    elif candidate not in old_files:
        return True, None
    old_c = old_files[candidate]
    r = old_image(old_c, new_c, start)
    if r is not None and r in starts(old_c, wanted):
        return (True, None) if candidate == path and r == origin else (False, 'pre-existing-copy')
    intact = False
    if old_p is not None and path in version:
        s_o = new_image(old_p, version[path][1], origin)
        intact = s_o is not None and s_o in starts(version[path][1], wanted)
    return (False, 'duplicate-added') if intact else (True, None)


def ig_flags(anchor, window):
    before, after = profile(anchor['quotation']), profile(window)
    python = PurePosixPath(anchor['path']).suffix.lower() in ('.py', '.pyw')
    return before != after if python else before[1] != after[1]


def window_layers(t, old_files, output, layers=LAYERS):
    """C6 safety_family window rules with AG (C6) and AG2 (WP I)."""
    from wpa_core import runs as _runs
    from wpb_variants import MATCHER
    a, version, at = t['anchor'], t['version'], output['placement']
    if output['label'] == 'execution_error':
        return {k: dict(output) for k in layers}
    if at is None:
        return {k: dict(output, label='removed', recheck=True, reasons=[]) for k in layers}
    candidate, start = at[0], at[1] - 1
    if candidate not in version:
        return {k: dict(label='execution_error', placement=None, range=None, recheck=True,
                        error='returned file unavailable to safety layer') for k in layers}
    text = version[candidate][1]
    lines = text.splitlines()
    end = output['range'][2] if output.get('range') else min(start + a['line_end'] - a['line_start'] + 1, len(lines))
    if not 0 <= start < end <= len(lines):
        return {k: dict(label='execution_error', placement=None, range=None, recheck=True,
                        error='invalid returned safety window') for k in layers}
    window = '\n'.join(lines[start:end])
    wanted = wanted_of(a['quotation'])
    exact = wanted == tuple(x.strip() for x in window.splitlines() if x.strip())
    path, origin = a['path'], a['line_start'] - 1
    base = 'exact' if candidate == path and start == origin else 'moved'
    expected = None
    result = {}
    for layer in layers:
        label, recheck, reasons = (base if exact else 'changed'), not exact, []
        if exact and layer in ('AG', 'IG+AG'):
            if expected is None:
                expected = MATCHER.expected_start('\n'.join(t['old_lines']) + '\n', version[path][1].splitlines(),
                                                  origin) if path in version else origin
            if candidate != path or start != expected:
                old = old_files.get(candidate)
                old_count = len(_runs(old, wanted)) if old is not None and wanted else 0
                new_count = len(_runs(text, wanted)) if wanted else 0
                if old is not None and new_count <= old_count:
                    label, recheck = 'moved', True
                    reasons.append('pre-existing-copy')
        if exact and layer in ('AG2', 'IG+AG2'):
            accept, why = ag2(a, wanted, old_files, version, candidate, start) if wanted else (False, 'blank-quotation')
            if not accept:
                label, recheck = 'moved', True
                reasons.append(why)
        if exact and layer.startswith('IG') and ig_flags(a, window):
            label, recheck = 'changed', True
            reasons.append('layout')
        result[layer] = dict(label=label, placement=output['placement'], range=output.get('range'),
                             recheck=recheck, reasons=reasons)
    return result


def choose2(data, theta, ig, vw):
    """Cascade with AG2 (protocol I1): origin-image selection at tier 2, then the AG2 decision."""
    a, version, old_files = data['anchor'], data['version'], data['old_files']
    path, origin = a['path'], data['origin']
    reasons = []
    if data['hash']:
        return dict(label='exact', placement=[path, origin + 1], range=[path, origin + 1, a['line_end']],
                    tier='hash', recheck=False, reasons=[])
    exact = False
    if data['same']:
        found = data['same']
        pick = []
        if old_files.get(path) is not None:
            s_o = new_image(old_files[path], version[path][1], origin)
            pick = [r for r in found if r[0] == s_o]
        start, end = pick[0] if pick else min(found, key=lambda r: abs(r[0] - origin))
        candidate, label, tier, exact = path, 'exact' if start == origin else 'moved', 'same_exact', True
    else:
        score, start, h = data['variable'] if vw else data['fixed']
        if start is not None and score >= theta:
            candidate, end, label, tier = path, start + h, 'changed', 'variable' if vw else 'local'
        elif data['cross']:
            candidate, start, end = data['cross']
            label, tier, exact = 'moved', 'cross_exact', True
        else:
            return dict(label='removed', placement=None, range=None, tier='no_match', recheck=True, reasons=[])
    recheck = label == 'changed'
    if exact:
        accept, why = ag2(a, data['wanted'], old_files, version, candidate, start)
        if not accept:
            label, recheck = 'moved', True
            reasons.append(why)
        if ig and ig_flags(a, '\n'.join(version[candidate][1].splitlines()[start:end])):
            label, recheck = 'changed', True
            reasons.append('layout')
    return dict(label=label, placement=[candidate, start + 1], range=[candidate, start + 1, end],
                tier=tier, recheck=recheck, reasons=reasons)


def cascade2(t, old_files):
    data = prepare(t, old_files)
    return {name: choose2(data, *args) for name, args in CASCADE2.items()}


def identity_ratio(q0, window):
    a = ' '.join(wanted_of(q0))
    b = ' '.join(wanted_of(window))
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def identity_hop(q0, window, base_label, base_recheck, floor=ID_FLOOR):
    """Protocol I4 identity rule. Returns (keep, reviewed_text_request, ratio)."""
    if window is None:
        return False, True, None
    same = wanted_of(q0) == wanted_of(window)
    ratio = 1. if same else identity_ratio(q0, window)
    if base_label == 'changed' and ratio < floor:
        return False, True, ratio
    return True, bool(base_recheck or not same), ratio


def write(name, data, extra=()):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    freeze = OUT / 'protocol-freeze.json'
    from datetime import datetime, timezone
    prov = dict(recorded_utc=datetime.now(timezone.utc).isoformat(), python=sys.version, executable=sys.executable,
                code_sha256=code_hashes(), protocol_sha256=sha(PROTOCOL),
                freeze_record_sha256=sha(freeze) if freeze.exists() else None,
                inputs={str(Path(p).relative_to(ROOT)).replace('\\', '/'): sha(p) for p in extra})
    with path.open('x', encoding='utf-8') as stream:
        json.dump(dict(provenance=prov, data=data), stream, separators=(',', ':'))


def verify_freeze():
    f = read(OUT / 'protocol-freeze.json')['data']
    amendments = sorted(OUT.glob('protocol-amendment-*.json'))
    current = read(amendments[-1])['data'] if amendments else f
    assert current['protocol_sha256'] == sha(PROTOCOL), 'WP I protocol drift'
    assert current['code_sha256'] == code_hashes(), 'WP I code drift'
    b1 = read(ROOT / 'evidence/v11-wpb1/protocol-freeze.json')['data']['code_sha256']
    here = Path(__file__).resolve().parent
    for n in ('wpb_variants.py', 'wpa_core.py', 'wpb_stress.py'):
        assert b1[f'tools/v11/{n}'] == sha(here / n), f'frozen B1 file changed: {n}'
    return f


# ---------------- Amendment 4: AGi, the narrow insertion fix of AG ----------------
CASCADE_I = {'t0.85-AGi': (.85, False, False), 't0.85-IG+AGi+VW': (.85, True, True), 't0.55-IG+AGi+VW': (.55, True, True)}


def origin_image(old_files, version, path, origin):
    old_p = old_files.get(path)
    if old_p is None or path not in version:
        return None
    return new_image(old_p, version[path][1], origin)


def agi_flags(anchor, wanted, old_files, version, candidate, start, expected):
    """AG with one change: a same-file run at the image of the anchor's own old start is not tested."""
    path, origin = anchor['path'], anchor['line_start'] - 1
    if candidate == path and start in (expected, origin_image(old_files, version, path, origin)):
        return False
    old = old_files.get(candidate)
    old_count = len(runs(old, wanted)) if old is not None and wanted else 0
    new_count = len(runs(version[candidate][1], wanted)) if wanted else 0
    return old is not None and new_count <= old_count


def window_layers_i(t, old_files, output):
    from wpb_variants import MATCHER
    a, version, at = t['anchor'], t['version'], output['placement']
    base_layers = window_layers(t, old_files, output, ('quote', 'IG'))
    if output['label'] == 'execution_error' or at is None or base_layers['quote']['label'] == 'execution_error':
        return {'AGi': base_layers['quote'], 'IG+AGi': base_layers['IG']}
    candidate, start = at[0], at[1] - 1
    wanted = wanted_of(a['quotation'])
    lines = version[candidate][1].splitlines()
    end = output['range'][2] if output.get('range') else min(start + a['line_end'] - a['line_start'] + 1, len(lines))
    exact = wanted == tuple(x.strip() for x in '\n'.join(lines[start:end]).splitlines() if x.strip())
    out = {}
    for layer, src in (('AGi', 'quote'), ('IG+AGi', 'IG')):
        o = dict(base_layers[src], reasons=list(base_layers[src]['reasons']))
        if exact:
            path, origin = a['path'], a['line_start'] - 1
            expected = MATCHER.expected_start('\n'.join(t['old_lines']) + '\n', version[path][1].splitlines(),
                                              origin) if path in version else origin
            if agi_flags(a, wanted, old_files, version, candidate, start, expected):
                o['recheck'] = True
                if o['label'] != 'changed':
                    o['label'] = 'moved'
                o['reasons'].append('pre-existing-copy')
        out[layer] = o
    return out


def choose_i(data, theta, ig, vw):
    """Frozen choose(ag=True) with AGi: the origin image also counts as the predicted start."""
    from wpb_variants import choose
    a, version, old_files = data['anchor'], data['version'], data['old_files']
    path, origin = a['path'], data['origin']
    image = origin_image(old_files, version, path, origin) if data['same'] else None
    if image is None or image == data['expected'] or not any(r[0] == image for r in data['same']):
        return choose(data, theta, ig, True, vw)
    # The run at the origin image is the anchor's own lines: select it and skip the count test.
    out = choose(dict(data, expected=image), theta, ig, True, vw)
    return out


def cascade_i(t, old_files):
    data = prepare(t, old_files)
    return {name: choose_i(data, *args) for name, args in CASCADE_I.items()}
