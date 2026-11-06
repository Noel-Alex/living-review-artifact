"""Isolated CodeMapper runner: native matching, read-only file/Git boundaries."""
import sys,json,os,subprocess,traceback,io,contextlib,types,shlex,time
from functools import lru_cache
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',GIT_TERMINAL_PROMPT='0',GIT_NO_LAZY_FETCH='1')
# Refuse Python network access during mapping; acquisition is a separate script.
def audit(event,args):
    if event in ('socket.connect','socket.bind','urllib.Request'):raise RuntimeError('network prohibited during mapping')
sys.addaudithook(audit)
import anything_tracker.AnythingTrackerOnHistoryPairs as native
from anything_tracker.SpecifyToTurnOffTechniques import SpecifyToTurnOffTechniques
import anything_tracker.GitDiffToCandidateRegion as gd
import anything_tracker.utils.ReadFile as rf
import anything_tracker.GetTargetFilePath as path_native
from git import Repo as RealRepo
CACHE={}
VIRTUAL_HEAD={}
LIVE_REPOS=[]
class ReadOnlyRepo:
    def __init__(self,path):
        self.path=path;self.repo=RealRepo(path);self.git=types.SimpleNamespace(checkout=self.checkout)
        LIVE_REPOS.append(self.repo)
    def commit(self,rev):return self.repo.commit(rev)
    def checkout(self,rev,force=True):VIRTUAL_HEAD[str(self.path)]=rev
def native_command(command,repo):
    words=shlex.split(command,posix=True)
    if words[:2] not in (['git','log'],['git','diff']):raise ValueError('unapproved native resolver command')
    if any(x in command for x in (';','&','|','`','$','\n','\r')):raise ValueError('unsafe native resolver command')
    if words[1]=='log':words.insert(2,VIRTUAL_HEAD[str(repo)])
    return git(repo,*words[1:]).decode('utf-8',errors='replace')
path_native.Repo=ReadOnlyRepo;path_native.run_command=native_command
@lru_cache(maxsize=1024)
def native_target(repo,old,new,path):
    try:return path_native.get_target_file_path(repo,old,new,path)
    finally:
        for handle in LIVE_REPOS:handle.close()
        LIVE_REPOS.clear()
def git(repo,*args):
    args=list(args)
    if args and args[0]=='diff':args.insert(1,'--no-ext-diff')
    p=subprocess.run(['git','-c','core.hooksPath='+str(OUT/'no-hooks'),'-c','core.autocrlf=false','-C',str(repo),*args],capture_output=True,timeout=55)
    if p.returncode:raise RuntimeError(p.stderr.decode(errors='replace'))
    return p.stdout
@lru_cache(maxsize=128)
def blob(repo,commit,path):
    raw=git(repo,'show',commit+':'+path)
    return raw.decode('utf-8' if valid_utf8(raw) else 'latin-1').replace('\r\n','\n').replace('\r','\n')
def valid_utf8(raw):
    try:raw.decode('utf-8');return True
    except UnicodeDecodeError:return False
def read_lines(repo,commit,path):return blob(repo,commit,path).splitlines(keepends=True)
native.checkout_to_read_file=read_lines;rf.checkout_to_read_file=read_lines
def run_diff(command,cwd,shell,encoding,stdout,universal_newlines):
    # Preserve upstream flags, replacing shell evaluation with an argument vector.
    words=shlex.split(command,posix=True)
    if words[:2]!=['git','diff'] or any(x in command for x in (';','&','|','`','$','\n','\r')):raise ValueError('unsafe upstream diff command')
    key=(str(cwd),command,encoding)
    if key not in CACHE:
        raw=git(cwd,*words[1:]);CACHE[key]=raw.decode(encoding)
        if len(CACHE)>256:CACHE.pop(next(iter(CACHE)))
    return types.SimpleNamespace(stdout=CACHE[key],returncode=0)
gd.subprocess=types.SimpleNamespace(run=run_diff,PIPE=subprocess.PIPE)
def run(q):
    verify_freeze()
    repo,old,new,path,target=q['repo'],q['old'],q['new'],q['path'],q['target_path']
    if q.get('resolver')=='native-readonly':
        freeze=read(OUT/'native-resolver-freeze.json')
        assert freeze['protocol_sha256']==sha(ROOT/'review/V11-WPC-NATIVE-RESOLVER-PROTOCOL.md')
        target=native_target(repo,old,new,path)
        if target=='D':return dict(removed(),native_deleted=True,native_resolver=True)
        if target is None:return failed('native resolver: uncommon/undetected target file')
    if target is None:return dict(removed(),native_deleted=True)
    log=io.StringIO();begin=time.perf_counter()
    with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        tracker=native.AnythingTrackerOnHistoryPairs(repo,old,path,new,target,q['source_region'],q['results_dir'],q['id'],15,SpecifyToTurnOffTechniques([False]*4))
        outputs,times=tracker.run()
    if len(outputs)!=1:raise ValueError(('native output length',len(outputs),log.getvalue()))
    o=outputs[0];r=o['target_range']
    r=json.loads(r) if isinstance(r,str) else r
    if r is None or r.count(0)>=3:out=removed()
    else:
        text=blob(repo,new,target);source=blob(repo,old,path)
        s,e=region_lines(r)
        if not 1<=s<=e<=len(text.splitlines()):raise ValueError(('invalid native range',r))
        label='exact' if region_text(source,q['source_region'])==region_text(text,r) else 'changed'
        out=dict(label=label,placement=[target,s],range=[target,s,e],character_range=r,recheck=label=='changed')
    out.update(native=outputs,log=log.getvalue(),elapsed_ms=1000*(time.perf_counter()-begin),resolved_path=target,resolver=q.get('resolver','frozen-direct-rename'))
    return out
for line in sys.stdin:
    try:result=run(json.loads(line))
    except BaseException as e:result=dict(failed(repr(e)),traceback=traceback.format_exc())
    print(json.dumps(result,ensure_ascii=True),flush=True)
