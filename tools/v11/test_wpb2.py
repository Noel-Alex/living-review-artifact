"""B2 construction checks on a development seed (never an evaluation seed)."""
import ast
from collections import Counter
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpb2_compound import compound, OPERATORS  # noqa: E402

DEV_SEED = 7


def _trials(n=12):
    out = []
    for meta, trial, old in compound(DEV_SEED, n=n, cap=40000):
        out.append((meta, trial, old))
    return out


def test_compound_construction():
    trials = _trials()
    audits = [m for m, t, _ in trials if m.get('generator_audit')]
    assert len(audits) == 4 and all(a['complete'] for a in audits), audits
    seen = Counter()
    for meta, t, old_files in trials:
        if meta.get('generator_audit'):
            continue
        seen.update(meta['operators'])
        for path, (_, text) in t['version'].items():
            if text != old_files.get(path):
                ast.parse(text)
        path, start = t['truth']
        new = t['version'][path][1].splitlines()
        old = t['old_lines']
        a = t['anchor']
        # The truth start line is a surviving original anchor line (possibly renamed/reindented).
        firsts = {x.strip() for x in old[a['line_start'] - 1:a['line_end']]}
        if 'rename' not in meta['operators']:
            # A wrap keeps the head of the original line on the tagged row.
            assert any(x.startswith(new[start].strip()) for x in firsts), (meta, new[start])
        assert t['truth_end'] > start
        ops = set(meta['operators'])
        if ops <= {'move-in-file', 'move-file', 'insert-above', 'token-edit-nearby', 'reformat'}:
            assert not t['changed'], meta
        if 'expand' in ops:
            assert t['changed'], meta
        if 'move-file' in ops:
            assert path != a['path'], meta
    assert set(seen) == set(OPERATORS), seen


if __name__ == '__main__':
    test_compound_construction()
    print('ok')
