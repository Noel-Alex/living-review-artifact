"""Proposed IG/AG/VW refinements. Pure matcher; no source execution or writes."""
from difflib import SequenceMatcher
from functools import lru_cache
import itertools
import math
from pathlib import PurePosixPath
from wpa_core import loaders, runs, fuzzy

MATCHER, _ = loaders()
SWITCHES = list(itertools.product((False, True), repeat=3))
THETAS = (.85, .55)


def profile(text):
    widths = [len(s.expandtabs(8))-len(s.expandtabs(8).lstrip())
              for s in text.splitlines() if s.strip()]
    return (widths[0], tuple(w-widths[0] for w in widths)) if widths else (0, ())


@lru_cache(maxsize=2048)
def variable_fuzzy(text, wanted, span, expected):
    lines, target = text.splitlines(), ' '.join(wanted)
    radius, d = max(10, 2*span), max(1, math.ceil(span/2))
    best, location, height, best_key = 0., None, None, None
    for h in range(max(1, span-d), span+d+1):
        for s in range(max(0, expected-radius), max(0, min(expected+radius+1, len(lines)-h+1))):
            window = ' '.join(x.strip() for x in lines[s:s+h] if x.strip())
            sm = SequenceMatcher(None, target, window, autojunk=False)
            if sm.quick_ratio() < best:
                continue
            ratio = sm.ratio()
            key = (ratio, -abs(s-expected), -abs(h-span), -s, -h)
            if ratio > 0 and (best_key is None or key > best_key):
                best, location, height, best_key = ratio, s, h, key
    return best, location, height


def prepare(trial, old_files):
    a, version = trial['anchor'], trial['version']
    path, origin = a['path'], a['line_start']-1
    wanted = tuple(x.strip() for x in a['quotation'].splitlines() if x.strip())
    span = max(1, a['line_end']-a['line_start']+1, len(a['quotation'].splitlines()))
    data = dict(anchor=a, version=version, old_files=old_files, wanted=wanted,
                origin=origin, span=span, same=(), cross=None, fixed=(0., None, span),
                variable=(0., None, None), expected=origin, hash=False)
    if path in version and a.get('content_hash') and a['content_hash'] == version[path][0]:
        data['hash'] = True
        return data
    if not wanted:
        return data
    if path in version:
        text = version[path][1]
        data['expected'] = MATCHER.expected_start('\n'.join(trial['old_lines'])+'\n', text.splitlines(), origin)
        data['same'] = runs(text, wanted)
        if not data['same']:
            radius, expected = max(10, 2*span), data['expected']
            starts = tuple(range(max(0, expected-radius), max(0, min(expected+radius+1, len(text.splitlines())-span+1))))
            score, at = fuzzy(text, wanted, span, starts)
            data['fixed'] = (score, at, span)
            data['variable'] = variable_fuzzy(text, wanted, span, expected)
    if not data['same'] and min(data['fixed'][0], data['variable'][0]) < max(THETAS):
        for p in sorted(p for p in version if p != path):
            found = runs(version[p][1], wanted)
            if found:
                data['cross'] = (p, *found[0])
                break
    return data


def choose(data, theta=.85, ig=False, ag=False, vw=False):
    a, version = data['anchor'], data['version']
    path, origin = a['path'], data['origin']
    reasons = []
    if data['hash']:
        return dict(label='exact', placement=[path, origin+1],
                    range=[path, origin+1, a['line_end']], tier='hash', recheck=False, reasons=[])
    exact = False
    if data['same']:
        found = data['same']
        at_expected = [r for r in found if r[0] == data['expected']]
        start, end = at_expected[0] if ag and at_expected else min(found, key=lambda r: abs(r[0]-origin))
        candidate, label, tier, exact = path, 'exact' if start == origin else 'moved', 'same_exact', True
    else:
        score, start, h = data['variable'] if vw else data['fixed']
        if start is not None and score >= theta:
            candidate, end, label, tier = path, start+h, 'changed', 'variable' if vw else 'local'
        elif data['cross']:
            candidate, start, end = data['cross']
            label, tier, exact = 'moved', 'cross_exact', True
        else:
            return dict(label='removed', placement=None, range=None, tier='no_match', recheck=True, reasons=[])
    recheck = label == 'changed'
    if exact and ag and (candidate != path or start != data['expected']):
        old = data['old_files'].get(candidate)
        old_count = len(runs(old, data['wanted'])) if old is not None else 0
        new_count = len(runs(version[candidate][1], data['wanted']))
        if old is not None and new_count <= old_count:
            label, recheck = 'moved', True
            reasons.append('pre-existing-copy')
    if exact and ig:
        before = profile(a['quotation'])
        after = profile('\n'.join(version[candidate][1].splitlines()[start:end]))
        python = PurePosixPath(path).suffix.lower() in ('.py', '.pyw')
        if (before != after if python else before[1] != after[1]):
            label, recheck = 'changed', True
            reasons.append('layout')
    return dict(label=label, placement=[candidate, start+1], range=[candidate, start+1, end],
                tier=tier, recheck=recheck, reasons=reasons)


def relocate(trial, old_files, theta=.85, ig=False, ag=False, vw=False):
    return choose(prepare(trial, old_files), theta, ig, ag, vw)


def all_outputs(trial, old_files):
    data = prepare(trial, old_files)
    return {variant_key(t, *s): choose(data, t, *s) for t in THETAS for s in SWITCHES}


def variant_key(theta, ig=False, ag=False, vw=False):
    return f't{theta:.2f}-' + ('+'.join(n for n, enabled in zip(('IG','AG','VW'), (ig,ag,vw)) if enabled) or 'deployed')
