"""Retain dataset repository licence texts at the acquired immutable heads."""
import sys,json,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
def main():
    entries=read(OUT/'dataset-acquisition.json');licences=[];folder=OUT/'dataset-licences';folder.mkdir(exist_ok=False)
    for entry in entries:
        repo=entry['path'];head=entry['head'];name=Path(repo).name
        listing=subprocess.run(['git','-C',repo,'ls-tree','--name-only',head],capture_output=True,check=True).stdout.decode().splitlines()
        candidates=[x for x in listing if x.lower().startswith(('license','licence','copying','notice')) and not x.endswith('/')]
        record=dict(url=entry['url'],head=head,files={},errors=[])
        for path in candidates:
            p=subprocess.run(['git','-C',repo,'show',head+':'+path],capture_output=True,timeout=90)
            if p.returncode:record['errors'].append(dict(path=path,error=p.stderr.decode(errors='replace')));continue
            target=folder/(name+'--'+path.replace('/','_'));target.write_bytes(p.stdout);record['files'][path]=dict(sha256=sha(target),path=str(target.relative_to(ROOT)).replace('\\','/'))
        licences.append(record)
    write('dataset-licences.json',licences)
    print('retained licence manifests',len(licences),flush=True)
if __name__=='__main__':main()
