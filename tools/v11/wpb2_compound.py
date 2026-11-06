"""B2a compound-edit trials on the original controlled corpus (protocol: review/V11-PROTOCOL-B2.md).

Lines carry construction tags, so the anchored lines' identity is known after any composition:
('A', i) original anchor line i, ('AI', n) a line inserted inside the anchor, ('O', path, i) other.
"""
import ast
from collections import Counter
import io
import keyword
import random
import re
import tokenize

from wpb_stress import corpus, build, digest

OPERATORS = ('move-in-file', 'move-file', 'rename', 'reformat', 'expand', 'contract', 'insert-above',
             'token-edit-nearby')
KS = (1, 2, 3, 4)
SEED_OFFSET = 303


def text_of(tagged):
    return '\n'.join(s for s, _ in tagged) + '\n'


def indent_of(line):
    return len(line) - len(line.lstrip())


def block_rows(tagged):
    rows = [i for i, (_, tag) in enumerate(tagged) if tag[0] in ('A', 'AI')]
    return rows[0], rows[-1] + 1


def statements(tree):
    return [n for n in ast.walk(tree) if isinstance(n, ast.stmt)]


def covered(tree, s, e):
    """Maximal statements lying inside 0-based rows [s, e)."""
    inside = [n for n in statements(tree) if n.lineno - 1 >= s and n.end_lineno <= e]
    keep = [n for n in inside if not any(o is not n and o.lineno <= n.lineno and n.end_lineno <= o.end_lineno
                                         and (o.lineno, o.end_lineno) != (n.lineno, n.end_lineno) for o in inside)]
    return sorted(keep, key=lambda n: (n.lineno, n.col_offset))


def aligned(text, start, span):
    """The anchor rows are exactly a run of complete sibling statements."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        for field in ('body', 'orelse', 'finalbody'):
            body = getattr(node, field, None)
            if not isinstance(body, list):
                continue
            firsts = [i for i, st in enumerate(body) if st.lineno - 1 == start]
            if not firsts:
                continue
            j = firsts[0]
            # Decorators belong to the statement; a decorated definition must start at its decorator.
            for k in range(j, len(body)):
                if body[k].end_lineno == start + span:
                    return [b for b in body[j:k + 1]]
                if body[k].end_lineno > start + span:
                    break
    return None


def boundaries(tree, lines, exclude):
    """Rows where a statement starts (insertion points), with that statement's indentation."""
    out = []
    for n in statements(tree):
        row = n.lineno - 1
        if hasattr(n, 'decorator_list') and n.decorator_list:
            row = n.decorator_list[0].lineno - 1
        if not (exclude[0] <= row < exclude[1]):
            out.append((row, indent_of(lines[row])))
    return sorted(set(out))


def reindent(block, width):
    base = min((indent_of(s) for s, _ in block if s.strip()), default=0)
    return [((' ' * (width + indent_of(s) - base) + s.lstrip()) if s.strip() else s, tag) for s, tag in block]


def names_in(lines):
    found = []
    try:
        for t in tokenize.generate_tokens(io.StringIO('\n'.join(lines) + '\n').readline):
            if t.type == tokenize.NAME and not keyword.iskeyword(t.string) and t.string not in ('self', 'cls'):
                found.append(t.string)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []
    return sorted(set(found))


def commas(line):
    """Column after each comma that lies inside brackets on this single line."""
    out, depth = [], 0
    try:
        for t in tokenize.generate_tokens(io.StringIO(line.strip() + '\n').readline):
            if t.type == tokenize.OP:
                depth += int(t.string in '([{') - int(t.string in ')]}')
                if t.string == ',' and depth > 0:
                    out.append(t.end[1])
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []
    return out


def apply(op, state, rng, bench, files, names):
    """Apply one operator in place; return a rejection reason or None."""
    path = state['block_path']
    tagged = state['files'][path]
    s, e = block_rows(tagged)
    lines = [x for x, _ in tagged]
    try:
        tree = ast.parse(text_of(tagged))
    except SyntaxError:
        return 'unparsable-intermediate'
    if op in ('move-in-file', 'move-file'):
        block = tagged[s:e]
        if op == 'move-in-file':
            rest = tagged[:s] + tagged[e:]
            try:
                rest_tree = ast.parse(text_of(rest))
            except SyntaxError:
                return 'removal-unparsable'
            spots = [(r, w) for r, w in boundaries(rest_tree, [x for x, _ in rest], (-1, -1)) if abs(r - s) >= 40]
            if not spots:
                return 'no-far-boundary'
            r, w = rng.choice(spots)
            state['files'][path] = rest[:r] + reindent(block, w) + rest[r:]
        else:
            others = [p for p in names if p != path and p not in state['files']] or [p for p in names if p != path]
            dest = rng.choice(others)
            dest_tagged = state['files'].get(dest) or [(x, ('O', dest, i)) for i, x in enumerate(files[dest])]
            try:
                dt = ast.parse(text_of(dest_tagged))
            except SyntaxError:
                return 'destination-unparsable'
            spots = boundaries(dt, [x for x, _ in dest_tagged], (-1, -1))
            if not spots:
                return 'no-destination-boundary'
            r, w = rng.choice(spots)
            state['files'][dest] = dest_tagged[:r] + reindent(block, w) + dest_tagged[r:]
            state['files'][path] = tagged[:s] + tagged[e:]
            state['block_path'] = dest
        return None
    if op == 'rename':
        pool = names_in(lines[s:e])
        if not pool:
            return 'no-identifier'
        old = rng.choice(pool)
        new = old + '_r2'
        pattern = re.compile(r'\b' + re.escape(old) + r'\b')
        state['files'][path] = [(pattern.sub(new, x), tag) if s <= i < e else (x, tag) for i, (x, tag) in enumerate(tagged)]
        return None
    if op == 'reformat':
        options = []
        for i in range(s, e):
            for col in commas(lines[i]):
                options.append(('wrap', i, col))
        cont = [i for i in range(s + 1, e) if lines[i].strip() and i - 1 >= s and lines[i - 1].rstrip().endswith((',', '(', '[', '{'))]
        options += [('align', i, None) for i in cont]
        if not options:
            return 'no-reformat-site'
        kind, i, col = rng.choice(options)
        x, tag = tagged[i]
        if kind == 'wrap':
            body = x.strip()
            head, tail = body[:col].rstrip(), body[col:].lstrip()
            if not tail:
                return 'wrap-at-end'
            w = indent_of(x)
            new_rows = [(' ' * w + head, tag), (' ' * (w + 4) + tail, ('AI', state['inserted']))]
            state['inserted'] += 1
            state['files'][path] = tagged[:i] + new_rows + tagged[i + 1:]
        else:
            state['files'][path] = tagged[:i] + [(' ' * (indent_of(x) + rng.choice((2, -2) if indent_of(x) >= 2 else (2,))) + x.lstrip(), tag)] + tagged[i + 1:]
        try:
            neutral = ast.dump(ast.parse(text_of(state['files'][path]))) == ast.dump(tree)
        except SyntaxError:
            neutral = False
        if not neutral:
            return 'reformat-not-AST-neutral'
        return None
    if op == 'expand':
        spots = [(r, w) for r, w in boundaries(tree, lines, (-1, -1)) if s < r < e]
        if not spots:
            return 'no-inner-boundary'
        r, w = rng.choice(spots)
        state['files'][path] = tagged[:r] + [(' ' * w + '_wpb2_probe = None', ('AI', state['inserted']))] + tagged[r:]
        state['inserted'] += 1
        return None
    if op == 'contract':
        inner = [i for i in range(s + 1, e - 1) if lines[i].strip() and tagged[i][1][0] == 'A']
        if not inner:
            return 'no-inner-line'
        i = rng.choice(inner)
        state['files'][path] = tagged[:i] + tagged[i + 1:]
        return None
    if op == 'insert-above':
        w = indent_of(lines[s])
        pad = [(' ' * w + f'_wpb2_pad_{state["inserted"]}_{j} = {j}', ('N', state['inserted'], j)) for j in range(rng.randint(2, 5))]
        state['inserted'] += 1
        state['files'][path] = tagged[:s] + pad + tagged[s:]
        return None
    if op == 'token-edit-nearby':
        near = [i for i in list(range(max(0, s - 5), s)) + list(range(e, min(len(lines), e + 5))) if lines[i].strip()]
        if not near:
            return 'no-nearby-line'
        i = rng.choice(near)
        x, tag = tagged[i]
        state['files'][path] = tagged[:i] + [(bench.mutate_token(rng, x), tag)] + tagged[i + 1:]
        return None
    raise ValueError(op)


def compound(seed, n=300, cap=200000):
    bench, files, old_files = corpus()
    rng = random.Random(seed + SEED_OFFSET)
    names = sorted(files)
    parse_ok = {}
    for k in KS:
        counts, made = Counter(), 0
        for attempt in range(cap):
            counts['attempted'] += 1
            name = rng.choice(names)
            if name not in parse_ok:
                try:
                    ast.parse(old_files[name])
                    parse_ok[name] = True
                except SyntaxError:
                    parse_ok[name] = False
            if not parse_ok[name]:
                counts['file-unparsable'] += 1
                continue
            lines = files[name]
            got = bench.pick_anchor(rng, lines)
            if got is None:
                counts['sampler-failed'] += 1
                continue
            start, span = got
            if aligned(old_files[name], start, span) is None:
                counts['not-statement-aligned'] += 1
                continue
            ops = rng.sample(OPERATORS, k)
            state = dict(files={name: [(x, ('A', i) if start <= i < start + span else ('O', name, i)) for i, x in enumerate(lines)]},
                         block_path=name, inserted=0)
            reason = None
            for op in ops:
                reason = apply(op, state, rng, bench, files, names)
                if reason:
                    break
            if reason:
                counts['rejected:' + reason] += 1
                continue
            texts = {p: text_of(t) for p, t in state['files'].items()}
            try:
                trees = {p: ast.parse(t) for p, t in texts.items()}
            except SyntaxError:
                counts['rejected:final-unparsable'] += 1
                continue
            final = state['files'][state['block_path']]
            a_rows = [i for i, (_, tag) in enumerate(final) if tag[0] == 'A']
            if not a_rows:
                counts['rejected:anchor-emptied'] += 1
                continue
            fs, fe = a_rows[0], block_rows(final)[1]
            old_dump = [ast.dump(x, include_attributes=False) for x in covered(ast.parse(old_files[name]), start, start + span)]
            new_dump = [ast.dump(x, include_attributes=False) for x in covered(trees[state['block_path']], fs, fe)]
            changed = old_dump != new_dump
            trial = build(name, old_files[name], texts, start, span, (state['block_path'], fs), changed, fe)
            for p in rng.sample(names, k=min(25, len(names))):
                trial['version'].setdefault(p, (digest(old_files[p]), old_files[p]))
            counts['accepted'] += 1
            yield dict(suite='compound', op='k=%d' % k, k=k, operators=sorted(ops), order=ops, index=made, seed=seed), trial, old_files
            made += 1
            if made == n:
                break
        yield dict(generator_audit=True, suite='compound', op='k=%d' % k, seed=seed, counts=dict(counts), requested=n,
                   complete=made == n), None, None
