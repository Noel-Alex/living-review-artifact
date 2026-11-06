"""WP K6a: mine GitHub review suggestions and label each with the dual-anchor oracle.

Rules: review/briefs/WPK6-decisions.md (D1-D5), protocol review/V12-PROTOCOL-K6.md.
Run from paper-drafts/:  python -I -B tools/v11/wpk6_mine.py [--languages Python,Go] [--max-candidates 12]
Resumable: raw API responses are cached under evidence/v12-wpk6/raw/, file texts under evidence/v12-wpk6/blobs/.
The GitHub token is read from `gh auth token` at run time and never written anywhere.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/v12-wpk6'
RAW, BLOBS = OUT / 'raw', OUT / 'blobs'
LANGUAGES = ('Python', 'TypeScript', 'Go', 'Rust', 'Java')
LICENCES = {'MIT', 'Apache-2.0', 'BSD-2-Clause', 'BSD-3-Clause', 'ISC', 'MPL-2.0'}
WINDOW = ('2024-01-01', '2026-06-30')
SCAN_PRS, MIN_UNITS, CAP, PER_LANG, SEED = 400, 40, 250, 2, '20261031'
MAX_BYTES = 1_000_000
CODE_EXT = {'.py', '.pyi', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.go', '.rs', '.java', '.kt', '.kts', '.scala',
            '.c', '.h', '.cc', '.cpp', '.cxx', '.hpp', '.cs', '.rb', '.php', '.swift', '.sh', '.vue', '.svelte'}
FENCE = re.compile(r'```suggestion[^\n]*\n(.*?)```', re.S)
import threading
FS = threading.RLock()  # serialises cache reads and writes (Windows refuses replace-while-open)
TOKEN = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True).stdout.strip()

PRQ = """query($q:String!,$cursor:String){rateLimit{remaining resetAt}
search(query:$q,type:ISSUE,first:20,after:$cursor){pageInfo{hasNextPage endCursor}
nodes{... on PullRequest{number mergedAt headRefOid
commits(last:100){nodes{commit{oid messageHeadline}}}
reviewThreads(first:60){nodes{id isOutdated line startLine originalLine originalStartLine diffSide path
comments(first:1){nodes{databaseId body originalCommit{oid} createdAt}}}}}}}}"""


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def _http(url, data=None, accept='application/vnd.github+json'):
    delay = 5
    for attempt in range(10):
        req = urllib.request.Request(url, data=data, headers={'Authorization': f'bearer {TOKEN}', 'Accept': accept,
                                                              'User-Agent': 'vcap-paper-k6'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            if e.code == 404:
                return 404, body
            if e.code in (403, 429, 502, 503, 504):
                reset = e.headers.get('x-ratelimit-reset')
                wait = max(5, int(reset) - int(time.time()) + 2) if (reset and e.headers.get('x-ratelimit-remaining') == '0') else delay
                log('wait', e.code, min(wait, 900), url[:90])
                time.sleep(min(wait, 900))
                delay = min(300, delay * 2)
                continue
            return e.code, body
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            log('transport', e, url[:90])
            time.sleep(delay)
            delay = min(300, delay * 2)
    raise RuntimeError(f'gave up: {url}')


def cached(name, fetch):
    p = RAW / name
    with FS:
        if p.exists():
            return json.loads(p.read_text(encoding='utf-8'))
    obj = fetch()
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic(p, json.dumps(obj, sort_keys=True))
    return obj


def graphql(query, variables):
    for attempt in range(8):
        code, body = _http('https://api.github.com/graphql', json.dumps({'query': query, 'variables': variables}).encode())
        obj = json.loads(body) if body else {}
        if code == 200 and not obj.get('errors'):
            rl = obj['data'].get('rateLimit') or {}
            if rl.get('remaining', 9999) < 200:
                log('graphql budget low; sleeping to reset', rl)
                time.sleep(max(60, min(3600, int(time.mktime(time.strptime(rl['resetAt'], '%Y-%m-%dT%H:%M:%SZ'))) - int(time.time()) + 30)))
            return obj['data']
        log('graphql retry', code, str(obj.get('errors') or body)[:300])
        time.sleep(30 * (attempt + 1))
    raise RuntimeError('graphql failed')


def rest(path):
    code, body = _http('https://api.github.com/' + path)
    return code, (json.loads(body) if code == 200 else None)


# ---------------------------------------------------------------- normalization and oracle (D4, D5)
def norm(text):
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def occurrences(lines_norm_index, needle):
    """Start indices (into the normalized line list) of contiguous runs equal to needle."""
    hay = [t for t, _ in lines_norm_index]
    k = len(needle)
    return [i for i in range(len(hay) - k + 1) if hay[i:i + k] == needle] if k else []


def norm_index(text):
    """Normalized lines with their 1-based source line numbers."""
    return [(ln.strip(), i + 1) for i, ln in enumerate(text.splitlines()) if ln.strip()]


def span(idx, start, k):
    return idx[start][1], idx[start + k - 1][1]


def oracle(o_text, s_text, c1_text, status):
    """Return (class, truth (start,end) or None). status: 'M' kept/modified, 'R' renamed, 'D' deleted."""
    if status == 'D' or c1_text is None:
        return 'gone-file', None
    o, s = norm(o_text), norm(s_text)
    idx = norm_index(c1_text)
    oo = occurrences(idx, o)
    if not s:
        if not oo:
            return 'applied-deletion', None
        return ('untouched', span(idx, oo[0], len(o))) if len(oo) == 1 else ('ambiguous', None)
    ss = occurrences(idx, s)
    contained = any(s[i:i + len(o)] == o for i in range(len(s) - len(o) + 1))
    if contained and ss:
        inside = set()
        for j in ss:
            for i in oo:
                if j <= i and i + len(o) <= j + len(s):
                    inside.add(i)
        oo = [i for i in oo if i not in inside]
        if len(ss) == 1 and not oo:
            return 'applied', span(idx, ss[0], len(s))
        if len(ss) > 1:
            return 'ambiguous', None
    if len(ss) == 1 and not oo:
        return 'applied', span(idx, ss[0], len(s))
    if len(oo) == 1 and not ss:
        return 'untouched', span(idx, oo[0], len(o))
    if not ss and not oo:
        return 'rewritten', None
    return 'ambiguous', None


# ---------------------------------------------------------------- objects
def read_exact(path):
    with open(path, encoding='utf-8', newline='') as f:
        return f.read()


def atomic(path, text):
    with FS:
        _atomic(path, text)


def _atomic(path, text):
    import os
    tmp = path.with_name(path.name + f'.{os.getpid()}.{threading.get_ident()}.tmp')
    tmp.write_text(text, encoding='utf-8', newline='')
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows: target open by a reader; the content is identical by construction
            if path.exists() and read_exact(path) == text:
                tmp.unlink(missing_ok=True)
                return
            time.sleep(0.2)
    raise RuntimeError(f'could not write {path}')


def blob(owner, name, sha, path):
    """File text at commit sha, cached by content hash; returns (text|None, reason)."""
    key = hashlib.sha256(f'{owner}/{name}@{sha}:{path}'.encode()).hexdigest()
    ref = BLOBS / 'index' / key[:2] / (key + '.json')
    with FS:
        if ref.exists():
            try:
                r = json.loads(ref.read_text(encoding='utf-8'))
                return (read_exact(BLOBS / r['sha256'][:2] / r['sha256']) if r['sha256'] else None), r['reason']
            except (ValueError, OSError):
                pass  # partial write by an earlier run: refetch
    url = f'https://raw.githubusercontent.com/{owner}/{name}/{sha}/' + urllib.parse.quote(path)
    code, body = _http(url, accept='*/*')
    text, reason = None, 'ok'
    if code != 200:
        reason = f'http {code}'
    elif len(body) > MAX_BYTES:
        reason = 'over 1 MB'
    elif b'\x00' in body[:8000]:
        reason = 'binary'
    else:
        try:
            text = body.decode('utf-8')
        except UnicodeDecodeError:
            reason = 'not utf-8'
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest() if text is not None else None
    if digest:
        p = BLOBS / digest[:2] / digest
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            atomic(p, text)
    ref.parent.mkdir(parents=True, exist_ok=True)
    atomic(ref, json.dumps({'sha256': digest, 'reason': reason}))
    return text, reason


def path_at_c1(owner, name, c0, c1, path):
    """D4 rename rule via the compare API (GitHub detects renames by similarity). Returns (status, new_path)."""
    data = cached(f'{owner}__{name}/compare/{c0[:12]}-{c1[:12]}.json',
                  lambda: (lambda r: {'code': r[0], 'files': [{k: f.get(k) for k in ('filename', 'previous_filename', 'status')}
                                                                for f in (r[1] or {}).get('files', [])],
                                      'truncated': len((r[1] or {}).get('files', [])) >= 300})(rest(f'repos/{owner}/{name}/compare/{c0}...{c1}')))
    if data['code'] != 200:
        return 'unknown', path
    for f in data['files']:
        if f['status'] == 'renamed' and f['previous_filename'] == path:
            return 'R', f['filename']
        if f['filename'] == path and f['status'] == 'removed':
            return 'D', None
    return 'M', path


# ---------------------------------------------------------------- selection (D1) and units (D2)
def scan_repo(full):
    owner, name = full.split('/')
    q = f'repo:{full} is:pr is:merged merged:{WINDOW[0]}..{WINDOW[1]} sort:updated-desc'
    prs, cursor, page = [], None, 0
    while len(prs) < SCAN_PRS:
        data = cached(f'{owner}__{name}/prs-{page:03d}.json', lambda: graphql(PRQ, {'q': q, 'cursor': cursor}))
        prs += [n for n in data['search']['nodes'] if n]
        page += 1
        if not data['search']['pageInfo']['hasNextPage']:
            break
        cursor = data['search']['pageInfo']['endCursor']
    units, excl = [], {}
    for pr in prs[:SCAN_PRS]:
        applied_commit = any((c['commit']['messageHeadline'] or '').lower().startswith('apply suggestion')
                             for c in pr['commits']['nodes'])
        for th in pr['reviewThreads']['nodes']:
            cs = th['comments']['nodes']
            if not cs:
                continue
            c = cs[0]
            body = c['body'] or ''
            fences = FENCE.findall(body)
            if '```suggestion' not in body:
                continue
            reason = None
            if len(fences) != 1 or body.count('```suggestion') != 1:
                reason = 'not exactly one fence'
            elif th['diffSide'] != 'RIGHT':
                reason = 'not RIGHT side'
            elif not c['originalCommit'] or not th['originalLine']:
                reason = 'no original commit or line'
            elif Path(th['path']).suffix.lower() not in CODE_EXT:
                reason = 'not a source-code file'
            if reason:
                excl[reason] = excl.get(reason, 0) + 1
                continue
            units.append(dict(repo=full, pr=pr['number'], c1=pr['headRefOid'], c0=c['originalCommit']['oid'],
                              comment_id=c['databaseId'], thread_id=th['id'], path_c0=th['path'],
                              start=th['originalStartLine'] or th['originalLine'], end=th['originalLine'],
                              suggestion=fences[0].rstrip('\n'), comment=FENCE.sub('', body).strip(),
                              github_outdated=th['isOutdated'], github_line=th['line'], github_start=th['startLine'],
                              apply_suggestion_commit=applied_commit))
    return prs[:SCAN_PRS], units, excl


def resolve(u):
    """Fetch O and the c1 file, apply exclusions D2 and the oracle D5."""
    owner, name = u['repo'].split('/')
    t0, r0 = blob(owner, name, u['c0'], u['path_c0'])
    if t0 is None:
        return u, f'c0 object: {r0}'
    lines = t0.splitlines()
    if u['end'] > len(lines) or u['start'] < 1 or u['start'] > u['end']:
        return u, 'line range outside c0 file'
    o_text = '\n'.join(lines[u['start'] - 1:u['end']])
    if not norm(o_text):
        return u, 'O blank'
    if norm(o_text) == norm(u['suggestion']):
        return u, 'S equals O'
    status, p1 = path_at_c1(owner, name, u['c0'], u['c1'], u['path_c0'])
    if status == 'unknown':
        return u, 'compare unavailable'
    t1 = None
    if status != 'D':
        t1, r1 = blob(owner, name, u['c1'], p1)
        if t1 is None:
            return u, f'c1 object: {r1}'
    cls, truth = oracle(o_text, u['suggestion'], t1, status)
    u.update(O=o_text, path_c1=p1, rename=status == 'R', cls=cls,
             truth=[p1, truth[0], truth[1]] if truth else None,
             c0_sha256=hashlib.sha256(t0.encode()).hexdigest(),
             c1_sha256=hashlib.sha256(t1.encode()).hexdigest() if t1 is not None else None)
    return u, None


def keyed(u):
    return hashlib.sha256(f"{SEED}|{u['repo']}|{u['comment_id']}".encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--languages', default=','.join(LANGUAGES))
    ap.add_argument('--max-candidates', type=int, default=15)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    sel_path = OUT / 'selection.json'
    selection = json.loads(sel_path.read_text(encoding='utf-8')) if sel_path.exists() else {}
    all_units, exclusions = [], {}
    for lang in args.languages.split(','):
        res = cached(f'search-{lang}.json', lambda: rest(
            'search/repositories?' + urllib.parse.urlencode({'q': f'language:{lang} stars:>3000 archived:false fork:false',
                                                             'sort': 'stars', 'order': 'desc', 'per_page': 50}))[1])
        entry = selection.setdefault(lang, {'candidates': [], 'accepted': []})
        done = {c['repo'] for c in entry['candidates']}
        for item in res['items'][:args.max_candidates]:
            if len(entry['accepted']) >= PER_LANG:
                break
            full = item['full_name']
            if full in done:
                continue
            spdx = (item.get('license') or {}).get('spdx_id')
            rec = {'repo': full, 'stars': item['stargazers_count'], 'spdx': spdx}
            if spdx not in LICENCES:
                rec['rejected'] = f'licence {spdx}'
            else:
                log('scan', lang, full)
                try:
                    prs, units, excl = scan_repo(full)
                except Exception as e:  # recorded, next candidate
                    rec['rejected'] = f'scan failed: {e}'[:300]
                    prs, units, excl = [], [], {}
                rec.update(prs_scanned=len(prs), raw_units=len(units), pre_exclusions=excl)
                if 'rejected' not in rec and len(units) < MIN_UNITS:
                    rec['rejected'] = f'{len(units)} units < {MIN_UNITS}'
                if 'rejected' not in rec:
                    entry['accepted'].append(full)
            entry['candidates'].append(rec)
            sel_path.write_text(json.dumps(selection, indent=1), encoding='utf-8')
            log(lang, full, rec.get('rejected', 'accepted'), rec.get('raw_units'))
    # Units of accepted repositories: resolve, exclude, cap.
    for lang, entry in selection.items():
        if lang not in args.languages.split(','):
            continue
        for full in entry['accepted']:
            _, units, excl = scan_repo(full)
            for k, v in excl.items():
                exclusions.setdefault(full, {})[k] = exclusions.setdefault(full, {}).get(k, 0) + v
            with ThreadPoolExecutor(16) as pool:
                resolved = list(pool.map(resolve, units))
            ok = []
            for u, reason in resolved:
                if reason:
                    key = reason.split(':')[0] if reason.startswith(('c0 object', 'c1 object')) else reason
                    exclusions.setdefault(full, {})[reason] = exclusions.setdefault(full, {}).get(reason, 0) + 1
                else:
                    u['language'] = lang
                    ok.append(u)
            ok.sort(key=keyed)
            if len(ok) > CAP:
                exclusions.setdefault(full, {})[f'over cap {CAP}'] = len(ok) - CAP
            all_units += ok[:CAP]
            log('resolved', full, len(ok), 'kept', min(CAP, len(ok)))
    prev = OUT / 'units.json'
    if prev.exists():  # merge runs over different language subsets
        keep = [u for u in json.loads(prev.read_text(encoding='utf-8'))['units'] if u['language'] not in args.languages.split(',')]
        old_ex = json.loads((OUT / 'exclusions.json').read_text(encoding='utf-8'))
        all_units = keep + all_units
        exclusions = {**{k: v for k, v in old_ex.items() if k not in exclusions}, **exclusions}
    code = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    prev.write_text(json.dumps({'code_sha256': code, 'recorded_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                                'units': all_units}, indent=0), encoding='utf-8')
    (OUT / 'exclusions.json').write_text(json.dumps(exclusions, indent=1), encoding='utf-8')
    counts = {}
    for u in all_units:
        c = counts.setdefault(u['language'], {})
        c[u['cls']] = c.get(u['cls'], 0) + 1
    log('units', len(all_units), json.dumps(counts))


if __name__ == '__main__':
    sys.exit(main())
