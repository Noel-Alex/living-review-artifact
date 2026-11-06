"""B2d: timing and memory of the deployed cascade and the frozen all-on variant on large public trees.

Sources are read as text and parsed with ast only; nothing downloaded is executed.
"""
import gc
import hashlib
import json
import platform
import random
import statistics
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path

from wpa_core import ROOT, loaders, runs, fuzzy
import wpb_variants
from wpb_variants import relocate as variant_relocate, variable_fuzzy
from regenerate_history_selection import harness

EXTERNAL = ROOT / 'evidence/v11-wpb2/external'
PAIRS = {'django': ('django-5.1', 'django-5.2', 'django'), 'cpython-Lib': ('cpython-v3.12.0', 'cpython-v3.13.0', 'Lib')}
SIZES = (1, 10, 100, 1000)
MAX_FILE_BYTES = 400_000
SEED = 20261101
REPS = 3


def file_map(directory, subtree):
    out, skipped = {}, {'over_size': 0, 'not_utf8': 0}
    base = EXTERNAL / directory
    for path in sorted((base / subtree).rglob('*.py')):
        raw = path.read_bytes()
        if len(raw) > MAX_FILE_BYTES:
            skipped['over_size'] += 1
            continue
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            skipped['not_utf8'] += 1
            continue
        out[path.relative_to(base).as_posix()] = (hashlib.sha256(raw).hexdigest(), text)
    return out, skipped


def head(directory):
    return subprocess.check_output(['git', '-C', str(EXTERNAL / directory), 'rev-parse', 'HEAD'], text=True).strip()


def sample_anchors(old, new, n, rng):
    original, _ = harness()
    pool = []
    for path in sorted(p for p in old if p in new and new[p][0] != old[p][0]):
        text = old[path][1]
        if not (60 <= len(text.splitlines()) <= 1500):
            continue
        for qual, i, s, e in original.candidates(text):
            pool.append((path, s, e))
    rng.shuffle(pool)
    anchors = []
    for path, s, e in pool[:n]:
        text = old[path][1]
        anchors.append(dict(path=path, line_start=s + 1, line_end=e, content_hash=old[path][0],
                            quotation='\n'.join(text.splitlines()[s:e])))
    return anchors, len(pool)


def absent_anchors(anchors, rng):
    """Foreign quotations: no file contains them and no window is similar, so tier 4 scans every file."""
    out = []
    for a in anchors:
        height = a['line_end'] - a['line_start'] + 1
        lines = ['zq%08x_%d = wpb2_absent_%08x(%d)' % (rng.getrandbits(32), j, rng.getrandbits(32), j) for j in range(height)]
        out.append(dict(a, quotation='\n'.join(lines)))
    return out


def tier_of(result, anchor, files):
    if result['match'] == 'exact' and result['path'] == anchor['path'] and result.get('line_start') == anchor['line_start'] \
            and files.get(anchor['path'], (None,))[0] == anchor['content_hash']:
        return 'tier1-hash'
    if result['match'] in ('exact', 'moved') and result['path'] == anchor['path']:
        return 'tier2-same-file'
    if result['match'] == 'changed':
        return 'tier3-local-fuzzy'
    if result['match'] == 'moved':
        return 'tier4-cross-file'
    return 'removed-after-all-tiers'


def clear_variant_caches():
    runs.cache_clear()
    fuzzy.cache_clear()
    variable_fuzzy.cache_clear()


def compose(method, anchors, old, new, matcher):
    """One review composition: relocate every anchor in turn; per-anchor seconds and tiers."""
    times, tiers = [], []
    if method == 'variant':
        clear_variant_caches()
        old_texts = {p: t for p, (_, t) in old.items()}
    start_all = time.perf_counter()
    for a in anchors:
        t0 = time.perf_counter()
        if method == 'deployed':
            r = matcher.relocate_code(a, new, old.get(a['path'], (None, None))[1])
            tier = tier_of(r, a, new)
        else:
            prev = old.get(a['path'], (None, ''))[1] or ''
            r = variant_relocate(dict(anchor=a, version=new, old_lines=prev.splitlines()), old_texts, .85, True, True, True)
            tier = r['tier']
        times.append(time.perf_counter() - t0)
        tiers.append(tier)
    return time.perf_counter() - start_all, times, tiers


def pct(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))]


def bench(name, old, new, anchors, matcher, label):
    result = {}
    for method in ('deployed', 'variant'):
        matcher.FUZZY_CODE = .85
        per = {}
        for size in SIZES:
            subset = anchors[:size]
            if len(subset) < size:
                per[str(size)] = dict(available=len(subset), complete=False)
                continue
            compose(method, subset[:min(size, 10)], old, new, matcher)  # warm-up
            totals, all_times, tier_time, tier_count = [], [], {}, {}
            for _ in range(REPS):
                gc.collect()
                total, times, tiers = compose(method, subset, old, new, matcher)
                totals.append(total)
                all_times += times
                for t, tier in zip(times, tiers):
                    tier_time[tier] = tier_time.get(tier, 0) + t
                    tier_count[tier] = tier_count.get(tier, 0) + 1
            per[str(size)] = dict(anchors=size, repetitions=REPS, composition_seconds=totals,
                                  composition_p50=statistics.median(totals),
                                  per_anchor_p50=pct(all_times, .5), per_anchor_p95=pct(all_times, .95),
                                  per_anchor_max=max(all_times),
                                  tier_time_share={k: v / sum(tier_time.values()) for k, v in sorted(tier_time.items())},
                                  tier_counts={k: v // REPS for k, v in sorted(tier_count.items())})
        largest = anchors[:max(s for s in SIZES if s <= len(anchors))]
        gc.collect()
        tracemalloc.start()
        compose(method, largest, old, new, matcher)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        per['peak_traced_bytes'] = dict(anchors=len(largest), bytes=peak)
        result[method] = per
    return result


def environment():
    cpu = platform.processor()
    try:
        cpu = subprocess.check_output(['powershell', '-NoProfile', '-Command',
                                       '(Get-CimInstance Win32_Processor).Name'], text=True).strip() or cpu
    except (OSError, subprocess.CalledProcessError):
        pass
    return dict(cpu=cpu, python=sys.version, platform=platform.platform(), executable=sys.executable)


def run():
    matcher, _ = loaders()
    rng = random.Random(SEED)
    out = dict(environment=environment(), corpora={})
    for name, (a, b, subtree) in PAIRS.items():
        old, skipped_old = file_map(a, subtree)
        new, skipped_new = file_map(b, subtree)
        anchors, pool = sample_anchors(old, new, max(SIZES), rng)
        info = dict(old=a, new=b, old_commit=head(a), new_commit=head(b), subtree=subtree,
                    files_old=len(old), files_new=len(new), lines_new=sum(len(t.splitlines()) for _, t in new.values()),
                    skipped_old=skipped_old, skipped_new=skipped_new, candidate_pool=pool, anchors=len(anchors))
        print(name, info, flush=True)
        info['results'] = bench(name, old, new, anchors, matcher, 'sampled')
        adversarial = absent_anchors(anchors[:100], rng)
        info['adversarial_tier4'] = bench(name, old, new, adversarial, matcher, 'absent')
        out['corpora'][name] = info
    return out


if __name__ == '__main__':
    print(json.dumps(environment()))
