"""Pre-freeze WP I plumbing smoke: executes each stage's batch function on a few inputs.

Prints only exceptions, gate-mismatch counts and output-row counts; outcomes are discarded unread.
Constructed inputs use development seed 7 (never an evaluation seed).
"""
import itertools
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_wpi  # noqa: E402
from wpa_core import ROOT, read  # noqa: E402


def chains_agi():
    """Amendment 7 plumbing: base-mode refactor equals the saved WP I chain rows; AGi mode passes its gate."""
    tmp = Path(tempfile.mkdtemp(prefix='wpi-smoke-'))
    out = run_wpi.OUT
    run_wpi.OUT = tmp
    try:
        import wpb2_chains as wc
        rows = wc.chain_rows()[:2]
        b2 = {r['row']: r for r in read(ROOT / 'evidence/v11-wpb2/chains/trials.json')['data']}
        wpi = {r['row']: r for r in read(out / 'chains/rows.json')['data']}
        for row in rows:
            s = b2[row['row']]
            base = run_wpi.chain_job((row['repo'], [(row, dict(prefixes=s['prefixes'], hops={k: s[k] for k in ('v0.85-off', 'v0.85-all')}))]))[0]
            print('base refactor equals saved WP I row', json.dumps(base, sort_keys=True) == json.dumps(wpi[row['row']], sort_keys=True))
            got = run_wpi.chain_job((row['repo'], [(row, dict(prefixes=s['prefixes'], hops={'v0.85-off': s['v0.85-off']}, wpi=wpi[row['row']]))], 'agi'))[0]
            print('agi gate mismatches', len(got['gate']), 'methods', sorted(k for k in got if k.startswith(('v0', 'cm'))))
    finally:
        if run_wpi.A is not None:
            run_wpi.A.close()
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if sys.argv[1:] == ['chains-agi']:
        return chains_agi()
    tmp = Path(tempfile.mkdtemp(prefix='wpi-smoke-'))
    run_wpi.PRIVATE = tmp
    run_wpi.OUT = tmp
    try:
        from wpb_stress import b1a, duplicates, short
        from wpb2_compound import compound
        run_wpi.init_fresh()
        items = []
        for gen in (b1a(7), duplicates(7), short(7), compound(7)):
            got = [(m, t, run_wpi.small_old(t, o)) for m, t, o in itertools.islice(gen, 40) if not m.get('generator_audit')]
            items += got[:2]
        rows = run_wpi.fresh_batch(items)
        print('fresh rows', len(rows), 'methods', len(rows[0]['methods']))
        print('fresh CodeMapper execution errors', sum(r['methods']['codemapper']['label'] == 'execution_error' for r in rows),
              [r['methods']['codemapper'].get('error', '')[:200] for r in rows if r['methods']['codemapper']['label'] == 'execution_error'][:2])
        saved = run_wpi.c6_saved()
        sample = []
        for ident, t, old in run_wpi.c6_stress_inputs():
            meta, methods, bases = saved[ident]
            sample.append((ident, meta, dict(methods, deployed_native=methods['t0.85-deployed']), bases, t, old))
            if len(sample) == 3:
                break
        got = run_wpi.transfer_batch(sample)
        print('transfer rows', len(got), 'gate mismatches', sum(len(r['gate_mismatch']) for r in got))
        private = ROOT / 'evidence/v11-wph/private'
        paths = {r['anonymous_id']: str(private / 'tmp' / str(r['repository_id'])) for r in read(private / 'selected.json')}
        recs = read(ROOT / 'evidence/v11-wph2/trials/S1.json')['data']
        first = [r for r in recs if (r['old_commit'], r['new_commit']) == (recs[0]['old_commit'], recs[0]['new_commit'])][:2]
        got = run_wpi.student_batch(('S1', paths['S1'], first[0]['old_commit'], first[0]['new_commit'], first))
        print('student rows', len(got))
        import wpb2_chains as wc
        rows = wc.chain_rows()
        chain_saved = {r['row']: r for r in read(ROOT / 'evidence/v11-wpb2/chains/trials.json')['data']}
        row = rows[0]
        s = chain_saved[row['row']]
        got = run_wpi.chain_job((row['repo'], [(row, dict(prefixes=s['prefixes'], hops={k: s[k] for k in ('v0.85-off', 'v0.85-all')}))]))
        print('chain rows', len(got), 'gate mismatches', len(got[0]['gate']), 'methods', sorted(k for k in got[0] if k.startswith(('v0', 'cm'))))
        errs = [h.get('error') for h in got[0]['cm-seq'] if h['label'] == 'execution_error']
        errs += [d.get('label') for p in got[0]['prefixes'].values() for d in [p['direct']['cm-direct']] if d['label'] == 'execution_error']
        print('chain CodeMapper execution errors', len(errs), errs[:2])
        print('smoke passed')
    finally:
        if run_wpi.A is not None:
            run_wpi.A.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
