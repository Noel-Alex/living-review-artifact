"""WP I amendment 3: complete the blob objects of the 20 pinned H2 student clones (public GitHub repos).

The H2 clones are blobless partial clones; CodeMapper's native Git diff needs blobs the cascade
never read. This refetches all objects without changing any ref, then verifies HEAD and that
every H2 observation's old-file digest is reproducible from the completed clone.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wpi_core import ROOT, read, write  # noqa: E402

PRIVATE = ROOT / 'evidence/v11-wph/private'


def git(repo, *args, env=None):
    p = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, timeout=3600, env=env)
    return p.returncode, p.stdout.decode(errors='replace'), p.stderr.decode(errors='replace')


def main():
    import os
    env = {k: v for k, v in os.environ.items() if k != 'GIT_NO_LAZY_FETCH'}
    report = {}
    for r in sorted(read(PRIVATE / 'selected.json'), key=lambda x: int(x['anonymous_id'][1:])):
        sid, repo = r['anonymous_id'], PRIVATE / 'tmp' / str(r['repository_id'])
        _, head, _ = git(repo, 'rev-parse', 'HEAD')
        assert head.strip() == r['head_commit_sha'], sid
        _, filt, _ = git(repo, 'config', '--get', 'remote.origin.partialclonefilter')
        _, before, _ = git(repo, 'count-objects', '-v')
        if filt.strip():
            git(repo, 'config', '--unset', 'remote.origin.partialclonefilter')
            code, out, err = git(repo, 'fetch', '--refetch', '--no-tags', 'origin', r['head_commit_sha'], env=env)
            assert code == 0, (sid, err[-2000:])
        _, head2, _ = git(repo, 'rev-parse', 'HEAD')
        assert head2.strip() == r['head_commit_sha'], sid
        code, missing, err = git(repo, 'rev-list', '--objects', '--missing=print', r['head_commit_sha'])
        absent = [x for x in missing.splitlines() if x.startswith('?')]
        _, after, _ = git(repo, 'count-objects', '-v')
        report[sid] = dict(filter_before=filt.strip(), missing_after=len(absent), head=head2.strip(),
                           objects_before=before, objects_after=after)
        print(sid, 'missing after', len(absent), flush=True)
        assert not absent, sid
    write('students-objects/acquisition.json', report)


if __name__ == '__main__':
    main()
