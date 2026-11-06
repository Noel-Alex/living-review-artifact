"""Run only after direct visual inspection of all C6 rendered contact sheets."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_c6 import *

def main():
    frozen=gate();audit=read(OUT/'c6/verification.json')['data'];assert audit['passed']
    tex=read(OUT/'c6/tex-verification.json')['data'];assert tex['compiled']
    for p,h in tex['page_sha256'].items():assert sha(OUT/'c6/tex'/p)==h
    report=read(OUT/'c6/report-data.json')['data'];assert sha(ROOT/'review/V11-WPC-C6-RESULTS.md')==report['report_sha256']
    assert tex['pages']==len(report['tex_files'])
    write('c6/visual-review.json',dict(passed=True,utc=now(),pages=tex['pages'],contact_sheets=len(tex['contacts']),contact_sha256={Path(p).name:sha(Path(p)) for p in tex['contacts']},finding='All rendered table pages directly inspected; no clipped table content, overlapping rows or unreadable scaling observed.'),[OUT/'c6/tex-verification.json'])
    write('c6/completion.json',dict(complete=True,utc=now(),n=audit['n'],suites=audit['suites'],original_protocol_sha256=frozen['original_sha256'],amendment_sha256=frozen['amendment_sha256'],independent_audit=True,visual_review=True,published_codemapper_gate_upgraded=False,c15_report_unchanged=True),[OUT/'c6/verification.json',OUT/'c6/visual-review.json',OUT/'c6/report-data.json',OUT/'c15-completion.json'])
    print('C6 complete',audit['n'],audit['suites'],flush=True)
if __name__=='__main__':main()
