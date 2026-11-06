"""Fetch pinned external data without importing or executing downloaded code."""
import hashlib,json,urllib.request,zipfile,io
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
EXT=ROOT/'tools/v11-ext'
OUT=ROOT/'evidence/v11-wpc'
def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Vcap-paper-reproduction'}),timeout=120).read()
def acquire(name,url,commit,licence):
    folder=EXT/name
    folder.mkdir(parents=True,exist_ok=False)
    raw=fetch(url)
    (folder/'download.zip').write_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for e in z.infolist():
            p=folder/'source'/e.filename
            assert p.resolve().is_relative_to((folder/'source').resolve()),e.filename
            assert (e.external_attr>>16)&0o170000 != 0o120000,'symlink'
            if e.is_dir():p.mkdir(parents=True,exist_ok=True)
            else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(e))
    manifest=dict(url=url,commit=commit,licence=licence,download_sha256=hashlib.sha256(raw).hexdigest(),utc=datetime.now(timezone.utc).isoformat(),files={str(p.relative_to(folder)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()})
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(name,commit,len(manifest['files']),flush=True)
if __name__=='__main__':
    c=json.loads((OUT/'codemapper-head.json').read_bytes())['sha']
    acquire('codemapper','https://codeload.github.com/sola-st/CodeMapper/zip/'+c,c,'MIT')
    tag=json.loads(fetch('https://api.github.com/repos/GumTreeDiff/gumtree/commits/v4.1.0'))['sha']
    (OUT/'gumtree-tag.json').write_text(json.dumps({'tag':'v4.1.0','commit':tag}))
    acquire('gumtree-release','https://github.com/GumTreeDiff/gumtree/releases/download/v4.1.0/gumtree-4.1.0.zip',tag,'LGPL-3.0')
    acquire('gumtree-source','https://codeload.github.com/GumTreeDiff/gumtree/zip/'+tag,tag,'LGPL-3.0')
