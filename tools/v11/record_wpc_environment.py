"""Capture tools, installed dependency licences/hashes, and unchanged native code."""
import sys,json,subprocess,platform,importlib.metadata as md
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
def main():
    root=ROOT/'tools/v11-ext';report=read(OUT/'dependency-install.json');dependencies=[]
    for item in report['install']:
        m=item['metadata'];dist=md.distribution(m['name']);licences={}
        for f in dist.files or ():
            path=Path(dist.locate_file(f))
            if path.is_file() and any(x in str(f).lower() for x in ('license','licence','copying')):licences[str(f)]=sha(path)
        dependencies.append(dict(name=m['name'],version=m['version'],url=item['download_info']['url'],archive_sha256=item['download_info']['archive_info']['hashes']['sha256'],licence_expression=m.get('license_expression'),licence_metadata=m.get('license'),licence_classifiers=[v for v in m.get('classifier',[]) if v.startswith('License')],licence_files=licences))
    source=next((root/'codemapper/source').iterdir())/'src/anything_tracker';installed=Path(md.distribution('anything_tracker').locate_file('anything_tracker'))
    identical={str(p.relative_to(source)).replace('\\','/'):sha(p) for p in source.rglob('*.py')}
    for path,h in identical.items():assert sha(installed/path)==h,path
    commands={}
    for label,args in [('git',['git','--version']),('java',['C:/Program Files/Java/jdk-26.0.1/bin/java.exe','-version'])]:
        r=subprocess.run(args,capture_output=True);commands[label]=dict(returncode=r.returncode,stdout=r.stdout.decode(errors='replace'),stderr=r.stderr.decode(errors='replace'))
    write('environment-manifest.json',dict(platform=platform.platform(),python=sys.version,executable=sys.executable,tools=commands,dependencies=dependencies,installed_native_code_identical=True,native_code_sha256=identical),[OUT/'dependency-install.json',root/'codemapper/manifest.json',root/'gumtree-release/manifest.json',root/'gumtree-source/manifest.json'])
    print('dependency and unchanged-code manifest',len(dependencies),len(identical),flush=True)
if __name__=='__main__':main()
