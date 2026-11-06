"""Run the complete scoped research-adapter suite with an auditable JSON count."""
import sys,unittest,warnings
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *
def main():
    suite=unittest.TestSuite();loader=unittest.defaultTestLoader
    for name in ('test_wpa','test_variants','test_wpb_reporting','test_wpc','test_wpc_processes'):suite.addTests(loader.loadTestsFromName(name))
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter('always',ResourceWarning)
        result=unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(suite)
    resources=[str(w.message) for w in seen if issubclass(w.category,ResourceWarning)]
    name='tests-verification-final.json' if '--final' in sys.argv else 'tests-verification.json'
    write(name,dict(passed=result.wasSuccessful() and not resources,tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),skipped=len(result.skipped),resource_warnings=resources))
    assert result.wasSuccessful() and not resources
if __name__=='__main__':main()
