"""Preserve the gate runner before adding automatic source snapshots for future runs."""
from wpa_core import *
path = Path(__file__).with_name('run_wpa_gate.py')
expected = read(OUT/'reproduction-gate.json')['provenance']['input_sha256']['tools/v11/run_wpa_gate.py']
assert sha(path)==expected
target = path.parent/'frozen'/f'{expected}-run_wpa_gate.py'
target.write_bytes(path.read_bytes())
write('gate-runner-snapshot.json',{'path':str(target.relative_to(ROOT)).replace('\\','/'),'sha256':expected,
    'purpose':'Runner that produced the completed gate; subsequent changes only add source snapshot capture for future reproductions.'})
