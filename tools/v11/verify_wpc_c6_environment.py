"""Recheck unchanged external pins and record the actual import locations."""
import sys,importlib,importlib.metadata as md
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_c6 import *

def main():
    gate();checked={};inputs=[];ext=ROOT/'tools/v11-ext'
    for name in ('codemapper','gumtree-release','gumtree-source','codemapper-archived-results'):
        path=OUT/'archived-results-acquisition.json' if name=='codemapper-archived-results' else ext/name/'manifest.json'
        record=read(path);manifest=record.get('data',record);n=0
        for relative,h in manifest['files'].items():assert sha(ext/name/relative)==h,(name,relative);n+=1
        checked[name]=dict(files=n,commit=manifest.get('commit'),licence=manifest.get('licence'),manifest_sha256=sha(path));inputs.append(path)
    native=read(OUT/'environment-manifest.json')['data']['native_code_sha256'];package=Path(md.distribution('anything_tracker').locate_file('anything_tracker'))
    for p,h in native.items():assert sha(package/p)==h,p
    modules={}
    for name in ('numpy','fast_edit_distance','git'):
        module=importlib.import_module(name);p=Path(module.__file__)
        modules[name]=dict(path=str(p),sha256=sha(p),version=getattr(module,'__version__',None))
    bridge={p.name:sha(p) for p in (ext/'gumtree-release/bridge').glob('*.class')}
    write('c6/environment-verification.json',dict(passed=True,third_party=checked,native_code_files=len(native),actual_imports=modules,compiled_bridge=bridge),inputs+[OUT/'environment-manifest.json'])
    print('C6 external identities verified',checked,modules,flush=True)
if __name__=='__main__':main()
