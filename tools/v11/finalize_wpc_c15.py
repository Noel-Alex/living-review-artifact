"""Close C1--C5 after direct inspection of every rendered table page."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from wpc_core import *

def main():
    verify_freeze()
    assert read(OUT/'verification.json')['data']['passed']
    assert read(OUT/'tests-verification-final.json')['data']['passed']
    tex=read(OUT/'tex-verification.json')['data'];assert tex['compiled'] and tex['pages']==39
    report=ROOT/'review/V11-WPC-RESULTS.md'
    original=report.read_bytes();(OUT/'results-before-c15-closeout.md').open('xb').write(original)
    text=original.decode('utf-8').replace('codemapper-reproduction-native-repaired.json','codemapper-reproduction-native-final.json')
    text=text.replace('deployed line accuracy is','deployed correct line location or absence is')
    text=text.replace('Real-history disagreement frame:','Real-history path/start-or-absence disagreement frame:')
    text+='\n## C1–C5 closeout\n\nThe independent audit passed 24,656 observations and 3,448 stratum/method count checks. All 39 generated table pages were compiled, rendered and directly inspected through ten contact sheets; no table clipping or overlap was observed. The original failed verification logs remain. A deterministic first-30 Java-variable native path-resolution probe found no difference between full and annotation-spelled commit references; this limited probe does not explain the published-number discrepancy. C1–C5 are complete as evaluations, with CodeMapper reproduction failed/qualified, canonical LHDiff unavailable, cold-start latency unmeasured and human adjudication pending. C6 is a separately registered extension and is not included in these results.\n'
    report.write_text(text,encoding='utf-8')
    write('c15-completion.json',dict(complete=True,utc=now(),observations=24656,tests_passed=True,artifact_audit_passed=True,visual_review=dict(pages=39,contact_sheets=10,passed=True),published_codemapper_reproduced=read(OUT/'codemapper-reproduction-native-final.json')['data']['passed'],limits=['canonical LHDiff unavailable','human adjudication not performed','cold-start timing unmeasured','external LR scope paired files'],report_sha256=sha(report)),[OUT/'verification.json',OUT/'tex-verification.json',report,OUT/'reference-spelling-probe.json'])
    print('C1--C5 closed; original protocol',sha(ROOT/'review/V11-PROTOCOL-C.md'))
if __name__=='__main__':main()
