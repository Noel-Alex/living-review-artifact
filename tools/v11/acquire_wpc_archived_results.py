"""Fetch CodeMapper's official archived output asset, never execute its loader."""
import sys,json,urllib.request,zipfile,io,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
def main():
    req=urllib.request.Request('https://api.github.com/repos/sola-st/CodeMapper/releases',headers={'User-Agent':'Vcap-paper-reproduction'})
    raw=urllib.request.urlopen(req,timeout=60).read();(OUT/'codemapper-releases.json').write_bytes(raw)
    releases=json.loads(raw);assets=[dict(a,tag=r['tag_name'],target=r['target_commitish']) for r in releases for a in r['assets'] if a['name']=='results.zip']
    assert assets,'official results.zip asset missing'
    a=assets[0];folder=ROOT/'tools/v11-ext/codemapper-archived-results';folder.mkdir(exist_ok=False)
    data=urllib.request.urlopen(a['browser_download_url'],timeout=120).read();(folder/'results.zip').write_bytes(data)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for entry in z.infolist():
            target=folder/'source'/entry.filename
            assert target.resolve().is_relative_to((folder/'source').resolve())
            assert (entry.external_attr>>16)&0o170000 != 0o120000
            if entry.is_dir():target.mkdir(parents=True,exist_ok=True)
            else:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(entry))
    write('archived-results-acquisition.json',dict(asset=a,sha256=hashlib.sha256(data).hexdigest(),licence='MIT CodeMapper artifact; derived results',files={str(p.relative_to(folder)):sha(p) for p in folder.rglob('*') if p.is_file()}))
    print(a['browser_download_url'],len(data),flush=True)
if __name__=='__main__':main()
