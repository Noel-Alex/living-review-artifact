"""Forward record of observed infrastructure failures; raw logs remain untouched."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_c6 import *

def main():
    gate();records=[];inputs=[]
    for name,needle,repair in [('c6-tests-before.log',"No module named 'wpc_c6'",'Implement the registered layer; later adapter/guard/statistics tests pass.'),('c6-environment-check.log','FileNotFoundError','Use the existing archived-results acquisition manifest in evidence rather than assuming a tool-local manifest.')]:
        p=OUT/name;raw=p.read_bytes();body=raw.decode('utf-16') if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else raw.decode('utf-8-sig',errors='replace');assert needle in body
        records.append(dict(log=name,sha256=sha(p),failure=needle,repair=repair));inputs.append(p)
    interruptions=list((OUT/'c6').glob('stress-interruption-*.json'));assert len(interruptions)==1
    # This exit status and stderr were observed in the PowerShell tool result.
    # The original taskkill stdout file is retained, and this forward record
    # also preserves the stderr diagnostic which PowerShell displayed separately.
    records.append(dict(record=str(interruptions[0].relative_to(OUT)),taskkill_exit_code=128,powershell_exit_code=1,stderr_observed='Several rapidly exiting Git descendants: The operation attempted is not supported / There is no running instance of the task.',followup='Independent process inventory found the former redirector and all six former workers absent; only the resumed stress writer remained. Saved rows and unfinished fixtures were preserved.'))
    inputs+=interruptions
    records.append(dict(failure='First incident-ledger attempt raised AssertionError while checking a PowerShell log as UTF-8.',repair='Detect the UTF-16 BOM used by Windows PowerShell redirection before checking diagnostic text.',evidence='Observed traceback at record_wpc_c6_incidents.py assert needle in body; this forward record preserves that failure.'))
    write('c6/execution-incident-ledger.json',dict(incidents=records,scope='infrastructure failures, not additional benchmark trials; original logs and initial results retained'),inputs)
    print('C6 infrastructure incident ledger retained',len(records))
if __name__=='__main__':main()
