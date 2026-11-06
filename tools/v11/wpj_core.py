"""WP J pure functions (review/V11-PROTOCOL-J.md): prompt, answer parsing and the safety layers over an LLM window."""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpi_core import window_layers, window_layers_i  # noqa: E402

PROMPT_VERSION = 'wpj-prompt-1'
CONTEXT = 15
MAX_NEW_LINES = 40000
MAX_PROMPT_CHARS = 700_000

SYSTEM = ('You are a precise code-tracking tool. You compare two versions of one source file and report where a marked '
          'region of the old version is in the new version. Answer with a single JSON object and nothing else.')

TASK = '''Task: find the code of the marked region in the NEW VERSION.
- If the region's code still exists in the new version (possibly shifted, moved within the file, edited or partly rewritten), give the first and last new-version line numbers of the corresponding code.
- If that code was deleted from this file, say so.
- Also say whether the region's code was changed: true if its text differs in anything other than leading or trailing whitespace on a line, or blank lines; false if it is the same text, even if it moved.

Answer with exactly one JSON object and no other text:
{"status": "found" or "deleted", "start": <integer or null>, "end": <integer or null>, "changed": <true or false>}'''


def numbered(lines, first=1, marked=None):
    out = []
    for i, line in enumerate(lines, start=first):
        mark = '>>' if marked and marked[0] <= i <= marked[1] else '  '
        out.append(f'{mark}{i:>6}| {line}' if marked else f'{i:>6}| {line}')
    return '\n'.join(out)


def build_prompt(it):
    a = it['anchor']
    s, e = a['line_start'], a['line_end']
    old = it['old_lines']
    lo, hi = max(1, s - CONTEXT), min(len(old), e + CONTEXT)
    new = it['version'][it['target']][1].splitlines()
    meta = dict(new_lines=len(new))
    if len(new) > MAX_NEW_LINES:
        return None, meta
    rename = '' if it['target'] == a['path'] else f' (the file was renamed to {it["target"]})'
    user = (f'File: {a["path"]}\n\n'
            f'OLD VERSION (excerpt, lines {lo}-{hi}). The marked region is lines {s}-{e}; its lines start with ">>". '
            'Line numbers are old-version line numbers.\n'
            f'```\n{numbered(old[lo - 1:hi], lo, (s, e))}\n```\n\n'
            f'NEW VERSION (complete file{rename}). Line numbers are new-version line numbers.\n'
            f'```\n{numbered(new)}\n```\n\n{TASK}')
    messages = [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}]
    text = SYSTEM + '\n' + user
    meta.update(prompt_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(), prompt_chars=len(text))
    if len(text) > MAX_PROMPT_CHARS:
        return None, meta
    return messages, meta


def parse_answer(content, it):
    """Strict parse: the last JSON object with a status key. Invalid answers are execution errors, never re-asked."""
    if not content:
        return dict(valid=False, error='empty answer')
    text = re.sub(r'```(?:json)?', '', content)
    found = None
    for m in re.finditer(r'\{[^{}]*\}', text, flags=re.S):
        try:
            obj = json.loads(m.group(0))
        except ValueError:
            continue
        if isinstance(obj, dict) and 'status' in obj:
            found = obj
    if found is None:
        return dict(valid=False, error='no JSON object with status')
    status, start, end, changed = found.get('status'), found.get('start'), found.get('end'), found.get('changed')
    if status == 'deleted':
        return dict(valid=True, status='deleted', start=None, end=None, changed=True)
    n = len(it['version'][it['target']][1].splitlines())
    if status != 'found' or not isinstance(changed, bool):
        return dict(valid=False, error=f'bad status/changed: {status!r} {changed!r}')
    if not (isinstance(start, int) and isinstance(end, int) and 1 <= start <= end <= n):
        return dict(valid=False, error=f'bad lines: {start!r}-{end!r} of {n}')
    return dict(valid=True, status='found', start=start, end=end, changed=changed)


def methods_of(it, r):
    """Outputs for llm-self (the model's own change judgement) and the transferable safety layers."""
    names = ('llm-self', 'llm+quote', 'llm+IG', 'llm+AGi', 'llm+IG+AGi')
    a = it['anchor']
    if r['status'] == 'no_target_file':
        gone = dict(label='removed', placement=None, range=None, recheck=True, reasons=['no-target-file'])
        return {n: dict(gone) for n in names}
    if r['status'] != 'answered':
        err = dict(label='execution_error', placement=None, range=None, recheck=True, error=r['status'])
        return {n: dict(err) for n in names}
    p = parse_answer(r.get('content'), it)
    if not p['valid']:
        err = dict(label='execution_error', placement=None, range=None, recheck=True, error='invalid answer: ' + p['error'])
        return {n: dict(err) for n in names}
    if p['status'] == 'deleted':
        gone = dict(label='removed', placement=None, range=None, recheck=True, reasons=[])
        return {n: dict(gone) for n in names}
    target, start, end = it['target'], p['start'], p['end']
    same_place = target == a['path'] and start == a['line_start']
    self_label = 'changed' if p['changed'] else ('exact' if same_place else 'moved')
    out = dict(label=self_label, placement=[target, start], range=[target, start, end], recheck=p['changed'], reasons=[])
    t = dict(anchor=a, old_lines=it['old_lines'], version=it['version'])
    base = window_layers(t, it['old_files'], out, ('quote', 'IG'))
    agi = window_layers_i(t, it['old_files'], out)
    return {'llm-self': out, 'llm+quote': base['quote'], 'llm+IG': base['IG'], 'llm+AGi': agi['AGi'], 'llm+IG+AGi': agi['IG+AGi']}
