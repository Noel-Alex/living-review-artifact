"""B2b: prefix references and variant replays for the 4,000 archived ten-hop chains.

Protocol: review/V11-PROTOCOL-B2.md. Reads pinned Git histories (no checkout, no execution).
"""
import hashlib
import json

from wpa_core import loaders, outcome  # noqa: I001 (puts tools/ on sys.path)
from history_context import ROOT, PRIVATE, History
from regenerate_history_selection import harness
import wpb_variants
from wpb_variants import prepare, choose

PREFIXES = (1, 2, 3, 5, 10)
VARIANTS = {'v0.85-all': (.85, True, True, True), 'v0.55-all': (.55, True, True, True),
            'v0.85-off': (.85, False, False, False), 'v0.55-off': (.55, False, False, False)}
DEPLOYED = {'default': .85, 'calibrated': .5}


class _Expected:
    """Pinned expected_start, but origin when the previous anchored file is unavailable (as carry does)."""

    def __init__(self, real):
        self.real, self.missing = real, False

    def expected_start(self, old_text, new_lines, origin):
        return origin if self.missing else self.real.expected_start(old_text, new_lines, origin)

    def __getattr__(self, name):
        return getattr(self.real, name)


def one_history(name):
    if name in PRIVATE:
        return History(name, *PRIVATE[name])
    record = next(r for r in json.loads((ROOT / 'evidence/public-histories/manifest.json').read_text()) if r['name'] == name)
    return History(name, ROOT / 'evidence/public-histories' / name, record['head'], record['expected_count'])


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def variant_hop(state, previous, version, theta, ig, ag, vw, proxy):
    prev_text = previous.get(state['path'], (None, None))[1]
    trial = dict(anchor=state, version=version, old_lines=(prev_text or '').splitlines())
    proxy.missing = prev_text is None
    try:
        data = prepare(trial, {p: t for p, (_, t) in previous.items()})
    finally:
        proxy.missing = False
    out = choose(data, theta, ig, ag, vw)
    new = dict(state)
    if out['label'] == 'removed':
        new['match'] = 'removed'
        return new, out
    if out['tier'] == 'hash':
        new['match'] = 'exact'
        return new, out
    candidate, start, end = out['range']
    new.update(path=candidate, line_start=start, line_end=end, content_hash=version[candidate][0], match=out['label'])
    if out['tier'] in ('local', 'variable'):
        new['quotation'] = '\n'.join(version[candidate][1].splitlines()[start - 1:end])
    return new, out


def run_repo(name, rows):
    original, _ = harness()
    matcher, _ = loaders()
    proxy = _Expected(wpb_variants.MATCHER)
    wpb_variants.MATCHER = proxy
    history = one_history(name)
    repo = original.Repo(str(history.path))
    versions, pairs = {}, {}

    def version(commit):
        if commit not in versions:
            if len(versions) > 24:
                versions.pop(next(iter(versions)))
            versions[commit] = {p: (digest(repo.blob(s)), repo.blob(s)) for p, s in repo.tree(commit).items()}
        return versions[commit]

    def pair_context(old_c, new_c):
        key = (old_c, new_c)
        if key not in pairs:
            if len(pairs) > 12:
                pairs.pop(next(iter(pairs)))
            renamed, touched = {}, []
            for line in repo.git('diff', '--name-status', '-M', old_c, new_c, '--', '*.py').splitlines():
                parts = line.split('\t')
                if parts[0].startswith('R') and len(parts) == 3:
                    renamed[parts[1]] = parts[2]
                    touched.append(parts[1])
                elif parts[0] in ('M', 'D'):
                    touched.append(parts[1])
            new_tree = repo.tree(new_c)
            v = version(new_c)
            index = [e for p, s in new_tree.items() for e in original.stmt_index(repo, s, p)]
            changed_texts = [v[p][1] for p in set(renamed.values()) | {p for p in touched if p in v}]
            pairs[key] = (renamed, index, changed_texts)
        return pairs[key]

    def reference(old_text, path, s, e, old_c, new_c):
        """The original oracle and exclusions, from the chain start to a prefix endpoint."""
        old_funcs = original.functions(old_text)
        cands = [c for c in original.candidates(old_text) if c[2] == s and c[3] == e]
        if len(cands) != 1:
            return dict(status='not-a-candidate', n=len(cands))
        qual, i, _, _ = cands[0]
        renamed, index, changed_texts = pair_context(old_c, new_c)
        v = version(new_c)
        new_path = renamed.get(path, path)
        new_text = v[new_path][1] if new_path in v else None
        truth, how = original.oracle(repo, qual, i, old_funcs, new_path, new_text, index, changed_texts)
        if truth == 'ambiguous':
            return dict(status='excluded', reason=how)
        block = old_text.splitlines()[s:e]
        if truth is None:
            return dict(status='ok', truth_at=None, cls='gone', how=how, changed=True)
        tp, ts = truth
        new_lines = v[tp][1].splitlines()
        changed = original.stripped(new_lines[ts:ts + (e - s)]) != original.stripped(block)
        want, nb = original.stripped(block), original.stripped(new_lines)
        if sum(nb[x:x + len(want)] == want for x in range(len(nb) - len(want) + 1)) > 1:
            return dict(status='excluded', reason='identical copy in the new version')
        cls = 'edited' if changed else 'moved file' if tp != path else 'in place' if ts == s else 'shifted'
        return dict(status='ok', truth_at=[tp, ts + 1], cls=cls, how=how, changed=changed)

    out = []
    try:
        for row in rows:
            commits = row['commits']
            path, start = row['anchor_at']
            v0 = version(commits[0])
            digest0, old_text = v0[path]
            record = dict(row=row['row'], repo=name, group=row['group'], sample=row['sample'], pair=row['pair'],
                          archived_cls=row['cls'], archived_truth_at=row['truth_at'], prefixes={})
            span = row['span']
            anchor = dict(path=path, line_start=start, line_end=start + span - 1,
                          quotation='\n'.join(old_text.splitlines()[start - 1:start - 1 + span]), content_hash=digest0)
            prev_full = old_text if old_text.endswith('\n') else old_text + '\n'
            for h in PREFIXES:
                ref = reference(old_text, path, start - 1, start - 1 + span, commits[0], commits[h])
                p = dict(reference=ref, direct={})
                vh = version(commits[h])
                for label, theta in DEPLOYED.items():
                    matcher.FUZZY_CODE = theta
                    o = matcher.relocate_code(anchor, vh, prev_full)
                    p['direct']['deployed-' + label] = dict(label=o['match'], placement=None if o['match'] == 'removed' else [o['path'], o['line_start']],
                                                            range=None if o['match'] == 'removed' else [o['path'], o['line_start'], o['line_end']])
                matcher.FUZZY_CODE = .85
                for key, (theta, ig, ag, vw) in VARIANTS.items():
                    _, o = variant_hop(anchor, v0, vh, theta, ig, ag, vw, proxy)
                    p['direct'][key] = dict(label=o['label'], placement=o['placement'], range=o['range'], recheck=o['recheck'])
                record['prefixes'][str(h)] = p
            for key, (theta, ig, ag, vw) in VARIANTS.items():
                state, hops = dict(anchor), []
                for index in range(1, 11):
                    state, o = variant_hop(state, version(commits[index - 1]), version(commits[index]), theta, ig, ag, vw, proxy)
                    hops.append(dict(label=o['label'], interval=o['range'], requested_recheck=o['recheck'], reasons=o['reasons']))
                record[key] = hops
            for label in DEPLOYED:
                record['archived-' + label] = row['methods'][label]['hops']
                record['archived-direct-' + label] = dict(outcome=row['methods'][label]['direct']['outcome'],
                                                          interval=row['methods'][label]['direct']['interval'])
            out.append(record)
    finally:
        repo.cat.stdin.close()
        repo.cat.wait(timeout=15)
        history.close()
    return out


def chain_rows():
    """Archived chain rows, with the anchor height taken from the original observation."""
    from history_context import load_rows
    base = load_rows()
    rows = json.loads((ROOT / 'evidence/revision-chains/trials.json').read_text())
    assert len(rows) == 4000
    for r in rows:
        b = base[r['row']]
        assert b['pair'] == r['pair'] and b['anchor_at'] == r['anchor_at']
        r['span'] = b['span']
    return rows


def placement(interval):
    return None if interval is None else interval[:2]


def score(record, method, h, direct=False):
    """Endpoint events at prefix h for a sequential trace or a direct relocation."""
    ref = record['prefixes'][str(h)]['reference']
    if ref['status'] != 'ok':
        return None
    if direct:
        d = record['prefixes'][str(h)]['direct'][method]
        at, label = d['placement'], d['label']
        request = d.get('recheck', label in ('changed', 'removed'))
        requested_any = request
    else:
        hops = record[method][:h]
        at, label = placement(hops[-1]['interval']), hops[-1]['label']
        request = hops[-1]['requested_recheck']
        requested_any = any(x['requested_recheck'] for x in hops)
    oc = outcome(ref['truth_at'], at)
    changed = ref['cls'] in ('edited', 'gone')
    wrong = oc == 'wrong_place'
    return dict(correct=int(oc == 'correct'), wrong=int(wrong), lost=int(oc == 'lost'), changed=int(changed),
                missed_cumulative=int(changed and not requested_any), missed_last=int(changed and not request),
                wrong_silent_cumulative=int(wrong and not requested_any), wrong_silent_last=int(wrong and not request),
                last_exact_wrong=int(wrong and label == 'exact'))


if __name__ == '__main__':
    import sys
    rows = chain_rows()
    name = sys.argv[1]
    got = run_repo(name, [r for r in rows if r['repo'] == name][:int(sys.argv[2])])
    print(json.dumps(got[0]['prefixes']['10']['reference']), got[0]['archived_truth_at'], got[0]['archived_cls'])
