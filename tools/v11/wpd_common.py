from pathlib import Path
import hashlib, json, os, sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/v11-wpd'
APP = ROOT / 'tools/v11-app'
PIN = '2d8d2816a0f14034a9665c4e392ae7a9a1b752e1'

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def inputs(extra=()):
    paths = [*APP.rglob('*.py'), *APP.rglob('*.toml'), *APP.rglob('*.html'),
             *ROOT.joinpath('tools/v11').glob('*wpd*.py'),
             ROOT/'v10-citation-methods/main.tex', ROOT/'review/briefs/WPD.md',
             ROOT/'evidence/pinned-corpus-manifest.json', *extra]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(paths))}

def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    data = {'pin':PIN, 'inputs':inputs(), **data}
    (OUT/name).write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str)+'\n', encoding='utf-8')
    return data

def bootstrap():
    os.environ['VCAP_SKIP_DOTENV']='1'
    os.environ['RECAP_DB_URL']='sqlite:///:memory:'
    os.environ['RECAP_AGENT_MODE']='deterministic'
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    vendor = ROOT/'tools/v11/wpd-deps'
    if vendor.exists(): sys.path.insert(0,str(vendor))
    sys.path.insert(0,str(APP/'vcap'))

if __name__ == '__main__':
    import importlib.util, platform
    modules=['sqlalchemy','pytest','fastapi','celery','redis','pydantic','pypdf','jwt','cryptography','httpx','litellm','psycopg2','multipart']
    save('environment-initial.json', {'python':sys.version,'executable':sys.executable,'platform':platform.platform(),
        'modules':{name: bool(importlib.util.find_spec(name)) for name in modules}})
    print((OUT/'environment-initial.json').read_text()[-700:])
