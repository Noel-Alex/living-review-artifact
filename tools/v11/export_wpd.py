"""Export the immutable WP D app and tests; never import the live checkout."""
from pathlib import Path
import hashlib, io, json, subprocess, tarfile

ROOT = Path(__file__).resolve().parents[2]
PIN = '2d8d2816a0f14034a9665c4e392ae7a9a1b752e1'
OUT = ROOT / 'evidence/v11-wpd'
APP = ROOT / 'tools/v11-app'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    APP.mkdir(parents=True, exist_ok=True)
    paths = ['vcap/app', 'vcap/tests', 'vcap/pyproject.toml', 'vcap/alembic', 'vcap/alembic.ini',
             'team2', 'docs', 'docker', 'scripts', '.gitmodules', 'AGENTS.md']
    raw = subprocess.check_output(['git', '-C', 'N:/VCAP', 'archive', PIN, *paths])
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive.getmembers():
            assert (APP / member.name).resolve().is_relative_to(APP.resolve())
        archive.extractall(APP, filter='data')
    hashes = {p.relative_to(APP).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(APP.rglob('*')) if p.is_file()}
    original = ROOT / 'evidence/pinned-corpus/vcap/app'
    mismatches = [p.relative_to(original).as_posix() for p in original.rglob('*') if p.is_file()
                  and (not (APP/'vcap/app'/p.relative_to(original)).exists()
                       or p.read_bytes() != (APP/'vcap/app'/p.relative_to(original)).read_bytes())]
    result = {'pin': PIN, 'archive_paths': paths, 'archive_sha256': hashlib.sha256(raw).hexdigest(),
              'files': hashes, 'existing_export_mismatches': mismatches,
              'inputs': {'evidence/pinned-corpus-manifest.json': hashlib.sha256((ROOT/'evidence/pinned-corpus-manifest.json').read_bytes()).hexdigest(),
                         'tools/v11/export_wpd.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    (OUT/'export.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'exported':len(hashes), 'mismatches':mismatches}))

if __name__ == '__main__': main()
