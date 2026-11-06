"""Fresh-process C6 finalization after both execution stages complete."""
import sys,os,time,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_c6 import *

def main():
    gate();deadline=time.monotonic()+8*3600
    while not all((OUT/'c6'/stage/'completion.json').exists() for stage in ('stress','reuse')):
        if time.monotonic()>deadline:raise TimeoutError('C6 stage budget exhausted')
        time.sleep(15)
    py=ROOT/'tools/v11-ext/codemapper/venv/Scripts/python.exe';folder=Path(__file__).parent
    test=subprocess.run([str(py),'-I','-B','-m','unittest','discover','-s',str(folder),'-p','test_wpc*.py'],cwd=ROOT,capture_output=True)
    (OUT/'c6/tests.log').open('xb').write(test.stdout+b'\n'+test.stderr)
    write('c6/tests-verification.json',dict(passed=test.returncode==0,returncode=test.returncode,log_sha256=sha(OUT/'c6/tests.log')))
    assert test.returncode==0,test.stderr[-3000:]
    for script,args in [('analyze_wpc_c6.py',[]),('build_wpc_c6.py',[]),('verify_wpc_c6.py',[]),('verify_wpc_tex.py',['c6/tex'])]:
        print('C6 phase',script,flush=True)
        result=subprocess.run([str(py),'-I','-B',str(folder/script),*args],cwd=ROOT,capture_output=True,env=dict(os.environ,OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2'))
        (OUT/'c6'/('pipeline-'+script+'.log')).open('xb').write(result.stdout+b'\n'+result.stderr)
        assert result.returncode==0,(script,result.stderr[-3000:])
    write('c6/pipeline-completion.json',dict(complete=True,utc=now(),direct_visual_review_pending=True))
    print('C6 analysis, audit and rendering complete',flush=True)
if __name__=='__main__':main()
