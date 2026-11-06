"""Bounded local pipeline, only after all primary execution stages complete."""
import sys,time,subprocess,traceback,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
def main():
    stages=('gumtree-living','external-frozen','external-codemapper-native','external-codemapper-native-repair','codemapper-living-native')
    deadline=time.monotonic()+12*3600
    while not all((OUT/s/'completion.json').exists() for s in stages):
        if time.monotonic()>deadline:raise TimeoutError('Primary stages not complete within pipeline budget')
        time.sleep(15)
    while not (OUT/'codemapper-reproduction-native-final.json').exists():
        if time.monotonic()>deadline:raise TimeoutError('final acquisition corrections incomplete')
        time.sleep(10)
    python=ROOT/'tools/v11-ext/codemapper/venv/Scripts/python.exe'
    for script,args in [('verify_wpc_tests.py',['--final']),('analyze_wpc.py',['all']),('build_wpc_results.py',[]),('verify_wpc.py',[]),('verify_wpc_tex.py',[])]:
        print('PIPELINE FRESH PROCESS',script,flush=True)
        result=subprocess.run([str(python),'-I','-B',str(Path(__file__).with_name(script)),*args],cwd=ROOT,capture_output=True)
        (OUT/('pipeline-final-'+script+'.log')).open('xb').write(result.stdout+b'\n'+result.stderr)
        if result.returncode:raise RuntimeError((script,result.returncode,result.stderr[-2000:].decode(errors='replace')))
    write('pipeline-completion-final.json',dict(complete=True,utc=now(),visual_inspection_pending=True))
if __name__=='__main__':
    try:main()
    except BaseException as e:write('pipeline-failure-'+str(time.time_ns())+'.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
