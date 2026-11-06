"""Instrument original selection without changing RNG draws or oracle decisions."""
import ast
from collections import Counter
import random
import re
import warnings

from wpa_core import *
from history_context import open_histories
from regenerate_history_selection import harness


def diff_stats(text, start, end):
    hunks = []
    added = deleted = 0
    for line in text.splitlines():
        match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
        if match:
            a, n, b, m = match.groups()
            hunks.append([int(a)-1, int(n or 1), int(b)-1, int(m or 1)])
        elif line.startswith('+') and not line.startswith('+++'):
            added += 1
        elif line.startswith('-') and not line.startswith('---'):
            deleted += 1
    touched = [h for h in hunks if start < h[0]+max(1,h[1]) and h[0] < end]
    size = added+deleted
    return {'added': added, 'deleted': deleted, 'diff_size': size,
            'diff_bin': '0' if size == 0 else '1-10' if size <= 10 else '11-50' if size <= 50 else '51-200' if size <= 200 else '>200',
            'hunks': len(hunks), 'max_hunk_size': max((h[1]+h[3] for h in hunks), default=0),
            'overlapping_hunks': len(touched), 'overlapping_hunk_size': sum(h[1]+h[3] for h in touched)}


def main():
    original, source_hash = harness()
    tree = ast.parse((SOURCE / 'real_history.py').read_text(encoding='utf-8'))
    run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_repo')
    sample_loop = run.body[-2].body[1].body[-1]
    first = next(i for i,n in enumerate(sample_loop.body) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "row['label']")
    sample_loop.body = sample_loop.body[:first] + [sample_loop.body[-1]]

    class Capture(ast.NodeTransformer):
        def visit_AugAssign(self, node):
            if isinstance(node.target, ast.Subscript) and ast.unparse(node.target.value) == 'excluded':
                reason = node.target.slice
                call = ast.Expr(ast.Call(ast.Name('capture', ast.Load()),
                    [ast.Constant('excluded'), reason, ast.Call(ast.Name('locals', ast.Load()), [], [])], []))
                return [call, node]
            return node

        def visit_Expr(self, node):
            if ast.unparse(node) == 'rows.append(row)':
                call = ast.Expr(ast.Call(ast.Name('capture', ast.Load()),
                    [ast.Constant('retained'), ast.Constant(None), ast.Call(ast.Name('locals', ast.Load()), [], [])], []))
                return [call, node]
            return node

    run = Capture().visit(run)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[run], type_ignores=[])), 'instrumented_original_selection', 'exec'), original.__dict__)
    histories = open_histories()
    saved = {g: read(SOURCE/f) for g,f in [('own','results-real-v1.json'),('oss','results-oss-v1.json')]}
    order = list(saved['own']['meta']['repos']) + list(saved['oss']['meta']['repos'])
    own_rng, reports, attempts = random.Random(original.SEED), {}, []
    base_repo = original.Repo
    try:
        for name in order:
            history = histories[name]
            group = 'own' if name in saved['own']['meta']['repos'] else 'oss'
            diffs, instances, project_attempts = {}, [], []

            class PinnedRepo(base_repo):
                def __init__(self, path):
                    super().__init__(path)
                    instances.append(self)

                def git(self, *args):
                    result = super().git(*(history.head if a == 'HEAD' else a for a in args))
                    if args[:2] == ('diff','-U0'):
                        diffs[(args[3],args[4],args[6])] = result
                    return result

            def capture(status, reason, local):
                p = local
                record = {k: p[k] for k in ('sample','path','old_c','new_c')}
                record.update(repo=name, group=group, status=status, reason=reason,
                    horizon=p['k'], pair=f"{name}:{p['k']}:{p['i']}", anchor_at=[p['path'],p['s']+1], span=p['e']-p['s'])
                record.update(diff_stats(diffs[(p['old_c'],p['new_c'],p['path'])], p['s'],p['e']))
                project_attempts.append(record)

            original.Repo, original.capture = PinnedRepo, capture
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', SyntaxWarning)
                    rows, excluded, count = original.run_repo(str(history.path), name,
                        own_rng if group == 'own' else random.Random(original.SEED))
            finally:
                for repo in instances:
                    repo.cat.stdin.close()
                    repo.cat.wait(timeout=15)
            expected = [r for r in saved[group]['rows'] if r['repo'] == name]
            projection = [{k:r[k] for k in rows[0]} for r in expected]
            assert rows == projection, name
            assert dict(excluded) == saved[group]['excluded'][name], name
            assert sum(p['status']=='retained' for p in project_attempts) == len(rows)
            assert sum(p['status']=='excluded' for p in project_attempts) == sum(excluded.values())
            reports[name] = dict(passed=True, retained=len(rows), excluded=dict(excluded), head=history.head)
            attempts.extend(project_attempts)
            write(f'exclusions-{name}.json', project_attempts)
            print('Exclusion regeneration gate:',name,len(rows),sum(excluded.values()),flush=True)
    finally:
        for history in histories.values():
            history.close()
    write('exclusion-gate.json', {'passed': True,'projects':reports,'source_sha256':source_hash})
    write('attempted-observations.json', attempts)


if __name__ == '__main__':
    main()
