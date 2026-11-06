"""Run only pinned local tests; preserve collection errors and every test outcome."""
from pathlib import Path
import json, os, sys, traceback, importlib.metadata
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpd_common import APP, OUT, ROOT, bootstrap, save
bootstrap()
os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
os.environ['HF_HUB_OFFLINE']='1'
os.environ['RECAP_JWT_SECRET']='wpd-local-fixture-secret-0123456789'
os.environ['VCAP_ARTIFACT_ROOT']=str(OUT/'runtime/artifacts')
os.environ['VCAP_REVIEW_MEDIA_ROOT']=str(OUT/'runtime/media')
os.environ['HYPOTHESIS_STORAGE_DIRECTORY']=str(OUT/'runtime/hypothesis')
os.environ['TEMP']=os.environ['TMP']=str(ROOT/'tools/v11/wpd-tmp')
os.chdir(APP/'vcap')

class Results:
    def __init__(self): self.reports=[]; self.collection=[]; self.items=[]
    def pytest_collection_finish(self,session): self.items=[i.nodeid for i in session.items]
    def pytest_collectreport(self,report):
        if report.failed or report.skipped:
            self.collection.append({'nodeid':report.nodeid,'outcome':report.outcome,'detail':str(report.longrepr)})
    def pytest_runtest_logreport(self,report):
        self.reports.append({'nodeid':report.nodeid,'phase':report.when,'outcome':report.outcome,
                             'detail':str(report.longrepr) if report.failed or report.skipped else None})

def main():
    import pytest
    mode=sys.argv[1] if len(sys.argv)>1 else 'existing'
    (OUT/'runtime').mkdir(parents=True,exist_ok=True)
    prior=OUT/f'{mode}-tests.json'
    if prior.exists():
        attempt=1
        while (OUT/f'{mode}-tests-attempt-{attempt:03}.json').exists(): attempt+=1
        (OUT/f'{mode}-tests-attempt-{attempt:03}.json').write_bytes(prior.read_bytes())
    result=Results()
    if mode=='existing':
        targets=['tests/review_studio','tests/artifacts']
        # These explicit live/deployment/provider tests require external services or credentials.
        ignore=['test_live_mcp.py','test_hermes_deployment.py','test_hermes_profiles.py','test_demo_kit.py']
        args=[*targets,*[f'--ignore=tests/review_studio/{p}' for p in ignore]]
    else:
        ignore=[]
        args=[str(ROOT/'tools/v11/test_wpd_scenarios.py')]
    try:
        code=pytest.main([*args,'-q','-p','no:cacheprovider','-p','pytest_asyncio.plugin',
                          '--basetemp',str(OUT/f'runtime/pytest-{mode}'),'-o','addopts=',
                          '-o','asyncio_default_fixture_loop_scope=function','--tb=short'],plugins=[result])
        data={'mode':mode,'exit_code':int(code),'collected':result.items,'collection_outcomes':result.collection,
              'reports':result.reports,'excluded_live_files':ignore,
              'counts':{outcome:sum(1 for node in result.items if any(r['nodeid']==node and r['outcome']==outcome for r in result.reports))
                        for outcome in ['failed','skipped']}}
        data['counts']['passed']=sum(1 for r in result.reports if r['phase']=='call' and r['outcome']=='passed')
    except BaseException:
        data={'mode':mode,'exception':traceback.format_exc(),'reports':result.reports,'collection_outcomes':result.collection}
    data['dependencies']={d.metadata['Name']:d.version for d in importlib.metadata.distributions(path=[str(ROOT/'tools/v11/wpd-deps')])}
    save(f'{mode}-tests.json',data)
    print(json.dumps({k:v for k,v in data.items() if k in {'exit_code','counts','exception'}},indent=2))

if __name__=='__main__': main()
