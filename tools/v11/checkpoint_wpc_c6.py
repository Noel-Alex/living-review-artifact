"""Descriptive C6 reuse-only checkpoint, never a substitute for complete results."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_c6 import *
from analyze_wpc_c6 import metric,strata,BASES,MATCHERS,native_alias

def main():
    gate();assert read(OUT/'c6/reuse/completion.json')['data']['complete']
    paths=sorted((OUT/'c6/reuse').glob('trials-*.json'));rows=[r for p in paths for r in read(p)['data']];native_alias(rows);pop=strata(rows)
    result={name:{m:metric(pop[name],m) for m in (*BASES,*(k+'+IG+AG' for k in MATCHERS))} for name in ('real','real:oss:targeted','external:human-AB:non-Python-code')}
    write('c6/reuse-only-checkpoint.json',dict(partial=True,stress_not_included=True,results=result),paths)
    for name,ms in result.items():print(name,{m:{k:v[k]['k'] for k in ('accuracy','missed','wrong_silent','lost','false_recheck')} for m,v in ms.items()},flush=True)
if __name__=='__main__':main()
