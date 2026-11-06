"""WP K2 generator: the parametric copy and anchor suite (protocol review/V12-PROTOCOL-K2.md).

Crossed factors over the controlled stress corpus (wpb_stress.corpus):
  c  pre-existing identical copies of the anchored lines   {0, 1, 2, 4, 8}
  d  placement of the nearest copy                         {adjacent, near (1-20 lines), far (>50 lines), other-file}
  k  anchor height in lines                                {1, 2, 3, 5, 8}
  fate of the original                                     {unchanged, shifted, token-edit, deleted}
plus the same-revision condition: no pre-existing copy, the original is token-edited or deleted, and one copy is
introduced by the same revision (the known blind spot of AGi). c = 0 has no d level.

Anchors are runs of complete statements of one body whose line extent is exactly k and whose stripped text occurs
once in every file of the trial before copies are placed. Copies are verbatim (same indentation) and inserted at
statement boundaries of a body with the same indentation, so every file parses (ast.parse is checked for every
file of both versions). Yields (meta, trial, old_files) like wpb_stress; meta['generator_audit'] rows close a cell.
"""
from __future__ import annotations

import ast
import random
from collections import Counter

from wpb_stress import corpus, digest

SEED = 20261106
COPIES = (0, 1, 2, 4, 8)
PLACES = ('adjacent', 'near', 'far', 'other-file')
HEIGHTS = (1, 2, 3, 5, 8)
FATES = ('unchanged', 'shifted', 'token-edit', 'deleted')
SAME_REVISION_FATES = ('token-edit', 'deleted')
PER_CELL = 20
UNRELATED = 25


def stripped(lines):
    return [x.strip() for x in lines if x.strip()]


def occurrences(lines, want):
    s = stripped(lines)
    n = len(want)
    return sum(s[i:i + n] == want for i in range(len(s) - n + 1))


def bodies(tree):
    for node in ast.walk(tree):
        for field in ('body', 'orelse', 'finalbody', 'handlers'):
            b = getattr(node, field, None)
            if isinstance(b, list) and b and isinstance(b[0], ast.stmt):
                yield b


def first_line(stmt):
    return min([stmt.lineno] + [d.lineno for d in getattr(stmt, 'decorator_list', [])])


def index_file(text):
    """Statement runs (start0, height, indent) and insertion boundaries {indent: [line index]} of one file."""
    tree = ast.parse(text)
    lines = text.splitlines()
    runs, bounds = [], {}
    for body in bodies(tree):
        col = body[0].col_offset
        for s in body:
            bounds.setdefault(s.col_offset, set()).add(first_line(s) - 1)
        bounds.setdefault(col, set()).add(body[-1].end_lineno)
        for i in range(len(body)):
            for j in range(i, len(body)):
                a, b = first_line(body[i]) - 1, body[j].end_lineno
                if b - a > max(HEIGHTS):
                    break
                if lines[a].strip() and lines[b - 1].strip() and not lines[a].lstrip().startswith(('#', '@')):
                    runs.append((a, b - a, body[i].col_offset))
    return runs, {k: sorted(v) for k, v in bounds.items()}


class Corpus:
    def __init__(self):
        self.bench, files, self.old = corpus()
        self.names = sorted(files)
        self.lines = {p: self.old[p].splitlines() for p in self.names}
        self.index = {}
        for p in self.names:
            try:
                self.index[p] = index_file(self.old[p])
            except SyntaxError:
                continue
        self.parseable = sorted(self.index)


def gap(p, start, k):
    """Lines between a copy inserted before base index p and the original [start, start+k)."""
    return start - p if p <= start else p - (start + k)


def place_class(g):
    return 'adjacent' if g == 0 else 'near' if 1 <= g <= 20 else 'far' if g > 50 else None


def parses(text):
    try:
        ast.parse(text)
        return True
    except (SyntaxError, ValueError):
        return False


def insert(tagged, at_list, block, tag):
    """Insert copies at base indices (descending so earlier indices stay valid)."""
    for n, at in sorted(enumerate(at_list), key=lambda x: -x[1]):
        tagged[at:at] = [(s, (tag, n, i)) for i, s in enumerate(block)]


def trial(rng, C, c, d, k, fate, same_revision=False):
    name = rng.choice(C.parseable)
    runs, bounds = C.index[name]
    runs = [r for r in runs if r[1] == k]
    if not runs:
        return None, 'no-run-of-height'
    start, _, col = rng.choice(runs)
    lines = C.lines[name]
    block = lines[start:start + k]
    want = stripped(block)
    if not want:
        return None, 'blank-block'
    others = [p for p in C.parseable if p != name]
    unrelated = rng.sample(others, k=min(UNRELATED, len(others)))
    if occurrences(lines, want) != 1 or any(occurrences(C.lines[p], want) for p in unrelated):
        return None, 'anchor-text-not-unique'
    n_copies = 1 if same_revision else c
    same_pos = [p for p in bounds.get(col, []) if not (start < p < start + k)]
    by_class = {cl: [p for p in same_pos if place_class(gap(p, start, k)) == cl] for cl in PLACES[:3]}
    other_pos = [(p, b) for p in unrelated for b in C.index[p][1].get(col, [])]
    same_at, other_at = [], []
    if n_copies:
        if d == 'other-file':
            if not other_pos:
                return None, 'no-other-file-boundary'
            other_at = [rng.choice(other_pos) for _ in range(n_copies)]
        else:
            if not by_class[d]:
                return None, f'no-{d}-boundary'
            first = rng.choice(by_class[d])
            same_at = [first]
            g0 = gap(first, start, k)
            farther = [p for p in same_pos if gap(p, start, k) > g0]
            for _ in range(n_copies - 1):
                if farther and (not other_pos or rng.random() < .5):
                    same_at.append(rng.choice(farther))
                elif other_pos:
                    other_at.append(rng.choice(other_pos))
                else:
                    return None, 'no-room-for-extra-copies'
    base = [(s, ('base', i)) for i, s in enumerate(lines)]
    for i in range(start, start + k):
        base[i] = (lines[i], ('original', i))
    other_tagged = {}
    for p, b in other_at:
        other_tagged.setdefault(p, [])
    old_tagged = list(base)
    if not same_revision:
        insert(old_tagged, same_at, block, 'copy')
        for p in other_tagged:
            t = [(s, ('base', i)) for i, s in enumerate(C.lines[p])]
            insert(t, [b for q, b in other_at if q == p], block, 'copy')
            other_tagged[p] = t
    new_tagged = list(old_tagged)
    new_other = {p: list(v) for p, v in other_tagged.items()}
    if same_revision:
        insert(new_tagged, same_at, block, 'copy')
        for p in other_tagged:
            t = [(s, ('base', i)) for i, s in enumerate(C.lines[p])]
            insert(t, [b for q, b in other_at if q == p], block, 'copy')
            new_other[p] = t
    idx = [i for i, (_, tag) in enumerate(new_tagged) if tag[0] == 'original']
    assert len(idx) == k and idx == list(range(idx[0], idx[0] + k))
    o0 = idx[0]
    changed = fate in ('token-edit', 'deleted')
    if fate == 'shifted':
        indent = block[0][:len(block[0]) - len(block[0].lstrip())]
        m = rng.randint(1, 5)
        new_tagged[o0:o0] = [(f'{indent}# note {j}', ('inserted', j)) for j in range(m)]
    elif fate == 'token-edit':
        cand = [i for i in idx if [w for w in new_tagged[i][0].replace('(', ' ').replace(')', ' ').replace(',', ' ').split()
                                   if w.isidentifier() and len(w) > 2]]
        if not cand:
            return None, 'no-editable-token'
        i = rng.choice(cand)
        new_tagged[i] = (C.bench.mutate_token(rng, new_tagged[i][0]), new_tagged[i][1])
    elif fate == 'deleted':
        del new_tagged[o0:o0 + k]
    old_text = '\n'.join(s for s, _ in old_tagged) + '\n'
    new_text = '\n'.join(s for s, _ in new_tagged) + '\n'
    old_files = {name: old_text}
    new_files = {name: new_text}
    for p in set(other_tagged) | set(new_other):
        old_files[p] = '\n'.join(s for s, _ in other_tagged[p]) + '\n' if other_tagged.get(p) else C.old[p]
        new_files[p] = '\n'.join(s for s, _ in new_other[p]) + '\n' if new_other.get(p) else C.old[p]
    if same_revision:
        for p in new_other:
            old_files[p] = C.old[p]
    for p in unrelated:
        old_files.setdefault(p, C.old[p])
        new_files.setdefault(p, C.old[p])
    for t in set(old_files.values()) | set(new_files.values()):
        if not parses(t):
            return None, 'parse-failed'
    old_lines = old_text.splitlines()
    a0 = next(i for i, (_, tag) in enumerate(old_tagged) if tag[0] == 'original')
    assert stripped(old_lines[a0:a0 + k]) == want
    # Copy counts actually present (stripped contiguous runs), excluding the original.
    pre = sum(occurrences(t.splitlines(), want) for t in old_files.values()) - 1
    post = sum(occurrences(t.splitlines(), want) for t in new_files.values()) - (1 if fate in ('unchanged', 'shifted') else 0)
    expect_pre, expect_post = (0, 1) if same_revision else (c, c)
    if pre != expect_pre or post != expect_post:
        return None, 'copy-count-check'
    if fate == 'deleted':
        truth = None
    else:
        t1 = next(i for i, (_, tag) in enumerate(new_tagged) if tag[0] == 'original')
        truth = [name, t1 + 1]
    nearest = None
    if same_at or other_at:
        cps = [i for i, (_, tag) in enumerate(new_tagged if same_revision else old_tagged) if tag[0] == 'copy' and tag[2] == 0]
        nearest = min((abs(i - a0) for i in cps), default=None)
    t = dict(anchor=dict(path=name, line_start=a0 + 1, line_end=a0 + k, content_hash=digest(old_text),
                         quotation='\n'.join(old_lines[a0:a0 + k])),
             old_lines=old_lines, version={p: (digest(x), x) for p, x in new_files.items()},
             truth=truth, changed=changed)
    meta = dict(c=c, d=d, k=k, fate=fate, same_revision=same_revision, source=name, truth_at=truth, changed=changed,
                copies_old=pre, copies_new=post, copy_files=sorted({p for p, _ in other_at}), nearest_copy_start_offset=nearest,
                old_sha256={p: digest(x) for p, x in old_files.items() if p == name or p in other_tagged or p in new_other},
                new_sha256={p: digest(x) for p, x in new_files.items() if p == name or p in other_tagged or p in new_other})
    return (meta, t, old_files), None


def cells():
    for k in HEIGHTS:
        for fate in FATES:
            yield (0, None, k, fate, False)
            for c in COPIES[1:]:
                for d in PLACES:
                    yield (c, d, k, fate, False)
    for k in HEIGHTS:
        for fate in SAME_REVISION_FATES:
            for d in PLACES:
                yield (None, d, k, fate, True)


def cell_key(c, d, k, fate, same):
    return f"{'same' if same else 'c' + str(c)}|{d or '-'}|k{k}|{fate}"


def generate(seed=SEED, per_cell=PER_CELL, max_attempts=4000):
    C = Corpus()
    for n, (c, d, k, fate, same) in enumerate(cells()):
        rng = random.Random(f'{seed}|{cell_key(c, d, k, fate, same)}')
        made, counts = 0, Counter()
        while made < per_cell and counts['attempted'] < max_attempts:
            counts['attempted'] += 1
            got, why = trial(rng, C, c, d, k, fate, same)
            if got is None:
                counts[why] += 1
                continue
            meta, t, old = got
            meta.update(cell=cell_key(c, d, k, fate, same), index=made, seed=seed,
                        id=f"{cell_key(c, d, k, fate, same).replace('|', '_')}_{made:02d}")
            yield meta, t, old
            made += 1
        yield dict(generator_audit=True, cell=cell_key(c, d, k, fate, same), requested=per_cell, made=made,
                   complete=made == per_cell, counts=dict(counts)), None, None


if __name__ == '__main__':
    import sys
    import time
    t0 = time.time()
    audits = []
    n = 0
    for meta, t, old in generate(per_cell=int(sys.argv[1]) if len(sys.argv) > 1 else PER_CELL):
        if meta.get('generator_audit'):
            audits.append(meta)
        else:
            n += 1
    short = [a for a in audits if not a['complete']]
    print('trials', n, 'cells', len(audits), 'incomplete', len(short), f'{time.time() - t0:.0f}s')
    for a in short[:40]:
        print(a['cell'], a['made'], a['counts'])
