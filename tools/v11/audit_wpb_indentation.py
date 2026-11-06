"""Complete-source indentation audit using saved outputs, never rerunning variants."""
from collections import Counter
from wpa_core import read, sha
from run_wpb import ROOT, OUT, histories, write, verify_freeze
from wpb_variants import profile


def main():
    verify_freeze()
    assert read(OUT/'evaluation/completion.json')['data']['complete']
    records={}
    inputs={}
    for path in sorted((OUT/'evaluation').glob('trials-*.json')):
        inputs[str(path.relative_to(ROOT)).replace('\\','/')]=sha(path)
        for r in read(path)['data']:
            if r['suite']=='real':records[r['row']]=r
    contexts=read(ROOT/'evidence/source-context-validation/source-rows.json')
    cases=[]
    views=('deployed_returned_span','oracle_AST_span','oracle_original_height_window')
    audits={view:Counter() for view in views}
    for meta,t,old_files in histories(('own','oss')):
        r=records[meta['row']]
        a=t['anchor']
        base=r['methods']['t0.85-deployed']
        want=[x.strip() for x in a['quotation'].splitlines() if x.strip()]
        candidates={views[0]:base['range'],views[1]:r['reference_range'],
                    views[2]:None if r['truth_at'] is None else r['truth_at']+[r['truth_at'][1]+r['span']-1]}
        for view,location in candidates.items():
            audits[view]['observations']+=1
            if location is None:
                audits[view]['unlocated_or_ambiguous']+=1
                continue
            p,s,e=location
            text='\n'.join(t['version'][p][1].splitlines()[s-1:e])
            if [x.strip() for x in text.splitlines() if x.strip()] != want:
                audits[view]['normalized_different']+=1
                continue
            audits[view]['normalized_equal']+=1
            if profile(a['quotation'])==profile(text):continue
            audits[view]['normalized_equal_profile_different']+=1
            context=contexts[meta['row']]
            cases.append(dict(view=view,row=meta['row'],repo=r['repo'],sample=r['sample'],pair=r['pair'],
                old_commit=r['old_commit'],new_commit=r['new_commit'],anchor_at=r['anchor_at'],located_span=location,
                truth_at=r['truth_at'],reference_range=r['reference_range'],label=base['label'],recheck=base['recheck'],
                tier=base['tier'],oracle_class=r['cls'],oracle_how=r['how'],oracle_AST_equal=context.get('ast_equal'),
                old_function=context.get('old_function'),new_function=context.get('new_function'),
                old_profile=profile(a['quotation']),new_profile=profile(text),quotation=a['quotation'],located_quotation=text,
                methods=r['methods']))
    assert len(records)==15064
    for view in views:
        selected=[c for c in cases if c['view']==view]
        audits[view].update({'label:'+k:v for k,v in Counter(c['label'] for c in selected).items()})
        audits[view].update({'oracle_class:'+k:v for k,v in Counter(c['oracle_class'] for c in selected).items()})
        audits[view].update({'oracle_how:'+k:v for k,v in Counter(c['oracle_how'] for c in selected).items()})
    write('real-indentation-audit.json',dict(n=len(records),views={v:dict(c) for v,c in audits.items()},cases=cases,
          raw_input_sha256=inputs,interpretation='Indentation difference establishes a normalisation blind spot. Oracle AST equality is statement-level and does not certify equal nesting/context or executed behavior. Wrong-location twins are separate from oracle-located targets.'))
    print({v:dict(c) for v,c in audits.items()},flush=True)


if __name__=='__main__':main()
