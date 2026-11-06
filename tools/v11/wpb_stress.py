"""Construction-labelled B1a/B1b inputs, using the original corpus and sampler."""
import ast
from collections import Counter
import hashlib
import io
import random
import re
import tokenize
from functools import lru_cache
from wpa_core import loaders, CORPUS

SEMANTIC = ('dedent-out', 'absorb', 'inner-relative', 'nest-shift')
LAYOUT = ('continuation', 'blank-lines', 'trailing-space', 'tabs-spaces')
DUPLICATIONS = ('near-above', 'far-above', 'near-below', 'far-below', 'other-file')
FATES = ('unchanged', 'token-edit', 'deleted', 'move-far', 'move-file')
TOKEN_BINS = ('1-3', '4-6', '7+')
FREQUENCIES = ('1', '2-3', '4+')


def digest(s):
    return hashlib.sha256(s.encode()).hexdigest()


def corpus():
    _, bench = loaders()
    bench.ROOTS = [CORPUS/'vcap/app', CORPUS/'partners/cdc-trace/cdc']
    files = bench.corpus()
    return bench, files, {p:'\n'.join(lines)+'\n' for p,lines in files.items()}


def build(name, old, changed_files, start, span, truth, changed, end=None):
    version = {p:(digest(t), t) for p,t in changed_files.items()}
    return dict(anchor=dict(path=name, line_start=start+1, line_end=start+span,
                            content_hash=digest(old), quotation='\n'.join(old.splitlines()[start:start+span])),
                old_lines=old.splitlines(), version=version, truth=truth, changed=changed,
                truth_end=end)


@lru_cache(maxsize=256)
def parsed(text):
    return ast.parse(text)


def scope_dump(text, start, end):
    tree = parsed(text)
    functions = [n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
                 and n.lineno <= start and n.end_lineno >= end]
    n = min(functions, key=lambda n:n.end_lineno-n.lineno) if functions else tree
    return ast.dump(n, include_attributes=False)


def indent(line):
    return len(line.expandtabs(8))-len(line.expandtabs(8).lstrip())


def shift(line, amount):
    return ' '*max(0,indent(line)+amount)+line.lstrip() if line.strip() else line


@lru_cache(maxsize=256)
def lexical(text):
    multiline, continuation = set(), set()
    depth = 0
    for t in tokenize.generate_tokens(io.StringIO(text).readline):
        if t.type == tokenize.STRING and t.end[0] > t.start[0]:
            multiline.update(range(t.start[0]-1,t.end[0]))
        if depth and t.type not in (tokenize.INDENT,tokenize.DEDENT,tokenize.NL,tokenize.NEWLINE):
            continuation.add(t.start[0]-1)
        if t.type == tokenize.OP:
            depth += int(t.string in '([{')-int(t.string in ')]}')
    return multiline, continuation


def indentation_edit(op, lines, start, span, rng):
    text = '\n'.join(lines)+'\n'
    multiline, continuation = lexical(text)
    indices = [i for i in range(start,start+span) if lines[i].strip()]
    if any(i in multiline for i in indices):
        return None, 'multiline-string'
    new, delta = list(lines), 0
    if op in ('dedent-out','absorb','nest-shift'):
        if op == 'nest-shift':
            nodes = [n for n in ast.walk(parsed(text)) if isinstance(n,(ast.If,ast.For,ast.While,ast.With,ast.Try,ast.AsyncFor,ast.AsyncWith))
                     and n.lineno == start+1 and n.end_lineno <= start+span]
            if not nodes:
                return None, 'not-complete-block-with-header'
        amount = -4 if op=='dedent-out' else 4 if op=='absorb' else rng.choice((-4,4))
        if amount<0 and any(indent(lines[i])<4 for i in indices):
            return None, 'insufficient-indent'
        for i in indices:
            new[i] = shift(new[i],amount)
    elif op == 'inner-relative':
        eligible = [i for i in indices if i>start]
        if not eligible:
            return None, 'single-nonblank-line'
        i = rng.choice(eligible)
        amount = rng.choice((-4,4))
        if amount<0 and indent(new[i])<4:
            return None, 'insufficient-indent'
        new[i] = shift(new[i],amount)
    elif op == 'continuation':
        eligible = [i for i in indices if i>start and i in continuation]
        if not eligible:
            return None, 'no-bracket-continuation'
        i = rng.choice(eligible)
        new[i] = shift(new[i],rng.choice((2,6)))
    elif op == 'blank-lines':
        blank = [i for i in range(start+1,start+span) if not lines[i].strip()]
        if blank and rng.random()<.5:
            del new[rng.choice(blank)]
            delta = -1
        else:
            new.insert(rng.randint(start+1,start+span), '')
            delta = 1
    elif op == 'trailing-space':
        new[rng.choice(indices)] += '   '
    elif op == 'tabs-spaces':
        eligible = [i for i in indices if indent(lines[i])>=8]
        if not eligible:
            return None, 'no-tab-width-indent'
        for i in eligible:
            w = indent(lines[i])
            new[i] = '\t'*(w//8)+' '*(w%8)+lines[i].lstrip()
        if new == lines:
            return None, 'already-tabbed'
    return (new,delta), None


def b1a(seed, n=300):
    bench, files, old_files = corpus()
    rng = random.Random(seed)
    names = sorted(files)
    for op in SEMANTIC+LAYOUT:
        counts, made, seen = Counter(), 0, set()
        for attempt in range(200000):
            name = rng.choice(names)
            lines = files[name]
            got = bench.pick_anchor(rng,lines)
            counts['attempted'] += 1
            if got is None:
                counts['sampler-failed'] += 1
                continue
            start,span = got
            old = old_files[name]
            try:
                parsed(old)
                edited, reason = indentation_edit(op,lines,start,span,rng)
                if edited is None:
                    counts[reason] += 1
                    continue
                new, delta = edited
                new_text = '\n'.join(new)+'\n'
                parsed(new_text)
            except (SyntaxError,IndentationError,tokenize.TokenError) as exc:
                counts['parse-failed:'+type(exc).__name__] += 1
                continue
            normalized = lambda xs:[x.strip() for x in xs if x.strip()]
            assert normalized(lines[start:start+span]) == normalized(new[start:start+span+delta])
            # Same enclosing function by its original header, or module if the anchor spans scopes.
            changed = scope_dump(old,start+1,start+span) != scope_dump(new_text,start+1,start+span+delta)
            whole_changed = ast.dump(parsed(old)) != ast.dump(parsed(new_text))
            if changed != (op in SEMANTIC) or whole_changed != changed:
                counts['wrong-AST-class'] += 1
                continue
            counts['accepted'] += 1
            seen.add((name,start,span,digest(new_text)))
            trial = build(name,old,{name:new_text},start,span,(name,start),changed,start+span+delta)
            # Match original benchmark's up-to-25 unrelated-file availability.
            for p in rng.sample(names,k=min(25,len(names))):
                trial['version'].setdefault(p,(digest(old_files[p]),old_files[p]))
            yield dict(suite='indentation', op=op, index=made, seed=seed, ast_changed=changed), trial, old_files
            made += 1
            if made == n:
                break
        yield dict(generator_audit=True,suite='indentation',op=op,seed=seed,
                   counts=dict(counts),unique_accepted=len(seen),requested=n,complete=made==n),None,None


def duplicate_trial(rng, bench, files, old_files, copy_position, fate):
    names = sorted(files)
    name = rng.choice(names)
    old,lines = old_files[name],files[name]
    got = bench.pick_anchor(rng,lines)
    if not got:
        return None
    start,span = got
    block = lines[start:start+span]
    tagged = [(s,('original',i) if start<=i<start+span else ('other',i)) for i,s in enumerate(lines)]
    other = rng.choice([p for p in names if p!=name])
    changed_files = {name:tagged}
    if copy_position=='other-file':
        dest = [(s,('otherfile',i)) for i,s in enumerate(files[other])]
        at = rng.randrange(len(dest)+1)
        dest[at:at] = [(s,('copy',i)) for i,s in enumerate(block)]
        changed_files[other] = dest
    else:
        if copy_position=='far-above':
            if start<40:return None
            at = rng.randint(0,start-40)
        elif copy_position=='near-above':at=start-rng.randint(0,10-span)
        elif copy_position=='near-below':at=start+span+rng.randint(0,10-span)
        else:
            if len(lines)-start-span<40:return None
            at=rng.randint(start+span+40,len(lines))
        tagged[at:at] = [(s,('copy',i)) for i,s in enumerate(block)]
    original_before=next(i for i,(_,tag) in enumerate(tagged) if tag[0]=='original')
    copy_path=other if copy_position=='other-file' else name
    copy_before=next(i for i,(_,tag) in enumerate(changed_files[copy_path]) if tag[0]=='copy')
    if copy_position.startswith('near'):
        assert abs(copy_before-original_before)<=10
    if copy_position.startswith('far'):
        assert abs(copy_before-original_before)>=40
    indices = [i for i,(_,tag) in enumerate(tagged) if tag[0]=='original']
    original = tagged[indices[0]:indices[-1]+1]
    target = name
    if fate=='token-edit':
        i=rng.choice([i for i in indices if tagged[i][0].strip()])
        tagged[i]=(bench.mutate_token(rng,tagged[i][0]),tagged[i][1])
    elif fate in ('deleted','move-far','move-file'):
        first=indices[0]
        del tagged[indices[0]:indices[-1]+1]
        if fate=='move-far':
            choices=[i for i in range(len(tagged)+1) if abs(i-first)>=40]
            if not choices:return None
            at=rng.choice(choices)
            tagged[at:at]=original
        elif fate=='move-file':
            target=rng.choice([p for p in names if p not in (name,other)])
            dest=[(s,('dest',i)) for i,s in enumerate(files[target])]
            at=rng.randrange(len(dest)+1)
            dest[at:at]=original
            changed_files[target]=dest
    truth=None if fate=='deleted' else (target,next(i for i,(_,tag) in enumerate(changed_files[target]) if tag[0]=='original'))
    texts={p:'\n'.join(s for s,_ in v)+'\n' for p,v in changed_files.items()}
    t=build(name,old,texts,start,span,truth,fate in ('token-edit','deleted'),None if truth is None else truth[1]+span)
    t['duplicate_construction']=dict(copy_before_fate=[copy_path,copy_before+1],original_before_fate=[name,original_before+1])
    for p in rng.sample(names,k=min(25,len(names))):
        t['version'].setdefault(p,(digest(old_files[p]),old_files[p]))
    return t


def duplicates(seed,n=150):
    bench,files,old_files=corpus()
    rng=random.Random(seed+101)
    for position in DUPLICATIONS:
        for fate in FATES:
            made,attempts=0,0
            while made<n and attempts<10000:
                attempts+=1
                t=duplicate_trial(rng,bench,files,old_files,position,fate)
                if t is None:continue
                yield dict(suite='duplicates',op=position+'/'+fate,index=made,seed=seed),t,old_files
                made+=1
            yield dict(generator_audit=True,suite='duplicates',op=position+'/'+fate,seed=seed,
                       requested=n,complete=made==n,counts={'attempted':attempts,'accepted':made,'rejected':attempts-made}),None,None


def short_bank(files):
    bank={(f,t):{} for f in FREQUENCIES for t in TOKEN_BINS}
    for p,lines in files.items():
        counts=Counter(s.strip() for s in lines if s.strip())
        for i,s in enumerate(lines):
            if not s.strip() or s.lstrip().startswith('#'):continue
            k=counts[s.strip()]
            freq='1' if k==1 else '2-3' if k<=3 else '4+'
            # Lexical word/punctuation tokens; indentation is excluded.
            tokens=len(re.findall(r'\w+|[^\s\w]',s.strip()))
            tb='1-3' if tokens<=3 else '4-6' if tokens<=6 else '7+'
            bank[freq,tb].setdefault(p,[]).append(i)
    return bank


class FirstChoice:
    def __init__(self,rng,name):self.rng,self.name,self.first=rng,name,True
    def choice(self,values):
        if self.first:self.first=False;return self.name
        return self.rng.choice(values)
    def __getattr__(self,name):return getattr(self.rng,name)


def short(seed,n=150):
    bench,files,old_files=corpus()
    bank=short_bank(files)
    rng=random.Random(seed+202)
    original_pick=bench.pick_anchor
    try:
        for (freq,tb),byfile in bank.items():
            for op in bench.OPS:
                made,attempts=0,0
                while made<n and byfile and attempts<10000:
                    attempts+=1
                    p=rng.choice(sorted(byfile))
                    start=rng.choice(byfile[p])
                    # Original operators require these bounds for insert/delete-above.
                    if start<20 or start>=len(files[p])-11:continue
                    bench.pick_anchor=lambda _rng,_lines:(start,1)
                    t=bench.make_trial(FirstChoice(rng,p),files,sorted(files),op)
                    if t is None:continue
                    t['truth_end']=None if t['truth'] is None else t['truth'][1]+1
                    yield dict(suite='short',op=op,frequency=freq,tokens=tb,index=made,seed=seed),t,old_files
                    made+=1
                yield dict(generator_audit=True,suite='short',op=op,frequency=freq,tokens=tb,seed=seed,
                           requested=n,complete=made==n,counts={'attempted':attempts,'accepted':made,'rejected':attempts-made}),None,None
    finally:
        bench.pick_anchor=original_pick
