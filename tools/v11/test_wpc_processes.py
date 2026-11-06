"""Windows regression: closing an owned worker also closes its venv child."""
import unittest,subprocess,json,sys,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_adapters import Worker,OUT
def inventory():
    r=subprocess.run(['powershell','-NoProfile','-Command','Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId | ConvertTo-Json -Compress'],capture_output=True,check=True)
    return json.loads(r.stdout)
@unittest.skipUnless(os.name=='nt','Windows process-tree regression')
class WorkerCleanupTests(unittest.TestCase):
    def test_close_stops_redirector_and_underlying_python(self):
        w=Worker('cm',OUT/'process-cleanup-test');w.start();root=w.proc.pid
        try:
            rows=inventory();owned={root}
            for _ in range(5):owned.update(r['ProcessId'] for r in rows if r['ParentProcessId'] in owned)
            self.assertGreaterEqual(len(owned),2,'Expected the Windows venv redirector child')
        finally:w.close()
        alive={r['ProcessId'] for r in inventory()}
        self.assertFalse(owned&alive,owned&alive)
if __name__=='__main__':unittest.main()
