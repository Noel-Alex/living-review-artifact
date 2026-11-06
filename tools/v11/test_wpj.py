"""Unit checks for WP J (python -I -B tools/v11/test_wpj.py). Synthetic inputs only; no model calls."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpj_core import build_prompt, parse_answer, methods_of  # noqa: E402
from wpi_core import digest  # noqa: E402


def make(old, new, s, e, path='a.py'):
    q = '\n'.join(old.splitlines()[s - 1:e])
    return dict(id='x', population='dev', anchor=dict(path=path, line_start=s, line_end=e, quotation=q, content_hash=digest(old)),
                old_lines=old.splitlines(), version={path: (digest(new), new)}, old_files={path: old}, target=path)


OLD = 'import os\n\ndef f(x):\n    if x:\n        return 1\n    return 2\n'
NEW_SHIFT = '# header\nimport os\n\ndef f(x):\n    if x:\n        return 1\n    return 2\n'
NEW_EDIT = 'import os\n\ndef f(x):\n    if x:\n        return 10\n    return 2\n'
NEW_DEDENT = 'import os\n\ndef f(x):\n    if x:\n        pass\n    return 1\n    return 2\n'


def answer(status, start=None, end=None, changed=False):
    import json
    return dict(status='answered', content='```json\n' + json.dumps(dict(status=status, start=start, end=end, changed=changed)) + '\n```')


def main():
    it = make(OLD, NEW_SHIFT, 5, 5)
    msgs, meta = build_prompt(it)
    assert msgs and '>>     5|         return 1' in msgs[1]['content'] and '     6|         return 1' in msgs[1]['content'], msgs[1]['content']
    # parser
    assert parse_answer('{"status":"found","start":6,"end":6,"changed":false}', it)['valid']
    assert not parse_answer('{"status":"found","start":0,"end":6,"changed":false}', it)['valid']
    assert not parse_answer('{"status":"found","start":6,"end":99,"changed":false}', it)['valid']
    assert not parse_answer('{"status":"found","start":6,"end":6}', it)['valid']
    assert not parse_answer('I think line 6.', it)['valid']
    assert parse_answer('reasoning {"a":1} then {"status":"deleted","start":null,"end":null,"changed":true}', it)['status'] == 'deleted'
    # shifted, unchanged: self and layers agree (moved, no re-check)
    m = methods_of(it, answer('found', 6, 6, False))
    assert m['llm-self']['label'] == 'moved' and not m['llm-self']['recheck']
    assert m['llm+quote']['label'] == 'moved' and not m['llm+IG+AGi']['recheck'], m
    # edited, model says unchanged: self is silent, the quotation layer requests re-check
    it2 = make(OLD, NEW_EDIT, 5, 5)
    m = methods_of(it2, answer('found', 5, 5, False))
    assert m['llm-self']['label'] == 'exact' and not m['llm-self']['recheck']
    assert m['llm+quote']['label'] == 'changed' and m['llm+quote']['recheck']
    # dedented statement (same stripped text): only IG catches it
    it3 = make(OLD, NEW_DEDENT, 5, 5)
    m = methods_of(it3, answer('found', 6, 6, False))
    assert not m['llm+quote']['recheck'] and m['llm+IG']['recheck'] and m['llm+IG+AGi']['recheck'], m
    # deleted, invalid and missing target
    assert methods_of(it, answer('deleted'))['llm+IG+AGi']['label'] == 'removed'
    bad = methods_of(it, dict(status='answered', content='no idea'))
    assert all(v['label'] == 'execution_error' and v['recheck'] for v in bad.values())
    assert methods_of(dict(it, target=None), dict(status='no_target_file'))['llm-self']['label'] == 'removed'
    assert methods_of(it, dict(status='transport_failed'))['llm-self']['label'] == 'execution_error'
    print('test_wpj ok')


if __name__ == '__main__':
    main()
