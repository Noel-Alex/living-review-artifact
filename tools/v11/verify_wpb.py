"""Independent conservation, input identity, freeze and handoff verification."""
from collections import Counter, defaultdict
from datetime import datetime
import io
import csv
import json
import math
from pathlib import Path
import unittest
from wpa_core import ROOT, read, sha, outcome
from run_wpb import OUT, verify_freeze, write
from wpb_stress import corpus, digest


def main():
    freeze=verify_freeze()
    gate=read(OUT/'reproduction-gate.json')['data']
    assert gate['passed']
    manifest=read(OUT/'input-manifest.json')['data']
    for p,h in manifest['inputs'].items():assert sha(ROOT/p)==h,('input-drift',p)
    inherited_inputs={p:h for p,h in read(ROOT/'evidence/v11-wpa/gate-trials.json')['provenance']['input_sha256'].items()
                      if p.startswith('evidence/') or p.startswith('tools/bin/')}
    for p,h in inherited_inputs.items():assert sha(ROOT/p)==h,('inherited-input-drift',p)
    _,_,files=corpus()
    assert {p:digest(t) for p,t in files.items()}==manifest['controlled_corpus']
    time=lambda v:datetime.fromisoformat(v)
    assert time(freeze['timestamp_utc'])<time(read(OUT/'gate-start.json')['data']['started_utc'])
    assert time(gate['completed_utc'])<time(read(OUT/'evaluation-start.json')['data']['started_utc'])
    thresholds=read(OUT/'threshold-reproduction-gate.json')['data']
    assert thresholds['passed']
    assert time(thresholds['completed_utc'])<time(read(OUT/'evaluation-start.json')['data']['started_utc'])
    completion=read(OUT/'evaluation/completion.json')['data']
    assert completion['complete']
    assert time(read(OUT/'evaluation-start.json')['data']['started_utc'])<time(completion['completed_utc'])
    summary=read(OUT/'evaluation-summary.json')['data']
    raw_counts=Counter();direct=defaultdict(Counter);n=0
    classes=Counter();ids=[];range_eligible=0;errors=0
    new_methods=None
    for path in sorted((OUT/'evaluation').glob('trials-*.json')):
        doc=read(path)
        assert doc['provenance']['code_sha256']==freeze['code_sha256'],path
        assert doc['provenance']['protocol_sha256']==freeze['protocol_sha256'],path
        assert sha(path)==summary['raw_input_sha256'][str(path.relative_to(ROOT)).replace('\\','/')]
        for r in doc['data']:
            n+=1;raw_counts[r['suite']]+=1
            if r['suite']=='real':
                ids.append(r['row']);classes[r['cls']]+=1;range_eligible+=r['reference_range'] is not None
                errors+=r['methods']['tracker_adapter']['label']=='execution_error'
            new_methods=new_methods or set(r['methods'])
            assert set(r['methods'])==new_methods
            if r['suite']=='duplicates':
                c=r['duplicate_construction']
                delta=abs(c['copy_before_fate'][1]-c['original_before_fate'][1])
                if r['op'].startswith('near'):assert delta<=10
                if r['op'].startswith('far'):assert delta>=40
            for name,o in r['methods'].items():
                c=direct[r['suite'],name]
                changed=r['cls'] in ('edited','gone')
                wrong=r['truth_at'] is None and o['placement'] is not None or r['truth_at'] is not None and o['placement'] is not None and r['truth_at']!=o['placement']
                failure=o['label']=='execution_error'
                c['n']+=1;c['correct']+=not failure and r['truth_at']==o['placement']
                c['missed']+=changed and not o['recheck']
                c['false_recheck']+=not changed and o['recheck']
                c['wrong_silent']+=wrong and not o['recheck']
                c['lost']+=r['truth_at'] is not None and o['placement'] is None and not failure
                c['range_correct']+=r['reference_range'] is not None and o['range']==r['reference_range']
                if name.startswith('t0.'):
                    base='t0.55-deployed' if name.startswith('t0.55') else 't0.85-deployed'
                    c['extra']+=not changed and o['recheck'] and not r['methods'][base]['recheck']
                    c['spared']+=not changed and not o['recheck'] and r['methods'][base]['recheck']
                    if 'layout' in o['reasons']:assert o['label']=='changed' and o['recheck']
                    if 'pre-existing-copy' in o['reasons']:assert o['recheck']
    assert n==completion['n']==summary['n']==41014,(n,completion['n'])
    assert raw_counts==dict(indentation=2400,duplicates=3750,short=16200,original=3600,real=15064),raw_counts
    assert sorted(ids)==list(range(15064)) and len(set(ids))==15064
    assert range_eligible==14917 and errors==143,(range_eligible,errors)
    for (suite,name),c in direct.items():
        target=summary['strata'][suite]['methods'][name]
        for key,metric in [('correct','accuracy'),('missed','missed'),('false_recheck','false_recheck'),
                           ('wrong_silent','wrong_silent'),('lost','lost')]:assert c[key]==target[metric]['k'],(suite,name,key)
        if name.startswith('t0.'):
            assert c['range_correct']==target['range_correct']['k']
            assert c['extra']==target['extra_recheck_counts']['extra']
            assert c['spared']==target['extra_recheck_counts']['spared']
    assert len(completion['generator_audits'])==141
    assert all(a['counts']['accepted']==a['requested'] for a in completion['generator_audits'])
    for a in completion['generator_audits']:
        assert a['counts']['attempted']==sum(v for k,v in a['counts'].items() if k!='attempted')
    cases=read(OUT/'evaluation-archived-safety-cases.json')['data']
    assert sum(c['original_missed'] for c in cases)==37
    assert sum(c['original_wrong_silent'] for c in cases)==40
    with (ROOT/'evidence/v11-wpa/missed-recheck-cases.csv').open(encoding='utf-8',newline='') as stream:
        original_missed={int(r['row']) for r in csv.DictReader(stream)}
    assert {c['row'] for c in cases if c['original_missed']}==original_missed
    original_silent=set()
    for r in read(ROOT/'evidence/v11-wpa/gate-trials.json')['data']:
        if r['benchmark']!='real':continue
        o=r['methods']['cascade']
        if o['placement'] is not None and o['placement']!=r['truth_at'] and o['label'] not in ('changed','removed'):
            original_silent.add(r['row'])
    assert {c['row'] for c in cases if c['original_wrong_silent']}==original_silent
    audit=read(OUT/'real-indentation-audit.json')['data']
    assert audit['n']==15064
    deployed_cases=[c for c in audit['cases'] if c['view']=='deployed_returned_span']
    assert len(deployed_cases)==summary['real_indentation_matches']['n']
    stream=io.StringIO()
    tests=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_*.py')
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(tests)
    (OUT/'unit-tests-final.log').write_text(stream.getvalue(),encoding='utf-8')
    assert result.wasSuccessful(),stream.getvalue()
    # Numeric outputs may be null for unavailable/zero-denominator quantities, never NaN/Inf.
    def finite(v):
        if isinstance(v,float):assert math.isfinite(v)
        elif isinstance(v,dict):
            if all(k in v for k in ('k','n','rate')) and v['k'] is not None:
                assert 0<=v['k']<=v['n']
                assert v['rate'] is None if not v['n'] else 0<=v['rate']<=1
            for x in v.values():finite(x)
        elif isinstance(v,list):
            for x in v:finite(x)
    for p in OUT.glob('*summary.json'):finite(read(p))
    finite(read(OUT/'evaluation-paired.json'))
    write('verification.json',dict(passed=True,n=n,suite_counts=dict(raw_counts),real_range_eligible=range_eligible,
          tracker_real_execution_errors=errors,unit_tests=result.testsRun,freeze_unchanged=True,input_hashes_verified=len(manifest['inputs']),
          verifier_sha256=sha(Path(__file__)),archived_threshold_gate=True,
          inherited_input_sha256=inherited_inputs,
          test_sha256={p.name:sha(p) for p in Path(__file__).parent.glob('test_*.py')},
          raw_summary_conservation=True,chronology_verified=True,all_requested_cells_complete=True,
          scope='Research adapters, frozen chronology, source identities and arithmetic. No application acceptance, human adjudication, WP C/H completion or manuscript compilation claimed.'))
    print('PASS',n,dict(raw_counts),'range',range_eligible,'tracker errors',errors,'tests',result.testsRun,flush=True)


if __name__=='__main__':main()
