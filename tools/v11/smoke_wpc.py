import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_adapters import *
def main():
    name=sys.argv[1]
    d=Adapters(OUT/name);old='def f():\n    return 1\n';new='def f():\n    return 2\n'
    t={'anchor':dict(path='a.py',line_start=2,line_end=2,quotation='    return 1',content_hash=digest(old)),'old_lines':old.splitlines(),'version':{'a.py':(digest(new),new)}}
    a,b=materialize(OUT/name/'repo',{'a.py':old},t['version'])
    gt=d.gumtree(t);cm=d.codemapper(t,OUT/name/'repo',a,b,'smoke')
    write(name+'.json',dict(gumtree=gt,codemapper=cm,old=a,new=b));d.close()
    assert gt['range']==['a.py',2,2] and gt['recheck'],gt
    assert cm['range']==['a.py',2,2] and cm['recheck'],cm
    print('GumTree and CodeMapper smoke pass',flush=True)
if __name__=='__main__':main()
