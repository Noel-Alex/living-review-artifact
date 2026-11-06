"""Killable persistent external workers and frozen Living Review adapters."""
import sys,subprocess,os,json,time,ctypes,msvcrt,hashlib,shutil,gzip
from pathlib import Path
from functools import lru_cache
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
from wpa_core import loaders,features,cell_output
from wpb_variants import all_outputs
from tracker_process import TrackerProcess
EXT=ROOT/'tools/v11-ext'
JAR=EXT/'gumtree-release/source/gumtree-4.1.0/lib/gumtree.jar'
PY=EXT/'codemapper/venv/Scripts/python.exe'
JAVA=Path('C:/Program Files/Java/jdk-26.0.1/bin/java.exe')
GENERATORS={'.py':'python','.pyw':'python','.java':'java','.js':'js','.jsx':'js','.cs':'cs','.cpp':'cpp','.cc':'cpp','.hpp':'cpp','.h':'cpp','.go':'go','.rb':'ruby','.ts':'ts','.tsx':'tsx','.php':'php'}
def git(repo,*args,check=True):
    r=subprocess.run(['git','-c','core.hooksPath='+str(OUT/'no-hooks'),'-c','core.autocrlf=false','-C',str(repo),*args],capture_output=True,timeout=55)
    if check and r.returncode:raise RuntimeError(r.stderr.decode(errors='replace'))
    return r.stdout
@lru_cache(maxsize=1024)
def target_path(repo,old,new,path):
    r=subprocess.run(['git','-C',str(repo),'cat-file','-e',new+':'+path],capture_output=True,timeout=55)
    if r.returncode==0:return path
    for line in git(repo,'diff','--name-status','-M',old,new).decode('utf-8',errors='replace').splitlines():
        parts=line.split('\t')
        if parts[0].startswith('R') and len(parts)==3 and parts[1]==path:return parts[2]
    return None
class Worker:
    def __init__(self,kind,folder):
        self.kind=kind;self.folder=folder;folder.mkdir(parents=True,exist_ok=True);self.proc=None;self.buffer=b''
    def start(self):
        temp=self.folder/'tmp';temp.mkdir(exist_ok=True)
        if self.kind=='gt':cmd=[str(JAVA),'-Xmx2g','-Djava.io.tmpdir='+str(temp),'-cp',str(EXT/'gumtree-release/bridge')+os.pathsep+str(JAR),'WpcGumTree']
        else:cmd=[str(PY),'-I','-B',str(Path(__file__).with_name('wpc_lr_worker.py' if self.kind=='lr' else 'wpc_cm_worker.py'))]
        self.err=(self.folder/(self.kind+'-stderr-'+str(time.time_ns())+'.log')).open('wb')
        self.proc=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.err,cwd=ROOT,env=dict(os.environ,TEMP=str(temp),TMP=str(temp)))
        self.buffer=b''
    def request(self,line):
        if self.proc is None or self.proc.poll() is not None:self.start()
        begin=time.perf_counter();self.proc.stdin.write((line+'\n').encode('utf-8'));self.proc.stdin.flush()
        handle=msvcrt.get_osfhandle(self.proc.stdout.fileno());available=ctypes.c_ulong()
        while time.perf_counter()-begin<60:
            if b'\n' in self.buffer:
                data,self.buffer=self.buffer.split(b'\n',1);return json.loads(data)
            if self.proc.poll() is not None:raise RuntimeError(('worker exited',self.proc.returncode))
            ok=ctypes.windll.kernel32.PeekNamedPipe(ctypes.c_void_p(handle),None,0,None,ctypes.byref(available),None)
            if not ok:raise RuntimeError('pipe unavailable')
            if available.value:self.buffer+=os.read(self.proc.stdout.fileno(),available.value)
            else:time.sleep(.003)
        self.close();raise TimeoutError(self.kind+' 60s timeout')
    def close(self):
        if self.proc is not None:
            if self.proc.poll() is None:
                # Windows venv redirectors own a second Python process; kill the owned tree.
                stopped=subprocess.run(['taskkill','/PID',str(self.proc.pid),'/T','/F'],capture_output=True,timeout=15)
                (self.folder/('owned-tree-stop-'+str(time.time_ns())+'.log')).write_bytes(stopped.stdout+b'\n'+stopped.stderr)
                if self.proc.poll() is None:self.proc.kill()
                self.proc.wait(timeout=10)
            for stream in (self.proc.stdin,self.proc.stdout):
                try:stream.close()
                except OSError:pass
            self.proc=None;self.err.close()
class Adapters:
    def __init__(self,folder):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.gt=Worker('gt',self.folder);self.cm=Worker('cm',self.folder)
        self.lr=Worker('lr',self.folder)
        self.base=Worker('lr',self.folder/'basic')
        self.gt_cache={};self.m,self.b=loaders();self.tracker=TrackerProcess(ROOT/'tools/bin/lhdiff-driver.exe');self.track_cache={}
    def gumtree(self,t):
        a=t['anchor'];path=a['path'];new=t['version'].get(path)
        if new is None:return removed()
        gen=GENERATORS.get(Path(path).suffix.lower())
        if gen is None:return failed('unsupported GumTree extension: '+Path(path).suffix)
        old='\n'.join(t['old_lines'])+'\n';neo=new[1];key=(digest(old),digest(neo),gen)
        begin=time.perf_counter();cached=key in self.gt_cache
        try:
            if not cached:
                p=self.folder/'old.txt';q=self.folder/'new.txt';p.write_text(old,encoding='utf-8',newline='');q.write_text(neo,encoding='utf-8',newline='')
                self.gt_cache[key]=self.gt.request(str(p)+'\t'+str(q)+'\t'+gen+'-treesitter-ng')
                raw=self.folder/('gt-'+digest('|'.join(key))+'.json.gz')
                if not raw.exists():raw.write_bytes(gzip.compress(json.dumps(self.gt_cache[key]).encode(),mtime=0))
                if len(self.gt_cache)>96:self.gt_cache.pop(next(iter(self.gt_cache)))
            data=self.gt_cache[key]
            out=gumtree_output(data,path,old,neo,a['line_start'],a['line_end'])
            out.update(elapsed_ms=1000*(time.perf_counter()-begin),file_pair_match_ms=data.get('ms'),cache_hit=cached,matcher=data.get('matcher'))
            out['raw_pair_output']=str((self.folder/('gt-'+digest('|'.join(key))+'.json.gz')).relative_to(ROOT)).replace('\\','/')
            return out
        except Exception as e:return failed(repr(e))
    def codemapper(self,t,repo,old,new,ident,source_region=None,resolver=None):
        a=t['anchor'];begin=time.perf_counter()
        try:
            target=a['path'] if resolver=='native-readonly' else target_path(str(repo),old,new,a['path'])
            source_region=source_region or line_region('\n'.join(t['old_lines'])+'\n',a['line_start'],a['line_end'])
            result=self.cm.request(json.dumps(dict(repo=str(repo),old=old,new=new,path=a['path'],target_path=target,source_region=source_region,results_dir=str(self.folder/'cm-native'),id=ident,resolver=resolver)))
            result['wall_ms']=1000*(time.perf_counter()-begin)
            return result
        except Exception as e:return failed(repr(e))
    def living(self,t,old_files):
        verify_freeze();begin=time.perf_counter()
        try:
            response=self.lr.request(json.dumps(dict(trial=t,old_files=old_files)))
            if 'error' in response:raise RuntimeError(response['error'])
            result=response['outputs']
        except Exception as e:
            from wpb_variants import THETAS,SWITCHES,variant_key
            result={variant_key(theta,*switches):failed(repr(e)) for theta in THETAS for switches in SWITCHES}
        for o in result.values():o['frozen_family_wall_ms']=1000*(time.perf_counter()-begin)
        for name in ('cascade','cascade_v1','quote_exact','diff_drift','line_number','tracker_adapter'):
            begin=time.perf_counter()
            try:
                response=self.base.request(json.dumps(dict(mode='basic',trial=t,method=name)))
                if 'error' in response:raise RuntimeError(response['error'])
                result[name]=response['output']
            except Exception as e:result[name]=failed(repr(e))
            result[name]['wall_ms']=1000*(time.perf_counter()-begin)
        return result
    def close(self):
        self.gt.close();self.cm.close();self.lr.close();self.base.close();self.tracker.close()
def materialize(folder,old_files,version):
    """Two immutable Git trees; no working-tree file writes or hooks."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    git(folder,'init','--bare')
    stream=bytearray()
    for index,files in enumerate((old_files,{p:v[1] for p,v in version.items()}),1):
        stream.extend(f'commit refs/heads/{"old" if index==1 else "evaluation"}\nmark :{index}\nauthor WP C <fixture@example.invalid> 1767225600 +0000\ncommitter WP C <fixture@example.invalid> 1767225600 +0000\ndata 3\nnew\n'.encode())
        if index==2:stream.extend(b'from :1\n')
        stream.extend(b'deleteall\n')
        for path,text in sorted(files.items()):
            p=Path(path)
            if p.is_absolute() or '..' in p.parts or '\n' in path or '\t' in path:raise ValueError('unsafe source path')
            raw=text.encode('utf-8');quoted=json.dumps(path,ensure_ascii=True)
            stream.extend(f'M 100644 inline {quoted}\ndata {len(raw)}\n'.encode()+raw+b'\n')
        stream.extend(b'\n')
    stream.extend(b'done\n')
    subprocess.run(['git','-C',str(folder),'fast-import','--quiet','--done'],input=stream,capture_output=True,check=True,timeout=55)
    old=git(folder,'rev-parse','refs/heads/old').decode().strip();new=git(folder,'rev-parse','refs/heads/evaluation').decode().strip()
    return old,new
