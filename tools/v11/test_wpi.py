"""Hand-built AG2 and identity-rule cases (no evaluation data). Run before the WP I freeze."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpi_core import cascade2, window_layers, identity_hop, digest  # noqa: E402
from wpb_variants import relocate  # noqa: E402

BODY = ['def f(x):', '    y = x + 1', '    return y', '', 'def g():', '    pass', '']
A = ['    total = compute(a, b)', '    log(total)']


def trial(old, new, start, other_old=None, other_new=None):
    old_text, new_text = '\n'.join(old) + '\n', '\n'.join(new) + '\n'
    version = {'m.py': (digest(new_text), new_text)}
    old_files = {'m.py': old_text}
    if other_new is not None:
        version['q.py'] = (digest(other_new), other_new)
    if other_old is not None:
        old_files['q.py'] = other_old
    anchor = dict(path='m.py', line_start=start, line_end=start + len(A) - 1, quotation='\n'.join(A),
                  content_hash=digest(old_text))
    return dict(anchor=anchor, version=version, old_lines=old), old_files


def locator(path, start):
    return dict(label='exact', placement=[path, start], range=[path, start, start + len(A) - 1], recheck=False)


def check(name, got, want):
    assert got == want, (name, got, want)
    print('ok', name, got)


def main():
    old = BODY[:2] + A + BODY[2:]
    # 1. Pure insertion directly above an unmoved anchor (the B2 defect).
    new = BODY[:2] + ['    z = 3', '    w = 4'] + A + BODY[2:]
    t, of = trial(old, new, 3)
    check('insert-above AG (frozen)', relocate(t, of, ag=True)['recheck'], True)
    check('insert-above AG2 cascade', cascade2(t, of)['t0.85-AG2']['recheck'], False)
    check('insert-above AG2 layer', window_layers(t, of, locator('m.py', 5))['AG2']['recheck'], False)
    # 2. Single-copy move within the file.
    new = BODY[:2] + BODY[2:] + ['def h():'] + A
    t, of = trial(old, new, 3)
    at = new.index(A[0]) + 1
    check('move-within AG layer', window_layers(t, of, locator('m.py', at))['AG']['recheck'], True)
    check('move-within AG2 layer', window_layers(t, of, locator('m.py', at))['AG2']['recheck'], False)
    # 3. Anchor deleted while a pre-existing identical copy remains.
    old3 = BODY[:2] + A + BODY[2:] + ['def k():'] + A
    new3 = BODY[:2] + BODY[2:] + ['def k():'] + A
    t, of = trial(old3, new3, 3)
    got = window_layers(t, of, locator('m.py', new3.index(A[0]) + 1))['AG2']
    check('deleted-with-copy AG2', (got['recheck'], got['reasons']), (True, ['copy-count-decreased']))
    # 4. Anchor unchanged; a new duplicate is added above it and returned by the locator.
    new4 = BODY[:1] + A + BODY[1:2] + A + BODY[2:]
    t, of = trial(old, new4, 3)
    got = window_layers(t, of, locator('m.py', 2))['AG2']
    check('duplicate-added AG2', (got['recheck'], got['reasons']), (True, ['duplicate-added']))
    got = window_layers(t, of, locator('m.py', 5))['AG2']
    check('original-after-duplicate AG2', got['recheck'], False)
    # 5. Anchor removed from m.py; q.py already held an identical copy.
    q_old = 'import os\n' + '\n'.join(A) + '\n'
    t, of = trial(old, BODY, 3, other_old=q_old, other_new=q_old)
    got = window_layers(t, of, locator('q.py', 2))['AG2']
    check('cross-file pre-existing AG2', (got['recheck'], got['reasons']), (True, ['pre-existing-copy']))
    # 6. Genuine move to q.py, which had no copy.
    t, of = trial(old, BODY, 3, other_old='import os\n', other_new='import os\n' + '\n'.join(A) + '\n')
    check('cross-file move AG2', window_layers(t, of, locator('q.py', 2))['AG2']['recheck'], False)
    check('cross-file move AG2 cascade', cascade2(t, of)['t0.85-AG2']['recheck'], False)
    # 7. Re-indentation still requested by IG with AG2.
    new7 = BODY[:2] + ['        ' + x.strip() for x in A] + BODY[2:]
    t, of = trial(old, new7, 3)
    check('reindent IG+AG2', window_layers(t, of, locator('m.py', 3))['IG+AG2']['recheck'], True)
    # Identity rule.
    q0 = '\n'.join(A)
    check('identity exact', identity_hop(q0, q0, 'exact', False)[:2], (True, False))
    check('identity drift bound', identity_hop(q0, 'print("hello world")', 'changed', True)[:2], (False, True))
    check('identity reviewed-text request', identity_hop(q0, '    total = compute(a, c)\n    log(total)', 'exact', False)[:2],
          (True, True))
    # Amendment 4: AGi accepts the insertion case and keeps AG's flag on in-file moves.
    from wpi_core import window_layers_i, cascade_i
    new = BODY[:2] + ['    z = 3', '    w = 4'] + A + BODY[2:]
    t, of = trial(old, new, 3)
    check('insert-above AGi layer', window_layers_i(t, of, locator('m.py', 5))['AGi']['recheck'], False)
    check('insert-above AGi cascade', cascade_i(t, of)['t0.85-AGi']['recheck'], False)
    new = BODY[:2] + BODY[2:] + ['def h():'] + A
    t, of = trial(old, new, 3)
    check('move-within AGi layer', window_layers_i(t, of, locator('m.py', new.index(A[0]) + 1))['AGi']['recheck'], True)
    t, of = trial(old3, new3, 3)
    check('deleted-with-copy AGi', window_layers_i(t, of, locator('m.py', new3.index(A[0]) + 1))['AGi']['recheck'], True)
    print('all WP I hand-built cases pass')


if __name__ == '__main__':
    main()
